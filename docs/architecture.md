# 架构说明

PersonalTradingAgents 的核心结构是：后端负责数据、分析、知识库和任务调度，前端负责把这些能力组织成一个本地工作台。

## 总体链路

```text
数据源
  -> src/data 多源采集与缓存
  -> src/agents 分析与辩论
  -> src/portfolio 持仓和交易记录
  -> src/knowledge 本地知识沉淀
  -> src/api FastAPI 对外提供接口
  -> web React 页面展示与操作
```

## 后端模块

`src/api/`

FastAPI 应用入口和路由。当前主要接口包括：

- `stocks`：个股数据和详情；
- `analysis`：分析任务和分析结果；
- `portfolio`：组合、持仓、交易记录；
- `raw`：原始材料；
- `wiki`：本地 Wiki；
- `settings`：运行配置；
- `sectors`：板块发现。

`src/data/`

行情和资料数据层。这里负责多数据源适配、缓存、本地历史数据、基金持仓等。数据源优先级由 `src/config.py` 配置。

`src/agents/`

Agent 分析层。包含 TradingAgents 包装、LLM provider/client、质量门禁、信号工具、板块发现 pipeline 等。

`src/portfolio/`

个人组合和交易层。负责持仓模型、交易应用、每日检查、交易记录等。

`src/knowledge/`

知识系统。分为 raw、wiki、derived 三层：

- raw 保存原始材料；
- wiki 生成可读 Markdown 页面；
- derived 做派生索引、chunk、entity、lint。

`src/orchestrator/`

后台任务、调度器和 worker，用于支撑分析任务、Wiki ingest、定时刷新等长期运行能力。

## 前端模块

`web/src/pages/` 是主要页面：

- 首页；
- 个股详情；
- 分析列表和分析详情；
- 组合；
- 每日交易日志；
- 原始材料和手动录入；
- Wiki 首页、ingest、lint、claims；
- 板块发现；
- 设置。

前端通过 API 访问后端，不直接读取 `data/*.db` 或 `data/knowledge/wiki/*.md`。

## 本地运行数据

默认运行数据在：

```text
data/
data/knowledge/raw/
data/knowledge/wiki/
data/knowledge/derived/
```

这些目录可能包含个人持仓、交易记录、研究结论、LLM 输出、缓存和日志，因此被 `.gitignore` 忽略。

`data/knowledge/schema/*.md` 是例外，它们是项目规则文件，可以提交。
