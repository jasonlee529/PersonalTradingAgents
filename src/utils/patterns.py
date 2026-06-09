"""Shared regex patterns and keyword mappings for text extraction."""
import re

# A-share stock code pattern: 600/601/603/000/001/002/300/301 + 3 digits = 6 digits total
# Use negative lookbehind/ahead for digits instead of \b (word boundary fails in CJK text)
STOCK_PATTERN = re.compile(r"(?<!\d)(600|601|603|000|001|002|300|301)\d{3}(?!\d)")

# Concept keywords -> canonical concept name
CONCEPT_KEYWORDS: dict[str, str] = {
    "AI算力": "AI算力",
    "算力": "算力",
    "人形机器人": "人形机器人",
    "低空经济": "低空经济",
    "固态电池": "固态电池",
    "无人驾驶": "无人驾驶",
    "自动驾驶": "无人驾驶",
    "数据要素": "数据要素",
    "信创": "信创",
    "中特估": "中特估",
    "国企改革": "国企改革",
}
