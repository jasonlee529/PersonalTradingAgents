# 设计：量化策略模块

## 目标

提供可扩展的量化选股策略框架，首期实现"放量回踩"策略，并对外提供统一的扫描 API 与前端页面。

## 后端设计

### 策略模块 `src/strategies/`

- `base.py`：`BaseStrategy` 抽象基类，定义 `id`/`name`/`description`/`default_params` 与 `detect()` 接口。`detect()` 接收单只股票的 K 线数据，返回命中结果 dict 或 None。
- `volume_pullback.py`：`VolumePullbackStrategy`，实现"放量回踩"形态检测。
- `registry.py`：策略注册表，`list_strategies()` 与 `get_strategy(id)`。
- `scanner.py`：`StrategyScanner`，依赖 `DataCollector`，负责获取全市场列表、并发拉取 K 线、调用策略 `detect()`、汇总结果。

### "放量回踩"检测算法

输入：单只股票日 K 线（至少 `rally_days + ma_period + min_pullback_days + 1` 根）。

参数（可调，默认值）：
- `rally_days`: 20（上涨回看窗口）
- `min_rally_pct`: 30.0（最小涨幅 %）
- `ma_period`: 10（回踩均线周期）
- `pullback_tolerance`: 0.02（触及 MA 的容差，2%）
- `contraction_ratio`: 0.7（回调均量 / 上涨均量 上限）
- `expansion_ratio`: 1.5（今日量 / 回调均量 下限）
- `min_pullback_days`: 2（峰值后至少多少个回调日）
- `require_bounce_up`: True（今日是否要求收阳）

步骤：
1. 按 date 升序，计算 `MA{ma_period}`。
2. 取最近 `rally_days` 根为上涨窗口，`start_close` = 窗口前一根收盘。
3. `peak` = 窗口内最高价的最高点，`rally_pct = (peak_high / start_close - 1) * 100`；若 `< min_rally_pct` 则不命中。
4. 回调窗口 = peak 之后至"今日"前一根；长度需 ≥ `min_pullback_days`。
5. 回踩判定：回调窗口中存在某根 K 线 `low <= MA * (1 + pullback_tolerance)`。
6. 缩量判定：回调均量 ≤ 上涨段均量 × `contraction_ratio`。
7. 放量判定：今日成交量 ≥ 回调均量 × `expansion_ratio`。
8. 若 `require_bounce_up`，今日需 `close > open`。
9. 命中则返回含 `rally_pct`/`peak_date`/`touch_date`/`contraction_ratio`/`expansion_ratio` 等字段的 dict。

### 扫描流程

复用 `DataCollector.get_market_list` 获取全市场行情，过滤创业板（300/301），按市场筛选，按成交额降序取前 `max_stocks`（默认 200）只，并发（信号量 10）拉取 60 根日 K，逐只运行 `detect()`，汇总并按 `rally_pct` 降序排序。

### API 路由 `src/api/routers/strategies.py`

- `GET /api/strategies`：返回策略列表（id/name/description/params）。
- `GET /api/strategies/{strategy_id}/scan`：运行策略扫描，query 参数：`trade_date`/`market`/`q`/`limit`/`offset` 及策略参数（`rally_days`/`min_rally_pct` 等）。

## 前端设计

- 主页面 `StrategiesPage`：顶部展示策略卡片列表；选中策略后展示筛选条件（市场/搜索/参数）与结果表格；未实现的策略卡片标记"敬请期待"。
- 结果表格列：股票、市场、最新价、涨幅、20日涨幅、峰值价/日期、回踩日期、缩量比、放量比、描述，行可跳转 `/stock?symbol=`。
- 复用 Arco Design + react-query，样式与 `ChanlunBuySignalsPage` 保持一致。

## 不做

- 不修改已有数据采集实现与已有路由逻辑，仅增量新增。
- 不做策略回测/历史胜率统计（后续策略再扩展）。
