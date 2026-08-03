from __future__ import annotations

import json
import math
import os
import statistics
import threading
from abc import ABC, abstractmethod
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator
from zoneinfo import ZoneInfo

from .db import data_dir
from .diagnostics import cache_write_lock
from .models import SourceMeta


class ProviderUnavailable(RuntimeError):
    pass


class ResearchProvider(ABC):
    @abstractmethod
    def snapshot(self, as_of: date) -> tuple[list[dict], SourceMeta]:
        raise NotImplementedError

    @abstractmethod
    def search(self, query: str) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    def research(self, code: str, as_of: date) -> dict | None:
        raise NotImplementedError

    @abstractmethod
    def status(self) -> dict:
        raise NotImplementedError


BASE_STOCKS = [
    ("600519", "贵州茅台", "消费", 1672.4, 1.2, 31.2, 0.24, 15.8, 12.4, 7.2, 0.12, 0.08),
    ("000858", "五粮液", "消费", 142.8, 0.7, 22.5, 0.21, 12.6, 9.8, 10.1, 0.15, 0.11),
    ("600036", "招商银行", "金融", 41.3, -0.3, 6.8, 0.16, 7.3, 5.1, 18.2, 0.11, 0.07),
    ("601318", "中国平安", "金融", 48.6, 0.5, 8.7, 0.14, 6.1, 4.8, 21.0, 0.13, 0.09),
    ("300750", "宁德时代", "新能源", 252.1, 2.1, 21.4, 0.19, 14.2, 10.2, 29.0, 0.22, 0.16),
    ("002594", "比亚迪", "汽车", 308.4, 1.4, 24.8, 0.17, 18.6, 15.2, 43.0, 0.25, 0.18),
    ("600276", "恒瑞医药", "医药", 52.7, -0.4, 42.2, 0.13, 10.4, 8.2, 9.0, 0.18, 0.13),
    ("000333", "美的集团", "制造", 78.2, 0.8, 15.9, 0.22, 9.6, 8.8, 34.0, 0.10, 0.07),
    ("601899", "紫金矿业", "资源", 20.4, 1.9, 13.6, 0.18, 24.0, 18.1, 47.0, 0.24, 0.17),
    ("600900", "长江电力", "公用事业", 29.8, 0.2, 18.3, 0.15, 5.4, 4.1, 28.0, 0.07, 0.04),
    ("688981", "中芯国际", "半导体", 88.5, 3.4, 78.0, 0.08, 28.0, 19.0, 31.0, 0.31, 0.22),
    ("002415", "海康威视", "科技", 34.6, -1.0, 19.2, 0.16, 3.2, 2.4, 24.0, 0.19, 0.14),
]


def _history(code: str, price: float, as_of: date, volatility: float) -> list[dict]:
    seed = sum(ord(char) for char in code)
    final_trend = 90 * ((seed % 9) - 2) / 1500
    final_wave = math.sin((90 + seed) / 7) * volatility
    final_factor = 1 + final_trend + final_wave
    rows: list[dict] = []
    previous_close = price / final_factor
    for offset in range(89, -1, -1):
        trend = (90 - offset) * ((seed % 9) - 2) / 1500
        wave = math.sin((90 - offset + seed) / 7) * volatility
        close = round(price * (1 + trend + wave) / final_factor, 2)
        open_price = round(previous_close * (1 + math.sin(seed + offset) * volatility * 0.08), 2)
        spread = max(close * 0.002, close * volatility * (0.08 + abs(math.cos(seed + offset)) * 0.12))
        high = round(max(open_price, close) + spread, 2)
        low = round(max(0.01, min(open_price, close) - spread), 2)
        volume = round(8_000_000 * (1 + abs(math.sin(seed + offset)) * 1.8))
        rows.append({
            "date": date.fromordinal(as_of.toordinal() - offset).isoformat(),
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        })
        previous_close = close
    return rows


