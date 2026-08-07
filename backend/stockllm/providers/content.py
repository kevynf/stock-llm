from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol

from ..storage import atomic_cache_write, read_json_cache


class ContentProviderContext(Protocol):
    ak: Any
    pd: Any
    cache_dir: Path

    def _akshare_frame(self, fetch: Callable[[], object]) -> Any: ...

    @staticmethod
    def _fresh(path: Path, max_age: timedelta) -> bool: ...

    @staticmethod
    def _latest_cache_age() -> timedelta: ...


def _cached_content(payload: dict | None) -> tuple[list[dict], datetime, list[str]] | None:
    if payload is None:
        return None
    raw_items = payload.get("items")
    fetched_at = payload.get("fetched_at")
    if not isinstance(raw_items, list) or not isinstance(fetched_at, str):
        return None
    if not all(isinstance(item, dict) for item in raw_items):
        return None
    try:
        fetched = datetime.fromisoformat(fetched_at)
    except ValueError:
        return None
    raw_errors = payload.get("errors", [])
    errors = [str(error) for error in raw_errors] if isinstance(raw_errors, list) else []
    items = [{
        **item,
        "content_level": item.get("content_level") or ("summary" if item.get("kind") == "新闻" else "title"),
        "freshness": "cached",
    } for item in raw_items]
    return items, fetched, errors


def fetch_content(
    provider: ContentProviderContext,
    code: str,
    as_of: date,
) -> tuple[list[dict], datetime, bool, list[str]]:
    cache = provider.cache_dir / f"content-{code}-{as_of.isoformat()}.json"
    cached = _cached_content(read_json_cache(cache))
    if cached is not None:
        _, fetched_at, cached_errors = cached
        immutable_history = as_of < date.today() and not cached_errors
        max_age = timedelta(days=36500) if immutable_history else provider._latest_cache_age()
        if provider._fresh(cache, max_age):
            return cached[0], fetched_at, True, cached_errors

    fetched_at = datetime.now(timezone.utc)
    items: list[dict] = []
    errors: list[str] = []

    try:
        frame = provider._akshare_frame(lambda: provider.ak.stock_news_em(symbol=code))
        for record in frame.to_dict("records"):
            published = provider.pd.to_datetime(record.get("发布时间"), errors="coerce")
            if provider.pd.isna(published) or published.date() > as_of:
                continue
            title = str(record.get("新闻标题") or "").strip()
            url = str(record.get("新闻链接") or "").strip()
            if not title or not url.startswith(("http://", "https://")):
                continue
            items.append({
                "kind": "新闻",
                "content_level": "summary",
                "title": title,
                "summary": " ".join(str(record.get("新闻内容") or "").split()),
                "published_at": published.isoformat(),
                "publisher": str(record.get("文章来源") or "未注明").strip(),
                "url": url,
                "source": "AKShare",
                "channel": "东方财富个股新闻",
                "fetched_at": fetched_at.isoformat(),
                "freshness": "latest",
            })
    except Exception as exc:
        errors.append(f"东方财富个股新闻：{exc}")

    try:
        start = as_of - timedelta(days=180)
        frame = provider._akshare_frame(
            lambda: provider.ak.stock_zh_a_disclosure_report_cninfo(
                symbol=code,
                start_date=start.strftime("%Y%m%d"),
                end_date=as_of.strftime("%Y%m%d"),
            )
        )
        for record in frame.to_dict("records"):
            published = provider.pd.to_datetime(record.get("公告时间"), errors="coerce")
            if provider.pd.isna(published) or published.date() > as_of:
                continue
            title = str(record.get("公告标题") or "").strip()
            url = str(record.get("公告链接") or "").strip()
            if not title or not url.startswith(("http://", "https://")):
                continue
            items.append({
                "kind": "公告",
                "content_level": "title",
                "title": title,
                "summary": "",
                "published_at": published.isoformat(),
                "publisher": "巨潮资讯",
                "url": url,
                "source": "AKShare",
                "channel": "巨潮资讯公告",
                "fetched_at": fetched_at.isoformat(),
                "freshness": "latest",
            })
    except Exception as exc:
        errors.append(f"巨潮资讯公告：{exc}")

    unique: dict[str, dict] = {}
    for item in items:
        unique[item["url"]] = item
    items = sorted(unique.values(), key=lambda item: item["published_at"], reverse=True)[:40]
    if items:
        payload = {"fetched_at": fetched_at.isoformat(), "items": items, "errors": errors}
        with atomic_cache_write(cache) as temporary:
            temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return items, fetched_at, False, errors

    cached = _cached_content(read_json_cache(cache))
    if cached is not None and provider._fresh(cache, timedelta(hours=24)):
        return cached[0], cached[1], True, errors
    return [], fetched_at, False, errors
