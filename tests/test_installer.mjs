import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const installer = path.join(repoRoot, "bin", "install.js");

function run(args, options = {}) {
  return execFileSync(process.execPath, [installer, ...args], {
    cwd: repoRoot,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    ...options,
  });
}

function makeTempRoot() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "a-share-installer-test-"));
}

test("dry-run validation succeeds", () => {
  const output = run(["--dry-run"]);
  assert.match(output, /Dry run OK/);
});

test("normal install copies required entries", () => {
  const target = makeTempRoot();
  run(["install", "--target", target]);
  assert.equal(fs.existsSync(path.join(target, "a-share-after-hours-brief", "SKILL.md")), true);
});

test("refuses to overwrite without --force", () => {
  const target = makeTempRoot();
  run(["install", "--target", target]);
  assert.throws(
    () => run(["install", "--target", target], { stdio: ["ignore", "pipe", "pipe"] }),
    /already exists/,
  );
});

test("force overwrite creates backup", () => {
  const target = makeTempRoot();
  run(["install", "--target", target]);
  const installed = path.join(target, "a-share-after-hours-brief");
  fs.writeFileSync(path.join(installed, "user-note.txt"), "keep me");
  const output = run(["install", "--target", target, "--force"]);
  assert.match(output, /backed up/);
  const backups = fs.readdirSync(target).filter((entry) => entry.startsWith("a-share-after-hours-brief.backup-"));
  assert.equal(backups.length, 1);
  assert.equal(fs.existsSync(path.join(target, backups[0], "user-note.txt")), true);
});

test("custom --target is honored", () => {
  const target = makeTempRoot();
  const output = run(["install", "--target", target]);
  assert.match(output, new RegExp(target.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
});

test("force --no-backup removes unexpected user files explicitly", () => {
  const target = makeTempRoot();
  run(["install", "--target", target]);
  const installed = path.join(target, "a-share-after-hours-brief");
  fs.writeFileSync(path.join(installed, "user-note.txt"), "remove me");
  run(["install", "--target", target, "--force", "--no-backup"]);
  assert.equal(fs.existsSync(path.join(installed, "user-note.txt")), false);
});
