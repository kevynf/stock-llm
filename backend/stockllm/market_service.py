from __future__ import annotations

import json
import logging
import time
from datetime import date

from .db import Database
from .diagnostics import log_event
from .providers import get_provider


PROVIDER_STATUS_CACHE_KEY = "providers.last_status"
PROVIDER_STATUS_VERSION_KEY = "providers.status_version"
PROVIDER_STATUS_VERSION = "2"
PROVIDER_SOURCES = [
    ("akshare-sina-spot", "AKShare", "新浪财经 A 股行情", "全市场最新价格、涨跌幅与成交额"),
    ("akshare-eastmoney-news", "AKShare", "东方财富个股新闻", "个股相关新闻、发布时间、发布机构与原文链接"),
    ("akshare-cninfo-notices", "AKShare", "巨潮资讯公告", "上市公司公告、公告日期与原文链接"),
    ("baostock-daily", "BaoStock", "A 股日线行情", "开盘、最高、最低、收盘、成交量与估值字段"),
    ("baostock-industry", "BaoStock", "行业分类", "证券所属行业"),
    ("baostock-financial", "BaoStock", "已发布财务数据", "盈利、成长、资产负债与现金流数据"),
]

class MarketDataUnavailableError(RuntimeError):
    """Provider failures translated into the market application boundary."""


__all__ = ["MarketDataUnavailableError", "MarketService"]


class MarketService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def search(self, query: str, data_mode: str) -> list[dict]:
        try:
            return get_provider(data_mode).search(query)
        except Exception as exc:
            raise MarketDataUnavailableError(str(exc)) from exc

    def research(self, code: str, as_of: date, data_mode: str) -> dict | None:
        try:
            result = get_provider(data_mode).research(code, as_of)
        except Exception as exc:
            raise MarketDataUnavailableError(str(exc)) from exc
        if result:
            source = result.get("source") if isinstance(result.get("source"), dict) else {}
            log_event(
                logging.INFO,
                "providers",
                "stock_research",
                "Stock research data loaded",
                data_source=source.get("source"),
                cache_hit=source.get("status") == "cached",
                status="success",
            )
        return result

    def provider_status(self) -> list[dict]:
        if self.db.get_setting(PROVIDER_STATUS_VERSION_KEY, "") != PROVIDER_STATUS_VERSION:
            return []
        try:
            cached = json.loads(self.db.get_setting(PROVIDER_STATUS_CACHE_KEY, "[]"))
        except json.JSONDecodeError:
            return []
        return cached if isinstance(cached, list) else []

    def check_provider_status(self) -> list[dict]:
        statuses = self._check_provider_status()
        self.db.set_setting(PROVIDER_STATUS_CACHE_KEY, json.dumps(statuses, ensure_ascii=False))
        self.db.set_setting(PROVIDER_STATUS_VERSION_KEY, PROVIDER_STATUS_VERSION)
        self.db.set_setting("providers.last_checked_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        log_event(
            logging.INFO,
            "providers",
            "status_check",
            "Provider status check completed",
            data_sources=sorted({item.get("provider") for item in statuses if item.get("provider")}),
            status="success" if any(item.get("status") != "unavailable" for item in statuses) else "unavailable",
        )
        return statuses

    @staticmethod
    def _unavailable_statuses(message: str) -> list[dict]:
        return [
            {
                "id": item_id,
                "provider": provider_name,
                "name": name,
                "description": description,
                "status": "unavailable",
                "message": message,
            }
            for item_id, provider_name, name, description in PROVIDER_SOURCES
        ]

    def _check_provider_status(self) -> list[dict]:
        try:
            provider = get_provider("live")
            source_statuses = getattr(provider, "source_statuses", None)
            if not callable(source_statuses):
                raise RuntimeError("真实数据源不支持独立状态检查")
            return source_statuses()
        except Exception as exc:
            return self._unavailable_statuses(str(exc))
