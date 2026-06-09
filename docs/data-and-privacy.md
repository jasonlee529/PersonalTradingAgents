# 数据与隐私

这个项目会保存个人投研数据，所以 GitHub 发布前最重要的事情不是“把文件都推上去”，而是明确哪些内容永远只能留在本地。

## 不提交的内容

```text
.env
data/
data/knowledge/raw/
data/knowledge/wiki/
data/knowledge/derived/
web/knowledge/
*.db
*.sqlite
*.sqlite3
*.log
*.err.log
*.out.log
```

这些内容可能包含：

- API Key；
- 持仓和交易记录；
- 每日交易日志；
- LLM 分析输出；
- 新闻、公告、研报缓存；
- 本地 Wiki；
- 后台任务日志；
- 通知 webhook 或邮箱配置。

## 可以提交的内容

```text
src/
tests/
web/src/
web/public/
data/knowledge/schema/*.md
docs/
.env.example
pyproject.toml
web/package.json
web/package-lock.json
```

其中 `data/knowledge/schema/*.md` 是特意保留的，因为它是规则文件，不是个人运行数据。

## 每个用户如何隔离数据

默认情况下，用户运行项目后会在本地生成：

```text
data/
```

`data/` 下的运行数据被 Git 忽略。每个用户自己的持仓、分析、知识库都留在自己的机器上。`data/knowledge/schema/` 是例外，只保存可提交的规则文件。

如果要更严格地隔离，可以在 `.env` 中把相关路径改到项目目录之外。

## 推送前检查

推送 GitHub 前建议运行：

```powershell
git status --short
git ls-files data web/knowledge .env
```

预期结果：

- 不应出现 `.env`；
- 不应出现 `data/`；
- 不应出现 `data/` 下的运行数据；
- 不应出现 `web/knowledge`；
- `data/knowledge/schema/*.md` 可以出现。
