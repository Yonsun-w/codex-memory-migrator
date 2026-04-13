#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Iterable


PATH_PATTERN = re.compile(r"(/(?:Users|home|Volumes|private|tmp|var|mnt|opt)[^\s\"'<>()[\]{}:,;]+)")
TEXT_SUFFIXES = {
    "",
    ".json",
    ".jsonl",
    ".md",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
    ".rules",
    ".log",
}
SQLITE_SUFFIXES = {".sqlite", ".db", ".sqlite3"}
DEFAULT_EXCLUDED_DIRS = {".tmp", "tmp", "__pycache__"}


@dataclass
class RewriteStats:
    text_files_changed: int = 0
    text_replacements: int = 0
    sqlite_files_changed: int = 0
    sqlite_replacements: int = 0


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def expand_path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except FileNotFoundError:
        return 0


def is_probably_text_file(path: Path) -> bool:
    if path.suffix.lower() in SQLITE_SUFFIXES:
        return False
    if path.suffix.lower() in TEXT_SUFFIXES:
        return True
    if path.is_symlink():
        return False
    try:
        with path.open("rb") as handle:
            sample = handle.read(8192)
    except OSError:
        return False
    return b"\x00" not in sample


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def parse_mapping(raw: str) -> tuple[str, str]:
    if "=" not in raw:
        raise argparse.ArgumentTypeError(f"Invalid mapping '{raw}'. Expected OLD=NEW.")
    old, new = raw.split("=", 1)
    if not old:
        raise argparse.ArgumentTypeError("Mapping OLD path must not be empty.")
    return old, new


def summarize_prefix(raw_path: str) -> str:
    raw_path = raw_path.rstrip("/")
    parts = list(PurePosixPath(raw_path).parts)
    if len(parts) >= 3 and parts[1] in {"Users", "home"}:
        return str(PurePosixPath(*parts[:3]))
    if len(parts) >= 2:
        return str(PurePosixPath(*parts[:2]))
    return raw_path


def should_skip_dir(path: Path, excluded_dirs: set[str]) -> bool:
    return path.name in excluded_dirs


def iter_files(root: Path, excluded_dirs: set[str] | None = None) -> Iterable[Path]:
    excluded = excluded_dirs or DEFAULT_EXCLUDED_DIRS
    for dirpath, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        dirnames[:] = sorted(name for name in dirnames if name not in excluded)
        current_dir = Path(dirpath)
        for filename in sorted(filenames):
            path = current_dir / filename
            try:
                if path.is_file() and not path.is_symlink():
                    yield path
            except OSError:
                continue


def collect_text_path_hits(root: Path) -> tuple[Counter, int]:
    prefixes: Counter[str] = Counter()
    files_scanned = 0
    for path in iter_files(root):
        if not is_probably_text_file(path):
            continue
        files_scanned += 1
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for match in PATH_PATTERN.findall(content):
            prefixes[summarize_prefix(match)] += 1
    return prefixes, files_scanned


def list_sqlite_files(root: Path) -> list[Path]:
    results: list[Path] = []
    for path in iter_files(root):
        if path.suffix.lower() in SQLITE_SUFFIXES:
            results.append(path)
    return results


def scan_summary(root: Path, top_n: int) -> dict:
    prefixes, text_files_scanned = collect_text_path_hits(root)
    sqlite_files = list_sqlite_files(root)
    total_size = sum(file_size(path) for path in iter_files(root))
    return {
        "generated_at": utc_now(),
        "root": str(root),
        "text_files_scanned": text_files_scanned,
        "sqlite_files": [str(path) for path in sqlite_files],
        "top_path_prefixes": prefixes.most_common(top_n),
        "file_count": sum(1 for _ in iter_files(root)),
        "total_size_bytes": total_size,
    }


def ignore_export_dirs(_dir: str, names: list[str]) -> list[str]:
    return [name for name in names if name in DEFAULT_EXCLUDED_DIRS]


