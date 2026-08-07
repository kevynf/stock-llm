from __future__ import annotations

import math
from datetime import date, datetime, timezone

from ..models.common import SourceMeta
from .base import ResearchProvider

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
