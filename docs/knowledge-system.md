# 知识系统说明

项目的知识系统不是普通文档目录，而是为了长期运行和复盘设计的本地研究记忆。

## 四类目录

```text
data/knowledge/schema/    规则和 schema，提交 GitHub
data/knowledge/raw/       原始材料，本地运行数据
data/knowledge/wiki/      生成的 Markdown Wiki，本地运行数据
data/knowledge/derived/   派生索引，本地运行数据
```

## schema：可公开规则

`data/knowledge/schema/*.md` 是项目规则文件，不是个人数据，因此保留在 GitHub：

```text
wiki-maintainer.md
raw-source-types.md
derived-index-schema.md
obsidian-conventions.md
```

这些文件告诉系统和 LLM 如何维护 Wiki、如何理解 raw source、derived index 应该怎么组织。

## raw：原始材料层

raw 层保存“材料本身”和 metadata，例如：

- 手动录入材料；
- 每日方向；
- 每日交易日志；
- 个股分析报告；
- analysis memory；
- 其他待进入 Wiki 的来源。

raw 层是本地数据，不应该提交。

## wiki：可读知识层

wiki 层把 raw source 整理成可读 Markdown 页面。它维护：

```text
data/knowledge/wiki/index.md
data/knowledge/wiki/log.md
data/knowledge/wiki/index.db
data/knowledge/wiki/pages/
data/knowledge/wiki/.lint_latest.json
```

`index.md` 是内容入口，`log.md` 是操作时间线，`pages/` 是生成页面。

这些内容可能包含个人股票、交易判断和研究结论，因此不提交 GitHub。

## derived：派生索引层

derived 层用于 chunk、entity、link、lint、索引等后续能力。它服务于检索和结构化分析，也是本地运行数据。

## 为什么删除 web/knowledge

当前前端通过 API 读取 Wiki，不直接读 `web/knowledge/`。

`web/knowledge/` 是旧运行产物或旧目录，不属于前端源码。继续保留会造成两个问题：

- 容易误以为前端依赖这些静态文件；
- 容易把个人 Wiki 内容误提交。

所以保留 `data/knowledge/wiki/` 作为运行目录，删除 `web/knowledge/`。
