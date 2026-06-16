#!/usr/bin/env node
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const SKILL_NAME = "a-share-after-hours-brief";
const REQUIRED_ENTRIES = [
  "SKILL.md",
  "agents",
  "assets",
  "references",
  "scripts",
];

function usage() {
  console.log(`Usage:
  a-share-after-hours-brief-skill install [--target <dir>] [--force]
  a-share-after-hours-brief-skill --dry-run

Options:
  --target <dir>  Skills root directory. Default: $CODEX_HOME/skills or ~/.codex/skills
  --force         Overwrite existing ${SKILL_NAME} installation
  --dry-run       Validate package contents without copying
`);
}

function parseArgs(argv) {
  const args = {
    command: "install",
    target: null,
    force: false,
    dryRun: false,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "install") {
      args.command = "install";
    } else if (arg === "--target") {
      const value = argv[i + 1];
      if (!value) throw new Error("--target requires a directory");
      args.target = value;
      i += 1;
    } else if (arg === "--force") {
      args.force = true;
    } else if (arg === "--dry-run") {
      args.dryRun = true;
    } else if (arg === "-h" || arg === "--help") {
      args.command = "help";
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }
  return args;
}

function packageRoot() {
  return path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
}

function defaultSkillsRoot() {
  const codexHome = process.env.CODEX_HOME;
  if (codexHome) return path.join(codexHome, "skills");
  return path.join(os.homedir(), ".codex", "skills");
}

function validatePackage(root) {
  const missing = REQUIRED_ENTRIES.filter((entry) => !fs.existsSync(path.join(root, entry)));
  if (missing.length > 0) {
    throw new Error(`Package is missing required entries: ${missing.join(", ")}`);
  }
}

function copyRecursive(src, dest) {
  const stat = fs.statSync(src);
  if (stat.isDirectory()) {
    fs.mkdirSync(dest, { recursive: true });
    for (const entry of fs.readdirSync(src)) {
      if (entry === "__pycache__") continue;
      copyRecursive(path.join(src, entry), path.join(dest, entry));
    }
    return;
  }
  fs.copyFileSync(src, dest);
}

function removeIfExists(target) {
  if (fs.existsSync(target)) {
    fs.rmSync(target, { recursive: true, force: true });
  }
}

function install({ target, force, dryRun }) {
  const root = packageRoot();
  validatePackage(root);
  if (dryRun) {
    console.log(`Dry run OK: package contains ${SKILL_NAME}`);
    return;
  }

  const skillsRoot = path.resolve(target || defaultSkillsRoot());
  const installDir = path.join(skillsRoot, SKILL_NAME);
  if (fs.existsSync(installDir) && !force) {
    throw new Error(`${installDir} already exists. Re-run with --force to overwrite.`);
  }

  fs.mkdirSync(skillsRoot, { recursive: true });
  removeIfExists(installDir);
  fs.mkdirSync(installDir, { recursive: true });

  for (const entry of REQUIRED_ENTRIES) {
    copyRecursive(path.join(root, entry), path.join(installDir, entry));
  }

  console.log(`Installed ${SKILL_NAME} to ${installDir}`);
}

try {
  const args = parseArgs(process.argv.slice(2));
  if (args.command === "help") {
    usage();
  } else {
    install(args);
  }
} catch (error) {
  console.error(`Error: ${error.message}`);
  usage();
  process.exit(1);
}
