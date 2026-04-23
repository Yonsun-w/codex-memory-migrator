---
name: codex-memory-migrator
description: Trigger on prompts like "迁移 Codex 到新 Mac", "修复 Codex 旧路径", "恢复 ~/.codex 历史", "fix old /Users paths", "move Codex to a new Mac", or "copy ~/.codex between users".
---

# Codex Memory Migrator

This skill helps migrate a local `~/.codex` between machines. Use it when you want to preserve conversation history, session metadata, and local memory files, especially if the target machine uses a different username, home directory, or workspace root.

Read [migration-workflow.md](./references/migration-workflow.md) when you need the full workflow, example mappings, and scope notes.

## Quick Start

Install the skill and local command aliases:

```bash
codex-memory-migrator install
```

That installs the skill plus command aliases such as `codex-memory-migrator`, `fix-codex-paths`, and `migrate-codex-memory`.

Export the current Codex home:

```bash
codex-memory-migrator export \
  --codex-home ~/.codex \
  --output-dir ~/codex-memory-export
```

On the target machine, inspect the export and let the tool suggest the home-directory rewrite:

```bash
fix-codex-paths plan \
  --manifest ~/codex-memory-export/manifest.json
```

Then rewrite the copied snapshot. If the manifest has enough information, you do not need to pass `--map` manually:

```bash
codex-memory-migrator rewrite \
  --root ~/codex-memory-export/codex-home \
  --manifest ~/codex-memory-export/manifest.json
```

Then copy the rewritten snapshot into `~/.codex`.

## When To Use This Skill

- You want to move all local Codex conversations to another machine.
- You reinstalled macOS or moved to a new user account and old Codex sessions now open the wrong folders.
- Your old sessions reference paths like `/Users/alice/project-x`.
- The new machine uses a different username or workspace root.
- You want a repeatable, scriptable migration workflow instead of manual edits.

## Workflow

1. If the user only wants the skill available locally, run `install-skill`.
2. If the user wants command-style usage, run `install` and use `fix-codex-paths ...` or `codex-memory-migrator ...`.
3. On the source machine, run `scan` or `export` to understand path usage and snapshot the full Codex home.
4. Transfer the export folder to the new machine.
5. Prefer `plan --manifest ...` to inspect the export and suggest mappings before rewriting.
6. Prefer `rewrite --manifest ...` if the old and new machines mainly differ by home directory or username.
7. Fall back to explicit `--map OLD=NEW` values when projects moved to a different workspace root.
8. Copy the rewritten `codex-home/` contents into the target `~/.codex`.

## Notes

- Prefer `plan` before `rewrite` when a manifest is available. It shows the next safe command and suggested mappings.
- Close Codex before exporting if you want the cleanest SQLite snapshot.
- Run rewrites on a copied snapshot, not on the live source directory.
- Put more specific mappings first if you pass multiple `--map` values.
- Export skips `.tmp/` and `tmp/` by default because they are volatile cache directories.
- The script rewrites text files and SQLite text columns. It does not rewrite binary blobs.
- `rewrite --manifest ...` automatically infers a home-directory mapping such as `/Users/oldname -> /Users/newname`.
- `install-skill` creates a symlink in `~/.codex/skills` by default, and can use `--copy` if symlinks are not desired.
- `install` also creates local command aliases so you can trigger the workflow with short command names instead of `$skill-name`.
- The public-facing CLI is the Node command. The bundled Python script remains in the repo for compatibility.

## Script

The bundled script lives at [codex_memory_migrator.py](./scripts/codex_memory_migrator.py).
