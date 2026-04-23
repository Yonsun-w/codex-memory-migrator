---
name: codex-memory-migrator
description: Use this skill when moving Codex to a new machine, restoring local conversation history after reinstall, copying ~/.codex between users, or fixing broken session and memory paths that still point at old absolute directories.
---

# Codex Memory Migrator

This skill helps migrate a local `~/.codex` between machines. Use it when you want to preserve conversation history, session metadata, and local memory files, especially if the target machine uses a different username, home directory, or workspace root.

Read [migration-workflow.md](./references/migration-workflow.md) when you need the full workflow, example mappings, and scope notes.

## Quick Start

Install the skill locally:

```bash
python3 skill/codex-memory-migrator/scripts/codex_memory_migrator.py install-skill
```

Export the current Codex home:

```bash
python3 skill/codex-memory-migrator/scripts/codex_memory_migrator.py export \
  --codex-home ~/.codex \
  --output-dir ~/codex-memory-export
```

On the target machine, inspect the export and let the tool suggest the home-directory rewrite:

```bash
python3 skill/codex-memory-migrator/scripts/codex_memory_migrator.py plan \
  --manifest ~/codex-memory-export/manifest.json
```

Then rewrite the copied snapshot. If the manifest has enough information, you do not need to pass `--map` manually:

```bash
python3 skill/codex-memory-migrator/scripts/codex_memory_migrator.py rewrite \
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
2. On the source machine, run `scan` or `export` to understand path usage and snapshot the full Codex home.
3. Transfer the export folder to the new machine.
4. Prefer `plan --manifest ...` to inspect the export and suggest mappings before rewriting.
5. Prefer `rewrite --manifest ...` if the old and new machines mainly differ by home directory or username.
6. Fall back to explicit `--map OLD=NEW` values when projects moved to a different workspace root.
7. Copy the rewritten `codex-home/` contents into the target `~/.codex`.

## Notes

- Prefer `plan` before `rewrite` when a manifest is available. It shows the next safe command and suggested mappings.
- Close Codex before exporting if you want the cleanest SQLite snapshot.
- Run rewrites on a copied snapshot, not on the live source directory.
- Put more specific mappings first if you pass multiple `--map` values.
- Export skips `.tmp/` and `tmp/` by default because they are volatile cache directories.
- The script rewrites text files and SQLite text columns. It does not rewrite binary blobs.
- `rewrite --manifest ...` automatically infers a home-directory mapping such as `/Users/oldname -> /Users/newname`.
- `install-skill` creates a symlink in `~/.codex/skills` by default, and can use `--copy` if symlinks are not desired.

## Script

The bundled script lives at [codex_memory_migrator.py](./scripts/codex_memory_migrator.py).
