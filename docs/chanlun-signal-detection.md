# 缠论信号检测方法 — `_detect_chanlun_signals_for_stock`

> 源码位置：`src/data/collector.py:770-932`

## 一、方法概览

```python
async def _detect_chanlun_signals_for_stock(
    self, stock: dict, kline: list[dict]
) -> list[dict]:
```

**职责**：对单只股票的 K 线数据进行技术分析，检测缠论三类买点（一买 / 二买 / 三买）。

**输入**：
- `stock`：股票基本信息（symbol, name, price, change_pct, volume, turnover 等）
- `kline`：K 线列表，每根为 `{"date": "...", "open": ..., "high": ..., "low": ..., "close": ..., "volume": ...}`

**输出**：信号 dict 列表，每个信号包含：
| 字段 | 含义 | 示例 |
|---|---|---|
| `signal_type` | 信号类型 | `type1` / `type2` / `type3` |
| `signal_type_label` | 中文标签 | `"一买"` |
| `pivot_level` | 缠论中枢级别 | `"30F"` / `"5F"` |
| `divergence_type` | 背离 / 确认类型 | `"MACD底背离"` / `"趋势确认"` / `"突破回抽"` |
| `confidence_score` | 置信度 | `0.65 ~ 0.75` |
| `macd_divergence` / `kdj_divergence` / `rsi_divergence` | 三指标辅助判断 | `bool` |

---

## 二、执行流程总览

```
kline 输入
   │
   ▼  (1) 数据校验与规范化
   │    ├─ 至少 30 根 K 线
   │    ├─ 转换为 pandas DataFrame
   │    └─ 按 date 升序排序
   │
   ▼  (2) 技术指标计算
   │    ├─ MACD (12, 26, 9)
   │    ├─ KDJ  (9, 3, 3)
   │    └─ RSI  (14)
   │
   ▼  (3) 三类买点扫描 ──┐
   │    ├─ 一买 (≥60 根) ─┤
   │    ├─ 二买 (≥40 根) ─┤
   │    └─ 三买 (≥30 根) ─┤
   │                       │
   ▼  (4) 汇总返回   ◄─────┘
```

---

## 三、逐段代码解析

### 3.1 初始化与快速失败（L773-781）

```python
signals = []
if not kline or len(kline) < 30:           # 数据不足直接返回
    return signals

symbol = stock.get("symbol", "")
name = stock.get("name", "")
market = stock.get("market",               # 若无显式 market，则按代码首位数推断
    "sh" if str(symbol).startswith("6") else "sz")
trade_date = stock.get("trade_date", datetime.now().strftime("%Y-%m-%d"))
```

> **注意**：`market` 的推断逻辑只判了 `6` 开头为沪市，那么科创板(688)、北交所(8/9)、主板(60/601/603)虽然都正确落入 `sh`，但 `0/3` 开头的深主板/创业板也都被归为 `sz`——对于后续「按市场筛选」的场景，若需要区分北交所，这里应扩展判断。

### 3.2 DataFrame 规范化（L783-794）

```python
df = pd.DataFrame(kline)
if len(df) < 30:
    return signals

df = df.sort_values("date").reset_index(drop=True)   # **关键**：指标计算对时序敏感

close_prices = df["close"].values    # 提取 numpy 数组备用
high_prices = df["high"].values
low_prices  = df["low"].values
volumes     = df["volume"].values
```

### 3.3 MACD 计算（L797-801）

```python
exp12 = df["close"].ewm(span=12, adjust=False).mean()   # EMA12 (快线)
exp26 = df["close"].ewm(span=26, adjust=False).mean()   # EMA26 (慢线)
macd  = exp12 - exp26                                   # DIF — MACD 线
signal = macd.ewm(span=9, adjust=False).mean()          # DEA — 信号线
histogram = macd - signal                               # MACD 柱
```

- `adjust=False`：使用「传统 EMA 公式」，与同花顺/东方财富等软件对齐
- `histogram` 用于二买判断柱是否转正

### 3.4 KDJ 计算（L804-809）

