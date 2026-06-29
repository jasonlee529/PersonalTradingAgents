"""DirectionReportBuilder — generate dynamic sector discovery reports with LLM deep analysis.

Replaces template-based generation with LLM-driven reasoning that injects:
- Market overview (indices, breadth stats, sector rankings)
- Scanner signals from all pipeline phases
- News context
- Chain reasoning results

The LLM produces structured analysis: market summary → index commentary →
sector/theme highlights → fund flow & sentiment → news catalysts →
direction-level recommendations without stock picks.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from src.agents.sector_discovery.llm_utils import llm_chain_reasoning
from src.agents.sector_discovery.models import DirectionReport, SectorSnapshot, StockSignal

logger = logging.getLogger(__name__)


class DirectionReportBuilder:
    """Build a DirectionReport with LLM-driven deep analysis."""

    SYSTEM_PROMPT = """你是 A 股市场方向研究员，擅长从热点政策、财经新闻、资金流向和产业链上下游中提炼方向性机会。

分析原则：
1. 先看政策和新闻催化，再看资金流向和市场情绪，最后沿产业链拆上游/中游/下游/配套服务
2. 每个方向必须有独立链路：热点政策/新闻 → 受益链条 → 资金验证 → 预期差 → 关注内容
3. 消息催化要区分"已兑现"和"未兑现"，只保留仍值得跟踪的方向
4. 资金面关注：主力资金流向、北向资金、游资活跃度、板块成交额和涨停结构
5. 输出方向性指导，不要求也不鼓励具体到个股
6. 不给出买卖点、仓位、止盈止损等交易计划

