from datetime import date, datetime, timezone

import pandas as pd

from stockllm.engine import build_candidates, eligibility_reason
from stockllm.models import StrategyId
from stockllm.providers import AKShareProvider, DemoProvider


def reliable_spot(price: float, change_pct: float) -> dict:
    return {
        "最新价": price,
        "涨跌幅": change_pct,
        "昨收": price / (1 + change_pct / 100),
        "今开": price,
        "成交量": 1_000_000,
        "成交额": price * 1_000_000,
        "时间戳": "15:00:00",
    }


def test_candidates_are_deterministic() -> None:
    as_of = date(2026, 8, 1)
    rows, source = DemoProvider().snapshot(as_of)
    first, excluded = build_candidates(rows, StrategyId.TREND, as_of, source.source)
    second, _ = build_candidates(rows, StrategyId.TREND, as_of, source.source)
    assert [item.code for item in first] == [item.code for item in second]
    assert excluded == []
    assert all(item.evidence for item in first)


def test_evidence_uses_field_level_sources() -> None:
    as_of = date(2026, 8, 1)
    rows, source = DemoProvider().snapshot(as_of)
    rows[0]["evidence_sources"] = {
        "price": "AKShare",
        "ma": "BaoStock",
        "returns": "BaoStock",
        "liquidity": "BaoStock",
        "fundamentals": "BaoStock",
        "risk": "BaoStock",
    }
    candidates, _ = build_candidates(rows, StrategyId.TREND, as_of, source.source)
    evidence_sources = {
        evidence.id.rsplit(":", 1)[-1]: evidence.source
        for evidence in next(item for item in candidates if item.code == rows[0]["code"]).evidence
    }
    assert evidence_sources["price"] == "AKShare"
    assert set(evidence_sources.values()) == {"AKShare", "BaoStock"}


def test_evidence_uses_field_level_dates_and_resolution() -> None:
    as_of = date(2026, 8, 4)
    rows, source = DemoProvider().snapshot(as_of)
    rows[0]["price_as_of"] = "2026-08-04"
    rows[0]["price_fetched_at"] = "2026-08-04T12:00:00+00:00"
    rows[0]["market_as_of"] = "2026-08-03"
    rows[0]["financial_as_of"] = "2026-06-30"
    rows[0]["evidence_resolution"] = {
        "price": {"freshness": "latest", "resolution": "conflict", "note": "来源数值存在冲突。"},
    }
    candidates, _ = build_candidates(rows, StrategyId.TREND, as_of, source.source)
    evidence = {
        item.id.rsplit(":", 1)[-1]: item
        for item in next(candidate for candidate in candidates if candidate.code == rows[0]["code"]).evidence
    }
    assert evidence["price"].as_of == date(2026, 8, 4)
    assert evidence["price"].fetched_at == datetime(2026, 8, 4, 12, tzinfo=timezone.utc)
    assert evidence["price"].resolution == "conflict"
    assert evidence["price"].freshness == "latest"
    assert evidence["ma"].as_of == date(2026, 8, 3)
    assert evidence["risk"].as_of == date(2026, 8, 3)
    assert evidence["fundamentals"].as_of == date(2026, 6, 30)


def test_price_source_comes_from_the_selected_observation() -> None:
    provider = object.__new__(AKShareProvider)
    row = {
        "price": 128.5,
        "change_pct": 0.05,
        "market_as_of": "2026-08-04",
        "market_fetched_at": "2026-08-04T10:00:00+00:00",
        "market_from_cache": False,
    }
    selected_date, _ = provider._resolve_price(
        row,
        reliable_spot(141.35, 10.0),
        datetime(2026, 8, 4, 12, tzinfo=timezone.utc),
        False,
    )
    assert selected_date == date(2026, 8, 4)
    assert row["price"] == 141.35
    assert row["evidence_sources"]["price"] == "AKShare"
    assert row["evidence_resolution"]["price"]["resolution"] == "conflict"
    assert row["evidence_resolution"]["price"]["freshness"] == "latest"


def test_price_source_is_not_reassigned_when_another_source_is_newer() -> None:
    provider = object.__new__(AKShareProvider)
    row = {
        "price": 141.35,
        "change_pct": 10.0,
        "market_as_of": "2026-08-04",
        "market_fetched_at": "2026-08-04T12:00:00+00:00",
        "market_from_cache": False,
    }
    selected_date, _ = provider._resolve_price(
        row,
        reliable_spot(128.5, 0.05),
        datetime(2026, 8, 3, 12, tzinfo=timezone.utc),
        True,
    )
    assert selected_date == date(2026, 8, 3)
    assert row["price"] == 128.5
    assert row["evidence_sources"]["price"] == "AKShare"
    assert row["evidence_resolution"]["price"]["resolution"] == "primary"
    assert row["evidence_resolution"]["price"]["freshness"] == "cached"


