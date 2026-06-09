"""Report quality auditor for analyst outputs.

The auditor is intentionally independent from the graph. It reviews the final
state after analysis finishes and writes a markdown summary that can be stored
with the rest of the run artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Optional

logger = logging.getLogger(__name__)

MIN_REPORT_LENGTH = 200

FAILURE_MARKERS = [
    "无法获取",
    "I cannot retrieve",
    "I don't have access",
    "unable to fetch",
    "工具调用失败",
]


@dataclass(frozen=True)
class ReportQualityRule:
    min_length: int = MIN_REPORT_LENGTH
    failure_markers: tuple[str, ...] = tuple(FAILURE_MARKERS)
    missing_data_marker: str = "[数据缺失"
    require_markdown_table: bool = True
    warn_missing_data_count: int = 3


@dataclass(frozen=True)
class ReportAuditResult:
    analyst_type: str
    display_name: str
    field: str
    grade: str
    detail: str
    length: int
    missing_data_count: int = 0
    has_table: bool = False
    llm_review: str = ""


@dataclass
class ReportQualityAuditor:
    """Configurable auditor for final analyst reports."""

    rule: ReportQualityRule = field(default_factory=ReportQualityRule)
    llm_client: Optional[object] = None

    def audit_state(self, final_state: dict) -> list[ReportAuditResult]:
        report_fields = _get_analyst_report_fields()
        display_names = _get_analyst_display_names()

        results: list[ReportAuditResult] = []
        for analyst_type, field_name in report_fields.items():
            report = final_state.get(field_name, "")
            result = self.audit_report(
                analyst_type=analyst_type,
                display_name=display_names.get(analyst_type, analyst_type),
                field=field_name,
                report=report,
            )
            if result.grade in ("C", "D", "F"):
                review = self.review_with_llm(
                    analyst_type=analyst_type,
                    report=report,
                    grade=result.grade,
                    detail=result.detail,
                )
                if review:
                    result = ReportAuditResult(
                        **{**result.__dict__, "llm_review": review}
                    )
            results.append(result)
        return results

    def audit_report(
        self,
        *,
        analyst_type: str,
        display_name: str,
        field: str,
        report: str,
    ) -> ReportAuditResult:
        text = (report or "").strip()
        length = len(text)
        missing_count = text.count(self.rule.missing_data_marker)
        has_table = "|" in text and "---" in text

        if not text:
            return ReportAuditResult(
                analyst_type, display_name, field, "F", "报告为空", length
            )

        if length < self.rule.min_length:
            return ReportAuditResult(
                analyst_type,
                display_name,
                field,
                "D",
                f"报告过短 ({length} chars < {self.rule.min_length})",
                length,
                missing_count,
                has_table,
            )

        failure_count = sum(1 for marker in self.rule.failure_markers if marker in text)
        stripped = text
        for marker in self.rule.failure_markers:
            stripped = stripped.replace(marker, "")
        if failure_count > 0 and len(stripped.strip()) < self.rule.min_length:
            return ReportAuditResult(
                analyst_type,
                display_name,
                field,
                "D",
                f"报告主要由失败信息构成 ({failure_count} 处)",
                length,
                missing_count,
                has_table,
            )

        issues: list[str] = []
        if self.rule.require_markdown_table and not has_table:
            issues.append("缺少结构化汇总表")
        if missing_count > 0:
            issues.append(f"{missing_count} 处数据缺失")

        if missing_count >= self.rule.warn_missing_data_count:
            return ReportAuditResult(
                analyst_type,
                display_name,
                field,
                "C",
                "；".join(issues),
                length,
                missing_count,
                has_table,
            )
        if issues:
            return ReportAuditResult(
                analyst_type,
                display_name,
                field,
                "B",
                "；".join(issues),
                length,
                missing_count,
                has_table,
            )
        return ReportAuditResult(
            analyst_type,
            display_name,
            field,
            "A",
            f"完整 ({length} chars)",
            length,
            missing_count,
            has_table,
        )

    def review_with_llm(
        self,
        *,
        analyst_type: str,
        report: str,
        grade: str,
        detail: str,
    ) -> str:
        if self.llm_client is None:
            return ""

        prompt = f"""你是金融研究报告质量审计员。请审查下面这份分析报告为什么没有通过质量检查，并给出可执行的补强建议。