class DemoProvider(ResearchProvider):
    """Explicit offline data for development; never presented as live market data."""

    def _rows(self, as_of: date) -> list[dict]:
        rows = []
        for index, item in enumerate(BASE_STOCKS):
            code, name, sector, price, change, pe, roe, profit, revenue, debt, vol, drawdown = item
            history = _history(code, price, as_of, vol / 8)
            closes = [point["close"] for point in history]
            ma20 = sum(closes[-20:]) / 20
            ma60 = sum(closes[-60:]) / 60
            rows.append(
                {
                    "code": code,
                    "name": name,
                    "sector": sector,
                    "price": price,
                    "change_pct": change,
                    "listed_days": 600 + index * 70,
                    "suspended": False,
                    "risk_label": "normal",
                    "avg_amount_20d": 80_000_000 + index * 13_000_000,
                    "ma20": round(ma20, 2),
                    "ma60": round(ma60, 2),
                    "return_20d": round((closes[-1] / closes[-20] - 1) * 100, 2),
                    "return_60d": round((closes[-1] / closes[-60] - 1) * 100, 2),
                    "volume_ratio": round(0.82 + (index % 5) * 0.13, 2),
                    "rsi": 44 + (index * 4) % 41,
                    "pe": pe,
                    "roe": roe * 100,
                    "profit_growth": profit,
                    "revenue_growth": revenue,
                    "debt_ratio": debt,
                    "cashflow_quality": round(0.72 + (index % 4) * 0.08, 2),
                    "volatility_60d": vol,
                    "max_drawdown_60d": drawdown,
                    "history": history,
                    "news": [
                        {
                            "title": f"{name}发布近期经营信息",
                            "published_at": as_of.isoformat(),
                            "summary": "示例快照新闻，仅用于验证研究工作流。",
                        }
                    ],
                }
            )
        return rows

    def snapshot(self, as_of: date) -> tuple[list[dict], SourceMeta]:
        return self._rows(as_of), SourceMeta(
            source="StockLLM 示例快照",
            as_of=as_of,
            fetched_at=datetime.now(timezone.utc),
            status="demo",
        )

    def search(self, query: str) -> list[dict]:
        lowered = query.strip().lower()
        rows = self._rows(date.today())
        return [
            {"code": row["code"], "name": row["name"], "sector": row["sector"]}
            for row in rows
            if lowered in row["code"].lower() or lowered in row["name"].lower()
        ][:20]

    def research(self, code: str, as_of: date) -> dict | None:
        row = next((item for item in self._rows(as_of) if item["code"] == code), None)
        if not row:
            return None
        row["source"] = {
            "source": "StockLLM 示例快照",
            "as_of": as_of.isoformat(),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "status": "demo",
        }
        return row

    def status(self) -> dict:
        return {
            "id": "demo",
            "name": "示例快照",
            "status": "demo",
            "message": "固定离线数据，仅用于体验和测试，不代表实时市场。",
        }


