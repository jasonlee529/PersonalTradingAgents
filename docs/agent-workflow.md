# Agent 分析流程

本项目里的 Agent 不是为了直接自动交易，而是为了把一次投研拆成可检查、可复盘的多个阶段。

## 一次分析大致发生什么

1. 从数据层获取行情、K 线、新闻、公告、基本面、板块和其他上下文。
2. 通过 `data_bridge` 和 `data_vendor` 把数据整理成 Agent 可用的输入。
3. 多个分析角色分别生成阶段报告，例如市场、情绪、新闻、基本面、政策、资金等。
4. 研究员角色做多空辩论。
5. 风险角色做风险讨论。
6. Trader 角色形成交易计划或观察建议。
7. 质量门禁和信号工具检查输出是否完整、是否存在明显冲突。
8. 结果写入本地分析记录，并可进入 raw/wiki 知识层。

## 主要代码位置

```text
src/agents/trading_agents_wrapper.py
src/agents/wrapper/
src/agents/tradingagents/
src/agents/signal_tools.py
src/agents/quality_gate.py
src/agents/data_bridge.py
src/agents/data_vendor.py
```

板块发现相关：

```text
src/agents/sector_discovery/
```

## LLM Provider

LLM 配置在 `.env` 中控制。项目支持多个 provider key 字段，例如 OpenAI、DeepSeek、Anthropic、Google、Azure OpenAI、OpenRouter、Kimi 等。

开发和测试时可以开启 mock/test 模式，避免每次运行都消耗真实 token。

## 使用原则

- Agent 输出是研究辅助，不是投资建议。
- 保留中间报告比只保留最终结论更重要。
- 分析结果要能回到数据和原始材料。
- 长期运行时，分析记录应进入本地知识库，方便后续复盘。