def test_price_resolution_keeps_primary_source_when_same_date_and_value() -> None:
    provider = object.__new__(AKShareProvider)
    row = {
        "price": 141.35,
        "change_pct": 10.0,
        "market_as_of": "2026-08-04",
        "market_fetched_at": "2026-08-04T12:30:00+00:00",
        "market_from_cache": False,
    }
    selected_date, _ = provider._resolve_price(
        row,
        reliable_spot(141.35, 10.0),
        datetime(2026, 8, 4, 12, tzinfo=timezone.utc),
        True,
    )
    assert selected_date == date(2026, 8, 4)
    assert row["evidence_sources"]["price"] == "AKShare"
    assert row["evidence_resolution"]["price"] == {
        "freshness": "cached", "resolution": "primary", "note": None,
    }


def test_zero_change_without_valid_opening_trade_uses_last_effective_daily_price() -> None:
    provider = object.__new__(AKShareProvider)
    row = {
        "price": 141.35,
        "change_pct": 5.0,
        "market_as_of": "2026-08-04",
        "market_fetched_at": "2026-08-05T01:20:00+00:00",
        "market_from_cache": False,
    }
    selected_date, _ = provider._resolve_price(
        row,
        {
            "最新价": 141.35, "涨跌幅": 0.0, "昨收": 141.35, "今开": 0.0,
            "成交量": 0.0, "成交额": 0.0, "时间戳": "09:25:00",
        },
        datetime(2026, 8, 5, 1, 25, tzinfo=timezone.utc),
        False,
    )
    assert selected_date == date(2026, 8, 4)
    assert row["price"] == 141.35
    assert row["change_pct"] == 5.0
    assert row["evidence_sources"]["price"] == "BaoStock"
    assert row["price_note"] == "实时行情尚未形成有效成交，显示最近有效日线。"


def test_research_content_keeps_source_semantics_and_respects_as_of(tmp_path) -> None:
    class StubAKShare:
        @staticmethod
        def stock_news_em(symbol: str) -> pd.DataFrame:
            assert symbol == "603259"
            return pd.DataFrame([
                {
                    "新闻标题": "研究日前新闻", "新闻内容": " 可核验的 新闻摘要 ",
                    "发布时间": "2026-08-04 10:48:00", "文章来源": "证券时报网",
                    "新闻链接": "https://example.com/news",
                },
                {
                    "新闻标题": "研究日后新闻", "新闻内容": "不应返回",
                    "发布时间": "2026-08-06 10:00:00", "文章来源": "测试来源",
                    "新闻链接": "https://example.com/future",
                },
            ])

        @staticmethod
        def stock_zh_a_disclosure_report_cninfo(**kwargs) -> pd.DataFrame:
            assert kwargs["symbol"] == "603259"
            return pd.DataFrame([{
                "公告标题": "董事会决议公告", "公告时间": "2026-08-04",
                "公告链接": "https://example.com/notice",
            }])

    provider = object.__new__(AKShareProvider)
    provider.ak = StubAKShare()
    provider.pd = pd
    provider.cache_dir = tmp_path

    items, _, from_cache, errors = provider._content("603259", date(2026, 8, 5))
    assert not from_cache
    assert errors == []
    assert [item["kind"] for item in items] == ["新闻", "公告"]
    assert [item["content_level"] for item in items] == ["summary", "title"]
    assert all(item["source"] == "AKShare" for item in items)
    assert items[0]["publisher"] == "证券时报网"
    assert items[1]["publisher"] == "巨潮资讯"
    assert all(item["published_at"][:10] <= "2026-08-05" for item in items)

    cached, _, from_cache, errors = provider._content("603259", date(2026, 8, 5))
    assert from_cache
    assert errors == []
    assert all(item["freshness"] == "cached" for item in cached)
    assert [item["url"] for item in cached] == [item["url"] for item in items]


def test_common_filter_rejects_illiquid_stock() -> None:
    stock = {
        "name": "测试公司", "risk_label": "normal", "suspended": False,
        "listed_days": 300, "avg_amount_20d": 10_000_000,
        "price": 10, "ma20": 10, "ma60": 10,
    }
    assert eligibility_reason(stock) == "近 20 日平均成交额不足 5000 万元"


def test_historical_snapshot_stops_at_as_of() -> None:
    as_of = date(2025, 6, 10)
    row = DemoProvider().research("600519", as_of)
    assert row is not None
    assert max(point["date"] for point in row["history"]) == as_of.isoformat()
    assert row["history"][-1]["close"] == row["price"]
    assert all({"open", "high", "low", "close", "volume"} <= point.keys() for point in row["history"])
    assert all(point["low"] <= min(point["open"], point["close"]) <= max(point["open"], point["close"]) <= point["high"] for point in row["history"])
