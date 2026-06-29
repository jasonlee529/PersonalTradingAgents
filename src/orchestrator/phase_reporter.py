# src/orchestrator/phase_reporter.py
import logging
from datetime import datetime
from typing import Any

from src.orchestrator.state import AnalysisJob, AnalysisStep, JobStatus, StepStatus

logger = logging.getLogger(__name__)


class PhaseReporter:
    """Reports analysis phase/step progress for the task-detail workflow."""

    NODE_TO_STEP = {
        "preparing": "preparing",
        "data_start": "prepare_data",
        "tools_market": "prepare_data",
        "tools_social": "prepare_data",
        "tools_news": "prepare_data",
        "tools_fundamentals": "prepare_data",
        "tools_catalyst": "prepare_data",
        "tools_flow_risk": "prepare_data",
        "Market Analyst": "analyst_market",
        "Sentiment Analyst": "analyst_sentiment",
        "Social Media Analyst": "analyst_sentiment",
        "News Analyst": "analyst_news",
        "Fundamentals Analyst": "analyst_fundamentals",
        "Catalyst Mapper": "analyst_catalyst",
        "Flow Risk Analyst": "analyst_flow_risk",
        "Bull Researcher": "debate_bull",
        "Bear Researcher": "debate_bear",
        "Research Manager": "debate_judge",
        "Trader": "trader_plan",
        "Aggressive Analyst": "risk_aggressive",
        "Conservative Analyst": "risk_conservative",
        "Neutral Analyst": "risk_neutral",
        "Portfolio Manager": "final_decision",
        "finalizing": "final_packaging",
        "completed": "completed",
    }

    STEP_CONFIG = {
        "preparing": {
            "module": "分析模块",
            "label": "初始化环境",
            "role": "系统调度",
            "character": "⚙️",
            "action": "初始化分析环境、装载配置和上下文",
        },
        "prepare_data": {
            "module": "分析模块",
            "label": "准备与数据收集",
            "role": "系统调度",
            "character": "⚙️",
            "action": "装载持仓、历史记忆和行情上下文",
        },
        "analyst_market": {
            "module": "分析模块",
            "label": "市场结构分析",
            "role": "市场分析师",
            "character": "📈",
            "action": "研判趋势、量价、技术位置",
            "artifact_key": "market_report",
        },
        "analyst_sentiment": {
            "module": "分析模块",
            "label": "情绪与叙事分析",
            "role": "情绪分析师",
            "character": "🧭",
            "action": "梳理市场叙事和媒体温度",
            "artifact_key": "sentiment_report",
        },
        "analyst_news": {
            "module": "分析模块",
            "label": "新闻事件分析",
            "role": "事件分析师",
            "character": "📰",
            "action": "提取短期催化和风险事件",
            "artifact_key": "news_report",
        },
        "analyst_fundamentals": {
            "module": "分析模块",
            "label": "基本面分析",
            "role": "基本面分析师",
            "character": "📊",
            "action": "核对估值、利润、现金流和财务质量",
            "artifact_key": "fundamentals_report",
        },
        "analyst_catalyst": {
            "module": "分析模块",
            "label": "政策与产业催化",
            "role": "A股政策分析师",
            "character": "🏛️",
            "action": "追踪政策方向、产业链催化和监管边界",
            "artifact_key": "catalyst_report",
        },
        "analyst_flow_risk": {
            "module": "分析模块",
            "label": "资金与供给风险",
            "role": "A股资金分析师",
            "character": "💹",
            "action": "合并观察资金流、龙虎榜、北向、解禁减持压力",
            "artifact_key": "flow_risk_report",
        },
        "debate_bull": {
            "module": "研究团队辩论",
            "label": "看多论证",
            "role": "多头研究员",
            "character": "⬆️",
            "action": "挑出最强上涨逻辑和可验证证据",
        },
        "debate_bear": {
            "module": "研究团队辩论",
            "label": "看空质询",
            "role": "空头研究员",
            "character": "⬇️",
            "action": "拆解估值、交易拥挤和基本面弱点",
        },
        "debate_judge": {
            "module": "研究团队辩论",
            "label": "研究结论",
            "role": "研究经理",
            "character": "🧠",
            "action": "压缩多空争议并形成投资方案",
            "artifact_key": "investment_plan",
        },
        "trader_plan": {
            "module": "交易与风控",
            "label": "交易计划",
            "role": "交易员",
            "character": "🎯",
            "action": "把研究结论转成仓位、触发位和执行节奏",
            "artifact_key": "trader_investment_plan",
        },
        "risk_aggressive": {
            "module": "交易与风控",
            "label": "进攻视角",
            "role": "进攻风控",
            "character": "🔥",
            "action": "评估高收益情景和加仓条件",
        },
        "risk_conservative": {
            "module": "交易与风控",
            "label": "防守视角",
            "role": "防守风控",
            "character": "🛡️",
            "action": "评估回撤、流动性和退出边界",
        },
        "risk_neutral": {
            "module": "交易与风控",
            "label": "中性复核",
            "role": "中立风控",
            "character": "⚖️",
            "action": "平衡进攻和防守观点",
        },
        "final_decision": {
            "module": "最终决策",
            "label": "最终投资决策",
            "role": "组合经理",
            "character": "✅",
            "action": "给出最终评级、理由和风险条件",
            "artifact_key": "final_trade_decision",
        },
        "final_packaging": {
            "module": "最终决策",
            "label": "报告归档",
            "role": "系统调度",
            "character": "📦",
            "action": "保存知识库、索引记忆树和输出文件",
        },
        "completed": {
            "module": "最终决策",
            "label": "分析完成",
            "role": "任务完成",
            "character": "🏁",
            "action": "全部产物已生成",
        },
    }

    DEBATE_ARTIFACTS = {
        "Bull Researcher": ("investment_debate_state", "bull_history"),
        "Bear Researcher": ("investment_debate_state", "bear_history"),
        "Research Manager": ("investment_debate_state", "judge_decision"),
        "Aggressive Analyst": ("risk_debate_state", "aggressive_history"),
        "Conservative Analyst": ("risk_debate_state", "conservative_history"),
        "Neutral Analyst": ("risk_debate_state", "neutral_history"),
    }

    def __init__(self, job: AnalysisJob, job_store=None):
        self.job = job
        self._job_store = job_store
        self._step_map: dict[str, AnalysisStep] = {}
        self._init_steps()

    def _init_steps(self) -> None:
        if self.job.steps:
            self._step_map = {s.step_id: s for s in self.job.steps}
            return

        steps = []
        for step_id, cfg in self.STEP_CONFIG.items():
            step = AnalysisStep(
                step_id=step_id,
                label=cfg["label"],
                role=cfg["role"],
                character=cfg["character"],
                module=cfg.get("module", ""),
                action=cfg.get("action", ""),
                artifact_key=cfg.get("artifact_key", ""),
                status=StepStatus.PENDING,
            )
            steps.append(step)
            self._step_map[step_id] = step
        self.job.steps = steps

    async def on_node_start(self, node_name: str, detail: str = "") -> None:
        step_id = self.NODE_TO_STEP.get(node_name)
        if not step_id:
            return
        step = self._step_map.get(step_id)
        if not step:
            return

        if step.status == StepStatus.DONE and step_id == "prepare_data":
            return
        if step_id.startswith("analyst_"):
            self._complete_prepare_data_if_needed()
        if step.status != StepStatus.ERROR:
            step.status = StepStatus.RUNNING
            step.started_at = step.started_at or datetime.utcnow()
        if detail:
            step.detail = detail
        self.job.phase = step_id
        self.job.update_progress(f"{step.label}：{step.action}")
        await self._persist()

    async def on_node_end(self, node_name: str, state_delta: dict[str, Any] | None = None) -> None:
        step_id = self.NODE_TO_STEP.get(node_name)
        if not step_id:
            return
        step = self._step_map.get(step_id)
        if not step:
            return

        artifact = self._extract_artifact(node_name, step, state_delta or {})
        if artifact:
            step.detail = artifact

        if self._requires_artifact_to_complete(node_name, step) and not artifact:
            await self._persist()
            return

        if step.status == StepStatus.RUNNING:
            step.status = StepStatus.DONE
            step.completed_at = datetime.utcnow()
            self._complete_prepare_data_if_needed()
        await self._persist()

    async def on_error(self, node_name: str, error: str) -> None:
        step_id = self.NODE_TO_STEP.get(node_name) or self.job.phase
        if step_id:
            step = self._step_map.get(step_id)
            if step:
                step.status = StepStatus.ERROR
                step.detail = error
        self.job.status = JobStatus.ERROR
        await self._persist()

    async def on_complete(self) -> None:
        for step in self.job.steps:
            if step.status == StepStatus.RUNNING:
                step.status = StepStatus.DONE
                step.completed_at = datetime.utcnow()
        completed = self._step_map.get("completed")
        if completed:
            completed.status = StepStatus.DONE
            completed.completed_at = datetime.utcnow()
        self.job.phase = "completed"
        self.job.update_progress("分析完成")
        await self._persist()

    async def on_finalizing(self, detail: str = "") -> None:
        await self.on_node_start("finalizing", detail)

    async def on_finalized(self, detail: str = "") -> None:
        step = self._step_map.get("final_packaging")
        if not step:
            return
        if detail:
            step.detail = detail
        step.status = StepStatus.DONE
        step.completed_at = datetime.utcnow()
        await self._persist()

    def _extract_artifact(self, node_name: str, step: AnalysisStep, state_delta: dict[str, Any]) -> str:
        raw = ""
        if step.artifact_key:
            value = state_delta.get(step.artifact_key)
            if value:
                raw = str(value)

        if not raw:
            debate_path = self.DEBATE_ARTIFACTS.get(node_name)
            if debate_path:
                parent, child = debate_path
                value = state_delta.get(parent, {})
                if isinstance(value, dict) and value.get(child):
                    raw = str(value[child])

        if not raw and node_name == "Portfolio Manager":
            value = state_delta.get("risk_debate_state", {})
            if isinstance(value, dict) and value.get("judge_decision"):
                raw = str(value["judge_decision"])

        return self._strip_markdown_fence(raw)

    def _requires_artifact_to_complete(self, node_name: str, step: AnalysisStep) -> bool:
        if node_name.startswith("tools_"):
            return False
        return bool(step.artifact_key) or node_name in self.DEBATE_ARTIFACTS

    def _complete_prepare_data_if_needed(self) -> None:
        step = self._step_map.get("prepare_data")
        if not step or step.status != StepStatus.RUNNING:
            return
        step.status = StepStatus.DONE
        step.completed_at = datetime.utcnow()

    @staticmethod
    def _strip_markdown_fence(text: str) -> str:
        t = text.strip()
        if t.startswith("```markdown"):
            t = t[len("```markdown"):]
        elif t.startswith("```"):
            t = t[3:]
        if t.endswith("```"):
            t = t[:-3]
        return t.strip()

    async def _persist(self) -> None:
        if self._job_store:
            try:
                await self._job_store.save(self.job)
            except Exception as e:
                logger.warning("PhaseReporter failed to persist job: %s", e)
