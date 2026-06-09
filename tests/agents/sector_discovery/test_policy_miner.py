"""Tests for PolicyMiner policy signal extraction."""

import pytest

from src.agents.sector_discovery.policy_miner import (
    LEVEL_KEYWORDS,
    POLICY_INDUSTRY_MAP,
    POLICY_KEYWORDS_2026,
    TIME_WINDOW_KEYWORDS,
    PolicyMiner,
    PolicySignal,
)


class TestPolicySignal:
    def test_policy_signal_defaults(self):
        signal = PolicySignal(keyword="固态电池", level="部委")
        assert signal.keyword == "固态电池"
        assert signal.level == "部委"
        assert signal.beneficiary_industries == []
        assert signal.time_window == ""
        assert signal.confidence == 0.0


class TestPolicyMinerMine:
    def test_extract_single_policy_from_news(self):
        miner = PolicyMiner()
        news = [{"title": "国务院发布固态电池产业发展指导意见", "source": "news"}]
        signals = miner.mine(news)

        assert len(signals) >= 1
        keywords = [s.keyword for s in signals]
        assert "固态电池" in keywords

    def test_grade_state_council_level(self):
        miner = PolicyMiner()
        news = [{"title": "国务院常务会议审议通过商业航天发展规划", "source": "news"}]
        signals = miner.mine(news)

        assert len(signals) >= 1
        state_council_signals = [s for s in signals if s.level == "国务院"]
        assert len(state_council_signals) >= 1

    def test_grade_ministry_level(self):
        miner = PolicyMiner()
        news = [{"title": "工信部发布算力基础设施建设计划", "source": "news"}]
        signals = miner.mine(news)

        ministry_signals = [s for s in signals if s.level == "部委"]
        assert len(ministry_signals) >= 1

    def test_map_industries(self):
        miner = PolicyMiner()
        industries = miner._map_industries("商业航天")
        assert "航天锻件" in industries
        assert "特种合金" in industries

    def test_estimate_time_window(self):
        miner = PolicyMiner()
        assert miner._estimate_time_window("Q2季度启动") == "3-month"
        assert miner._estimate_time_window("年度规划") == "annual"
        assert miner._estimate_time_window("立即实施") == "immediate"
        assert miner._estimate_time_window("普通文本") == "3-month"  # default

    def test_deduplication_by_domain(self):
        miner = PolicyMiner()
        news = [
            {"title": "固态电池技术突破", "source": "news"},
            {"title": "固态电池产业链调研", "source": "news"},
        ]
        signals = miner.mine(news)
        # Should deduplicate: only one signal for "固态电池" domain
        solid_state_signals = [s for s in signals if s.keyword == "固态电池"]
        assert len(solid_state_signals) == 1

    def test_announcement_boosts_confidence(self):
        miner = PolicyMiner()
        news = [{"title": "低空经济政策预期升温", "source": "news"}]
        announcements = [{"title": "民航局发布低空经济发展指导意见"}]
        signals = miner.mine(news, announcements)

        low_altitude = [s for s in signals if s.keyword == "低空经济"]
        assert len(low_altitude) >= 1
        # Announcement should have higher confidence
        ann_signals = [s for s in low_altitude if s.source_type == "announcement"]
        if ann_signals:
            assert ann_signals[0].confidence >= 0.8

    def test_multiple_policies_in_one_title(self):
        miner = PolicyMiner()
        news = [{"title": "十五五规划强调人工智能与算力协同发展", "source": "news"}]
        signals = miner.mine(news)

        keywords = [s.keyword for s in signals]
        assert "十五五规划" in keywords or "人工智能" in keywords or "算力" in keywords

    def test_get_top_signals_with_threshold(self):
        miner = PolicyMiner()
        news = [
            {"title": "国务院发布重磅政策", "source": "news"},
            {"title": "地方出台配套措施", "source": "news"},
        ]
        top_signals = miner.get_top_signals(news, min_confidence=0.7, limit=5)
        # Should filter out low-confidence signals
        assert all(s.confidence >= 0.7 for s in top_signals)
        assert len(top_signals) <= 5

    def test_empty_input(self):
        miner = PolicyMiner()
        signals = miner.mine([])
        assert signals == []

    def test_no_policy_keywords(self):
        miner = PolicyMiner()
        news = [{"title": "某公司股票今日大涨", "source": "news"}]
        signals = miner.mine(news)
        assert signals == []


class TestPolicyKeywordLibrary:
    def test_2026_keywords_coverage(self):
        """Verify key 2026 policy terms are present."""
        key_terms = [
            "十五五",
            "新质生产力",
            "商业航天",
            "低空经济",
            "固态电池",
            "人形机器人",
            "数据要素",
            "信创",
        ]
        for term in key_terms:
            assert term in POLICY_KEYWORDS_2026, f"Missing keyword: {term}"

    def test_industry_map_coverage(self):
        """Verify key policy domains have industry mappings."""
        key_domains = [
            "商业航天",
            "低空经济",
            "固态电池",
            "人工智能",
            "半导体",
            "人形机器人",
        ]
        for domain in key_domains:
            assert domain in POLICY_INDUSTRY_MAP, f"Missing industry map for: {domain}"
            assert len(POLICY_INDUSTRY_MAP[domain]) > 0


class TestConfidenceCalculation:
    def test_state_council_higher_confidence(self):
        miner = PolicyMiner()
        state_council = miner._calculate_confidence("国务院", "news", "国务院发布政策")
        ministry = miner._calculate_confidence("部委", "news", "部委发布政策")
        assert state_council > ministry

    def test_announcement_higher_than_news(self):
        miner = PolicyMiner()
        announcement = miner._calculate_confidence("部委", "announcement", "公告")
        news = miner._calculate_confidence("部委", "news", "新闻")
        assert announcement > news

    def test_confidence_capped_at_1(self):
        miner = PolicyMiner()
        confidence = miner._calculate_confidence("国务院", "announcement", "国务院")
        assert confidence <= 1.0