```python
low_min  = df["low"].rolling(window=9).min()           # 9 日最低
high_max = df["high"].rolling(window=9).max()          # 9 日最高
rsv = (df["close"] - low_min) / (high_max - low_min) * 100   # 未成熟随机值
k = rsv.ewm(com=2, adjust=False).mean()                # K: alpha = 1/(1+2) = 1/3
d = k.ewm(com=2, adjust=False).mean()                  # D: K 的 EMA
j = 3 * k - 2 * d                                      # J: 3K - 2D
```

- `com=2` 等价于 span≈5，是 A 股 KDJ 的主流参数（9,3,3）

### 3.5 RSI 计算（L812-816）

```python
delta = df["close"].diff()                              # 每日收盘涨跌
gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()   # 14日平均涨幅
loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()  # 14日平均跌幅
rs  = gain / loss
rsi = 100 - (100 / (1 + rs))                            # RSI(14)
```

> **注意**：这里用的是 **SMA 版 RSI**，而非 Wilder 原版 EMA。初期数值会有差异，长期趋势一致。

---

## 四、三类买点核心判定逻辑

### 4.1 一买（Type 1）— 下跌趋势底背离（L818-857）

```python
if len(df) >= 60:
    recent_df = df.tail(60).copy()            # 取最近 60 根 K 线
    half_idx = len(recent_df) // 2
    first_half  = recent_df.iloc[:half_idx]    # 前段 30 根
    second_half = recent_df.iloc[half_idx:]    # 后段 30 根

    first_low  = first_half["low"].min()       # 前段最低
    second_low = second_half["low"].min()      # 后段最低
    first_macd_low  = macd.iloc[-60:-30].min() if len(macd) >= 60 else None
    second_macd_low = macd.iloc[-30:].min()    if len(macd) >= 30 else None

    # ▼ 底背离：价格创新低，MACD 不创新低
    if (second_low < first_low and              # 价格：后段新低 < 前段新低
        second_macd_low > first_macd_low):      # MACD：后段低点 > 前段低点
        signals.append({ ... "signal_type": "type1", ... })
```

**图解**：
```
价格:   高点1  高点2    ↘ 低点1  ↘ 新低（更低）
MACD:   高点1' 高点2'  ↘ 低点1'  ↗ 低点2'（抬高 ✅ 背离）
```

**辅助判断**：
- `kdj_divergence`：`k < 30` → KDJ 处于超卖
- `rsi_divergence`：`rsi < 30` → RSI 处于超卖
- 中枢级别：`"30F"`
- 置信度：`0.7`

> **⚠️ 数据对齐风险**：`macd` 是用 **全量 DataFrame** 计算出的 Series，其长度可能 ≠ 60。`macd.iloc[-60:-30]` 是「全量数据的倒数第 60~30 根」，而 `recent_df.iloc[:half_idx]` 是「最近 60 根的前半段」—— 若全量 K 线数远大于 60，两者并不是同一段数据，背离比较会错位。
>
> **建议修复**：应改用 `macd.tail(60).iloc[:30]` 与 `macd.tail(60).iloc[30:]`，确保与 `recent_df` 切片对齐。

### 4.2 二买（Type 2）— 回调确认不创新低（L859-893）

```python
if len(df) >= 40:
    recent_df = df.tail(40).copy()
    mid_idx = len(recent_df) // 2
    early_low  = recent_df.iloc[:mid_idx]["low"].min()
    later_low  = recent_df.iloc[mid_idx:]["low"].min()
    early_high = recent_df.iloc[:mid_idx]["high"].max()
    later_high = recent_df.iloc[mid_idx:]["high"].max()

    # later_low > early_low   → 回调低点抬高（不创新低 ✅）
    # later_high > early_high → 走势抬升（有一波上涨）
    # k > d                   → KDJ 金叉
    # k < 50                  → 仍在低位（未过热）
    if (later_low > early_low and later_high > early_high and
        k.iloc[-1] > d.iloc[-1] and k.iloc[-1] < 50):
        signals.append({ ... "signal_type": "type2", ... })
```

