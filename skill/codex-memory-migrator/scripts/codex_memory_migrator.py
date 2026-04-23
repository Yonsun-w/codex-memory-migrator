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
SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPT_PATH = Path(__file__).resolve()
DEFAULT_COMMAND_NAMES = ("codex-memory-migrator", "fix-codex-paths", "migrate-codex-memory")


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


def posix_path(value: str | os.PathLike[str]) -> str:
    return PurePosixPath(os.fspath(value)).as_posix()


def summarize_prefix(raw_path: str) -> str:
    raw_path = raw_path.rstrip("/")
    parts = list(PurePosixPath(raw_path).parts)
    if len(parts) >= 3 and parts[1] in {"Users", "home"}:
        return str(PurePosixPath(*parts[:3]))
    if len(parts) >= 2:
        return str(PurePosixPath(*parts[:2]))
    return raw_path


def home_prefix(path_text: str) -> str | None:
    parts = list(PurePosixPath(path_text).parts)
    if len(parts) >= 3 and parts[1] in {"Users", "home"}:
        return str(PurePosixPath(*parts[:3]))
    return None


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


def load_manifest(manifest_path: Path) -> dict:
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"Manifest '{manifest_path}' does not exist.") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Manifest '{manifest_path}' is not valid JSON: {exc}") from exc


def infer_mappings_from_manifest(manifest: dict, target_home: Path) -> list[tuple[str, str]]:
    suggestions: list[tuple[str, str]] = []
    target_home_text = posix_path(target_home)

    source_codex_home = manifest.get("source_codex_home")
    if isinstance(source_codex_home, str):
        source_home = home_prefix(posix_path(Path(source_codex_home).parent))
        if source_home and source_home != target_home_text:
            suggestions.append((source_home, target_home_text))

    scan = manifest.get("scan") or {}
    for item in scan.get("top_path_prefixes") or []:
        if not isinstance(item, list) or not item:
            continue
        prefix = item[0]
        if not isinstance(prefix, str):
            continue
        source_home = home_prefix(prefix)
        if source_home and source_home != target_home_text:
            suggestions.append((source_home, target_home_text))

    unique: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for old, new in suggestions:
        pair = (old.rstrip("/"), new.rstrip("/"))
        if pair not in seen:
            seen.add(pair)
            unique.append(pair)
    return unique


def resolve_mappings(raw_mappings: list[str], manifest_path: str | None, target_home: str | None) -> list[tuple[str, str]]:
    mappings = [parse_mapping(item) for item in raw_mappings]
    if mappings:
        return sorted(mappings, key=lambda item: len(item[0]), reverse=True)

    if manifest_path:
        manifest = load_manifest(expand_path(manifest_path))
        inferred = infer_mappings_from_manifest(manifest, expand_path(target_home or "~"))
        if inferred:
            return sorted(inferred, key=lambda item: len(item[0]), reverse=True)

    raise SystemExit(
        "No mappings available. Pass --map OLD=NEW or provide --manifest so the tool can infer a home-directory rewrite."
    )


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


def plan_summary(manifest_path: Path, target_home: Path) -> dict:
    manifest = load_manifest(manifest_path)
    inferred = infer_mappings_from_manifest(manifest, target_home)
    snapshot_dir = manifest.get("snapshot_dir")
    next_step = "manual-review"
    if snapshot_dir and inferred:
        next_step = "rewrite-exported-snapshot"
    elif snapshot_dir:
        next_step = "rewrite-with-manual-mapping"

    return {
        "generated_at": utc_now(),
        "manifest": str(manifest_path),
        "target_home": str(target_home),
        "source_codex_home": manifest.get("source_codex_home"),
        "snapshot_dir": snapshot_dir,
        "suggested_mappings": [{"old": old, "new": new} for old, new in inferred],
        "top_path_prefixes": (manifest.get("scan") or {}).get("top_path_prefixes", []),
        "recommended_next_step": next_step,
        "rewrite_example": (
            f"python3 {SKILL_DIR / 'scripts' / 'codex_memory_migrator.py'} rewrite "
            f"--root {snapshot_dir} --manifest {manifest_path}"
            if snapshot_dir
            else None
        ),
    }


