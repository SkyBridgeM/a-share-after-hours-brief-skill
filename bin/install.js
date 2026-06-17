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
  "examples",
  "references",
  "schemas",
  "scripts",
];

function usage() {
  console.log(`Usage:
  a-share-after-hours-brief-skill install [--target <dir>] [--force] [--no-backup]
  a-share-after-hours-brief-skill --dry-run

Options:
  --target <dir>  Skills root directory. Default: $CODEX_HOME/skills or ~/.codex/skills
  --force         Overwrite existing ${SKILL_NAME} installation after creating a timestamped backup
  --no-backup     With --force, overwrite without creating a backup
  --dry-run       Validate package contents without copying
`);
}

function parseArgs(argv) {
  const args = {
    command: "install",
    target: null,
    force: false,
    backup: true,
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
    } else if (arg === "--no-backup") {
      args.backup = false;
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
  const stat = fs.lstatSync(src);
  if (stat.isSymbolicLink()) {
    throw new Error(`Refusing to copy symlink: ${src}`);
  }
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

function timestamp() {
  return new Date().toISOString()
    .replace(/[-:]/g, "")
    .replace(/\..+$/, "")
    .replace("T", "-");
}

function ensureInstallDestination(skillsRoot, installDir) {
  if (path.basename(installDir) !== SKILL_NAME) {
    throw new Error(`Install destination must end with ${SKILL_NAME}`);
  }
  const relative = path.relative(skillsRoot, installDir);
  if (relative !== SKILL_NAME || relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error(`Install destination is outside the target skills root: ${installDir}`);
  }
}

function prepareOverwrite(installDir, { force, backup }) {
  if (!fs.existsSync(installDir)) {
    return null;
  }
  if (!force) {
    throw new Error(`${installDir} already exists. Re-run with --force to overwrite.`);
  }
  const existing = fs.lstatSync(installDir);
  if (backup) {
    const backupDir = path.join(
      path.dirname(installDir),
      `${SKILL_NAME}.backup-${timestamp()}`,
    );
    fs.renameSync(installDir, backupDir);
    return backupDir;
  }
  fs.rmSync(installDir, {
    recursive: existing.isDirectory() && !existing.isSymbolicLink(),
    force: true,
  });
  return null;
}

function install({ target, force, backup, dryRun }) {
  if (backup === false && !force) {
    throw new Error("--no-backup can only be used with --force");
  }
  const root = packageRoot();
  validatePackage(root);
  if (dryRun) {
    console.log(`Dry run OK: package contains ${SKILL_NAME}`);
    return;
  }

  const skillsRoot = path.resolve(target || defaultSkillsRoot());
  const installDir = path.join(skillsRoot, SKILL_NAME);
  ensureInstallDestination(skillsRoot, installDir);

  fs.mkdirSync(skillsRoot, { recursive: true });
  const backupDir = prepareOverwrite(installDir, { force, backup });
  fs.mkdirSync(installDir, { recursive: true });

  for (const entry of REQUIRED_ENTRIES) {
    copyRecursive(path.join(root, entry), path.join(installDir, entry));
  }

  console.log(`Installed ${SKILL_NAME} to ${installDir}`);
  if (backupDir) {
    console.log(`Previous installation backed up to ${backupDir}`);
  }
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
