from __future__ import annotations

from datetime import date, datetime

from .models import (
    Candidate,
    CheckState,
    Evidence,
    ResearchCheck,
    StrategyDefinition,
    StrategyId,
)


STRATEGIES = [
    StrategyDefinition(
        id=StrategyId.TREND,
        name="趋势观察",
        summary="寻找近期走势较好、成交活跃且没有明显过热的公司。",
        checks=["中短期方向", "均线结构", "成交量确认", "是否过热", "近期风险"],
    ),
    StrategyDefinition(
        id=StrategyId.QUALITY,
        name="质量优先",
        summary="比较公司的盈利、增长、负债、现金流和估值。",
        checks=["盈利能力", "经营增长", "负债压力", "现金流质量", "估值与趋势"],
    ),
    StrategyDefinition(
        id=StrategyId.STABILITY,
        name="稳健低波动",
        summary="寻找近期跌幅较小、经营稳定且成交活跃的公司。",
        checks=["近期回撤", "价格波动", "流动性", "经营稳定", "风险事件"],
    ),
]


def _evidence(
    code: str,
    as_of: date,
    key: str,
    title: str,
    value: str,
    source: str,
    fetched_at: datetime | str | None = None,
    freshness: str = "latest",
    resolution: str = "primary",
    note: str | None = None,
) -> Evidence:
    return Evidence(
        id=f"{code}:{key}", title=title, value=value, source=source,
        as_of=as_of, fetched_at=fetched_at, freshness=freshness, resolution=resolution, note=note,
    )


def _check(label: str, state: CheckState, reason: str, *evidence_ids: str) -> ResearchCheck:
    return ResearchCheck(label=label, state=state, reason=reason, evidence_ids=list(evidence_ids))


def eligibility_reason(stock: dict) -> str | None:
    name = str(stock.get("name", ""))
    if stock.get("risk_label") == "data_unavailable":
        return f"数据无法完整核验：{stock.get('data_error', '行情或财务字段缺失')}"
    if "ST" in name.upper() or stock.get("risk_label") != "normal":
        return "存在 ST、退市整理或其他重大风险标记"
    if stock.get("suspended"):
        return "当前处于停牌状态"
    if int(stock.get("listed_days", 0)) < 120:
        return "上市交易不足 120 个交易日"
    if float(stock.get("avg_amount_20d", 0)) < 50_000_000:
        return "近 20 日平均成交额不足 5000 万元"
    required = ("price", "ma20", "ma60", "avg_amount_20d")
    if any(stock.get(field) is None for field in required):
        return "核心行情字段缺失或来源不可确认"
    return None


def _common_evidence(stock: dict, as_of: date, source: str) -> list[Evidence]:
    code = stock["code"]
    evidence_sources = stock.get("evidence_sources", {})

    def source_for(key: str) -> str:
        return str(evidence_sources.get(key, source))

    evidence_resolution = stock.get("evidence_resolution", {})

    def resolution_for(key: str) -> dict:
        value = evidence_resolution.get(key, {})
        return value if isinstance(value, dict) else {}

    price_as_of = date.fromisoformat(stock["price_as_of"]) if stock.get("price_as_of") else as_of
    market_as_of = date.fromisoformat(stock["market_as_of"]) if stock.get("market_as_of") else as_of
    financial_as_of = date.fromisoformat(stock["financial_as_of"]) if stock.get("financial_as_of") else market_as_of
    return [
        _evidence(
            code, price_as_of, "price", "最新价格", f"{stock['price']:.2f} 元",
            source_for("price"), stock.get("price_fetched_at"),
            resolution_for("price").get("freshness", "latest"),
            resolution_for("price").get("resolution", "primary"),
            resolution_for("price").get("note"),
        ),
        _evidence(code, market_as_of, "ma", "均线位置", f"MA20 {stock['ma20']:.2f} / MA60 {stock['ma60']:.2f}", source_for("ma")),
        _evidence(code, market_as_of, "returns", "阶段涨跌", f"20日 {stock['return_20d']:.2f}% / 60日 {stock['return_60d']:.2f}%", source_for("returns")),
        _evidence(code, market_as_of, "liquidity", "近20日平均成交额", f"{stock['avg_amount_20d'] / 100_000_000:.2f} 亿元", source_for("liquidity")),
        _evidence(code, financial_as_of, "fundamentals", "经营概览", f"ROE {stock['roe']:.1f}% / 利润增速 {stock['profit_growth']:.1f}% / 负债率 {stock['debt_ratio']:.1f}%", source_for("fundamentals")),
        _evidence(code, market_as_of, "risk", "价格风险", f"60日波动 {stock['volatility_60d'] * 100:.1f}% / 最大回撤 {stock['max_drawdown_60d'] * 100:.1f}%", source_for("risk")),
    ]


