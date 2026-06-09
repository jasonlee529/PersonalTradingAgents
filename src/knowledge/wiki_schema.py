from pathlib import Path

from src.config import Settings


DEFAULT_WIKI_SCHEMA = """# Wiki Maintainer Schema

## 分层

- raw: 不可变源材料，由 RawStore 管理。wiki 只读取，不修改。
- wiki: LLM 维护的结构化 markdown 页面。wiki 页面不是 source of truth，而是基于 raw 的当前综合理解。
- derived: chunk、embedding、entity、tree summary，后续实现。

## 页面类型

- home: index.md，内容索引。
- log: log.md，时间日志。
- source_digest: 单个 raw source 摘要页。
- analysis_run_digest: 个股分析 run 摘要页。
- stock_profile: 股票实体页。
- stock_timeline: 股票时间线页。
- stock_analysis_runs: 股票分析 run 列表页。
- topic: 主题页。
- daily_direction: 今日方向页。
- trade_month: 每日操作月度页。
- portfolio_overview: 组合总览页。
- trade_review: 交易复盘页。
- contradictions: 观点冲突页。
- open_questions: 待验证问题页。
- saved_query: 保存的问答页。

## Source Kind 处理规则

- daily_direction: 生成 source_digest，更新 daily_direction 页面，更新相关 stock timeline。
- stock_analysis: 建议通过 analysis-run 入口按 run_id 分组处理。
- news_article: 生成 source_digest，更新 stock timeline 和 stock profile recent_updates。
- announcement: 高优先级事实源，更新 stock profile facts/risks/catalysts。
- research_report: 外部观点，记录 institution/analyst/rating/target_price。
- manual_source: 根据 manual_subtype 处理，用户材料不自动视为事实。
- daily_trade_log: 更新 trade_month、portfolio_overview、stock timeline、trade_review。

## Claim 规则

- 每条事实 claim 必须引用至少一个 raw source_id。
- claim_type: fact, decision, thesis, risk, catalyst, contradiction, question。
- claim status: active, superseded, contradicted, resolved, rejected。
- 没有 source_id 的 claim 不允许写入 wiki。

## 引用规则

- wiki 内部链接: [[slug|显示文本]]。
- raw source 引用: 代码格式 `source_id` 或 source_digest 页面链接。
- 公告优先级高于新闻和 AI 分析。
- 研报是外部观点，需标注机构和发布时间。
- 用户实际交易记录是事实，不等同于正确决策。
- AI 分析是观点，不等同于事实。

## Update Plan JSON 结构

```json
{
  "source_ids": ["..."],
  "title": "...",
  "summary": "...",
  "pages_to_create": [{"page_id": "...", "page_type": "...", "title": "...", "slug": "...", "markdown": "...", "metadata": {}}],
  "page_patches": [{"page_id": "...", "section_id": "...", "markdown": "...", "mode": "replace"}],
  "claims": [{"claim_id": "...", "subject_type": "...", "subject_id": "...", "claim_type": "...", "statement": "...", "source_ids": ["..."]}],
  "contradictions": [],
  "log_entry": "...",
  "warnings": []
}
```

## 禁止事项

- 不要编造未提供的事实、数据、来源、公司名、公告内容或研报观点。
- 不要复制大段 raw 正文，只写摘要和引用。
- 如果证据不足，写入 open_questions，不要写成结论。
- 不允许输出 raw 文件系统绝对路径。
- 不自动联网补充资料。
- 不修改 raw。
"""


class WikiSchema:
    def __init__(self, settings: Settings):
        self.schema_dir = settings.wiki_schema_dir
        self.schema_path = self.schema_dir / "wiki-maintainer.md"

    async def ensure_schema(self) -> Path:
        self.schema_dir.mkdir(parents=True, exist_ok=True)
        if not self.schema_path.exists():
            await __import__("asyncio").to_thread(
                self.schema_path.write_text,
                DEFAULT_WIKI_SCHEMA,
                encoding="utf-8",
                newline="\n",
            )
        return self.schema_path

    async def read_schema(self) -> str:
        await self.ensure_schema()
        return await __import__("asyncio").to_thread(
            self.schema_path.read_text,
            encoding="utf-8",
        )
