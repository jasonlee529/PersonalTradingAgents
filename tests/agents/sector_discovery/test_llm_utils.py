"""Tests for sector-discovery LLM parsing helpers."""

from src.agents.sector_discovery.llm_utils import _ChainAnalysisLLM


def test_chain_analysis_accepts_string_key_players():
    result = _ChainAnalysisLLM.model_validate(
        {
            "direction_name": "AI算力",
            "segments": [
                {
                    "segment_name": "先进封装",
                    "position": "midstream",
                    "expectation_gap": 8.5,
                    "key_players": "600584 长电科技, 002156 通富微电、688072 拓荆科技",
                }
            ],
            "top_segment": "先进封装",
            "diffusion_path": "芯片制造 -> 先进封装",
            "supporting_segments": [],
        }
    )

    assert result.segments[0].key_players == [
        "600584 长电科技",
        "002156 通富微电",
        "688072 拓荆科技",
    ]