输出要求：
- 必须输出纯 Markdown 文本
- 禁止输出 JSON
- 只分析输入证据中出现的方向，最多 10 个；不要为了凑数编造方向
- 不输出具体个股推荐、股票代码、股票名单
- 每个方向必须写清"应该关注什么内容"
- 预期差分析要具体：市场当前怎么看、实际可能是什么、差距有多大
- 严禁编造未在输入中出现的指数涨跌、成交额、涨跌停家数、北向资金、主力资金、政策或新闻；缺失时写"未获取"或"暂无数据"
"""

    async def build(
        self,
        snapshots: list[SectorSnapshot],
        date: str | None = None,
        market_overview: dict | None = None,
        news_context: str = "",
        policy_signals: list | None = None,
        chain_signals: list | None = None,
        settings = None,
    ) -> DirectionReport:
        """Create a DirectionReport with LLM-driven deep analysis.

        Args:
            snapshots: Screened sector snapshots from the pipeline.
            date: Report date string.
            market_overview: Dict with indices, stats, sector_rankings.
            news_context: Aggregated news text for context.
            policy_signals: Policy signals from PolicyMiner.
            chain_signals: Chain signals from ChainMapper.
            settings: Project Settings for LLM configuration.
        """
        date_str = date or datetime.now().strftime("%Y-%m-%d")
        report = DirectionReport(date=date_str, sectors=snapshots)

        # Try LLM deep analysis first
        if settings and snapshots:
            try:
                llm_content = await self._generate_llm_report(
                    snapshots=snapshots,
                    date_str=date_str,
                    market_overview=market_overview,
                    news_context=news_context,
                    policy_signals=policy_signals,
                    chain_signals=chain_signals,
                    settings=settings,
                )
                if llm_content:
                    report.summary = llm_content
                    return report
            except Exception as e:
                logger.warning("LLM report generation failed, falling back to template: %s", e)

        # Fallback to template-based generation
        report.summary = self._build_summary(
            snapshots,
            market_overview=market_overview,
            policy_signals=policy_signals,
            chain_signals=chain_signals,
        )
        return report

    async def _generate_llm_report(
        self,
        snapshots: list[SectorSnapshot],
        date_str: str,
        market_overview: dict | None,
        news_context: str,
        policy_signals: list | None,
        chain_signals: list | None,
        settings,
    ) -> str | None:
        """Call LLM to generate deep analysis report."""
        prompt = self._build_llm_prompt(
            snapshots=snapshots,
            date_str=date_str,
            market_overview=market_overview,
            news_context=news_context,
            policy_signals=policy_signals,
            chain_signals=chain_signals,
        )
        content = await llm_chain_reasoning(
            prompt, settings, system_prompt=self.SYSTEM_PROMPT,
            test_mode=settings.sector_discovery_mock_mode,
        )
        if content and len(content) > 200:
            return content
        return None

    def _build_llm_prompt(
        self,
        snapshots: list[SectorSnapshot],
        date_str: str,
        market_overview: dict | None,
        news_context: str,
        policy_signals: list | None,
        chain_signals: list | None,
    ) -> str:
        """Construct structured prompt for LLM deep analysis."""
        parts = [f"# {date_str} A股今日方向分析任务", ""]

        # 1. Market overview
        parts.append(self._build_market_overview_text(market_overview))
        parts.append("")

        # 2. News context
        if news_context:
            parts.append("## 热点新闻、政策与公告上下文")
            parts.append(news_context[:4000])  # direction work relies more on news/policy context
            parts.append("")

        # 3. Policy signals
        if policy_signals:
            parts.append(self._build_policy_signals_text(policy_signals))
            parts.append("")

        # 4. Chain reasoning signals
        if chain_signals:
            parts.append(self._build_chain_signals_text(chain_signals))
            parts.append("")

        # 5. Scanner signals (direction evidence; stocks are internal evidence only)
        parts.append(self._build_signals_text(snapshots))
        parts.append("")

        # 6. Output format instructions
        parts.append(self._build_output_template(len(snapshots)))

        return "\n".join(parts)

    def _build_market_overview_text(self, market_overview: dict | None) -> str:
        """Format market overview data for prompt."""
        if not market_overview:
            return (
                "## 市场概况\n"
                "暂无大盘数据。报告中不得编造指数涨跌、成交额、涨跌停家数、北向资金或主力资金数据；"
                "相关字段必须写未获取。"
            )

        lines = ["## 市场概况"]

        # Indices
        indices = market_overview.get("indices", [])
        if indices:
            lines.append("### 主要指数")
            for idx in indices:
                direction = "↑" if idx.get("change_pct", 0) > 0 else "↓" if idx.get("change_pct", 0) < 0 else "-"
                lines.append(
                    f"- {idx.get('name', '')}: {idx.get('current', 0):.2f} "
                    f"({direction}{abs(idx.get('change_pct', 0)):.2f}%)"
                )

        # Statistics
        stats = market_overview.get("statistics", {})
        if stats:
            lines.append("### 涨跌统计")
            lines.append(
                f"- 上涨: {stats.get('up_count', 0)} | 下跌: {stats.get('down_count', 0)} | "
                f"平盘: {stats.get('flat_count', 0)}"
            )
            lines.append(
                f"- 涨停: {stats.get('limit_up_count', 0)} | 跌停: {stats.get('limit_down_count', 0)}"
            )
            lines.append(f"- 两市成交额: {stats.get('total_amount', 0):.0f} 亿元")

        # Northbound flow
        northbound = market_overview.get("northbound_flow", {})
        close = northbound.get("close", {}) if isinstance(northbound, dict) else {}
        if close:
            hgt = close.get("hgt")
            sgt = close.get("sgt")
            total = close.get("total")
            lines.append("### 北向资金")
            if total is not None:
                lines.append(f"- 沪深股通合计净流入: {float(total):.2f} 亿元")
            if hgt is not None or sgt is not None:
                hgt_text = f"{float(hgt):.2f}" if hgt is not None else "未获取"
                sgt_text = f"{float(sgt):.2f}" if sgt is not None else "未获取"
                lines.append(f"- 沪股通: {hgt_text} 亿元 | 深股通: {sgt_text} 亿元")

        # Sector rankings
        rankings = market_overview.get("sector_rankings", {})
        top = rankings.get("top", [])
        bottom = rankings.get("bottom", [])
        if top:
            lines.append("### 领涨板块")
            for s in top[:5]:
                lines.append(f"- {s.get('name', '')}: {s.get('change_pct', 0):+.2f}%")
        if bottom:
            lines.append("### 领跌板块")
            for s in bottom[:5]:
                lines.append(f"- {s.get('name', '')}: {s.get('change_pct', 0):+.2f}%")

        return "\n".join(lines)

    def _build_policy_signals_text(self, policy_signals: list) -> str:
        """Format policy signals for prompt."""
        lines = ["## 政策信号"]
        for sig in policy_signals[:10]:
            lines.append(
                f"- {getattr(sig, 'keyword', '')} ({getattr(sig, 'level', '')}级政策) | "
                f"受益: {', '.join(getattr(sig, 'beneficiary_industries', [])[:3])} | "
                f"时间窗口: {getattr(sig, 'time_window', '')}"
            )
        return "\n".join(lines)

    def _build_chain_signals_text(self, chain_signals: list) -> str:
        """Format chain reasoning signals for prompt."""
        lines = ["## 产业链预期差分析"]
        for sig in chain_signals[:10]:
            lines.append(
                f"- 概念: {getattr(sig, 'concept', '')} | 环节: {getattr(sig, 'segment_name', '')} "
                f"({getattr(sig, 'position', '')}) | 预期差分: {getattr(sig, 'expectation_gap_score', 0):.1f}/10"
            )
            reasoning = getattr(sig, 'reasoning', '')
            if reasoning:
                lines.append(f"  - 推理: {reasoning}")
        return "\n".join(lines)

    def _build_signals_text(self, snapshots: list[SectorSnapshot]) -> str:
        """Format scanner signals for prompt."""
        lines = ["## 扫描器方向证据汇总"]
        for snap in snapshots:
            category = snap.tags[0] if snap.tags else "未分类"
            lines.append(
                f"\n### 【{category}】{snap.name} — 方向强度 {snap.composite_score:.1f}/10"
            )
            if snap.expectation_gap_score >= 6:
                lines.append(f"- 预期差分: {snap.expectation_gap_score:.1f}/10")

            # Dimension scores
            dims = []
            if snap.market_heat_score > 0:
                dims.append(f"热点 {snap.market_heat_score:.1f}")
            if snap.policy_score > 0:
                dims.append(f"政策 {snap.policy_score:.1f}")
            if snap.fund_score > 0:
                dims.append(f"机构 {snap.fund_score:.1f}")
            if snap.value_score > 0:
                dims.append(f"价值 {snap.value_score:.1f}")
            if snap.chain_score > 0:
                dims.append(f"产业链 {snap.chain_score:.1f}")
            if dims:
                lines.append(f"- 维度评分: {' | '.join(dims)}")

            # Stock-level records are only evidence for deriving directions.
            for st in snap.top_stocks[:5]:
                lines.append(f"- 样本证据: {st.reason}")
                if st.catalyst:
                    lines.append(f"  - 催化: {st.catalyst}")
                meta = st.metadata or {}
                if meta.get("price_change") is not None:
                    lines.append(f"  - 当日涨幅: {meta['price_change']:.2f}%")

            # Raw metrics
            metrics = snap.raw_metrics or {}
            if metrics.get("data_date"):
                lines.append(f"- 市场热度数据日期: {metrics['data_date']}")
            if metrics.get("limit_up_count"):
                lines.append(f"- 涨停家数: {int(metrics['limit_up_count'])}")
            if metrics.get("order_flow_profile"):
                lines.append(f"- 板块资金净流入: {metrics['order_flow_profile']/1e8:.1f}亿")

        return "\n".join(lines)

    def _build_output_template(self, direction_count: int) -> str:
        """Return output format instructions for LLM."""
        count_text = f"{min(direction_count, 10)} 个" if direction_count else "0 个"
        return f"""## 输出格式要求

