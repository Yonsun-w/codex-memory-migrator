import { cpSync, chmodSync, lstatSync, mkdirSync, readFileSync, readlinkSync, readdirSync, rmSync, statSync, symlinkSync, unlinkSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { basename, dirname, extname, join, resolve } from "node:path";
import { DatabaseSync } from "node:sqlite";

const PATH_PATTERN = /(?:^|[\s"'(<\[{:,;])((?:\/(?:Users|home|Volumes|private|tmp|var|mnt|opt))[^\\\s"'<>()[\]{}:,;]+)/g;
const TEXT_SUFFIXES = new Set(["", ".json", ".jsonl", ".md", ".toml", ".txt", ".yaml", ".yml", ".rules", ".log"]);
const SQLITE_SUFFIXES = new Set([".sqlite", ".db", ".sqlite3"]);
const DEFAULT_EXCLUDED_DIRS = new Set([".tmp", "tmp", "__pycache__", "node_modules", ".git"]);
const SKILL_DIR = resolve(dirname(new URL(import.meta.url).pathname), "../skill/codex-memory-migrator");
const BIN_SCRIPT = resolve(dirname(new URL(import.meta.url).pathname), "../bin/codex-memory-migrator.js");
export const DEFAULT_COMMAND_NAMES = ["codex-memory-migrator", "fix-codex-paths", "migrate-codex-memory"];

function decodeFileUrlPath(value) {
  return decodeURIComponent(value);
}

const SKILL_DIR_PATH = decodeFileUrlPath(SKILL_DIR);
const BIN_SCRIPT_PATH = decodeFileUrlPath(BIN_SCRIPT);

export function utcNow() {
  return new Date().toISOString();
}

export function expandPath(value) {
  const expanded = value.startsWith("~/") ? join(homedir(), value.slice(2)) : value === "~" ? homedir() : value;
  return resolve(expanded);
}

export function posixPath(value) {
  return String(value).replaceAll("\\", "/");
}

export function parseMapping(raw) {
  const separatorIndex = raw.indexOf("=");
  if (separatorIndex < 1) {
    throw new Error(`Invalid mapping '${raw}'. Expected OLD=NEW.`);
  }
  return [raw.slice(0, separatorIndex), raw.slice(separatorIndex + 1)];
}

export function homePrefix(pathText) {
  const normalized = posixPath(pathText).replace(/\/+$/, "");
  const parts = normalized.split("/").filter(Boolean);
  if (parts.length >= 2 && (parts[0] === "Users" || parts[0] === "home")) {
    return `/${parts[0]}/${parts[1]}`;
  }
  return null;
}

export function summarizePrefix(rawPath) {
  const normalized = posixPath(rawPath).replace(/\/+$/, "");
  const parts = normalized.split("/").filter(Boolean);
  if (parts.length >= 2 && (parts[0] === "Users" || parts[0] === "home")) {
    return `/${parts[0]}/${parts[1]}`;
  }
  if (parts.length >= 1) {
    return `/${parts[0]}`;
  }
  return normalized;
}

function fileSize(path) {
  try {
    return statSync(path).size;
  } catch {
    return 0;
  }
}

function isTextSuffix(path) {
  return TEXT_SUFFIXES.has(extname(path).toLowerCase());
}

function isSqliteFile(path) {
  return SQLITE_SUFFIXES.has(extname(path).toLowerCase());
}

export function isProbablyTextFile(path) {
  if (isSqliteFile(path)) {
    return false;
  }
  if (isTextSuffix(path)) {
    return true;
  }
  try {
    const sample = readFileSync(path);
    return !sample.subarray(0, 8192).includes(0);
  } catch {
    return false;
  }
}

export function *iterFiles(root, excludedDirs = DEFAULT_EXCLUDED_DIRS) {
  for (const entry of readdirSync(root, { withFileTypes: true })) {
    const fullPath = join(root, entry.name);
    if (entry.isDirectory()) {
      if (!excludedDirs.has(entry.name)) {
        yield *iterFiles(fullPath, excludedDirs);
      }
      continue;
    }
    if (entry.isFile()) {
      yield fullPath;
    }
  }
}

export function collectTextPathHits(root) {
  const prefixes = new Map();
  let filesScanned = 0;

  for (const path of iterFiles(root)) {
    if (!isProbablyTextFile(path)) {
      continue;
    }

    filesScanned += 1;
    let content = "";
    try {
      content = readFileSync(path, "utf8");
    } catch {
      continue;
    }

    for (const match of content.matchAll(PATH_PATTERN)) {
      const prefix = summarizePrefix(match[1]);
      prefixes.set(prefix, (prefixes.get(prefix) || 0) + 1);
    }
  }

  return { prefixes, filesScanned };
}

export function listSqliteFiles(root) {
  return [...iterFiles(root)].filter((path) => isSqliteFile(path));
}

export function scanSummary(root, topN = 20) {
  const { prefixes, filesScanned } = collectTextPathHits(root);
  const topPathPrefixes = [...prefixes.entries()].sort((a, b) => b[1] - a[1]).slice(0, topN);
  const allFiles = [...iterFiles(root)];

  return {
    generated_at: utcNow(),
    root,
    text_files_scanned: filesScanned,
    sqlite_files: listSqliteFiles(root),
    top_path_prefixes: topPathPrefixes,
    file_count: allFiles.length,
    total_size_bytes: allFiles.reduce((sum, path) => sum + fileSize(path), 0)
  };
}

export function exportSnapshot(codexHome, outputDir, force = false, topN = 20) {
  mkdirSync(outputDir, { recursive: true });
  const snapshotDir = join(outputDir, "codex-home");

  if (existsAndNotEmpty(outputDir) && !force && !existsAndNotEmpty(snapshotDir)) {
    const manifestPath = join(outputDir, "manifest.json");
    if (!isPathEmpty(manifestPath)) {
      throw new Error(`Output directory '${outputDir}' is not empty. Use --force to continue.`);
    }
  }

  if (existsAndNotEmpty(snapshotDir)) {
    if (!force) {
      throw new Error(`Snapshot directory '${snapshotDir}' already exists. Use --force to continue.`);
    }
    rmSync(snapshotDir, { recursive: true, force: true });
  }

  cpSync(codexHome, snapshotDir, {
    recursive: true,
    verbatimSymlinks: true,
    filter(source) {
      const name = basename(source);
      if (DEFAULT_EXCLUDED_DIRS.has(name)) {
        try {
          return !lstatSync(source).isDirectory();
        } catch {
          return false;
        }
      }
      return true;
    }
  });

  const manifest = {
    schema_version: 1,
    created_at: utcNow(),
    source_codex_home: codexHome,
    snapshot_dir: snapshotDir,
    scan: scanSummary(snapshotDir, topN)
  };
  const manifestPath = join(outputDir, "manifest.json");
  writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");

  return { exported_to: snapshotDir, manifest: manifestPath };
}

function existsAndNotEmpty(path) {
  try {
    const stats = lstatSync(path);
    if (stats.isDirectory()) {
      return readdirSync(path).length > 0;
    }
    return true;
  } catch {
    return false;
  }
}

function isPathEmpty(path) {
  try {
    const stats = lstatSync(path);
    return stats.isDirectory() ? readdirSync(path).length === 0 : false;
  } catch {
    return true;
  }
}

export function loadManifest(manifestPath) {
  return JSON.parse(readFileSync(manifestPath, "utf8"));
}

export function inferMappingsFromManifest(manifest, targetHome) {
  const suggestions = [];
  const targetHomeText = posixPath(targetHome);

  if (typeof manifest.source_codex_home === "string") {
    const sourceHome = homePrefix(dirname(posixPath(manifest.source_codex_home)));
    if (sourceHome && sourceHome !== targetHomeText) {
      suggestions.push([sourceHome, targetHomeText]);
    }
  }

  for (const item of manifest.scan?.top_path_prefixes || []) {
    const prefix = item[0];
    if (typeof prefix !== "string") {
      continue;
    }
    const sourceHome = homePrefix(prefix);
    if (sourceHome && sourceHome !== targetHomeText) {
      suggestions.push([sourceHome, targetHomeText]);
    }
  }

  const seen = new Set();
  return suggestions.filter(([oldPrefix, newPrefix]) => {
    const key = `${oldPrefix}=>${newPrefix}`;
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

export function resolveMappings(rawMappings, manifestPath, targetHome) {
  if (rawMappings.length > 0) {
    return rawMappings.map(parseMapping).sort((a, b) => b[0].length - a[0].length);
  }
  if (manifestPath) {
    const inferred = inferMappingsFromManifest(loadManifest(manifestPath), targetHome);
    if (inferred.length > 0) {
      return inferred.sort((a, b) => b[0].length - a[0].length);
    }
  }
  throw new Error("No mappings available. Pass --map OLD=NEW or provide --manifest.");
}

export function replaceTextContent(content, mappings) {
  let replacements = 0;
  let updated = content;
  for (const [oldValue, newValue] of mappings) {
    const count = updated.split(oldValue).length - 1;
    if (count > 0) {
      updated = updated.split(oldValue).join(newValue);
      replacements += count;
    }
  }
  return { updated, replacements };
}

export function rewriteTextFiles(root, mappings, dryRun = false) {
  const stats = {
    text_files_changed: 0,
    text_replacements: 0
  };

  for (const path of iterFiles(root)) {
    if (!isProbablyTextFile(path)) {
      continue;
    }

    let content = "";
    try {
      content = readFileSync(path, "utf8");
    } catch {
      continue;
    }

    const { updated, replacements } = replaceTextContent(content, mappings);
    if (replacements === 0) {
      continue;
    }

    stats.text_files_changed += 1;
    stats.text_replacements += replacements;
    if (!dryRun) {
      writeFileSync(path, updated, "utf8");
    }
  }

  return stats;
}

function sqliteTables(db) {
  return db.prepare("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'").all().map((row) => row.name);
}

function textColumns(db, table) {
  return db.prepare(`PRAGMA table_info("${table.replaceAll("\"", "\"\"")}")`).all()
    .filter((row) => String(row.type || "").toUpperCase().match(/CHAR|CLOB|TEXT/))
    .map((row) => row.name);
}

export function rewriteSqliteFile(path, mappings, dryRun = false) {
  const db = new DatabaseSync(path);
  let changed = false;
  let totalReplacements = 0;

  try {
    db.exec("PRAGMA busy_timeout = 3000");
    db.exec("BEGIN");

    for (const table of sqliteTables(db)) {
      for (const column of textColumns(db, table)) {
        const safeTable = `"${String(table).replaceAll("\"", "\"\"")}"`;
        const safeColumn = `"${String(column).replaceAll("\"", "\"\"")}"`;
        for (const [oldValue, newValue] of mappings) {
          const countStatement = db.prepare(
            `SELECT COUNT(*) AS count FROM ${safeTable} WHERE typeof(${safeColumn}) = 'text' AND instr(${safeColumn}, ?) > 0`
          );
          const count = countStatement.get(oldValue).count;
          if (count > 0) {
            changed = true;
            totalReplacements += count;
            if (!dryRun) {
              const updateStatement = db.prepare(
                `UPDATE ${safeTable} SET ${safeColumn} = replace(${safeColumn}, ?, ?) WHERE typeof(${safeColumn}) = 'text' AND instr(${safeColumn}, ?) > 0`
              );
              updateStatement.run(oldValue, newValue, oldValue);
            }
          }
        }
      }
    }

    db.exec(dryRun ? "ROLLBACK" : "COMMIT");
  } finally {
    db.close();
  }

  return { changed, replacements: totalReplacements };
}

export function rewriteSqliteFiles(root, mappings, dryRun = false) {
  const stats = {
    sqlite_files_changed: 0,
    sqlite_replacements: 0
  };

  for (const path of listSqliteFiles(root)) {
    const { changed, replacements } = rewriteSqliteFile(path, mappings, dryRun);
    if (changed) {
      stats.sqlite_files_changed += 1;
      stats.sqlite_replacements += replacements;
    }
  }

  return stats;
}

export function planSummary(manifestPath, targetHome) {
  const manifest = loadManifest(manifestPath);
  const suggestedMappings = inferMappingsFromManifest(manifest, targetHome).map(([oldValue, newValue]) => ({
    old: oldValue,
    new: newValue
  }));
  const snapshotDir = manifest.snapshot_dir || null;

  return {
    generated_at: utcNow(),
    manifest: manifestPath,
    target_home: targetHome,
    source_codex_home: manifest.source_codex_home || null,
    snapshot_dir: snapshotDir,
    suggested_mappings: suggestedMappings,
    top_path_prefixes: manifest.scan?.top_path_prefixes || [],
    recommended_next_step: snapshotDir && suggestedMappings.length > 0 ? "rewrite-exported-snapshot" : "manual-review",
    rewrite_example: snapshotDir ? `codex-memory-migrator rewrite --root ${snapshotDir} --manifest ${manifestPath}` : null
  };
}

export function removeExistingTarget(path) {
  try {
    const stats = lstatSync(path);
    if (stats.isDirectory() && !stats.isSymbolicLink()) {
      rmSync(path, { recursive: true, force: true });
      return;
    }
    unlinkSync(path);
  } catch {
  }
}

export function installSkill(skillsDir, force = false, copyMode = false) {
  mkdirSync(skillsDir, { recursive: true });
  const target = join(skillsDir, basename(SKILL_DIR_PATH));

  if (existsAndNotEmpty(target) || isSymlink(target)) {
    if (isSymlink(target) && resolve(readlinkSafe(target)) === resolve(SKILL_DIR_PATH)) {
      return target;
    }
    if (!force) {
      throw new Error(`Skill target '${target}' already exists. Use --force to replace it.`);
    }
    removeExistingTarget(target);
  }

  if (copyMode) {
    cpSync(SKILL_DIR_PATH, target, { recursive: true, verbatimSymlinks: true });
  } else {
    symlinkSync(SKILL_DIR_PATH, target, "dir");
  }
  return target;
}

function isSymlink(path) {
  try {
    return lstatSync(path).isSymbolicLink();
  } catch {
    return false;
  }
}

function readlinkSafe(path) {
  try {
    return lstatSync(path).isSymbolicLink() ? resolve(dirname(path), readlinkSync(path)) : path;
  } catch {
    return path;
  }
}

export function commandWrapperText() {
  return `#!/bin/sh\nexec node "${BIN_SCRIPT_PATH}" "$@"\n`;
}

export function installCommands(binDir, force = false, commandNames = DEFAULT_COMMAND_NAMES) {
  mkdirSync(binDir, { recursive: true });
  const wrapper = commandWrapperText();
  const installed = [];

  for (const name of commandNames) {
    const target = join(binDir, name);
    if (existsAndNotEmpty(target) || isSymlink(target)) {
      try {
        if (readFileSync(target, "utf8") === wrapper) {
          installed.push(target);
          continue;
        }
      } catch {
      }
      if (!force) {
        throw new Error(`Command target '${target}' already exists. Use --force to replace it.`);
      }
      removeExistingTarget(target);
    }
    writeFileSync(target, wrapper, "utf8");
    chmodSync(target, 0o755);
    installed.push(target);
  }

  return installed;
}

export function pathContains(directory) {
  const resolved = resolve(directory);
  return process.env.PATH?.split(":").some((entry) => {
    if (!entry) {
      return false;
    }
    try {
      return resolve(expandPath(entry)) === resolved;
    } catch {
      return false;
    }
  }) || false;
}

function requireOption(options, key, label) {
  if (!options[key]) {
    throw new Error(`Missing required option ${label}.`);
  }
}

export async function commandScan(options) {
  return scanSummary(expandPath(options.codexHome || "~/.codex"), Number(options.top || 20));
}

export async function commandExport(options) {
  requireOption(options, "outputDir", "--output-dir");
  return exportSnapshot(
    expandPath(options.codexHome || "~/.codex"),
    expandPath(options.outputDir),
    Boolean(options.force),
    Number(options.top || 20)
  );
}

export async function commandPlan(options) {
  requireOption(options, "manifest", "--manifest");
  return planSummary(expandPath(options.manifest), expandPath(options.targetHome || "~"));
}

export async function commandRewrite(options) {
  requireOption(options, "root", "--root");
  const root = expandPath(options.root);
  const mappings = resolveMappings(options.map || [], options.manifest ? expandPath(options.manifest) : null, expandPath(options.targetHome || "~"));
  const textStats = rewriteTextFiles(root, mappings, Boolean(options.dryRun));
  const sqliteStats = rewriteSqliteFiles(root, mappings, Boolean(options.dryRun));

  return {
    root,
    dry_run: Boolean(options.dryRun),
    mappings: mappings.map(([oldValue, newValue]) => ({ old: oldValue, new: newValue })),
    ...textStats,
    ...sqliteStats
  };
}

export async function commandInstallSkill(options) {
  const target = installSkill(expandPath(options.skillsDir || "~/.codex/skills"), Boolean(options.force), Boolean(options.copy));
  return {
    installed_to: target,
    source: SKILL_DIR_PATH,
    mode: options.copy ? "copy" : "symlink"
  };
}

export async function commandInstallCommands(options) {
  const binDir = expandPath(options.binDir || "~/.local/bin");
  const commandNames = options.commandName?.length ? options.commandName : DEFAULT_COMMAND_NAMES;
  const commands = installCommands(binDir, Boolean(options.force), commandNames);
  return {
    bin_dir: binDir,
    commands,
    bin_dir_on_path: pathContains(binDir)
  };
}

export async function commandInstall(options) {
  if (options.skillOnly && options.commandsOnly) {
    throw new Error("--skill-only and --commands-only cannot be used together.");
  }

  const result = {};
  if (!options.commandsOnly) {
    result.skill = await commandInstallSkill(options);
  }
  if (!options.skillOnly) {
    result.commands = await commandInstallCommands(options);
  }
  return result;
}

function optionKey(flag) {
  return flag.replace(/^--/, "").replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
}

export function parseCliArgs(argv) {
  const result = {
    command: null,
    options: {
      map: [],
      commandName: []
    },
    help: false
  };

  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (index === 0 && !value.startsWith("-")) {
      result.command = value;
      continue;
    }

    if (value === "-h" || value === "--help") {
      result.help = true;
      continue;
    }

    if (value.startsWith("--")) {
      const key = optionKey(value);
      const nextValue = argv[index + 1];
      if (nextValue && !nextValue.startsWith("--")) {
        if (key === "map" || key === "commandName") {
          result.options[key].push(nextValue);
        } else {
          result.options[key] = nextValue;
        }
        index += 1;
      } else {
        result.options[key] = true;
      }
      continue;
    }

    throw new Error(`Unexpected argument '${value}'.`);
  }

  return result;
}

export function buildHelpText() {
  return `codex-memory-migrator

Modern Node CLI for moving Codex state across machines.

Commands:
  install            Install the skill and local command aliases
  scan               Inspect a Codex home and summarize absolute paths
  export             Copy a Codex home into a portable snapshot
  plan               Read a manifest and suggest rewrite mappings
  rewrite            Rewrite copied paths in text files and SQLite
  install-skill      Install the Codex skill only
  install-commands   Install local shell command aliases only

Examples:
  codex-memory-migrator install
  fix-codex-paths export --codex-home ~/.codex --output-dir ~/codex-memory-export
  migrate-codex-memory plan --manifest ~/codex-memory-export/manifest.json
  codex-memory-migrator rewrite --root ~/codex-memory-export/codex-home --manifest ~/codex-memory-export/manifest.json`;
}
