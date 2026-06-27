## 为什么

当前已有简单的"放量回踩"策略，但缺少工业级的强势股识别、多买点触发、风控和回测能力。个人投研需要一套完整的"强势股识别 → 健康回踩 → 买点触发 → 回测评估"系统，才能验证策略有效性并形成可复盘的方法论。新增该系统将量化选股从"单次筛选"升级为"可回测的策略框架"。

## 变更内容

- 新增因子层 `src/strategies/factors.py`：从 K 线计算 MA5/10/20/60、ATR14、RSI14、VOL_MA5、HIGH_20、HIGH_60、涨停标记等完整指标序列。
- 新增强势回踩策略 `src/strategies/strong_pullback.py`：实现强势股评分模型（动量+新高+均线趋势+放量+涨停）、回踩检测（幅度+缩量+不破MA20+整理结构）、3 种买点触发（放量突破/MA20反弹/箱体突破）。
- 新增风控模块 `src/strategies/risk.py`：止损（跌破MA20或固定百分比）、三段止盈（+10%/-30%、+20%/-30%、+30%清仓）、仓位控制（单票占比+最大持仓数）。
- 新增回测引擎 `src/strategies/backtest.py`：支持 A 股 T+1、涨跌停不可成交、滑点、佣金印花税，输出权益曲线、交易记录和绩效指标（年化收益、最大回撤、胜率、盈亏比等）。
- 注册新策略 `strong_pullback` 到策略注册表。
- 扩展 API：新增 `POST /api/strategies/backtest` 回测接口。
- 新增前端回测页面 `BacktestPage.tsx`，展示回测配置、权益曲线、绩效指标和交易记录。

## 功能 (Capabilities)

### 新增功能
- `quant-strong-pullback-scan`: 运行强势回踩策略的全市场实时扫描。
- `quant-strategy-backtest`: 对指定策略进行历史回测，输出绩效指标与交易明细。

### 修改功能
- `quant-strategy-browse`: 策略列表新增 `strong_pullback` 策略卡片。

## 影响

- 后端：新增 `src/strategies/{factors,strong_pullback,risk,backtest}.py`；`registry.py` 增量注册新策略；`strategies.py` 路由增量增加回测接口。
- 前端：新增 `BacktestPage.tsx`；`App.tsx` 增量增加路由；`Layout.tsx` 增量增加导航子项；`client.ts` 增量增加回测 API。
- 数据层：复用现有 `DataCollector.get_kline` 与 `get_market_list`，不修改已有实现。
- 测试：新增因子、策略、风控、回测的单元测试。