请按以下结构输出分析报告：

### 一、市场总览
（2-3句话概括已有市场数据。只允许使用上文"市场概况"里的数字；缺失的指数表现、涨跌结构、成交额、北向资金、主力资金必须写"未获取"。）

### 二、热点政策与新闻
（只提炼上文"热点新闻、政策与公告上下文"或"政策信号"中出现的信息。没有输入证据时写"暂无可验证的新催化"，不得编造新闻。）

### 三、资金与情绪
（只解读扫描器证据和市场概况中出现的资金/涨停数据。没有数据时写"未获取"，不得估算。）

### 四、产业链拆解方法
（说明如何从政策/新闻向上游材料设备、中游制造、下游应用、配套服务扩散。）

### 五、方向分析
必须只输出输入证据中的 {count_text}方向，最多 10 个，不要补充额外方向。格式如下：

#### 1. 方向名称
- **核心驱动**：来自哪类政策/新闻/财经信息/资金流向
- **产业链扩散**：上游、中游、下游或关联配套怎么挖
- **资金与情绪验证**：资金流、涨停结构、成交额或情绪信号
- **预期差**：市场当前怎么看，实际可能是什么
- **应该关注**：后续要盯的政策细则、数据、订单、价格、监管、海外事件或资金指标
- **风险点**：该方向何时失效