class AkShareProvider(ResearchProvider):
    """Cached live universe from AkShare, enriched with BaoStock research data."""

    _baostock_lock = threading.Lock()

    def __init__(self) -> None:
        try:
            import akshare as ak  # type: ignore
            import baostock as bs  # type: ignore
            import pandas as pd  # type: ignore
        except ImportError as exc:
            raise ProviderUnavailable("未安装真实市场数据依赖，请重新运行 bootstrap 脚本") from exc
        self.ak = ak
        self.bs = bs
        self.pd = pd
        self.cache_dir = data_dir() / "cache" / "market"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _number(value: object, default: float | None = None) -> float | None:
        try:
            result = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return default
        return result if math.isfinite(result) else default

    @staticmethod
    def _plain_code(value: object) -> str:
        return str(value).replace("sh", "").replace("sz", "").replace(".", "")[-6:]

    @staticmethod
    def _bao_code(code: str) -> str:
        return f"sh.{code}" if code.startswith(("5", "6", "9")) else f"sz.{code}"

    @staticmethod
    def _fresh(path: Path, max_age: timedelta) -> bool:
        if not path.exists():
            return False
        modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        return datetime.now(timezone.utc) - modified <= max_age

    @staticmethod
    def _cache_time(path: Path) -> datetime:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)

    @staticmethod
    def _latest_cache_age() -> timedelta:
        minutes = min(max(int(os.getenv("STOCKLLM_LIVE_CACHE_MINUTES", "15")), 1), 60)
        return timedelta(minutes=minutes)

    @contextmanager
    def _baostock(self) -> Iterator[object]:
        with self._baostock_lock:
            login = self.bs.login()
            if login.error_code != "0":
                raise ProviderUnavailable(f"BaoStock 连接失败：{login.error_msg}")
            try:
                yield self.bs
            finally:
                self.bs.logout()

    @staticmethod
    def _query_rows(result: object) -> list[dict]:
        if result.error_code != "0":
            raise ProviderUnavailable(f"BaoStock 查询失败：{result.error_msg}")
        rows: list[dict] = []
        while result.next():
            rows.append(dict(zip(result.fields, result.get_row_data(), strict=True)))
        return rows

    def _spot_frame(self, force_refresh: bool = False) -> tuple[object, bool, datetime]:
        cache = self.cache_dir / "akshare-sina-spot.parquet"
        if not force_refresh and self._fresh(cache, self._latest_cache_age()):
            return self.pd.read_parquet(cache), True, self._cache_time(cache)
        try:
            frame = self.ak.stock_zh_a_spot()
            required = {"代码", "名称", "最新价", "涨跌幅", "昨收", "今开", "成交量", "成交额", "时间戳"}
            if frame.empty or not required.issubset(frame.columns):
                raise ProviderUnavailable("AkShare 实时列表字段发生变化")
            fetched_at = datetime.now(timezone.utc)
            with cache_write_lock():
                frame.to_parquet(cache, index=False)
            return frame, False, fetched_at
        except Exception as exc:
            if self._fresh(cache, timedelta(hours=24)):
                return self.pd.read_parquet(cache), True, self._cache_time(cache)
            raise ProviderUnavailable(f"AkShare 实时列表不可用：{exc}") from exc

    def _history(self, bs: object, code: str, as_of: date) -> tuple[list[dict], datetime, bool]:
        cache = self.cache_dir / f"history-{code}-{as_of.isoformat()}.parquet"
        max_age = self._latest_cache_age() if as_of == date.today() else timedelta(days=36500)
        if self._fresh(cache, max_age):
            return self.pd.read_parquet(cache).to_dict("records"), self._cache_time(cache), True
        start = as_of - timedelta(days=550)
        fields = (
            "date,code,open,high,low,close,preclose,volume,amount,turn,"
            "tradestatus,pctChg,peTTM,pbMRQ,psTTM,pcfNcfTTM,isST"
        )
        result = bs.query_history_k_data_plus(
            self._bao_code(code), fields, start_date=start.isoformat(),
            end_date=as_of.isoformat(), frequency="d", adjustflag="2",
        )
        rows = self._query_rows(result)
        rows = [row for row in rows if self._number(row.get("close")) is not None]
        if len(rows) < 60:
            raise ProviderUnavailable("有效历史行情不足 60 个交易日")
        fetched_at = datetime.now(timezone.utc)
        with cache_write_lock():
            self.pd.DataFrame(rows).to_parquet(cache, index=False)
        return rows, fetched_at, False

    def _financial(self, bs: object, code: str, as_of: date) -> dict:
        bao_code = self._bao_code(code)
        start_quarter = (as_of.month - 1) // 3 + 1
        for offset in range(10):
            absolute = as_of.year * 4 + start_quarter - 1 - offset
            year, quarter_index = divmod(absolute, 4)
            quarter = quarter_index + 1
            profit_rows = self._query_rows(bs.query_profit_data(code=bao_code, year=year, quarter=quarter))
            profit = next(
                (row for row in reversed(profit_rows) if row.get("pubDate") and date.fromisoformat(row["pubDate"]) <= as_of and row.get("MBRevenue")),
                None,
            )
            if not profit:
                continue
            growth_rows = self._query_rows(bs.query_growth_data(code=bao_code, year=year, quarter=quarter))
            balance_rows = self._query_rows(bs.query_balance_data(code=bao_code, year=year, quarter=quarter))
            cash_rows = self._query_rows(bs.query_cash_flow_data(code=bao_code, year=year, quarter=quarter))
            previous_rows = self._query_rows(bs.query_profit_data(code=bao_code, year=year - 1, quarter=quarter))
            growth = growth_rows[-1] if growth_rows else {}
            balance = balance_rows[-1] if balance_rows else {}
            cash = cash_rows[-1] if cash_rows else {}
            previous_revenue = self._number(previous_rows[-1].get("MBRevenue")) if previous_rows else None
            revenue = self._number(profit.get("MBRevenue"))
            revenue_growth = ((revenue / previous_revenue - 1) * 100) if revenue and previous_revenue else None
            values = {
                "roe": (self._number(profit.get("roeAvg")) or 0) * 100,
                "profit_growth": (self._number(growth.get("YOYNI")) or 0) * 100,
                "revenue_growth": revenue_growth,
                "debt_ratio": (self._number(balance.get("liabilityToAsset")) or 0) * 100,
                "cashflow_quality": self._number(cash.get("CFOToNP")),
                "financial_as_of": profit.get("statDate"),
                "financial_published_at": profit.get("pubDate"),
            }
            if all(values[key] is not None for key in ("revenue_growth", "cashflow_quality")):
                return values
        raise ProviderUnavailable("截至研究日没有找到字段完整且已公开的财务报告")

    def _industry(self, bs: object, code: str) -> str:
        try:
            rows = self._query_rows(bs.query_stock_industry(code=self._bao_code(code)))
            return str(rows[-1].get("industry") or "行业未分类") if rows else "行业未分类"
        except Exception:
            return "行业未分类"

    def _content(self, code: str, as_of: date) -> tuple[list[dict], datetime, bool, list[str]]:
        cache = self.cache_dir / f"content-{code}-{as_of.isoformat()}.json"
        if cache.exists():
            payload = json.loads(cache.read_text(encoding="utf-8"))
            immutable_history = as_of < date.today() and not payload.get("errors")
            max_age = timedelta(days=36500) if immutable_history else self._latest_cache_age()
            if self._fresh(cache, max_age):
                cached_items = [{
                    **item,
                    "content_level": item.get("content_level") or ("summary" if item.get("kind") == "新闻" else "title"),
                    "freshness": "cached",
                } for item in payload["items"]]
                return cached_items, datetime.fromisoformat(payload["fetched_at"]), True, payload.get("errors", [])

        fetched_at = datetime.now(timezone.utc)
        items: list[dict] = []
        errors: list[str] = []

        try:
            with self.pd.option_context("mode.string_storage", "python"):
                frame = self.ak.stock_news_em(symbol=code)
            for record in frame.to_dict("records"):
                published = self.pd.to_datetime(record.get("发布时间"), errors="coerce")
                if self.pd.isna(published) or published.date() > as_of:
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
                    "source": "AkShare",
                    "channel": "东方财富个股新闻",
                    "fetched_at": fetched_at.isoformat(),
                    "freshness": "latest",
                })
        except Exception as exc:
            errors.append(f"东方财富个股新闻：{exc}")

        try:
            start = as_of - timedelta(days=180)
            frame = self.ak.stock_zh_a_disclosure_report_cninfo(
                symbol=code,
                start_date=start.strftime("%Y%m%d"),
                end_date=as_of.strftime("%Y%m%d"),
            )
            for record in frame.to_dict("records"):
                published = self.pd.to_datetime(record.get("公告时间"), errors="coerce")
                if self.pd.isna(published) or published.date() > as_of:
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
                    "source": "AkShare",
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
            with cache_write_lock():
                temporary = cache.with_suffix(".tmp")
                temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                temporary.replace(cache)
            return items, fetched_at, False, errors

        if cache.exists() and self._fresh(cache, timedelta(hours=24)):
            payload = json.loads(cache.read_text(encoding="utf-8"))
            cached_items = [{
                **item,
                "content_level": item.get("content_level") or ("summary" if item.get("kind") == "新闻" else "title"),
                "freshness": "cached",
            } for item in payload["items"]]
            return cached_items, datetime.fromisoformat(payload["fetched_at"]), True, errors
        return [], fetched_at, False, errors

    def _build_row(self, bs: object, code: str, name: str, as_of: date) -> dict:
        history, market_fetched_at, market_from_cache = self._history(bs, code, as_of)
        financial = self._financial(bs, code, as_of)
        closes = [self._number(row.get("close"), 0.0) or 0.0 for row in history]
        amounts = [self._number(row.get("amount"), 0.0) or 0.0 for row in history]
        volumes = [self._number(row.get("volume"), 0.0) or 0.0 for row in history]
        latest = history[-1]
        daily_returns = [closes[index] / closes[index - 1] - 1 for index in range(max(1, len(closes) - 59), len(closes)) if closes[index - 1] > 0]
        peak = closes[-60]
        max_drawdown = 0.0
        for close in closes[-60:]:
            peak = max(peak, close)
            max_drawdown = max(max_drawdown, (peak - close) / peak if peak else 0.0)
        changes = [closes[index] - closes[index - 1] for index in range(len(closes) - 14, len(closes))]
        gain = sum(max(change, 0) for change in changes) / 14
        loss = sum(max(-change, 0) for change in changes) / 14
        rsi = 100.0 if loss == 0 else 100 - 100 / (1 + gain / loss)
        row = {
            "code": code,
            "name": name,
            "sector": self._industry(bs, code),
            "price": closes[-1],
            "change_pct": self._number(latest.get("pctChg"), 0.0) or 0.0,
            "listed_days": len(history),
            "suspended": str(latest.get("tradestatus")) != "1",
            "risk_label": "st" if str(latest.get("isST")) == "1" or "ST" in name.upper() else "normal",
            "avg_amount_20d": sum(amounts[-20:]) / 20,
            "ma20": sum(closes[-20:]) / 20,
            "ma60": sum(closes[-60:]) / 60,
            "return_20d": (closes[-1] / closes[-20] - 1) * 100,
            "return_60d": (closes[-1] / closes[-60] - 1) * 100,
            "volume_ratio": volumes[-1] / (sum(volumes[-20:]) / 20) if sum(volumes[-20:]) else 0.0,
            "rsi": rsi,
            "pe": self._number(latest.get("peTTM"), 0.0) or 0.0,
            "volatility_60d": statistics.pstdev(daily_returns) * math.sqrt(252) if daily_returns else 0.0,
            "max_drawdown_60d": max_drawdown,
            "history": [{
                "date": str(item["date"]),
                "open": self._number(item.get("open"), 0.0) or 0.0,
                "high": self._number(item.get("high"), 0.0) or 0.0,
                "low": self._number(item.get("low"), 0.0) or 0.0,
                "close": self._number(item.get("close"), 0.0) or 0.0,
                "volume": self._number(item.get("volume"), 0.0) or 0.0,
            } for item in history[-120:]],
            "news": [],
            "market_as_of": str(latest["date"]),
            "market_fetched_at": market_fetched_at.isoformat(),
            "market_from_cache": market_from_cache,
            **financial,
        }
        return row

    def _resolve_price(
        self,
        row: dict,
        spot: dict,
        spot_fetched_at: datetime,
        spot_from_cache: bool,
    ) -> tuple[date, datetime]:
        spot_price = self._number(spot.get("最新价"))
        spot_change = self._number(spot.get("涨跌幅"))
        if spot_price is None or spot_change is None:
            raise ProviderUnavailable("AkShare 最新价格或涨跌幅字段缺失")

        market_date = date.fromisoformat(str(row["market_as_of"]))
        prior_close = self._number(spot.get("昨收"))
        open_price = self._number(spot.get("今开"))
        volume = self._number(spot.get("成交量"))
        amount = self._number(spot.get("成交额"))
        quote_time = str(spot.get("时间戳") or "").strip()
        observed = spot_fetched_at.astimezone(ZoneInfo("Asia/Shanghai"))
        reliable = all(
            value is not None and value > 0
            for value in (prior_close, open_price, volume, amount)
        )
        try:
            quote_clock = datetime.strptime(quote_time, "%H:%M:%S").time()
            reliable = reliable and quote_clock >= datetime.strptime("09:30:00", "%H:%M:%S").time()
        except ValueError:
            reliable = False
        if observed.weekday() >= 5 or observed.time() < datetime.strptime("09:30:00", "%H:%M:%S").time():
            reliable = False
        if prior_close:
            calculated_change = (spot_price / prior_close - 1) * 100
            reliable = reliable and math.isclose(calculated_change, spot_change, abs_tol=0.05)
        if not reliable:
            market_fetched_at = datetime.fromisoformat(str(row["market_fetched_at"]))
            market_freshness = "cached" if row.get("market_from_cache") else "latest"
            row["price_as_of"] = market_date.isoformat()
            row["price_fetched_at"] = market_fetched_at.isoformat()
            row["price_note"] = "实时行情尚未形成有效成交，显示最近有效日线。"
            row["evidence_sources"] = {
                key: "BaoStock" for key in ("price", "ma", "returns", "liquidity", "fundamentals", "risk")
            }
            row["evidence_resolution"] = {
                key: {"freshness": market_freshness, "resolution": "primary", "note": row["price_note"] if key == "price" else None}
                for key in ("price", "ma", "returns", "liquidity", "risk")
            }
            return market_date, market_fetched_at

        observed_date = spot_fetched_at.astimezone(ZoneInfo("Asia/Shanghai")).date()
        same_quote = math.isclose(spot_price, float(row["price"]), rel_tol=1e-6, abs_tol=0.001) and math.isclose(
            spot_change, float(row["change_pct"]), rel_tol=1e-6, abs_tol=0.001,
        )
        same_date_conflict = observed_date == market_date and not same_quote
        row["price"] = spot_price
        row["change_pct"] = spot_change
        source = "AkShare"
        selected_date = observed_date
        selected_fetched_at = spot_fetched_at
        if same_date_conflict:
            resolution = "conflict"
            note = "AkShare 行情与 BaoStock 当日日线收盘价不同；两条来源记录保持独立。"
        else:
            resolution = "primary"
            note = None
        freshness = "cached" if spot_from_cache else "latest"

        market_resolution = "cached" if row.get("market_from_cache") else "latest"
        row["price_as_of"] = selected_date.isoformat()
        row["price_fetched_at"] = selected_fetched_at.isoformat()
        row["price_note"] = None
        row["evidence_sources"] = {
            "price": source, "ma": "BaoStock", "returns": "BaoStock",
            "liquidity": "BaoStock", "fundamentals": "BaoStock", "risk": "BaoStock",
        }
        row["evidence_resolution"] = {
            "price": {"freshness": freshness, "resolution": resolution, "note": note},
            **{
                key: {
                    "freshness": market_resolution,
                    "resolution": "primary",
                    "note": "采用本机最新 BaoStock 日线缓存。" if market_resolution == "cached" else "采用最新 BaoStock 日线。",
                }
                for key in ("ma", "returns", "liquidity", "risk")
            },
        }
        return selected_date, selected_fetched_at

    def snapshot(self, as_of: date) -> tuple[list[dict], SourceMeta]:
        if as_of < date.today():
            return self._historical_snapshot(as_of)
        frame, from_cache, spot_fetched_at = self._spot_frame()
        normalized: list[dict] = []
        for record in frame.to_dict("records"):
            raw_code = str(record.get("代码", ""))
            if not raw_code.startswith(("sh", "sz")):
                continue
            code = self._plain_code(raw_code)
            amount = self._number(record.get("成交额"), 0.0) or 0.0
            price = self._number(record.get("最新价"), 0.0) or 0.0
            change_pct = self._number(record.get("涨跌幅"), 0.0) or 0.0
            if amount >= 50_000_000 and price > 0:
                normalized.append({
                    "code": code,
                    "name": str(record.get("名称", code)),
                    "amount": amount,
                    "price": price,
                    "change_pct": change_pct,
                    "spot": record,
                })
        normalized.sort(key=lambda item: (-item["amount"], item["code"]))
        pool_size = min(max(int(os.getenv("STOCKLLM_LIVE_POOL_SIZE", "24")), 8), 50)
        selected = normalized[:pool_size]
        rows: list[dict] = []
        market_dates: list[date] = []
        price_dates: list[date] = []
        price_fetched_times: list[datetime] = []
        with self._baostock() as bs:
            for item in selected:
                try:
                    row = self._build_row(bs, item["code"], item["name"], as_of)
                    selected_date, selected_fetched_at = self._resolve_price(
                        row,
                        item["spot"],
                        spot_fetched_at,
                        from_cache,
                    )
                    rows.append(row)
                    market_dates.append(date.fromisoformat(row["market_as_of"]))
                    price_dates.append(selected_date)
                    price_fetched_times.append(selected_fetched_at)
                except Exception as exc:
                    rows.append({
                        "code": item["code"], "name": item["name"], "sector": "数据待核验",
                        "risk_label": "data_unavailable", "data_error": str(exc),
                    })
        if not price_dates:
            raise ProviderUnavailable("真实数据补齐失败，没有可核验的最新价格日期")
        latest_price_date = max(price_dates)
        for row in rows:
            if row.get("risk_label") != "data_unavailable" and date.fromisoformat(row["price_as_of"]) != latest_price_date:
                row["risk_label"] = "data_unavailable"
                row["data_error"] = f"最新价格日期落后于候选池统一日期 {latest_price_date.isoformat()}"
        valid_count = sum(row.get("risk_label") != "data_unavailable" for row in rows)
        if valid_count < 3 or not market_dates:
            raise ProviderUnavailable("真实数据补齐失败，可核验证券不足 3 只")
        return rows, SourceMeta(
            source="AkShare · BaoStock",
            as_of=latest_price_date,
            fetched_at=max(price_fetched_times),
            status="cached" if from_cache else "live",
        )

    def _historical_snapshot(self, as_of: date) -> tuple[list[dict], SourceMeta]:
        pool_size = min(max(int(os.getenv("STOCKLLM_LIVE_POOL_SIZE", "24")), 8), 50)
        rows: list[dict] = []
        market_dates: list[date] = []
        with self._baostock() as bs:
            universe = self._query_rows(bs.query_all_stock(day=as_of.isoformat()))
            selected = sorted(
                (
                    {"code": self._plain_code(item.get("code", "")), "name": str(item.get("code_name") or "")}
                    for item in universe
                    if str(item.get("tradeStatus")) == "1"
                    and str(item.get("code", "")).startswith(("sh.6", "sz.0", "sz.3"))
                ),
                key=lambda item: item["code"],
            )[:pool_size]
            if not selected:
                raise ProviderUnavailable("研究日期不是有效交易日，未找到当日证券清单")
            for item in selected:
                try:
                    row = self._build_row(bs, item["code"], item["name"] or item["code"], as_of)
                    row["price_as_of"] = row["market_as_of"]
                    row["price_fetched_at"] = row["market_fetched_at"]
                    row["evidence_sources"] = {
                        key: "BaoStock" for key in ("price", "ma", "returns", "liquidity", "fundamentals", "risk")
                    }
                    rows.append(row)
                    market_dates.append(date.fromisoformat(row["market_as_of"]))
                except Exception as exc:
                    rows.append({
                        "code": item["code"], "name": item["name"] or item["code"], "sector": "数据待核验",
                        "risk_label": "data_unavailable", "data_error": str(exc),
                    })
        valid_count = sum(row.get("risk_label") != "data_unavailable" for row in rows)
        if valid_count < 3 or not market_dates:
            raise ProviderUnavailable("历史数据补齐失败，可核验证券不足 3 只")
        return rows, SourceMeta(
            source="BaoStock",
            as_of=min(market_dates),
            fetched_at=datetime.now(timezone.utc),
            status="historical",
        )

    def search(self, query: str) -> list[dict]:
        frame, _, _ = self._spot_frame()
        query = query.strip().lower()
        results: list[dict] = []
        for record in frame.to_dict("records"):
            raw_code = str(record.get("代码", ""))
            if not raw_code.startswith(("sh", "sz")):
                continue
            code = self._plain_code(raw_code)
            name = str(record.get("名称", code))
            if query in code.lower() or query in name.lower():
                results.append({"code": code, "name": name, "sector": "行业信息将在研究时补齐"})
            if len(results) == 20:
                break
        return results

    def research(self, code: str, as_of: date) -> dict | None:
        code = self._plain_code(code)
        if len(code) != 6 or not code.isdigit():
            return None
        with self._baostock() as bs:
            basics = self._query_rows(bs.query_stock_basic(code=self._bao_code(code)))
            if not basics:
                return None
            name = str(basics[-1].get("code_name") or code)
            row = self._build_row(bs, code, name, as_of)
        market_as_of = date.fromisoformat(row["market_as_of"])
        if as_of == date.today():
            frame, from_cache, spot_fetched_at = self._spot_frame()
            spot = next(
                (record for record in frame.to_dict("records") if self._plain_code(record.get("代码", "")) == code),
                None,
            )
            if not spot:
                raise ProviderUnavailable("AkShare 最新行情中未找到该证券")
            price_as_of, price_fetched_at = self._resolve_price(row, spot, spot_fetched_at, from_cache)
            row["source"] = SourceMeta(
                source=" · ".join(dict.fromkeys(row["evidence_sources"].values())),
                as_of=price_as_of, fetched_at=price_fetched_at,
                status="cached" if from_cache or row["evidence_sources"]["price"] != "AkShare" else "live",
            ).model_dump(mode="json")
        else:
            row["price_as_of"] = market_as_of.isoformat()
            row["price_fetched_at"] = row["market_fetched_at"]
            row["evidence_sources"] = {
                key: "BaoStock" for key in ("price", "ma", "returns", "liquidity", "fundamentals", "risk")
            }
            row["source"] = SourceMeta(
                source="BaoStock", as_of=market_as_of,
                fetched_at=datetime.fromisoformat(row["market_fetched_at"]), status="historical",
            ).model_dump(mode="json")
        content, content_fetched_at, content_from_cache, content_errors = self._content(code, as_of)
        row["news"] = content
        row["content_fetched_at"] = content_fetched_at.isoformat()
        row["content_scope"] = {"news": "最近 10 条", "notices": "研究日前 180 日"}
        row["content_errors"] = content_errors
        if content:
            row["evidence_sources"]["news"] = "AkShare"
            row.setdefault("evidence_resolution", {})["news"] = {
                "freshness": "cached" if content_from_cache else "latest",
                "resolution": "primary",
                "note": None,
            }
        return row

    def status(self) -> dict:
        return {"id": "live", "name": "真实市场数据", "status": "available", "message": "新浪财经行情与 BaoStock 日线、财务数据已配置"}

    def source_statuses(self) -> list[dict]:
        checked_at = datetime.now(timezone.utc).isoformat()
        statuses: list[dict] = []
        try:
            frame, from_cache, _ = self._spot_frame(force_refresh=True)
            count = len(frame.index)
            cache = self.cache_dir / "akshare-sina-spot.parquet"
            if from_cache:
                updated = datetime.fromtimestamp(cache.stat().st_mtime).astimezone().strftime("%Y-%m-%d %H:%M")
                message = f"在线探测失败，已读取 {count} 条缓存；缓存更新于 {updated}"
                status = "cached"
            else:
                message = f"在线探测成功，返回 {count} 条证券行情"
                status = "available"
            statuses.append({
                "id": "akshare-sina-spot", "provider": "AkShare",
                "name": "新浪财经 A 股行情",
                "description": "全市场最新价格、涨跌幅与成交额",
                "status": status,
                "message": message, "checked_at": checked_at,
            })
        except Exception as exc:
            statuses.append({
                "id": "akshare-sina-spot", "provider": "AkShare",
                "name": "新浪财经 A 股行情",
                "description": "全市场最新价格、涨跌幅与成交额",
                "status": "unavailable",
                "message": str(exc), "checked_at": checked_at,
            })

        akshare_content_items = [
            (
                "akshare-eastmoney-news", "东方财富个股新闻", "个股相关新闻、发布时间、发布机构与原文链接",
                lambda: self.ak.stock_news_em(symbol="600519"),
            ),
            (
                "akshare-cninfo-notices", "巨潮资讯公告", "上市公司公告、公告日期与原文链接",
                lambda: self.ak.stock_zh_a_disclosure_report_cninfo(
                    symbol="600519",
                    start_date=(date.today() - timedelta(days=30)).strftime("%Y%m%d"),
                    end_date=date.today().strftime("%Y%m%d"),
                ),
            ),
        ]
        for item_id, name, description, probe in akshare_content_items:
            try:
                with self.pd.option_context("mode.string_storage", "python"):
                    frame = probe()
                statuses.append({
                    "id": item_id, "provider": "AkShare", "name": name,
                    "description": description, "status": "available",
                    "message": f"在线探测成功，返回 {len(frame.index)} 条记录",
                    "checked_at": checked_at,
                })
            except Exception as exc:
                statuses.append({
                    "id": item_id, "provider": "AkShare", "name": name,
                    "description": description, "status": "unavailable",
                    "message": str(exc), "checked_at": checked_at,
                })

        baostock_items = [
            ("baostock-daily", "A 股日线行情", "开盘、最高、最低、收盘、成交量与估值字段"),
            ("baostock-industry", "行业分类", "证券所属行业"),
            ("baostock-financial", "已发布财务数据", "盈利、成长、资产负债与现金流数据"),
        ]
        try:
            with self._baostock() as bs:
                today = date.today()
                probes = {
                    "baostock-daily": lambda: bs.query_history_k_data_plus(
                        "sh.600519", "date,code,close,volume",
                        start_date=(today - timedelta(days=14)).isoformat(),
                        end_date=today.isoformat(), frequency="d", adjustflag="2",
                    ),
                    "baostock-industry": lambda: bs.query_stock_industry(code="sh.600519"),
                    "baostock-financial": lambda: bs.query_profit_data(
                        code="sh.600519", year=today.year - 1, quarter=4,
                    ),
                }
                for item_id, name, description in baostock_items:
                    try:
                        rows = self._query_rows(probes[item_id]())
                        if not rows:
                            raise ProviderUnavailable("查询成功但没有返回可核验记录")
                        statuses.append({
                            "id": item_id, "provider": "BaoStock", "name": name,
                            "description": description, "status": "available",
                            "message": f"在线探测成功，返回 {len(rows)} 条记录",
                            "checked_at": checked_at,
                        })
                    except Exception as exc:
                        statuses.append({
                            "id": item_id, "provider": "BaoStock", "name": name,
                            "description": description, "status": "unavailable",
                            "message": str(exc), "checked_at": checked_at,
                        })
        except Exception as exc:
            statuses.extend({
                "id": item_id, "provider": "BaoStock", "name": name,
                "description": description, "status": "unavailable",
                "message": str(exc), "checked_at": checked_at,
            } for item_id, name, description in baostock_items)
        return statuses


def get_provider(mode: str) -> ResearchProvider:
    if mode == "live":
        return AkShareProvider()
    if mode == "demo" and os.getenv("STOCKLLM_ENABLE_DEMO") == "1":
        return DemoProvider()
    raise ProviderUnavailable("示例数据仅限开发测试，用户研究必须使用可核验数据源")
