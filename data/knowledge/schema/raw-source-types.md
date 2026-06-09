# Raw Source Types

## Source Kind 列表

| source_kind | 说明 | 典型来源 |
|-------------|------|----------|
| `manual_source` | 用户手工材料 | user |
| `daily_trade_log` | 每日交易记录 | trading_system |
| `daily_direction` | 每日方向分析 | analysis |
| `stock_analysis` | 个股分析 run | analysis |
| `news_article` | 新闻 | news_api |
| `announcement` | 公告 | exchange |
| `research_report` | 研报 | broker |

---

## manual_source

用户手工输入的材料。

### 必填 metadata

- `title`
- `origin`: `user`

### 可选 metadata

- `tags`
- `symbol` / `symbols`
- `trade_date`

### Wiki 映射

- 生成 `source_digest` 页面。
- 根据内容更新相关 `stock_profile` 或 `topic`。

### Derived 映射

- doc_type: `raw_source`
- entity: 从 `symbol/symbols` 提取股票；从 `tags` 提取主题。

---

## daily_trade_log

每日交易记录（买入、卖出、持仓变化）。

### 必填 metadata

- `trade_date`
- `origin`: `trading_system`

### 可选 metadata

- `symbol`
- `tags`: `["trade_log"]`

### Wiki 映射

- 生成 `source_digest`。
- 更新 `trade_month` 页面。
- 更新 `portfolio_overview`。
- 更新相关 `stock_timeline`。

### Derived 映射

- doc_type: `raw_source`
- entity: 日期、股票代码、source_kind。

---

## daily_direction

每日市场/组合方向分析。

### 必填 metadata

- `trade_date`
- `origin`: `analysis`
- `run_id`

### 可选 metadata

- `symbols`
- `tags`

### Wiki 映射

- 生成 `source_digest`。
- 更新 `daily_direction` 页面。
- 更新相关 `stock_timeline`。

### Derived 映射

- doc_type: `raw_source`
- entity: 日期、股票代码、source_kind。

---

## stock_analysis

个股分析 run 的完整或中间输出。

### 必填 metadata

- `symbol`
- `trade_date`
- `origin`: `analysis`
- `run_id`
- `analysis_node`

### 可选 metadata

- `tags`

### Wiki 映射

- 按 `run_id` 分组生成 `analysis_run_digest`。
- 更新 `stock_profile`、`stock_timeline`、`stock_analysis_runs`。

### Derived 映射

- doc_type: `raw_source`
- entity: 股票代码、日期、analysis_node、source_kind。

---

## news_article

新闻文章。

### 必填 metadata

- `title`
- `origin`: `news_api`
- `published_at`

### 可选 metadata

- `symbol`
- `source_ref` / `canonical_uri`
- `provider`
- `tags`

### Wiki 映射

- 生成 `source_digest`。
- 更新相关 `stock_timeline` 和 `stock_profile`（recent_updates）。

### Derived 映射

- doc_type: `raw_source`
- entity: 股票代码、日期、source_kind、provider。

---

## announcement

交易所公告。

### 必填 metadata

- `title`
- `origin`: `exchange`
- `published_at`
- `symbol`

### 可选 metadata

- `source_ref` / `canonical_uri`
- `tags`

### Wiki 映射

- 生成 `source_digest`（高优先级事实源）。
- 更新 `stock_profile` facts/risks/catalysts。

### Derived 映射

- doc_type: `raw_source`
- entity: 股票代码、日期、source_kind。

---

## research_report

券商研报。

### 必填 metadata

- `title`
- `origin`: `broker`
- `published_at`
- `symbol`

### 可选 metadata

- `provider`（券商名称）
- `source_ref`
- `tags`

### Wiki 映射

- 生成 `source_digest`。
- 记录 institution/analyst/rating/target_price。
- 更新 `stock_profile` 外部观点。

### Derived 映射

- doc_type: `raw_source`
- entity: 股票代码、日期、source_kind、provider。

---

## Derived 通用映射规则

所有 raw source 进入 derived 时：

- `doc_type = "raw_source"`
- `doc_id = "raw:{source_id}"`
- `source_id = source_id`
- `title = title`
- `path = content_path`
- `content_sha256 = content_sha256`
- metadata 来自 raw record（`metadata_json`）。
