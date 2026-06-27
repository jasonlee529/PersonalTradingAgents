# 设计：强势回踩策略 + 回测引擎

## 五层架构

```
数据层 (DataCollector) → 因子层 (factors.py) → 强势股识别 (strong_pullback.py)
  → 回踩信号 (strong_pullback.py) → 回测引擎 (backtest.py) + 风控 (risk.py)
```

## 因子层 `factors.py`

`compute_factors(df: pd.DataFrame) -> pd.DataFrame`

输入 OHLCV DataFrame，增量添加列：
- `ma5`/`ma10`/`ma20`/`ma60`：移动平均
- `atr14`：14日 ATR
- `rsi14`：14日 RSI
- `vol_ma5`：5日成交量均线
- `high_20`/`high_60`：滚动最高价
- `pct_change`：日收益率
- `is_limit_up`：涨停标记（主板 ≥9.5%，创业板/科创板 ≥19.5%）

## 强势回踩策略 `strong_pullback.py`

### 强势股评分（min_strong_score=5）

| 条件 | 分值 |
| --- | --- |
| 动量：close[-1]/close[-20] > 1.2 | +2 |
| 新高：close[-1] >= high_60[-1] | +2 |
| 均线趋势：ma5 > ma10 > ma20 | +2 |
| 放量突破：vol[-5:].mean() > vol[-20:].mean() | +1 |
| 近10日涨停过 | +1 |

### 回踩检测

- `pullback_pct = (close[-1] - high_20[-1]) / high_20[-1]`，范围 (-0.15, 0)
- `close[-1] > ma20[-1] * 0.98`（不破 MA20）
- `vol[-1] < vol_ma5[-1]`（缩量）
- `close[-3:].max() <= close[-10:].max()`（整理结构）

### 买点触发（3选1，entry_type 可选）

- **A 放量突破**：close[-1] > high[-5:-1].max() 且 vol[-1] > vol_ma5[-1]*1.5 且收阳
- **B MA20反弹**：近期触及MA20后收阳放量
- **C 箱体突破**：回踩平台后突破箱体上沿

## 风控 `risk.py`

- `RiskConfig`：止损类型(ma20/fixed)、止损百分比、止盈档位、单票仓位、最大持仓
- `Position`：入场信息 + 止损价 + 已止盈档位
- `check_exit(position, bar)` → 止损/止盈/持有

## 回测引擎 `backtest.py`

### 流程

1. 确定股票池（用户指定 symbols 或市场TopN）
2. 预加载所有股票 K 线（异步并发）
3. 计算因子
4. 遍历交易日：
   - 检测信号 → 次日开盘买入（T+1，滑点，涨跌停检查）
   - 检查持仓止损/止盈
5. 计算绩效指标

### A 股规则

- T+1：买入次日才能卖出
- 涨停不可买：开盘价 == 前日收盘 × 1.1 时跳过
- 滑点：买入价 × (1+slippage)，卖出价 × (1-slippage)
- 佣金 + 印花税

### 绩效指标

- 累计收益、年化收益、最大回撤、波动率
- 胜率、盈亏比、平均持仓天数、交易次数
- 权益曲线、逐笔交易记录

## 不做

- 不修改已有 volume_pullback 策略与 scanner
- 不做机器学习版本（后续扩展）
- 不做行业/情绪周期过滤（后续扩展）