分析师类型: {analyst_type}
质量评级: {grade}
问题描述: {detail}

报告内容（前2000字符）:
{(report or "")[:2000]}

请用中文输出三部分:
1. 主要问题（2-3点）
2. 需要补充的数据或证据
3. 建议修改后的报告结构
"""
        try:
            response = self.llm_client.invoke(prompt)
            return getattr(response, "content", str(response)).strip()
        except Exception as e:
            logger.warning("LLM review failed for %s: %s", analyst_type, e)
            return f"LLM 复审失败: {e}"


def _get_analyst_report_fields() -> dict[str, str]:
    """Discover active analyst -> report field mapping from AnalystRegistry."""
    try:
        from tradingagents.agents.analyst_registry import AnalystRegistry

        registry = AnalystRegistry()
        return {entry.name: entry.report_key for entry in registry.list()}
    except Exception as e:
        logger.warning("Failed to discover analysts from registry: %s", e)
        return {
            "market": "market_report",
            "social": "sentiment_report",
            "news": "news_report",
            "fundamentals": "fundamentals_report",
            "catalyst": "catalyst_report",
            "flow_risk": "flow_risk_report",
        }


def _get_analyst_display_names() -> dict[str, str]:
    """Discover active analyst display names from AnalystRegistry."""
    try:
        from tradingagents.agents.analyst_registry import AnalystRegistry

        registry = AnalystRegistry()
        return {entry.name: entry.label for entry in registry.list()}
    except Exception as e:
        logger.warning("Failed to get analyst labels: %s", e)
        return {
            "market": "市场分析师",
            "social": "情绪分析师",
            "news": "新闻分析师",
            "fundamentals": "基本面分析师",
            "catalyst": "政策与产业催化",
            "flow_risk": "资金与供给风险",
        }


def _hard_check_report(analyst_type: str, report: str) -> tuple[str, str]:
    """Compatibility wrapper for tests and older callers."""
    auditor = ReportQualityAuditor()
    result = auditor.audit_report(
        analyst_type=analyst_type,
        display_name=analyst_type,
        field=f"{analyst_type}_report",
        report=report,
    )
    return result.grade, result.detail


def _llm_review_report(
    analyst_type: str, report: str, grade: str, detail: str, llm_client=None
) -> str:
    """Compatibility wrapper around ReportQualityAuditor.review_with_llm."""
    return ReportQualityAuditor(llm_client=llm_client).review_with_llm(
        analyst_type=analyst_type,
        report=report,
        grade=grade,
        detail=detail,
    )


def _render_summary(final_state: dict, results: list[ReportAuditResult]) -> str:
    trade_date = final_state.get("trade_date", "")
    ticker = final_state.get("company_of_interest", "")

    hard_summary = "\n".join(
        f"- {result.display_name}: [{result.grade}] {result.detail}"
        for result in results
    )
    fail_count = sum(1 for result in results if result.grade in ("F", "D"))
    warn_count = sum(1 for result in results if result.grade == "C")
    status = "通过" if fail_count < 4 else "警告"

    summary = (
        "## 报告完整性审计\n\n"
        f"**标的**: {ticker} | **交易日**: {trade_date}\n\n"
        f"### 硬检查结果\n{hard_summary}\n\n"
        f"**未通过数**: {fail_count}/{len(results)}\n"
        f"**警告数**: {warn_count}/{len(results)}\n"
        f"**整体评级**: {status}\n"
    )

    llm_results = [result for result in results if result.llm_review]
    if llm_results:
        summary += "\n### LLM 复审建议\n\n"
        for result in llm_results:
            summary += f"#### {result.display_name}\n{result.llm_review}\n\n"
    return summary


def run_quality_gate(final_state: dict, llm_client=None) -> str:
    """Run report quality auditing on final_state reports."""
    auditor = ReportQualityAuditor(llm_client=llm_client)
    return _render_summary(final_state, auditor.audit_state(final_state))
