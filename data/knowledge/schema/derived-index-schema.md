# Derived Index Schema

## 什么是 Derived

Derived 是从 `data/knowledge/raw/` 和 `data/knowledge/wiki/` 派生出来的**机器索引层**。

- 人类通常不直接阅读或编辑 derived artifacts。
- Derived 必须可丢弃、可重建。删除 `data/knowledge/derived/` 后，应能从 raw/wiki 重新生成。
- Derived 中不得保存不可替代的用户内容。

## Derived 不是什么

- 不是 source of truth。
- 不是搜索工具本身（本阶段不实现 Search CLI/API）。
- 不替代 wiki。
- 不侵入 TradingAgents 流程。
- 不使用 embedding 或向量检索（本阶段）。

## 输入来源

- `data/knowledge/raw/index.db` 和 `data/knowledge/raw/**`
- `data/knowledge/wiki/index.db` 和 `data/knowledge/wiki/**`

## 输出位置

```text
data/knowledge/derived/
  index.db
  manifest.json
  chunks/
    wiki/
    raw/
  summaries/
  reports/
```

## 可重建要求

Derived artifacts 的生成必须是确定性的：

1. 相同的 raw + wiki 输入应产生相同的 derived 输出。
2. 重建时应先清空 derived，再重新构建。
3. 构建过程必须记录审计日志（`derived_build_runs`）。

## 表结构

### derived_documents

每个进入 derived 的 raw source 或 wiki page 一行。

| 字段 | 类型 | 说明 |
|------|------|------|
| doc_id | TEXT PK | 如 `raw:manual_source:abc` 或 `wiki:stock:603738` |
| doc_type | TEXT | `raw_source` 或 `wiki_page` |
| source_id | TEXT | raw source_id（仅 raw_source） |
| page_id | TEXT | wiki page_id（仅 wiki_page） |
| title | TEXT | 文档标题 |
| path | TEXT | 文件相对路径 |
| content_sha256 | TEXT | 正文 SHA256 |
| metadata_json | TEXT | 附加元数据 JSON |
| created_at | TEXT | ISO 时间 |
| updated_at | TEXT | ISO 时间 |

### derived_chunks

每个从文档派生出的 chunk 一行。

| 字段 | 类型 | 说明 |
|------|------|------|
| chunk_id | TEXT PK | 全局唯一 |
| doc_id | TEXT | 所属文档 |
| doc_type | TEXT | `raw_source` 或 `wiki_page` |
| ordinal | INTEGER | 在文档中的顺序 |
| heading_path | TEXT | 层级标题路径 |
| text | TEXT | chunk 正文 |
| text_sha256 | TEXT | chunk 文本 SHA256 |
| token_estimate | INTEGER | 预估 token 数 |
| metadata_json | TEXT | 附加元数据 |
| created_at | TEXT | ISO 时间 |

### derived_entities

规范实体注册表。

| 字段 | 类型 | 说明 |
|------|------|------|
| entity_id | TEXT PK | 全局唯一 |
| entity_type | TEXT | `stock`, `topic`, `source_kind`, `claim_type`, `date`, `unknown` |
| name | TEXT | 显示名称 |
| canonical_key | TEXT | 规范键（如股票代码） |
| metadata_json | TEXT | 附加元数据 |
| created_at | TEXT | ISO 时间 |
| updated_at | TEXT | ISO 时间 |

### derived_entity_mentions

实体在文档/chunk 中的出现。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK AUTOINCREMENT | |
| entity_id | TEXT | 关联实体 |
| doc_id | TEXT | 所在文档 |
| chunk_id | TEXT | 所在 chunk（可选） |
| mention_text | TEXT | 匹配到的文本 |
| mention_type | TEXT | 匹配类型 |
| metadata_json | TEXT | |
| created_at | TEXT | ISO 时间 |

### derived_claim_refs

Wiki claims 与文档的引用关系。

| 字段 | 类型 | 说明 |
|------|------|------|
| claim_id | TEXT | claim ID |
| doc_id | TEXT | 文档 ID |
| chunk_id | TEXT | chunk ID（可选） |
| source_id | TEXT | raw source ID |
| page_id | TEXT | wiki page ID |
| claim_type | TEXT | claim 类型 |
| status | TEXT | 状态 |
| metadata_json | TEXT | |
| created_at | TEXT | ISO 时间 |

### derived_links

规范化链接图。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK AUTOINCREMENT | |
| from_type | TEXT | 源类型 |
| from_id | TEXT | 源 ID |
| to_type | TEXT | 目标类型 |
| to_id | TEXT | 目标 ID |
| link_type | TEXT | 链接类型 |
| metadata_json | TEXT | |
| created_at | TEXT | ISO 时间 |

### derived_build_runs

构建审计日志。

| 字段 | 类型 | 说明 |
|------|------|------|
| run_id | TEXT PK | UUID |
| mode | TEXT | `dry_run`, `apply` |
| status | TEXT | `completed`, `failed` |
| documents_seen | INTEGER | |
| documents_indexed | INTEGER | |
| chunks_indexed | INTEGER | |
| entities_indexed | INTEGER | |
| error | TEXT | 错误信息 |
| started_at | TEXT | ISO 时间 |
| completed_at | TEXT | ISO 时间 |

## Chunking 规则

- 优先按 heading 分割 Markdown。
- 保留 heading path（如 `# 股票 > ## 风险`）。
- 目标 chunk 长度：800-1500 个中文字符或等效文本长度。
- 不把 frontmatter 切进正文 chunk。
- 每个 chunk 保留 source/page metadata。
- 很短的页面允许只有一个 chunk。
- 不使用 LLM 做 chunking。

## Entity Extraction 规则

确定性抽取，不使用 LLM：

- **股票代码**：`symbol`, `symbols` metadata 字段；正文中 6 位数字模式（`\d{6}`）。
- **source kinds**：raw source metadata 中的 `source_kind`；wiki source digest 中的 `source_kind`。
- **日期**：`trade_date` metadata；ISO date 模式（`\d{4}-\d{2}-\d{2}`）。
- **topics**：`page_type=topic` 的 wiki pages；`topic/...` tags。
- **claim types**：wiki claims 表中的 `claim_type` 值。

## Link Extraction 规则

Derived links 包含：

- wiki page -> wiki page wikilinks（来自 `wiki_page_links`）。
- wiki page -> raw source source_ids（来自 `wiki_page_sources`）。
- wiki claim -> raw source source_ids（来自 `wiki_claims.source_ids`）。
- entity -> document mentions（来自 `derived_entity_mentions`）。
- raw source -> supersedes source（来自 `raw_sources.supersedes_source_id`）。

## Lint / Check 规则

- derived DB 必须存在。
- manifest 必须存在。
- 每个 raw source 都有 derived document。
- 每个 wiki page 都有 derived document。
- 每个非空 derived document 至少有一个 chunk。
- document hash 与 raw/wiki hash 一致。
- chunk doc_id 指向存在的 document。
- entity mentions 指向存在的 document/chunk。
- claim refs 指向存在的 claims/documents。
- 最近一次 derived build run status 为 `completed`。

## 禁止事项

- 不要在 derived 中保存不可替代的用户内容。
- 不要把 derived 内容反写回 raw 或 wiki。
- 不要把旧 two-hex chunk 系统混淆进 derived。
- 本阶段不在 derived 中存储 embedding。
