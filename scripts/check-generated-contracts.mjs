#!/usr/bin/env node

import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { spawnSync } from "node:child_process";

const root = process.cwd();
const committed = resolve(root, "packages/contracts/src/generated/openapi.ts");
const temporaryDirectory = await mkdtemp(join(tmpdir(), "wearo-contracts-"));
const generated = join(temporaryDirectory, "openapi.ts");

try {
  const result = spawnSync(
    resolve(root, "node_modules/.bin/openapi-typescript"),
    [resolve(root, "docs/sdd/openapi.yaml"), "-o", generated],
    { cwd: root, encoding: "utf8" },
  );
  if (result.status !== 0) {
    process.stderr.write(result.stdout);
    process.stderr.write(result.stderr);
    process.exit(result.status ?? 1);
  }

  const [committedText, generatedText] = await Promise.all([
    readFile(committed, "utf8"),
    readFile(generated, "utf8"),
  ]);
  assert.equal(
    committedText,
    generatedText,
    "Generated OpenAPI types are stale. Run `pnpm generate:contracts` and commit the result.",
  );
  console.log("Generated OpenAPI contracts are synchronized.");
} finally {
  await rm(temporaryDirectory, { recursive: true, force: true });
}
