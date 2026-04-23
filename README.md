# Codex Memory Migrator

[中文说明](./README.zh-CN.md) | English

> Move Codex history between machines without losing sessions, memories, or path-linked context. ⚡

## Why This Repo Exists

Codex local state is not just one chat log. A typical `~/.codex` contains:

- `history.jsonl`
- `sessions/**/*.jsonl`
- `config.toml`
- `state_*.sqlite`
- `logs_*.sqlite`

When you move to a new Mac, rename your user account, or relocate projects, those files can still point at old absolute paths like `/Users/alice/project-x`. This repo fixes that at the source instead of relying on manual edits.

## Highlights

- ⚡ Pure Node CLI with real npm bins
- 🧠 Codex skill included for keyword-based triggering
- 🔍 `scan` and `plan` help you see what will break before rewrite
- 🛠 `rewrite` updates text files and SQLite text columns
- 📦 `install` sets up both the skill and command aliases locally
- 🌍 Bilingual docs for GitHub open source use

## Install

### 1. Run from the repo

```bash
node ./bin/codex-memory-migrator.js --help
```

### 2. Global install for real commands

```bash
npm install -g .
```

This gives you commands like:

```bash
codex-memory-migrator
fix-codex-paths
migrate-codex-memory
```

### 3. Local Codex skill + aliases

```bash
codex-memory-migrator install
```

By default this installs:

- the skill into `~/.codex/skills`
- local command wrappers into `~/.local/bin`

## Fast Workflow

### Export on the old machine

```bash
codex-memory-migrator export \
  --codex-home ~/.codex \
  --output-dir ~/codex-memory-export
```

### Inspect on the new machine

```bash
fix-codex-paths plan \
  --manifest ~/codex-memory-export/manifest.json
```

### Rewrite broken paths

```bash
codex-memory-migrator rewrite \
  --root ~/codex-memory-export/codex-home \
  --manifest ~/codex-memory-export/manifest.json
```

### Restore to the target Codex home

```bash
rsync -a ~/codex-memory-export/codex-home/ ~/.codex/
```

## Command Surface

- `install`
  Installs the bundled skill and local command aliases.
- `scan`
  Scans a Codex home and summarizes absolute path usage.
- `export`
  Copies `~/.codex` into a portable snapshot and writes `manifest.json`.
- `plan`
  Reads `manifest.json` and suggests target-machine rewrites.
- `rewrite`
  Rewrites copied paths in text files and SQLite text columns.
- `install-skill`
  Installs the Codex skill only.
- `install-commands`
  Installs local wrapper commands only.

## Codex Trigger Keywords

If you prefer natural-language triggering inside Codex, the bundled skill is tuned for phrases like:

```text
修复 Codex 旧路径
迁移 Codex 到新 Mac
恢复 ~/.codex 历史
fix old /Users paths
move Codex to a new Mac
copy ~/.codex between users
```

## Open Source Notes

- 🧪 Requires Node `>=22`
- 🗃 Uses the built-in `node:sqlite` module for SQLite rewriting
- 📁 Skips volatile cache folders like `.tmp/`, `tmp/`, `node_modules/`, and `.git`
- 🔒 Rewrites copied snapshots, not your live source directory

## Development

```bash
npm test
python3 -m unittest discover -s tests -v
```

The Python script is still kept in the repo for compatibility with the existing skill workflow, but the public-facing CLI is now the Node version.

## License

MIT
