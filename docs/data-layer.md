# 数据层说明

数据层负责把外部行情和资料整理成本地系统可用的数据。

## 数据源

项目的数据源适配器在：

```text
src/data/sources/
```

当前包含 Eastmoney、Sina、Tencent、THS、CNInfo、CLS、Baostock、Baidu、yfinance 等来源或工具模块。

不同数据类型有不同优先级，例如报价、K 线、基本面、新闻、公告、研报、概念板块、行业板块、资金流等。优先级配置在 `src/config.py` 的 `data_source_priority`。

## 本地数据库

默认数据库路径：

```text
data/db/cache.db
data/db/historical.db
data/db/portfolio.db
data/db/analysis.db
data/db/fund_holdings.db
data/db/checkpoints/
data/cache/
data/artifacts/analysis/
data/knowledge/
```

这些数据库都是运行数据，不提交 GitHub。

## 缓存策略

缓存 TTL 在 `.env` 或 `src/config.py` 中配置。不同数据使用不同缓存时间：

- 行情报价较短；
- K 线和指标中等；
- 新闻、公告按天；
- 基本面、研报更长。

目标不是追求每次请求都实时，而是在个人研究场景下平衡可用性、速度和外部数据源压力。

## 历史数据

`local_history_enabled` 默认开启，用于把常用历史数据落到本地。这样 Agent 分析和前端图表可以优先复用本地数据，减少重复请求。

## 测试

数据层测试覆盖：

- source adapter；
- collector fallback；
- cache；
- historical store；
- fund holdings；
- 部分真实数据源回归。

公开仓库中的测试不应依赖用户自己的本地数据库。