def remove_existing_target(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def install_skill(skills_dir: Path, force: bool, copy_mode: bool) -> Path:
    skills_dir.mkdir(parents=True, exist_ok=True)
    target = skills_dir / SKILL_DIR.name

    if target.exists() or target.is_symlink():
        if target.is_symlink() and target.resolve() == SKILL_DIR.resolve():
            return target
        if not force:
            raise SystemExit(f"Skill target '{target}' already exists. Use --force to replace it.")
        remove_existing_target(target)

    if copy_mode:
        shutil.copytree(SKILL_DIR, target, symlinks=True)
    else:
        target.symlink_to(SKILL_DIR, target_is_directory=True)
    return target


def command_wrapper_text() -> str:
    return (
        "#!/bin/sh\n"
        f'exec python3 "{SCRIPT_PATH}" "$@"\n'
    )


def install_commands(bin_dir: Path, force: bool, command_names: Iterable[str]) -> list[Path]:
    bin_dir.mkdir(parents=True, exist_ok=True)
    installed: list[Path] = []
    wrapper_text = command_wrapper_text()

    for name in command_names:
        target = bin_dir / name
        if target.exists() or target.is_symlink():
            if target.is_file():
                try:
                    if target.read_text(encoding="utf-8") == wrapper_text:
                        installed.append(target)
                        continue
                except OSError:
                    pass
            if not force:
                raise SystemExit(f"Command target '{target}' already exists. Use --force to replace it.")
            remove_existing_target(target)

        target.write_text(wrapper_text, encoding="utf-8")
        target.chmod(0o755)
        installed.append(target)

    return installed


def path_contains(directory: Path) -> bool:
    resolved_dir = directory.resolve()
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry:
            continue
        try:
            if Path(entry).expanduser().resolve() == resolved_dir:
                return True
        except OSError:
            continue
    return False


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
    ordered_mappings = resolve_mappings(args.map, args.manifest, args.target_home)
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


def command_plan(args: argparse.Namespace) -> int:
    summary = plan_summary(expand_path(args.manifest), expand_path(args.target_home))
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def command_install_skill(args: argparse.Namespace) -> int:
    skills_dir = expand_path(args.skills_dir)
    target = install_skill(skills_dir, args.force, args.copy)
    print(
        json.dumps(
            {
                "installed_to": str(target),
                "source": str(SKILL_DIR),
                "mode": "copy" if args.copy else "symlink",
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def command_install_commands(args: argparse.Namespace) -> int:
    bin_dir = expand_path(args.bin_dir)
    command_names = args.command_name or list(DEFAULT_COMMAND_NAMES)
    installed = install_commands(bin_dir, args.force, command_names)
    print(
        json.dumps(
            {
                "bin_dir": str(bin_dir),
                "commands": [str(path) for path in installed],
                "bin_dir_on_path": path_contains(bin_dir),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def command_install(args: argparse.Namespace) -> int:
    if args.skill_only and args.commands_only:
        raise SystemExit("--skill-only and --commands-only cannot be used together.")

    result: dict[str, object] = {}

    if not args.commands_only:
        skills_dir = expand_path(args.skills_dir)
        skill_target = install_skill(skills_dir, args.force, args.copy)
        result["skill"] = {
            "installed_to": str(skill_target),
            "source": str(SKILL_DIR),
            "mode": "copy" if args.copy else "symlink",
        }

    if not args.skill_only:
        bin_dir = expand_path(args.bin_dir)
        command_names = args.command_name or list(DEFAULT_COMMAND_NAMES)
        installed = install_commands(bin_dir, args.force, command_names)
        result["commands"] = {
            "bin_dir": str(bin_dir),
            "installed": [str(path) for path in installed],
            "bin_dir_on_path": path_contains(bin_dir),
        }

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export, plan, rewrite, and install a Codex migration skill for moving state across machines."
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

    install_parser = subparsers.add_parser(
        "install", help="Install the skill and local command aliases in one step."
    )
    install_parser.add_argument(
        "--skills-dir",
        default="~/.codex/skills",
        help="Destination Codex skills directory. Defaults to ~/.codex/skills.",
    )
    install_parser.add_argument(
        "--bin-dir",
        default="~/.local/bin",
        help="Directory for local command aliases. Defaults to ~/.local/bin.",
    )
    install_parser.add_argument(
        "--command-name",
        action="append",
        default=[],
        help="Command name to install. Can be repeated. Defaults to several aliases.",
    )
    install_parser.add_argument("--copy", action="store_true", help="Copy the skill instead of creating a symlink.")
    install_parser.add_argument("--force", action="store_true", help="Replace existing install targets.")
    install_parser.add_argument("--skill-only", action="store_true", help="Install only the skill.")
    install_parser.add_argument("--commands-only", action="store_true", help="Install only command aliases.")
    install_parser.set_defaults(func=command_install)

    plan_parser = subparsers.add_parser(
        "plan", help="Read an export manifest and suggest rewrite mappings for the current machine."
    )
    plan_parser.add_argument("--manifest", required=True, help="Path to the export manifest.json.")
    plan_parser.add_argument(
        "--target-home",
        default=str(Path.home()),
        help="Home directory on the target machine. Defaults to the current user's home.",
    )
    plan_parser.set_defaults(func=command_plan)

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
    rewrite_parser.add_argument("--manifest", help="Optional export manifest.json used to infer a home-directory mapping.")
    rewrite_parser.add_argument(
        "--target-home",
        default=str(Path.home()),
        help="Target home directory used with --manifest. Defaults to the current user's home.",
    )
    rewrite_parser.add_argument("--dry-run", action="store_true", help="Show what would change without writing.")
    rewrite_parser.set_defaults(func=command_rewrite)

    install_parser = subparsers.add_parser(
        "install-skill", help="Install this skill into a local Codex skills directory."
    )
    install_parser.add_argument(
        "--skills-dir",
        default="~/.codex/skills",
        help="Destination Codex skills directory. Defaults to ~/.codex/skills.",
    )
    install_parser.add_argument("--copy", action="store_true", help="Copy the skill instead of creating a symlink.")
    install_parser.add_argument("--force", action="store_true", help="Replace an existing installation target.")
    install_parser.set_defaults(func=command_install_skill)

    commands_parser = subparsers.add_parser(
        "install-commands", help="Install local command aliases that run this script directly."
    )
    commands_parser.add_argument(
        "--bin-dir",
        default="~/.local/bin",
        help="Directory for local command aliases. Defaults to ~/.local/bin.",
    )
    commands_parser.add_argument(
        "--command-name",
        action="append",
        default=[],
        help="Command name to install. Can be repeated. Defaults to several aliases.",
    )
    commands_parser.add_argument("--force", action="store_true", help="Replace an existing command target.")
    commands_parser.set_defaults(func=command_install_commands)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