def export_snapshot(codex_home: Path, output_dir: Path, force: bool, top_n: int) -> Path:
    if output_dir.exists():
        if any(output_dir.iterdir()) and not force:
            raise SystemExit(f"Output directory '{output_dir}' is not empty. Use --force to continue.")
    else:
        output_dir.mkdir(parents=True, exist_ok=True)

    snapshot_dir = output_dir / "codex-home"
    if snapshot_dir.exists():
        if any(snapshot_dir.iterdir()) and not force:
            raise SystemExit(f"Snapshot directory '{snapshot_dir}' already exists. Use --force to continue.")
        shutil.rmtree(snapshot_dir)

    shutil.copytree(codex_home, snapshot_dir, symlinks=True, ignore=ignore_export_dirs)
    manifest = {
        "schema_version": 1,
        "created_at": utc_now(),
        "source_codex_home": str(codex_home),
        "snapshot_dir": str(snapshot_dir),
        "scan": scan_summary(snapshot_dir, top_n),
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return snapshot_dir


def replace_text_content(content: str, mappings: list[tuple[str, str]]) -> tuple[str, int]:
    replacements = 0
    updated = content
    for old, new in mappings:
        count = updated.count(old)
        if count:
            updated = updated.replace(old, new)
            replacements += count
    return updated, replacements


def rewrite_text_files(root: Path, mappings: list[tuple[str, str]], dry_run: bool) -> RewriteStats:
    stats = RewriteStats()
    for path in iter_files(root):
        if not is_probably_text_file(path):
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        updated, replacements = replace_text_content(content, mappings)
        if replacements == 0:
            continue
        stats.text_files_changed += 1
        stats.text_replacements += replacements
        if not dry_run:
            path.write_text(updated, encoding="utf-8")
    return stats


def sqlite_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return [row[0] for row in rows]


def text_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({quote_ident(table)})").fetchall()
    columns: list[str] = []
    for row in rows:
        name = row[1]
        declared_type = (row[2] or "").upper()
        if any(token in declared_type for token in ("CHAR", "CLOB", "TEXT")):
            columns.append(name)
    return columns


def rewrite_sqlite_file(path: Path, mappings: list[tuple[str, str]], dry_run: bool) -> tuple[bool, int]:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA busy_timeout = 3000")
    total_replacements = 0
    changed = False
    try:
        for table in sqlite_tables(conn):
            for column in text_columns(conn, table):
                for old, new in mappings:
                    sql = (
                        f"UPDATE {quote_ident(table)} "
                        f"SET {quote_ident(column)} = replace({quote_ident(column)}, ?, ?) "
                        f"WHERE typeof({quote_ident(column)}) = 'text' "
                        f"AND instr({quote_ident(column)}, ?) > 0"
                    )
                    if dry_run:
                        count = conn.execute(
                            f"SELECT COUNT(*) FROM {quote_ident(table)} "
                            f"WHERE typeof({quote_ident(column)}) = 'text' "
                            f"AND instr({quote_ident(column)}, ?) > 0",
                            (old,),
                        ).fetchone()[0]
                    else:
                        cursor = conn.execute(sql, (old, new, old))
                        count = cursor.rowcount if cursor.rowcount != -1 else 0
                    if count:
                        changed = True
                        total_replacements += count
        if dry_run:
            conn.rollback()
        else:
            conn.commit()
    finally:
        conn.close()
    return changed, total_replacements


def rewrite_sqlite_files(root: Path, mappings: list[tuple[str, str]], dry_run: bool) -> RewriteStats:
    stats = RewriteStats()
    for path in list_sqlite_files(root):
        changed, replacements = rewrite_sqlite_file(path, mappings, dry_run)
        if changed:
            stats.sqlite_files_changed += 1
            stats.sqlite_replacements += replacements
    return stats


def command_scan(args: argparse.Namespace) -> int:
    root = expand_path(args.codex_home)
    summary = scan_summary(root, args.top)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def command_export(args: argparse.Namespace) -> int:
    codex_home = expand_path(args.codex_home)
    output_dir = expand_path(args.output_dir)
    snapshot_dir = export_snapshot(codex_home, output_dir, args.force, args.top)
    print(json.dumps({"exported_to": str(snapshot_dir), "manifest": str(output_dir / "manifest.json")}, indent=2))
    return 0


def command_rewrite(args: argparse.Namespace) -> int:
    root = expand_path(args.root)
    mappings = [parse_mapping(item) for item in args.map]
    if not mappings:
        raise SystemExit("At least one --map OLD=NEW entry is required.")

    ordered_mappings = sorted(mappings, key=lambda item: len(item[0]), reverse=True)
    text_stats = rewrite_text_files(root, ordered_mappings, args.dry_run)
    sqlite_stats = rewrite_sqlite_files(root, ordered_mappings, args.dry_run)
    summary = {
        "root": str(root),
        "dry_run": args.dry_run,
        "mappings": [{"old": old, "new": new} for old, new in ordered_mappings],
        "text_files_changed": text_stats.text_files_changed,
        "text_replacements": text_stats.text_replacements,
        "sqlite_files_changed": sqlite_stats.sqlite_files_changed,
        "sqlite_replacements": sqlite_stats.sqlite_replacements,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export and rewrite a Codex home snapshot for migration across machines."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="Inspect a Codex home and summarize absolute paths.")
    scan_parser.add_argument("--codex-home", default="~/.codex", help="Path to the Codex home directory.")
    scan_parser.add_argument("--top", type=int, default=20, help="Number of top path prefixes to show.")
    scan_parser.set_defaults(func=command_scan)

    export_parser = subparsers.add_parser("export", help="Copy a Codex home into a portable snapshot.")
    export_parser.add_argument("--codex-home", default="~/.codex", help="Path to the Codex home directory.")
    export_parser.add_argument("--output-dir", required=True, help="Directory where the export bundle is written.")
    export_parser.add_argument("--top", type=int, default=20, help="Number of top path prefixes to store in the manifest.")
    export_parser.add_argument("--force", action="store_true", help="Overwrite an existing snapshot directory.")
    export_parser.set_defaults(func=command_export)

    rewrite_parser = subparsers.add_parser(
        "rewrite", help="Rewrite copied absolute paths inside text files and SQLite databases."
    )
    rewrite_parser.add_argument("--root", required=True, help="Root directory of the copied Codex home.")
    rewrite_parser.add_argument(
        "--map",
        action="append",
        default=[],
        metavar="OLD=NEW",
        help="Path mapping. Can be repeated. More specific mappings win.",
    )
    rewrite_parser.add_argument("--dry-run", action="store_true", help="Show what would change without writing.")
    rewrite_parser.set_defaults(func=command_rewrite)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
