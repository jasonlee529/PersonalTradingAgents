# 任务清单

## 后端

- [ ] 1. 新建 `src/strategies/__init__.py`
- [ ] 2. 新建 `src/strategies/base.py`：`BaseStrategy` 抽象基类
- [ ] 3. 新建 `src/strategies/volume_pullback.py`：`VolumePullbackStrategy` 检测算法
- [ ] 4. 新建 `src/strategies/registry.py`：策略注册表
- [ ] 5. 新建 `src/strategies/scanner.py`：`StrategyScanner` 全市场扫描器
- [ ] 6. 新建 `src/api/routers/strategies.py`：策略列表与扫描 API
- [ ] 7. `src/api/main.py` 增量注册 strategies 路由

## 前端

- [ ] 8. `web/src/api/client.ts` 增量增加 `strategyApi` 与类型
- [ ] 9. 新建 `web/src/pages/StrategiesPage.tsx`
- [ ] 10. `web/src/App.tsx` 增量增加 `/strategies` 路由
- [ ] 11. `web/src/components/Layout.tsx` 增量增加导航菜单项

## 测试

- [ ] 12. 新建 `tests/strategies/__init__.py`
- [ ] 13. 新建 `tests/strategies/test_volume_pullback.py`：覆盖命中/不命中/边界场景
