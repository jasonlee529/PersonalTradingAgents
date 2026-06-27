# 任务清单

## 后端因子与策略

- [ ] 1. 新建 `src/strategies/factors.py`：因子计算（MA/ATR/RSI/VOL_MA/HIGH_N/涨停）
- [ ] 2. 新建 `src/strategies/strong_pullback.py`：强势股评分 + 回踩检测 + 3种买点
- [ ] 3. `src/strategies/registry.py` 增量注册 strong_pullback 策略

## 后端风控与回测

- [ ] 4. 新建 `src/strategies/risk.py`：止损/止盈/仓位控制
- [ ] 5. 新建 `src/strategies/backtest.py`：回测引擎（A股规则 + 绩效指标）
- [ ] 6. 扩展 `src/api/routers/strategies.py`：新增回测接口 `POST /strategies/backtest`

## 前端

- [ ] 7. `web/src/api/client.ts` 增量增加回测 API 与类型
- [ ] 8. 新建 `web/src/pages/BacktestPage.tsx`
- [ ] 9. `web/src/App.tsx` 增量增加 `/backtest` 路由
- [ ] 10. `web/src/components/Layout.tsx` 增量增加回测导航子项

## 测试

- [ ] 11. 新建 `tests/strategies/test_factors.py`
- [ ] 12. 新建 `tests/strategies/test_strong_pullback.py`
- [ ] 13. 新建 `tests/strategies/test_risk.py`
- [ ] 14. 新建 `tests/strategies/test_backtest.py`
