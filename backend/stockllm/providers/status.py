from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol

from .base import ProviderUnavailable


class StatusProviderContext(Protocol):
    ak: Any
    cache_dir: Path

    def _spot_frame(self, force_refresh: bool = False) -> tuple[Any, bool, datetime]: ...

    def _akshare_frame(self, fetch: Callable[[], object]) -> Any: ...

    def _baostock(self) -> AbstractContextManager[Any]: ...

    @staticmethod
    def _query_rows(result: object) -> list[dict]: ...


def probe_source_statuses(provider: StatusProviderContext) -> list[dict]:
    checked_at = datetime.now(timezone.utc).isoformat()
    statuses: list[dict] = []
    try:
        frame, from_cache, _ = provider._spot_frame(force_refresh=True)
        count = len(frame.index)
        cache = provider.cache_dir / "akshare-sina-spot.parquet"
        if from_cache:
            updated = datetime.fromtimestamp(cache.stat().st_mtime).astimezone().strftime("%Y-%m-%d %H:%M")
            message = f"在线探测失败，已读取 {count} 条缓存；缓存更新于 {updated}"
            status = "cached"
        else:
            message = f"在线探测成功，返回 {count} 条证券行情"
            status = "available"
        statuses.append({
            "id": "akshare-sina-spot", "provider": "AKShare",
            "name": "新浪财经 A 股行情",
            "description": "全市场最新价格、涨跌幅与成交额",
            "status": status,
            "message": message, "checked_at": checked_at,
        })
    except Exception as exc:
        statuses.append({
            "id": "akshare-sina-spot", "provider": "AKShare",
            "name": "新浪财经 A 股行情",
            "description": "全市场最新价格、涨跌幅与成交额",
            "status": "unavailable",
            "message": str(exc), "checked_at": checked_at,
        })

    akshare_content_items = [
        (
            "akshare-eastmoney-news", "东方财富个股新闻", "个股相关新闻、发布时间、发布机构与原文链接",
            lambda: provider.ak.stock_news_em(symbol="600519"),
        ),
        (
            "akshare-cninfo-notices", "巨潮资讯公告", "上市公司公告、公告日期与原文链接",
            lambda: provider.ak.stock_zh_a_disclosure_report_cninfo(
                symbol="600519",
                start_date=(date.today() - timedelta(days=30)).strftime("%Y%m%d"),
                end_date=date.today().strftime("%Y%m%d"),
            ),
        ),
    ]
    for item_id, name, description, probe in akshare_content_items:
        try:
            frame = provider._akshare_frame(probe)
            statuses.append({
                "id": item_id, "provider": "AKShare", "name": name,
                "description": description, "status": "available",
                "message": f"在线探测成功，返回 {len(frame.index)} 条记录",
                "checked_at": checked_at,
            })
        except Exception as exc:
            statuses.append({
                "id": item_id, "provider": "AKShare", "name": name,
                "description": description, "status": "unavailable",
                "message": str(exc), "checked_at": checked_at,
            })

    baostock_items = [
        ("baostock-daily", "A 股日线行情", "开盘、最高、最低、收盘、成交量与估值字段"),
        ("baostock-industry", "行业分类", "证券所属行业"),
        ("baostock-financial", "已发布财务数据", "盈利、成长、资产负债与现金流数据"),
    ]
    try:
        with provider._baostock() as bs:
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
                    rows = provider._query_rows(probes[item_id]())
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