注意：
- 不要给出具体买卖点或仓位建议
- 不要推荐具体个股，不要输出股票代码或股票名单
- 每个方向必须有独立链路，不能泛泛而谈
- 预期差分析要具体，不能只说"有预期差"
- 所有具体数字必须来自上文输入；没有输入依据时写"未获取"
"""

    # ── Fallback template methods (kept for resilience) ────────────────────

    def _build_summary(
        self,
        snapshots: list[SectorSnapshot],
        market_overview: dict | None = None,
        policy_signals: list | None = None,
        chain_signals: list | None = None,
    ) -> str:
        """Generate template-based summary when LLM fails."""
        directions = self._fallback_directions(snapshots, policy_signals, chain_signals)
        if not directions:
            return "暂无有效方向信号。"

        lines: list[str] = []
        lines.append(f"共生成 {len(directions)} 个方向观察：")
        lines.append("")

        if market_overview:
            stats = market_overview.get("statistics", {}) or {}
            if stats:
                lines.append(
                    "市场温度: "
                    f"上涨 {stats.get('up_count', 0)} / 下跌 {stats.get('down_count', 0)}，"
                    f"涨停 {stats.get('limit_up_count', 0)}，成交额 {stats.get('total_amount', 0):.0f} 亿。"
                )
                lines.append("")

        for idx, direction in enumerate(directions, start=1):
            lines.append(f"### {idx}. {direction['name']}")
            lines.append(f"- 核心驱动: {direction['driver']}")
            lines.append(f"- 产业链扩散: {direction['chain']}")
            lines.append(f"- 资金与情绪验证: {direction['funds']}")
            lines.append(f"- 预期差: {direction['gap']}")
            lines.append(f"- 应该关注: {direction['watch']}")
            lines.append(f"- 风险点: {direction['risk']}")
            lines.append("")

        return "\n".join(lines)

    def _fallback_directions(
        self,
        snapshots: list[SectorSnapshot],
        policy_signals: list | None,
        chain_signals: list | None,
    ) -> list[dict[str, str]]:
        directions: list[dict[str, str]] = []

        for snap in snapshots:
            category = snap.tags[0] if snap.tags else "未分类"
            driver = self._infer_driver(snap, category)
            risk = self._infer_risk(snap, category)
            watch = self._infer_catalyst(snap, category) or "关注资金流向、成交额变化、政策落地和新闻催化是否延续"
            funds = self._infer_fund_context(snap)
            directions.append({
                "name": snap.name.replace(" 方向", ""),
                "driver": driver,
                "chain": self._infer_chain_context(snap, category),
                "funds": funds,
                "gap": self._infer_gap_context(snap),
                "watch": watch,
                "risk": risk,
            })

        for sig in policy_signals or []:
            industries = "、".join(getattr(sig, "beneficiary_industries", [])[:5]) or "相关受益产业"
            directions.append({
                "name": f"{getattr(sig, 'keyword', '政策')}政策受益链",
                "driver": f"{getattr(sig, 'level', '')}政策信号，来源: {getattr(sig, 'source', '')}",
                "chain": f"从政策关键词向 {industries} 扩散，优先拆上游供给、核心设备、中游制造和下游落地场景",
                "funds": "等待板块成交额、主力净流入、涨停扩散和北向资金验证",
                "gap": "若政策细则强于市场初始理解，预期差集中在尚未被短线资金充分定价的细分环节",
                "watch": "关注部委细则、地方配套、预算安排、招标节奏、行业订单和资金连续性",
                "risk": "政策落地慢、执行口径弱于预期或短线资金提前兑现",
            })

        for sig in chain_signals or []:
            directions.append({
                "name": f"{getattr(sig, 'segment_name', '产业链')}预期差",
                "driver": f"{getattr(sig, 'concept', '')} 产业链扩散",
                "chain": f"位置: {getattr(sig, 'position', '')}; 逻辑: {getattr(sig, 'reasoning', '')}",
                "funds": "关注相关概念板块成交额、主力资金和涨停扩散是否从龙头扩到细分环节",
                "gap": f"预期差评分 {getattr(sig, 'expectation_gap_score', 0):.1f}/10，重点验证认知差能否转为订单或价格信号",
                "watch": "关注下游需求、上游价格、产能利用率、供需缺口和细分板块资金轮动",
                "risk": "产业链传导弱、主题退潮或细分环节基本面兑现不足",
            })

        deduped: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in directions:
            name = item["name"]
            if name in seen:
                continue
            seen.add(name)
            deduped.append(item)
            if len(deduped) == 10:
                break
        return deduped

    def _infer_fund_context(self, snap: SectorSnapshot) -> str:
        metrics = snap.raw_metrics or {}
        parts = []
        if metrics.get("data_date"):
            parts.append(f"市场热度数据日期 {metrics['data_date']}")
        if metrics.get("order_flow_profile"):
            parts.append(f"资金净流入 {metrics['order_flow_profile']/1e8:.1f} 亿")
        if metrics.get("limit_up_count"):
            parts.append(f"涨停 {int(metrics['limit_up_count'])} 家")
        if metrics.get("news_heat"):
            parts.append(f"新闻热度 {metrics['news_heat']}")
        if parts:
            return "，".join(parts)
        return "关注主力净流入、成交额放大、涨停扩散和市场宽度是否同步改善"

    def _infer_chain_context(self, snap: SectorSnapshot, category: str) -> str:
        metrics = snap.raw_metrics or {}
        if metrics.get("position"):
            return f"优先关注 {metrics['position']} 环节，再向配套设备、材料和应用端扩散"
        if category == "政策前瞻":
            industries = metrics.get("beneficiary_industries", [])
            if industries:
                return f"政策受益产业: {'、'.join(industries[:5])}，沿上游资源/设备、中游制造、下游应用拆解"
        if category == "热点追逐":
            return "从热点概念向材料、设备、零部件、应用场景和服务配套扩散"
        return "沿上游供给、中游制造、下游需求、配套服务四层拆解"

    def _infer_gap_context(self, snap: SectorSnapshot) -> str:
        if snap.expectation_gap_score >= 7:
            return f"预期差 {snap.expectation_gap_score:.1f}/10，市场可能只交易表层热点，细分环节仍有认知修正空间"
        if snap.expectation_gap_score >= 4:
            return f"预期差 {snap.expectation_gap_score:.1f}/10，需要资金和新闻二次验证"
        return "预期差一般，更多作为情绪和资金线索跟踪"

    def _infer_driver(self, snap: SectorSnapshot, category: str) -> str:
        """Infer driver from snapshot data (fallback)."""
        metrics = snap.raw_metrics or {}

        if category == "热点追逐":
            limit_up = metrics.get("limit_up_count", 0)
            order_flow_profile = metrics.get("order_flow_profile", 0)
            parts = []
            if limit_up:
                parts.append(f"{int(limit_up)}股涨停")
            if order_flow_profile:
                parts.append(f"资金净流入{order_flow_profile/1e8:.1f}亿")
            if parts:
                return "，".join(parts) + "，市场热度高"
            return "资金连续流入，市场热度高"

        if category == "政策前瞻":
            policy_level = metrics.get("policy_level", "")
            industries = metrics.get("beneficiary_industries", [])
            parts = []
            if policy_level:
                parts.append(f"{policy_level}级政策出台")
            if industries:
                parts.append(f"受益产业: {', '.join(industries[:3])}")
            if parts:
                return "，".join(parts) + "，市场尚未充分认识"
            return "政策利好出台，市场尚未充分认识"

        if category == "机构错配":
            fund_count = metrics.get("fund_new_count", 0)
            if fund_count:
                return f"Q2新增{int(fund_count)}只基金持仓，但股价仍低位"
            return "机构资金布局，股价尚未反映"

        if category == "价值蓄势":
            pe = metrics.get("avg_pe", 0)
            growth = metrics.get("avg_revenue_growth", 0)
            parts = []
            if pe:
                parts.append(f"PE {pe:.1f}")
            if growth:
                parts.append(f"营收增速 {growth*100:.1f}%")
            if parts:
                return "，".join(parts) + "，基本面改善但市场忽视"
            return "基本面改善，市场关注度低，长期价值被低估"

        if category == "产业链预期差":
            position = metrics.get("position", "")
            segments = metrics.get("upstream_segments", [])
            parts = []
            if segments:
                parts.append(f"上游{'/'.join(segments[:2])}预期差最大")
            elif position:
                parts.append(f"产业链{position}位置")
            if parts:
                return "，".join(parts) + "，下游热但上游尚未启动"
            return "下游需求旺盛，上游供给受限，产业链传导存在时滞"

        return "多因素驱动"

    def _infer_risk(self, snap: SectorSnapshot, category: str) -> str:
        """Infer risk from snapshot data (fallback)."""
        metrics = snap.raw_metrics or {}

        if category == "热点追逐":
            return "短期涨幅过大，追高风险，情绪退潮后回调剧烈"

        if category == "政策前瞻":
            policy_level = metrics.get("policy_level", "")
            if policy_level == "地方":
                return "地方政策力度有限，落地不及预期风险高"
            return "政策落地不及预期，时间窗口不确定，市场认知转换慢"

        if category == "机构错配":
            return "机构调仓方向变化，市场发现滞后，短期波动大"

        if category == "价值蓄势":
            return "业绩兑现周期长，需耐心等待，市场风格可能不切换"

        if category == "产业链预期差":
            return "产业链传导受阻，订单不及预期，上游扩产超预期"

        return "市场系统性风险"

    def _infer_catalyst(self, snap: SectorSnapshot, category: str) -> str:
        """Infer catalyst timeline from snapshot data (fallback)."""
        metrics = snap.raw_metrics or {}

        if category == "热点追逐":
            return "1-5个交易日，关注资金流向持续性"

        if category == "政策前瞻":
            time_window = metrics.get("policy_time_window", "")
            if time_window == "immediate":
                return "即刻反应，关注部委细则出台"
            if time_window == "annual":
                return "1-3个月，关注政策细则出台和部委落地"
            return "1-3个月，关注政策细则出台和部委落地"

        if category == "机构错配":
            return "1-3个月，关注基金季报披露和机构调研"

        if category == "价值蓄势":
            return "3-6个月+，关注季报业绩兑现和估值修复"

        if category == "产业链预期差":
            return "1-3个月，关注下游订单传导和上游产能利用率"

        return ""

    def to_enhanced_markdown(self, report: DirectionReport) -> str:
        """Render an enhanced markdown report from actual data."""
        lines = [f"# {report.date} 今日方向", ""]

        for snap in report.sectors:
            category = snap.tags[0] if snap.tags else "未分类"
            driver = self._infer_driver(snap, category)
            risk = self._infer_risk(snap, category)
            catalyst = self._infer_catalyst(snap, category)

            gap_badge = f" 预期差 {snap.expectation_gap_score:.1f}/10" if snap.expectation_gap_score >= 7 else ""
            lines.append(f"## 【{category}】{snap.name} — 方向强度 {snap.composite_score:.1f}/10{gap_badge}")
            lines.append("")
            lines.append(f"**逻辑:** {driver}")
            lines.append(f"- **产业链:** {self._infer_chain_context(snap, category)}")
            lines.append(f"- **资金:** {self._infer_fund_context(snap)}")
            lines.append(f"- **关注:** {catalyst or '政策细则、资金流向、订单/价格数据和新闻催化延续性'}")
            lines.append(f"- **风险:** {risk}")
            lines.append("")

        if report.summary:
            lines.append("---")
            lines.append("")
            lines.append(report.summary)

        return "\n".join(lines)


