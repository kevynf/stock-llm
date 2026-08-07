from __future__ import annotations

import math
import os
import statistics
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator
from zoneinfo import ZoneInfo

from ..models.common import SourceMeta
from ..storage import atomic_cache_write, data_dir
from .base import ProviderUnavailable, ResearchProvider
from .content import fetch_content
from .status import probe_source_statuses


class AKShareProvider(ResearchProvider):
    """Cached live universe from AKShare, enriched with BaoStock research data."""

    _baostock_lock = threading.Lock()
    _akshare_lock = threading.Lock()

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
        try:
            modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        except OSError:
            return False
        return datetime.now(timezone.utc) - modified <= max_age

    @staticmethod
    def _cache_time(path: Path) -> datetime:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)

    def _read_parquet_cache(self, path: Path, required: set[str]) -> object | None:
        """Treat missing, corrupt, or schema-incompatible cache files as misses."""
        try:
            frame = self.pd.read_parquet(path)
            columns = set(getattr(frame, "columns", ()))
            return frame if required.issubset(columns) else None
        except Exception:
            return None

    @staticmethod
    def _latest_cache_age() -> timedelta:
        minutes = min(max(int(os.getenv("STOCKLLM_LIVE_CACHE_MINUTES", "15")), 1), 60)
        return timedelta(minutes=minutes)

    def _akshare_frame(self, fetch: Callable[[], object]) -> object:
        for attempt in range(2):
            try:
                with self._akshare_lock, self.pd.option_context("mode.string_storage", "python"):
                    return fetch()
            except Exception:
                if attempt == 1:
                    raise
                time.sleep(0.25)
        raise RuntimeError("AKShare retry loop exited unexpectedly")

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
        required = {"代码", "名称", "最新价", "涨跌幅", "昨收", "今开", "成交量", "成交额", "时间戳"}
        if not force_refresh and self._fresh(cache, self._latest_cache_age()):
            cached = self._read_parquet_cache(cache, required)
            if cached is not None:
                return cached, True, self._cache_time(cache)
        try:
            frame = self._akshare_frame(self.ak.stock_zh_a_spot)
            if frame.empty or not required.issubset(frame.columns):
                raise ProviderUnavailable("AKShare 实时列表字段发生变化")
            fetched_at = datetime.now(timezone.utc)
            with atomic_cache_write(cache) as temporary:
                frame.to_parquet(temporary, index=False)
            return frame, False, fetched_at
        except Exception as exc:
            if self._fresh(cache, timedelta(hours=24)):
                cached = self._read_parquet_cache(cache, required)
                if cached is not None:
                    return cached, True, self._cache_time(cache)
            raise ProviderUnavailable(f"AKShare 实时列表不可用：{exc}") from exc

    def _history(self, bs: object, code: str, as_of: date) -> tuple[list[dict], datetime, bool]:
        cache = self.cache_dir / f"history-{code}-{as_of.isoformat()}.parquet"
        max_age = self._latest_cache_age() if as_of == date.today() else timedelta(days=36500)
        required = {"date", "close"}
        if self._fresh(cache, max_age):
            cached = self._read_parquet_cache(cache, required)
            if cached is not None:
                return cached.to_dict("records"), self._cache_time(cache), True
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
        with atomic_cache_write(cache) as temporary:
            self.pd.DataFrame(rows).to_parquet(temporary, index=False)
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
        return fetch_content(self, code, as_of)

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
            raise ProviderUnavailable("AKShare 最新价格或涨跌幅字段缺失")

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
        source = "AKShare"
        selected_date = observed_date
        selected_fetched_at = spot_fetched_at
        if same_date_conflict:
            resolution = "conflict"
            note = "AKShare 行情与 BaoStock 当日日线收盘价不同；两条来源记录保持独立。"
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
            source="AKShare · BaoStock",
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
                raise ProviderUnavailable("AKShare 最新行情中未找到该证券")
            price_as_of, price_fetched_at = self._resolve_price(row, spot, spot_fetched_at, from_cache)
            row["source"] = SourceMeta(
                source=" · ".join(dict.fromkeys(row["evidence_sources"].values())),
                as_of=price_as_of, fetched_at=price_fetched_at,
                status="cached" if from_cache or row["evidence_sources"]["price"] != "AKShare" else "live",
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
            row["evidence_sources"]["news"] = "AKShare"
            row.setdefault("evidence_resolution", {})["news"] = {
                "freshness": "cached" if content_from_cache else "latest",
                "resolution": "primary",
                "note": None,
            }
        return row

    def status(self) -> dict:
        return {"id": "live", "name": "真实市场数据", "status": "available", "message": "新浪财经行情与 BaoStock 日线、财务数据已配置"}

    def source_statuses(self) -> list[dict]:
        return probe_source_statuses(self)
