# Codex Memory Migrator

Open-source tooling for moving a local Codex home between machines without losing conversation history, session metadata, and path-linked memories.

The repository contains:

- a reusable Codex skill in `skill/codex-memory-migrator`
- a Python CLI that scans, exports, and rewrites a copied Codex home snapshot
- minimal docs for safe migration workflows

By default the exporter skips volatile cache directories such as `.tmp/` and `tmp/`. Those folders can be large and are not required for preserving conversation history.

## Why this exists

Codex stores more than plain chat text. A local `~/.codex` usually includes:

- `history.jsonl`
- `sessions/**/*.jsonl`
- `config.toml`
- `state_*.sqlite`
- `logs_*.sqlite`

Those files often contain absolute paths such as `/Users/alice/project-x`. Copying only one file is not enough, and moving to a different machine or username may require bulk path rewrites inside text files and SQLite text columns.

## What the CLI does

- `scan`: inspect a Codex home and summarize where absolute paths appear
- `export`: copy a Codex home into a transportable snapshot and write a manifest
- `rewrite`: rewrite copied paths inside text files and SQLite databases

## Recommended workflow

On the source machine:

```bash
python3 skill/codex-memory-migrator/scripts/codex_memory_migrator.py scan \
  --codex-home ~/.codex

python3 skill/codex-memory-migrator/scripts/codex_memory_migrator.py export \
  --codex-home ~/.codex \
  --output-dir ~/codex-memory-export
```

Move `~/codex-memory-export` to the target machine, then run:

```bash
python3 skill/codex-memory-migrator/scripts/codex_memory_migrator.py rewrite \
  --root ~/codex-memory-export/codex-home \
  --map /Users/oldname=/Users/newname
```

Finally copy the rewritten snapshot into the target Codex home:

```bash
rsync -a ~/codex-memory-export/codex-home/ ~/.codex/
```

## Install the skill

Copy or symlink the skill directory into your Codex skills directory:

```bash
mkdir -p ~/.codex/skills
ln -s /absolute/path/to/codex-memory-migrator/skill/codex-memory-migrator \
  ~/.codex/skills/codex-memory-migrator
```

Then invoke it in Codex with:

```text
Use $codex-memory-migrator to export my Codex data and prepare it for another machine.
```

## Safety notes

- Close Codex before exporting if you want the cleanest SQLite snapshot.
- Run `rewrite` on a copied snapshot, not on your live `~/.codex`.
- Prefer preserving the old directory layout when possible. Rewriting is best-effort.
- Export skips `.tmp/` and `tmp/` by default because they are volatile caches, not durable chat history.
- The SQLite rewrite only updates text columns. It does not mutate binary blobs.

## License

MIT
