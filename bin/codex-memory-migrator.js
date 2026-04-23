#!/usr/bin/env node

import {
  buildHelpText,
  commandExport,
  commandInstall,
  commandInstallCommands,
  commandInstallSkill,
  commandPlan,
  commandRewrite,
  commandScan,
  parseCliArgs
} from "../lib/migrator.js";

async function main() {
  try {
    const parsed = parseCliArgs(process.argv.slice(2));
    if (parsed.help || !parsed.command) {
      console.log(buildHelpText());
      process.exitCode = 0;
      return;
    }

    const commandMap = {
      scan: commandScan,
      export: commandExport,
      plan: commandPlan,
      rewrite: commandRewrite,
      install: commandInstall,
      "install-skill": commandInstallSkill,
      "install-commands": commandInstallCommands
    };

    const handler = commandMap[parsed.command];
    if (!handler) {
      throw new Error(`Unknown command '${parsed.command}'.`);
    }

    const result = await handler(parsed.options);
    if (result !== undefined) {
      console.log(JSON.stringify(result, null, 2));
    }
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  }
}

main();
