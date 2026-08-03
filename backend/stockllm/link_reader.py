from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader

from .db import data_dir
from .diagnostics import cache_write_lock


ALLOWED_HOSTS = {
    "finance.eastmoney.com",
    "www.cninfo.com.cn",
    "static.cninfo.com.cn",
}
MAX_HTML_BYTES = 4 * 1024 * 1024
MAX_PDF_BYTES = 20 * 1024 * 1024
MAX_TEXT_CHARS = 16_000
MAX_PDF_PAGES = 12
URL_PATTERN = re.compile(r"https?://[^\s<>\]\[\"']+")


class LinkReadUnavailable(RuntimeError):
    pass


def _validate_url(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or host not in ALLOWED_HOSTS:
        raise LinkReadUnavailable("该链接域名不在允许列表中")
    if parsed.username or parsed.password or parsed.port not in {None, 80, 443}:
        raise LinkReadUnavailable("链接包含不允许的认证信息或端口")
    return url


def extract_allowed_urls(text: str) -> list[str]:
    urls: list[str] = []
    for match in URL_PATTERN.findall(text):
        url = match.rstrip(".,;:!?，。；：！？、)")
        try:
            _validate_url(url)
        except LinkReadUnavailable:
            continue
        if url not in urls:
            urls.append(url)
    return urls[:5]


def _fetch(client: httpx.Client, url: str, max_bytes: int) -> tuple[bytes, str, str]:
    current = _validate_url(url)
    for _ in range(4):
        with client.stream("GET", current) as response:
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise LinkReadUnavailable("重定向缺少目标地址")
                current = _validate_url(urljoin(current, location))
                continue
            response.raise_for_status()
            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > max_bytes:
                    raise LinkReadUnavailable("链接内容超过读取上限")
                chunks.append(chunk)
            return b"".join(chunks), response.headers.get("content-type", ""), current
    raise LinkReadUnavailable("链接重定向次数过多")


def _cninfo_pdf_url(client: httpx.Client, detail_url: str) -> str:
    query = parse_qs(urlparse(detail_url).query)
    announcement_id = (query.get("announcementId") or [""])[0]
    announcement_time = (query.get("announcementTime") or [""])[0]
    if not announcement_id or not announcement_time:
        raise LinkReadUnavailable("巨潮公告链接缺少公告标识")
    response = client.post(
        "http://www.cninfo.com.cn/new/announcement/bulletin_detail",
        params={"announceId": announcement_id, "flag": "false", "announceTime": announcement_time},
    )
    response.raise_for_status()
    if len(response.content) > 1024 * 1024:
        raise LinkReadUnavailable("巨潮公告元数据超过读取上限")
    file_url = str(response.json().get("fileUrl") or "")
    return _validate_url(file_url)


def _extract_html(data: bytes, source_url: str) -> tuple[str, str, bool]:
    soup = BeautifulSoup(data, "lxml")
    title = soup.title.get_text(" ", strip=True) if soup.title else source_url
    container = soup.select_one("#ContentBody, article, .txtinfos, main")
    if container is None:
        raise LinkReadUnavailable("网页没有可识别的正文区域")
    for node in container.select("script, style, noscript, nav, footer"):
        node.decompose()
    lines = [" ".join(line.split()) for line in container.get_text("\n").splitlines()]
    text = "\n".join(line for line in lines if line)
    if len(text) < 80:
        raise LinkReadUnavailable("网页正文过短，无法可靠使用")
    truncated = len(text) > MAX_TEXT_CHARS
    return title, text[:MAX_TEXT_CHARS], truncated


def _extract_pdf(data: bytes, source_url: str) -> tuple[str, str, bool]:
    reader = PdfReader(BytesIO(data))
    texts: list[str] = []
    page_count = min(len(reader.pages), MAX_PDF_PAGES)
    for page in reader.pages[:page_count]:
        texts.append(page.extract_text() or "")
        if sum(len(text) for text in texts) >= MAX_TEXT_CHARS:
            break
    text = "\n".join(part.strip() for part in texts if part.strip())
    if len(text) < 40:
        raise LinkReadUnavailable("PDF 没有可提取的文字正文")
    truncated = len(reader.pages) > page_count or len(text) > MAX_TEXT_CHARS
    return Path(urlparse(source_url).path).name or "公司公告", text[:MAX_TEXT_CHARS], truncated


def _cache_path(url: str) -> Path:
    directory = data_dir() / "cache" / "external-links"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{hashlib.sha256(url.encode('utf-8')).hexdigest()}.json"


def read_external_url(url: str) -> dict:
    url = _validate_url(url)
    cache = _cache_path(url)
    if cache.exists():
        modified = datetime.fromtimestamp(cache.stat().st_mtime, timezone.utc)
        if datetime.now(timezone.utc) - modified <= timedelta(hours=24):
            return {**json.loads(cache.read_text(encoding="utf-8")), "from_cache": True}

    try:
        timeout = httpx.Timeout(12.0, connect=6.0)
        with httpx.Client(
            timeout=timeout,
            follow_redirects=False,
            headers={"User-Agent": "StockLLM/0.1 research-link-reader"},
            trust_env=True,
        ) as client:
            resolved_url = url
            if urlparse(url).hostname == "www.cninfo.com.cn" and "/disclosure/detail" in urlparse(url).path:
                resolved_url = _cninfo_pdf_url(client, url)
            content_limit = MAX_PDF_BYTES if resolved_url.lower().endswith(".pdf") else MAX_HTML_BYTES
            data, content_type, final_url = _fetch(client, resolved_url, content_limit)
            if "pdf" in content_type.lower() or final_url.lower().endswith(".pdf"):
                title, text, truncated = _extract_pdf(data, final_url)
                document_type = "pdf"
            else:
                title, text, truncated = _extract_html(data, final_url)
                document_type = "html"
        payload = {
            "source_url": url,
            "resolved_url": final_url,
            "title": title,
            "text": text,
            "document_type": document_type,
            "truncated": truncated,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "from_cache": False,
        }
        with cache_write_lock():
            temporary = cache.with_suffix(".tmp")
            temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            temporary.replace(cache)
        return payload
    except Exception as exc:
        if cache.exists():
            modified = datetime.fromtimestamp(cache.stat().st_mtime, timezone.utc)
            if datetime.now(timezone.utc) - modified <= timedelta(days=7):
                return {**json.loads(cache.read_text(encoding="utf-8")), "from_cache": True}
        if isinstance(exc, LinkReadUnavailable):
            raise
        raise LinkReadUnavailable(str(exc)) from exc
