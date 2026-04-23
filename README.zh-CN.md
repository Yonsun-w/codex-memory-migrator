# Codex Memory Migrator

中文 | [English](./README.md)

> 把 Codex 本地历史、会话和记忆从旧机器迁到新机器，并修复残留的旧绝对路径。🚀

## 这是什么

这是一个面向 GitHub 开源和 Node CLI 使用场景的 Codex 迁移工具。

很多人以为只要复制一个聊天记录文件就够了，但真实的 `~/.codex` 往往还包含：

- `history.jsonl`
- `sessions/**/*.jsonl`
- `config.toml`
- `state_*.sqlite`
- `logs_*.sqlite`

这些文件里经常带着旧机器路径，比如 `/Users/alice/project-x`。一旦换 Mac、换用户名、换工作目录，历史会话就会“看起来还在”，但引用的路径已经坏掉了。

这个项目就是专门解决这个问题的。

## 特性

- ⚡ 纯 Node CLI，适合公开发到 GitHub / npm
- 🧠 附带 Codex skill，可通过关键词触发
- 🔍 支持 `scan`、`plan`，先看问题再改
- 🛠 支持批量改写文本文件和 SQLite 文本列
- 📦 `install` 一条命令同时安装 skill 和本地命令别名
- 🌏 中英文 README，适合现代开源项目展示

## 安装方式

### 1. 直接在仓库里运行

```bash
node ./bin/codex-memory-migrator.js --help
```

### 2. 当作全局命令安装

```bash
npm install -g .
```

安装后可直接使用这些命令：

```bash
codex-memory-migrator
fix-codex-paths
migrate-codex-memory
```

### 3. 安装到本地 Codex 环境

```bash
codex-memory-migrator install
```

默认会做两件事：

- 把 skill 安装到 `~/.codex/skills`
- 把命令包装器安装到 `~/.local/bin`

## 推荐流程

### 在旧机器导出

```bash
codex-memory-migrator export \
  --codex-home ~/.codex \
  --output-dir ~/codex-memory-export
```

### 在新机器查看迁移建议

```bash
fix-codex-paths plan \
  --manifest ~/codex-memory-export/manifest.json
```

### 改写旧路径

```bash
codex-memory-migrator rewrite \
  --root ~/codex-memory-export/codex-home \
  --manifest ~/codex-memory-export/manifest.json
```

### 恢复到目标 Codex 目录

```bash
rsync -a ~/codex-memory-export/codex-home/ ~/.codex/
```

## 命令说明

- `install`
  同时安装 skill 和本地命令别名。
- `scan`
  扫描 `~/.codex` 内部有哪些绝对路径。
- `export`
  导出完整快照并生成 `manifest.json`。
- `plan`
  根据 `manifest.json` 推断旧路径到新路径的映射。
- `rewrite`
  改写文本文件和 SQLite 文本列中的旧路径。
- `install-skill`
  只安装 skill。
- `install-commands`
  只安装本地命令包装器。

## Codex 关键词触发

如果你更喜欢在 Codex 里直接说一句话，当前 skill 已经偏向这些关键词：

```text
修复 Codex 旧路径
迁移 Codex 到新 Mac
恢复 ~/.codex 历史
fix old /Users paths
move Codex to a new Mac
copy ~/.codex between users
```

## 开源说明

- 🧪 需要 Node `>=22`
- 🗃 SQLite 改写使用 Node 内置 `node:sqlite`
- 📁 默认跳过 `.tmp/`、`tmp/`、`node_modules/`、`.git`
- 🔒 建议只改写导出的快照，不直接改活跃中的 `~/.codex`

## 开发测试

```bash
npm test
python3 -m unittest discover -s tests -v
```

仓库里仍然保留 Python 脚本，用于兼容原有 skill 工作流；但面向 GitHub / Node / 命令行分发的主入口已经切到 Node 版。

## License

MIT
