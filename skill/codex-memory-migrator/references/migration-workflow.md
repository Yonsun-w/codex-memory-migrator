# Migration Workflow

## When to use this skill

Use this skill when you need to move a local Codex home to another machine and one of these is true:

- the target machine uses a different username or home directory
- historical sessions reference local project paths that moved
- you want a repeatable export-and-rewrite workflow instead of ad hoc copy commands

## Core steps

1. Run `scan` against the source `~/.codex`.
2. Run `export` to copy the whole Codex home into a bundle directory.
3. Transfer the bundle directory to the target machine.
4. Run `rewrite` with one or more `OLD=NEW` path mappings.
5. Copy the rewritten `codex-home/` contents into the target `~/.codex`.

## Example mappings

```text
/Users/yonsun=/Users/alice
/Users/yonsun/wjh_sum=/Users/alice/work/wjh_sum
```

Mappings are applied in the order you pass them. Put more specific mappings first.

## What gets rewritten

- text files under the copied Codex home
- SQLite text columns inside `*.sqlite`

## What gets skipped by default during export

- `.tmp/`
- `tmp/`

These are volatile cache directories and are not required for preserving durable Codex conversations.

## What does not get copied automatically

- your original source repositories outside the exported Codex home
- API keys or shell environment from the other machine unless they were already stored in local files

If you want old sessions to open the same workspaces cleanly, copy the referenced repositories separately.
