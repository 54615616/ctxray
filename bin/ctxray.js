#!/usr/bin/env node
/**
 * ctxray — Node/NPX CLI wrapper (npx ctxray ...)
 * Bridges seamlessly to the zero-dependency Python engine or opens Studio directly.
 */
const { spawnSync } = require("node:child_process");
const path = require("node:path");

const entryPy = path.resolve(__dirname, "..", "ctxray.py");
const args = process.argv.slice(2);

for (const pyBin of ["python3", "python", "py"]) {
  const res = spawnSync(pyBin, [entryPy, ...args], { stdio: "inherit" });
  if (!res.error) {
    process.exit(res.status ?? 0);
  }
}

console.error("ctxray requires Python 3.9+ in PATH, or open studio/index.html directly in your browser.");
process.exit(1);
