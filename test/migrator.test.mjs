import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import {
  DEFAULT_COMMAND_NAMES,
  inferMappingsFromManifest,
  installCommands,
  parseCliArgs,
  replaceTextContent
} from "../lib/migrator.js";

test("inferMappingsFromManifest infers home rewrite", () => {
  const manifest = {
    source_codex_home: "/Users/olduser/.codex",
    scan: {
      top_path_prefixes: [["/Users/olduser/project-a", 3]]
    }
  };

  const result = inferMappingsFromManifest(manifest, "/Users/newuser");

  assert.deepEqual(result, [["/Users/olduser", "/Users/newuser"]]);
});

test("replaceTextContent rewrites every occurrence", () => {
  const result = replaceTextContent(
    "/Users/olduser/work and /Users/olduser/code",
    [["/Users/olduser", "/Users/newuser"]]
  );

  assert.equal(result.replacements, 2);
  assert.equal(result.updated, "/Users/newuser/work and /Users/newuser/code");
});

test("installCommands writes default wrappers", () => {
  const tempRoot = mkdtempSync(join(tmpdir(), "codex-memory-migrator-"));
  const binDir = join(tempRoot, "bin");

  const installed = installCommands(binDir, false, DEFAULT_COMMAND_NAMES);

  assert.deepEqual(installed.map((path) => path.split("/").at(-1)), DEFAULT_COMMAND_NAMES);
  for (const file of installed) {
    assert.match(readFileSync(file, "utf8"), /codex-memory-migrator\.js/);
  }
});

test("parseCliArgs collects repeated options", () => {
  const parsed = parseCliArgs([
    "rewrite",
    "--root", "~/codex-memory-export/codex-home",
    "--map", "/Users/a=/Users/b",
    "--map", "/Users/a/work=/Users/b/work"
  ]);

  assert.equal(parsed.command, "rewrite");
  assert.deepEqual(parsed.options.map, ["/Users/a=/Users/b", "/Users/a/work=/Users/b/work"]);
});
