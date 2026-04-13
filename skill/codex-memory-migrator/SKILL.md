---
name: codex-memory-migrator
description: Use this skill when migrating a local Codex home to another machine, especially when sessions, memories, or SQLite state contain absolute paths that must be copied and rewritten safely.
---

# Codex Memory Migrator

This skill helps migrate a local `~/.codex` between machines. Use it when you want to preserve conversation history, session metadata, and local memory files and you suspect the target machine will use different absolute paths.

Read [migration-workflow.md](./references/migration-workflow.md) when you need the full workflow, example mappings, and scope notes.

## Quick Start

Run the bundled script:

```bash
python3 skill/codex-memory-migrator/scripts/codex_memory_migrator.py scan \
  --codex-home ~/.codex
```

Export the full Codex home into a portable snapshot:

```bash
python3 skill/codex-memory-migrator/scripts/codex_memory_migrator.py export \
  --codex-home ~/.codex \
  --output-dir ~/codex-memory-export
```

On the target machine, rewrite copied paths inside the exported snapshot:

```bash
python3 skill/codex-memory-migrator/scripts/codex_memory_migrator.py rewrite \
  --root ~/codex-memory-export/codex-home \
  --map /Users/oldname=/Users/newname
```

Then copy the rewritten snapshot into `~/.codex`.

## When To Use This Skill

- You want to move all local Codex conversations to another machine.
- Your old sessions reference paths like `/Users/alice/project-x`.
- The new machine uses a different username or workspace root.
- You want a repeatable, scriptable migration workflow instead of manual edits.

## Workflow

1. Run `scan` on the source machine to understand path usage.
2. Run `export` to snapshot the full Codex home.
3. Transfer the export folder to the new machine.
4. Run `rewrite` with one or more `OLD=NEW` mappings.
5. Copy the rewritten `codex-home/` contents into the target `~/.codex`.

## Notes

- Close Codex before exporting if you want the cleanest SQLite snapshot.
- Run rewrites on a copied snapshot, not on the live source directory.
- Put more specific mappings first if you pass multiple `--map` values.
- Export skips `.tmp/` and `tmp/` by default because they are volatile cache directories.
- The script rewrites text files and SQLite text columns. It does not rewrite binary blobs.

## Script

The bundled script lives at [codex_memory_migrator.py](./scripts/codex_memory_migrator.py).