def trend_checks(stock: dict) -> list[ResearchCheck]:
    code = stock["code"]
    direction_ok = stock["return_20d"] > 0 and stock["return_60d"] > 0
    ma_ok = stock["price"] > stock["ma20"] > stock["ma60"]
    volume = stock["volume_ratio"]
    rsi = stock["rsi"]
    return [
        _check("中短期方向", CheckState.PASS if direction_ok else CheckState.CONCERN, "20日与60日走势同向向上。" if direction_ok else "中短期方向尚未形成一致向上。", f"{code}:returns"),
        _check("均线结构", CheckState.PASS if ma_ok else CheckState.CONCERN, "价格位于20日和60日均线上方。" if ma_ok else "价格或均线结构仍需确认。", f"{code}:price", f"{code}:ma"),
        _check("成交量确认", CheckState.PASS if 0.9 <= volume <= 1.6 else CheckState.CONCERN, f"量比为 {volume:.2f}，" + ("量价配合处于可观察区间。" if 0.9 <= volume <= 1.6 else "当前量能确认不足或放大过快。"), f"{code}:liquidity"),
        _check("是否过热", CheckState.FAIL if rsi >= 80 else CheckState.PASS if rsi < 72 else CheckState.CONCERN, f"RSI 为 {rsi:.0f}，" + ("存在明显过热迹象。" if rsi >= 80 else "尚未出现明显过热。" if rsi < 72 else "接近偏热区间。"), f"{code}:returns"),
        _check("近期风险", CheckState.CONCERN if stock["max_drawdown_60d"] > 0.18 else CheckState.PASS, "近期回撤需要额外关注。" if stock["max_drawdown_60d"] > 0.18 else "近期回撤仍在可观察范围。", f"{code}:risk"),
    ]


def quality_checks(stock: dict) -> list[ResearchCheck]:
    code = stock["code"]
    growth_ok = stock["profit_growth"] > 0 and stock["revenue_growth"] > 0
    debt_ok = stock["debt_ratio"] < 60
    valuation = CheckState.CONCERN if stock["pe"] > 55 else CheckState.PASS
    return [
        _check("盈利能力", CheckState.PASS if stock["roe"] >= 12 else CheckState.CONCERN, f"ROE 为 {stock['roe']:.1f}%，" + ("盈利能力较扎实。" if stock["roe"] >= 12 else "盈利能力仍需同行比较。"), f"{code}:fundamentals"),
        _check("经营增长", CheckState.PASS if growth_ok else CheckState.CONCERN, "营收与利润保持正增长。" if growth_ok else "营收或利润增长出现分化。", f"{code}:fundamentals"),
        _check("负债压力", CheckState.PASS if debt_ok else CheckState.CONCERN, f"负债率为 {stock['debt_ratio']:.1f}%，" + ("暂未显示明显压力。" if debt_ok else "需要结合所在行业进一步判断。"), f"{code}:fundamentals"),
        _check("现金流质量", CheckState.PASS if stock["cashflow_quality"] >= 0.8 else CheckState.CONCERN, f"现金流质量指标为 {stock['cashflow_quality']:.2f}。", f"{code}:fundamentals"),
        _check("估值与趋势", valuation if stock["price"] >= stock["ma60"] else CheckState.CONCERN, f"PE 为 {stock['pe']:.1f}，价格" + ("未跌破" if stock["price"] >= stock["ma60"] else "低于") + "60日均线。", f"{code}:price", f"{code}:ma"),
    ]


def stability_checks(stock: dict) -> list[ResearchCheck]:
    code = stock["code"]
    return [
        _check("近期回撤", CheckState.PASS if stock["max_drawdown_60d"] <= 0.12 else CheckState.CONCERN, f"60日最大回撤约 {stock['max_drawdown_60d'] * 100:.1f}%。", f"{code}:risk"),
        _check("价格波动", CheckState.PASS if stock["volatility_60d"] <= 0.18 else CheckState.CONCERN, f"60日波动约 {stock['volatility_60d'] * 100:.1f}%。", f"{code}:risk"),
        _check("流动性", CheckState.PASS, f"近20日平均成交额约 {stock['avg_amount_20d'] / 100_000_000:.2f} 亿元。", f"{code}:liquidity"),
        _check("经营稳定", CheckState.PASS if stock["roe"] >= 10 and stock["profit_growth"] >= 0 else CheckState.CONCERN, "盈利和利润变化保持稳定。" if stock["roe"] >= 10 and stock["profit_growth"] >= 0 else "经营稳定性仍需观察。", f"{code}:fundamentals"),
        _check("风险事件", CheckState.PASS if stock["debt_ratio"] < 55 else CheckState.CONCERN, "当前基础数据未显示突出风险标记。" if stock["debt_ratio"] < 55 else "负债水平需要继续关注。", f"{code}:fundamentals"),
    ]


CHECKERS = {
    StrategyId.TREND: trend_checks,
    StrategyId.QUALITY: quality_checks,
    StrategyId.STABILITY: stability_checks,
}


def build_candidates(stocks: list[dict], strategy: StrategyId, as_of: date, source: str) -> tuple[list[Candidate], list[dict]]:
    candidates: list[Candidate] = []
    excluded: list[dict] = []
    for stock in stocks:
        reason = eligibility_reason(stock)
        if reason:
            excluded.append({"code": stock.get("code"), "name": stock.get("name"), "reason": reason})
            continue
        evidence = _common_evidence(stock, as_of, source)
        checks = CHECKERS[strategy](stock)
        passed = sum(check.state == CheckState.PASS for check in checks)
        concerns = sum(check.state == CheckState.CONCERN for check in checks)
        completeness = 1.0
        candidates.append(
            Candidate(
                code=stock["code"], name=stock["name"], sector=stock["sector"],
                price=stock["price"], change_pct=stock["change_pct"], checks=checks,
                evidence=evidence, passed=passed, concerns=concerns, completeness=completeness,
            )
        )
    candidates.sort(key=lambda item: (-item.passed, item.concerns, -item.completeness, item.code))
    return candidates[:20], excluded