**逻辑**：
- 缠论二买的理论前提是「已有一个一买」，当前实现是**独立判断**（简化版）
- 以「低点抬高 + 高点抬高」判断趋势反转，叠加 KDJ 金叉（且 k 值仍处中低区）确认买点

**辅助判断**：
- `macd_divergence`：`histogram.iloc[-1] > 0`（MACD 柱转正）
- `kdj_divergence`：`k > d`（金叉保持）
- `rsi_divergence`：`40 < rsi < 60`（中性偏强，非极端区）
- 中枢级别：`"5F"`
- 置信度：`0.65`

### 4.3 三买（Type 3）— 突破回抽（L895-930）

```python
if len(df) >= 30:
    recent_df = df.tail(30).copy()
    pivot_high  = recent_df.iloc[:-5]["high"].max()   # 前 25 根最高点 = 压力位
    current_price = close_prices[-1]                  # 当前收盘价
    current_low   = low_prices[-1]                    # 当前最低价
    prev_high     = high_prices[-5:].max()            # 最近 5 根最高价

    # 突破 + 回踩 三重确认：
    if (current_price > pivot_high * 0.98 and   # 当前价接近/越过压力位（≤2% 容忍）
        current_low   > pivot_high * 0.95 and   # 回踩不跌破压力位（≤5% 容忍）
        prev_high     > pivot_high):            # 最近 5 根已创新高（真实突破发生）
        signals.append({ ... "signal_type": "type3", ... })
```

**图解**：
```
价格:     pivot_high (压力位) ─────────┐
          /   ↘   ↗  (突破后回踩)       │
         /     └──── current_low > pivot_high*0.95 (未跌破 ✅)
        /
       /
      └─ prev_high > pivot_high (已创新高 ✅)
```

**辅助判断**：
- `macd_divergence`：`macd.iloc[-1] > 0`（MACD 线在零轴上方）
- `kdj_divergence`：`k > 50`（KDJ 强势区）
- `rsi_divergence`：`rsi > 50`（RSI 强势区）
- 中枢级别：`"30F"`
- 置信度：`0.75`（三类买点中最高）

---

## 五、三类买点对比表

| 维度 | 一买 (Type 1) | 二买 (Type 2) | 三买 (Type 3) |
|---|---|---|---|
| **缠论定位** | 下跌趋势终结点 | 回调确认点 | 突破回踩点 |
| **最少K线** | 60 | 40 | 30 |
| **核心条件** | MACD 底背离 + 价格创新低 | 低点抬高 + 高点抬高 + KDJ金叉 | 突破前高后回踩不破 |
| **中枢级别** | `30F` | `5F` | `30F` |
| **置信度** | 0.70 | 0.65 | 0.75 |
| **典型收益/风险** | 高收益 / 高风险 | 中等 / 中等 | 稳健 / 低风险 |

---

## 六、指标辅助判断速查

| 信号 | macd_divergence | kdj_divergence | rsi_divergence |
|---|---|---|---|
| **一买** | `True`（底背离） | `k < 30`（超卖） | `rsi < 30`（超卖） |
| **二买** | `histogram > 0`（红柱） | `k > d`（金叉） | `40 < rsi < 60`（中性） |
| **三买** | `macd > 0`（零轴上方） | `k > 50`（强势） | `rsi > 50`（强势） |

---

## 七、潜在问题与优化建议

### ✅ 已做得很好的点

1. **快速失败**：多处提前 `return`，避免无意义计算
2. **防御取值**：`stock.get(...)`、`float()` 包装
3. **多指标交叉验证**：MACD + KDJ + RSI 三重验证，降低单一指标误判率
4. **排序归一**：`sort_values("date")` 是技术分析必不可少的一步
5. **可调参数**：阈值（如 `pivot_high * 0.98`）用公式表达而非硬编码数字，便于后续参数化

---

### ⚠️ 可改进点

