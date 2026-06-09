"""PolicyMiner — Phase 0 policy signal extraction and grading.

Scans news and announcements for policy signals, grades them by authority level,
and maps them to beneficiary industries. Outputs structured PolicySignal objects
that feed into PolicyScout for targeted stock discovery.

Input: Global news + regulatory announcements
Processing:
  1. Keyword matching against expanded policy keyword library
  2. Level grading: 国务院 > 部委 > 地方
  3. Beneficiary industry mapping via rule engine
  4. Time window estimation: immediate / 3-month / annual
Output: list[PolicySignal] with structured metadata.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class PolicySignal:
    """A structured policy signal extracted from news/announcements."""

    keyword: str
    level: str  # 国务院 / 部委 / 地方
    beneficiary_industries: list[str] = field(default_factory=list)
    time_window: str = ""  # immediate / 3-month / annual
    source: str = ""  # news title or announcement title
    source_type: str = ""  # news / announcement / cls_telegram
    confidence: float = 0.0  # 0-1 based on source authority + keyword match quality


# ── Expanded 2026 policy keyword library ───────────────────────────────

POLICY_KEYWORDS_2026: dict[str, str] = {
    # 宏观政策
    "降准": "货币政策",
    "降息": "货币政策",
    "LPR": "货币政策",
    "MLF": "货币政策",
    "逆回购": "货币政策",
    # 资本市场改革
    "国九条": "资本市场改革",
    "IPO": "资本市场改革",
    "减持": "资本市场改革",
    "增持": "资本市场改革",
    "分红": "资本市场改革",
    "回购": "资本市场改革",
    "退市": "资本市场改革",
    "注册制": "资本市场改革",
    "科创板": "资本市场改革",
    "北交所": "资本市场改革",
    "并购重组": "资本市场改革",
    "市值管理": "资本市场改革",
    # 新质生产力
    "新质生产力": "新质生产力",
    "战略性新兴产业": "新质生产力",
    "未来产业": "新质生产力",
    # 商业航天
    "商业航天": "商业航天",
    "卫星互联网": "商业航天",
    "低轨卫星": "商业航天",
    "航天强国": "商业航天",
    "火箭": "商业航天",
    # 低空经济
    "低空经济": "低空经济",
    "eVTOL": "低空经济",
    "无人机": "低空经济",
    "飞行器": "低空经济",
    "通航": "低空经济",
    # 固态电池
    "固态电池": "固态电池",
    "半固态电池": "固态电池",
    "硫化物电池": "固态电池",
    "氧化物电池": "固态电池",
    # AI / 算力
    "人工智能": "人工智能",
    "大模型": "人工智能",
    "AI": "人工智能",
    "算力": "算力",
    "智算中心": "算力",
    "AIDC": "算力",
    "数据中心": "算力",
    # 半导体
    "半导体": "半导体",
    "芯片": "半导体",
    "集成电路": "半导体",
    "光刻": "半导体",
    "先进封装": "半导体",
    "国产替代": "半导体",
    "设备国产化": "半导体",
    # 机器人
    "人形机器人": "人形机器人",
    "工业机器人": "机器人",
    "具身智能": "具身智能",
    "减速器": "机器人",
    "丝杠": "机器人",
    "灵巧手": "机器人",
    # 数据要素
    "数据要素": "数据要素",
    "数据资产": "数据要素",
    "数据交易": "数据要素",
    "数字中国": "数据要素",
    # 双碳 / 新能源
    "双碳": "双碳",
    "碳中和": "双碳",
    "碳达峰": "双碳",
    "光伏": "光伏",
    "储能": "储能",
    "氢能": "氢能",
    "海上风电": "海上风电",
    # 消费 / 内需
    "以旧换新": "以旧换新",
    "家电下乡": "家电下乡",
    "汽车下乡": "汽车下乡",
    "消费券": "消费券",
    "内需": "内需",
    "扩内需": "内需",
    "消费补贴": "消费补贴",
    # 医药 / 医疗
    "创新药": "创新药",
    "医保谈判": "医保谈判",
    "集采": "集采",
    "医疗器械": "医疗器械",
    "CXO": "CXO",
    # 国防
    "国防": "国防",
    "军工": "国防",
    "武器装备": "国防",
    # 十五五规划
    "十五五": "十五五规划",
    "五年规划": "十五五规划",
    # 区域发展
    "粤港澳大湾区": "区域发展",
    "长三角": "区域发展",
    "京津冀": "区域发展",
    "西部大开发": "区域发展",
    "海南自贸港": "区域发展",
    # 信创 / 安全
    "信创": "信创",
    "信息安全": "信创",
    "网络安全": "信创",
    "操作系统": "信创",
    "数据库": "信创",
    "中间件": "信创",
}

# ── Policy → beneficiary industry mapping ──────────────────────────────

POLICY_INDUSTRY_MAP: dict[str, list[str]] = {
    "货币政策": ["银行", "保险", "券商", "地产"],
    "资本市场改革": ["券商", "创投", "金融科技", "并购重组服务"],
    "新质生产力": ["人工智能", "机器人", "半导体", "商业航天", "低空经济", "量子计算"],
    "商业航天": ["航天锻件", "特种合金", "卫星载荷", "火箭制造", "卫星运营"],
    "低空经济": ["碳纤维", "电机", "电池", "飞控系统", "通航运营"],
    "固态电池": ["锂矿", "电解液", "隔膜", "正负极材料", "电芯"],
    "人工智能": ["算力", "大模型", "AI芯片", "应用场景"],
    "算力": ["服务器", "光模块", "HVDC", "液冷", "数据中心"],
    "半导体": ["设备", "材料", "设计", "封测", "EDA"],
    "人形机器人": ["减速器", "丝杠", "电机", "传感器", "灵巧手"],
    "具身智能": ["传感器", "算法", "执行器", "机器人整机"],
    "数据要素": ["数据服务", "云计算", "信息安全", "数据库"],
    "双碳": ["光伏", "储能", "氢能", "风电", "碳交易"],
    "光伏": ["硅料", "硅片", "电池片", "组件", "逆变器", "支架"],
    "储能": ["电池", "PCS", "BMS", "EMS", "温控"],
    "氢能": ["电解槽", "储氢", "燃料电池", "氢能车"],
    "海上风电": ["海缆", "风机", "基础", "安装"],
    "以旧换新": ["家电", "汽车", "消费电子"],
    "创新药": ["CXO", "创新药", "生物制药", "医疗器械"],
    "国防": ["军工电子", "航空", "航天", "船舶", "兵器"],
    "十五五规划": ["战略新兴产业", "基础设施", "高端制造", "数字经济"],
    "信创": ["操作系统", "数据库", "中间件", "办公软件", "CPU"],
}

# ── Level grading keywords ─────────────────────────────────────────────

LEVEL_KEYWORDS: dict[str, list[str]] = {
    "国务院": [
        "国务院",
        "国务院办公厅",
        "总理",
        "国务院常务会议",
        "政府工作报告",
    ],
    "部委": [
        "发改委",
        "证监会",
        "工信部",
        "科技部",
        "财政部",
        "商务部",
        "央行",
        "人民银行",
        "金融监管总局",
        "国资委",
        "能源局",
        "药监局",
        "卫健委",
    ],
    "地方": [
        "省政府",
        "市政府",
        "自治区",
        "自贸区",
        "开发区",
        "高新区",
    ],
}

# ── Time window estimation keywords ────────────────────────────────────

TIME_WINDOW_KEYWORDS: dict[str, str] = {
    " immediate": "immediate",
    "立即": "immediate",
    "马上": "immediate",
    "即日起": "immediate",
    "季度": "3-month",
    "Q1": "3-month",
    "Q2": "3-month",
    "Q3": "3-month",
    "Q4": "3-month",
    "半年": "3-month",
    "中期": "3-month",
    "年度": "annual",
    "全年": "annual",
    "长期": "annual",
    "五年": "annual",
    "规划": "annual",
}


class PolicyMiner:
    """Extract and grade policy signals from news and announcements."""

    def __init__(
        self,
        policy_keywords: Optional[dict[str, str]] = None,
        industry_map: Optional[dict[str, list[str]]] = None,
        level_keywords: Optional[dict[str, list[str]]] = None,
        time_keywords: Optional[dict[str, str]] = None,
    ):
        self.policy_keywords = policy_keywords or POLICY_KEYWORDS_2026
        self.industry_map = industry_map or POLICY_INDUSTRY_MAP
        self.level_keywords = level_keywords or LEVEL_KEYWORDS
        self.time_keywords = time_keywords or TIME_WINDOW_KEYWORDS

    def mine(
        self,
        news_items: list[dict],
        announcements: Optional[list[dict]] = None,
    ) -> list[PolicySignal]:
        """Extract policy signals from news and announcements.

        Args:
            news_items: List of news dicts with 'title' and optional 'content' keys.
            announcements: Optional list of announcement dicts with 'title' key.

        Returns:
            List of PolicySignal objects, deduplicated by keyword.
        """
        signals: list[PolicySignal] = []
        seen_keywords: set[str] = set()

        # Process news items
        for item in news_items:
            title = item.get("title", "")
            content = item.get("content", "")
            source_text = f"{title} {content}"
            source_type = item.get("source", "news")

            for keyword, policy_domain in self.policy_keywords.items():
                if keyword not in source_text:
                    continue

                # Deduplicate: one signal per policy domain per source
                dedup_key = f"{policy_domain}:{source_type}"
                if dedup_key in seen_keywords:
                    continue
                seen_keywords.add(dedup_key)

                level = self._grade_level(source_text)
                industries = self._map_industries(policy_domain)
                time_window = self._estimate_time_window(source_text)
                confidence = self._calculate_confidence(level, source_type, title)

                signals.append(
                    PolicySignal(
                        keyword=policy_domain,
                        level=level,
                        beneficiary_industries=industries,
                        time_window=time_window,
                        source=title[:100],
                        source_type=source_type,
                        confidence=round(confidence, 2),
                    )
                )

        # Process announcements (higher authority)
        if announcements:
            for ann in announcements:
                title = ann.get("title", "")
                for keyword, policy_domain in self.policy_keywords.items():
                    if keyword not in title:
                        continue

                    dedup_key = f"{policy_domain}:announcement"
                    if dedup_key in seen_keywords:
                        # Upgrade confidence if announcement confirms news
                        for s in signals:
                            if s.keyword == policy_domain:
                                s.confidence = min(1.0, s.confidence + 0.2)
                                s.level = self._upgrade_level(s.level, "部委")
                        continue
                    seen_keywords.add(dedup_key)

                    level = self._grade_level(title)
                    # Announcements from 巨潮 are typically 部委 level or higher
                    if level == "地方":
                        level = "部委"

                    industries = self._map_industries(policy_domain)
                    time_window = self._estimate_time_window(title)

                    signals.append(
                        PolicySignal(
                            keyword=policy_domain,
                            level=level,
                            beneficiary_industries=industries,
                            time_window=time_window,
                            source=title[:100],
                            source_type="announcement",
                            confidence=0.85,
                        )
                    )

        # Sort by confidence descending
        signals.sort(key=lambda s: s.confidence, reverse=True)
        return signals

    def _grade_level(self, text: str) -> str:
        """Grade policy authority level from text."""
        for level, keywords in self.level_keywords.items():
            for kw in keywords:
                if kw in text:
                    return level
        return "地方"  # Default to lowest level

    def _upgrade_level(self, current: str, minimum: str) -> str:
        """Upgrade level to at least the minimum."""
        levels = ["地方", "部委", "国务院"]
        current_idx = levels.index(current)
        minimum_idx = levels.index(minimum)
        return levels[max(current_idx, minimum_idx)]

    def _map_industries(self, policy_domain: str) -> list[str]:
        """Map policy domain to beneficiary industries."""
        return self.industry_map.get(policy_domain, [])

    def _estimate_time_window(self, text: str) -> str:
        """Estimate policy impact time window from text."""
        for keyword, window in self.time_keywords.items():
            if keyword in text:
                return window
        return "3-month"  # Default

    def _calculate_confidence(
        self, level: str, source_type: str, title: str
    ) -> float:
        """Calculate confidence score based on source authority and clarity."""
        base = 0.5

        # Level bonus
        level_bonus = {"地方": 0.0, "部委": 0.15, "国务院": 0.3}
        base += level_bonus.get(level, 0.0)

        # Source type bonus
        source_bonus = {"news": 0.0, "cls_telegram": 0.05, "announcement": 0.2}
        base += source_bonus.get(source_type, 0.0)

        # Title clarity bonus (policy keywords in title = higher confidence)
        title_hits = sum(
            1 for kw in self.policy_keywords if kw in title
        )
        base += min(0.1, title_hits * 0.02)

        return min(1.0, base)

    def get_top_signals(
        self,
        news_items: list[dict],
        announcements: Optional[list[dict]] = None,
        min_confidence: float = 0.6,
        limit: int = 10,
    ) -> list[PolicySignal]:
        """Get top policy signals above confidence threshold."""
        signals = self.mine(news_items, announcements)
        filtered = [s for s in signals if s.confidence >= min_confidence]
        return filtered[:limit]
