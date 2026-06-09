# Obsidian Conventions

## Vault Root

推荐将 `knowledge/` 作为 Obsidian vault root。

```text
knowledge/
  raw/          # 可选浏览
  wiki/         # 主要阅读区
  schema/       # 维护规约
  derived/      # 机器派生（可隐藏）
```

## 人类可读目录

- `wiki/` — 结构化 Markdown 页面，支持 wikilink。
- `raw/` — 原始材料，可按来源浏览。
- `schema/` — 维护规约文档。

## 机器派生目录

- `derived/` — 索引、chunk、实体注册表。人类通常不直接编辑。

在 Obsidian 中可通过 `.obsidian/app.json` 或文件夹设置隐藏 `derived/`。

## Link Style

使用 Obsidian wikilink：

```markdown
[[slug|显示文本]]
```

例如：

```markdown
- [[stocks/603738|603738 泰晶科技]]
- [[topics/ai|AI 算力]]
```

## Frontmatter 字段约定

Wiki 页面统一使用 YAML frontmatter：

```yaml
---
page_id: stock:603738
page_type: stock_profile
title: 603738 泰晶科技
slug: stocks/603738
symbol: "603738"
tags: ["stock/603738"]
status: active
review_status: generated
revision: 1
created_at: "2026-06-05T10:00:00+08:00"
updated_at: "2026-06-05T10:00:00+08:00"
---
```

Raw source 统一使用 YAML frontmatter：

```yaml
---
source_id: manual_source:abc123
source_kind: manual_source
origin: user
title: "..."
content_sha256: "..."
captured_at: "2026-06-05T10:00:00+08:00"
tags: []
---
```

## Assets 约定

- 图片、PDF 等附件放入 `data/knowledge/wiki/assets/`。
- Raw 附件放入 `data/knowledge/raw/assets/`。

## Dataview-ready 字段

以下字段可直接用于 Obsidian Dataview 查询：

- `page_type` — 过滤页面类型。
- `symbol` — 按股票过滤。
- `topic` — 按主题过滤。
- `trade_date` — 按日期过滤。
- `tags` — 按标签过滤。
- `status` — 按状态过滤。
- `review_status` — 按审阅状态过滤。

示例 Dataview 查询：

```dataview
TABLE title, updated_at
FROM "wiki/pages/stocks"
WHERE page_type = "stock_profile"
SORT updated_at DESC
```

## 日常操作清单

```text
1. ingest raw         →  python -m src.knowledge.wiki_build --apply --limit 10
2. rebuild wiki index  →  自动在 ingest 后执行
3. run wiki lint       →  python -m src.knowledge.wiki_lint
4. rebuild derived     →  python -m src.knowledge.derived_build --rebuild
5. run derived check   →  python -m src.knowledge.derived_lint
```

## 目录结构速查

```text
knowledge/
  raw/
    index.db
    sources/
    assets/
  schema/
    wiki-maintainer.md
    derived-index-schema.md
    obsidian-conventions.md
    raw-source-types.md
  wiki/
    index.db
    index.md
    log.md
    pages/
      stocks/
      topics/
      sources/
      daily/
      portfolio/
      claims/
      queries/
    assets/
  derived/
    index.db
    manifest.json
    chunks/
    summaries/
    reports/
```