| 编号 | 问题 | 严重度 | 建议修复 |
|---|---|---|---|
| **1** | 一买中 `macd.iloc[-60:-30]` 与 `recent_df.iloc[:half_idx]` **数据不对齐** | 🔴 高 | 改用 `macd.tail(60).iloc[:30]` 与 `macd.tail(60).iloc[30:]`，确保与切片对齐 |
| **2** | 一买/二买逻辑**独立判断**，没有「先有一买才有二买」的依赖关系 | 🟡 中 | 可引入「前向回溯」：二买必须匹配近期已出现过一买信号 |
| **3** | 一买样本段 60 根偏少，对折后每段仅 30 根，**不足以判断趋势背驰** | 🟡 中 | 可扩展到 120 根，或引入段内的涨跌分段来识别中枢结构 |
| **4** | 二买的 `histogram.iloc[-1] > 0` 只看**最后一根柱**，易受震荡干扰 | 🟢 低 | 改为「连续 3 根红柱」或「柱体放大」判断 |
| **5** | `confidence_score` 是**固定值**（0.65 / 0.7 / 0.75） | 🟡 中 | 可根据背离程度、量能放大倍数、指标超卖程度做动态评分 |
| **6** | `market` 推断只判 `6` 开头为 sh，**北交所(8/9) 被归为 sz** | 🟢 低 | 可扩展为独立市场或修正规则 |
| **7** | 三买的中枢级别写死为 `30F`，但实际上它也经常出现在 `5F/1F` | 🟢 低 | 根据数据粒度动态标注 |
| **8** | RSI 使用 SMA 版而非 Wilder 的 EMA 版，**初期数值差异较大** | 🟢 低 | 切换为 `df["close"].ewm(alpha=1/14, adjust=False)` |
| **9** | `second_low` 用 `.min()` 取极端值，**易被单日异常击穿干扰** | 🟢 低 | 改用 Rolling window 的中位数或取 `min()` 时做离群点剔除 |
| **10** | 缺乏**量能配合**的判断 — 下跌缩量、突破放量是缠论重要信号 | 🟡 中 | 可加入 `volumes[-1] > volumes[-20:].mean()` 作为放量确认 |

---

## 八、信号 dict 结构参考

```jsonc
{
  "symbol": "600519",
  "name": "贵州茅台",
  "market": "sh",
  "trade_date": "2026-06-19",
  "signal_type": "type1",
  "signal_type_label": "一买",
  "price": 1680.00,
  "change_pct": 1.23,
  "volume": 2345678,
  "turnover": 3940000000,
  "turnover_rate": 0.12,
  "pivot_level": "30F",
  "recent_pivot_high": 1720.00,
  "recent_pivot_low": 1650.00,
  "divergence_type": "MACD底背离",
  "macd_divergence": true,
  "kdj_divergence": true,
  "rsi_divergence": true,
  "description": "贵州茅台(600519) 出现一买信号，MACD底背离",
  "confidence_score": 0.7
}
```

---

## 九、调用链与上下文

该方法被 `get_chanlun_buy_signals`（L934+）调用，调用流程：

```
API /stocks/chanlun-signals
    ▼
get_chanlun_buy_signals(trade_date, market, signal_type)
    ├─ get_market_list(trade_date)   # 读取全市场数据
    ├─ 过滤创业板 / 按市场筛选
    └─ 对每只股票调用:
         kline ← _fetch_with_fallback("kline", ...)
         _detect_chanlun_signals_for_stock(stock, kline)
              ├─ MACD / KDJ / RSI 计算
              ├─ type1 / type2 / type3 检测
              └─ 返回 signals[]
    ▼
汇总返回 signal 列表
```

---

## 十、总结

该方法是一个**工程化的缠论信号速筛器**，而非严格意义上的缠论笔段中枢自动识别。其设计哲学是：

- **用最少代码覆盖核心判断**：舍弃了复杂的笔段识别、中枢构建，改用「折半比较 + 多指标交叉」的简化方案
- **适合粗筛**：从数千只股票中快速圈出候选，再由人工或更精细的算法做二次确认
- **可演进性强**：`confidence_score`、`divergence_type` 等字段为后续的机器学习打分预留了扩展位

如果后续要提升信号质量，推荐按**优先级**优化：① 修复一买的数据对齐 → ② 加入一买→二买的依赖关系 → ③ 量能配合判断 → ④ 动态置信度评分。
