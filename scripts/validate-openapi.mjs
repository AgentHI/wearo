#!/usr/bin/env node

import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { spawnSync } from "node:child_process";

const root = process.cwd();
const contract = resolve(root, "docs/sdd/openapi.yaml");
const temporaryDirectory = await mkdtemp(join(tmpdir(), "wearo-openapi-"));
const bundledContract = join(temporaryDirectory, "openapi.json");
const httpMethods = new Set(["get", "post", "put", "patch", "delete", "options", "head"]);

try {
  const bundle = spawnSync(
    resolve(root, "node_modules/.bin/redocly"),
    ["bundle", contract, "--ext", "json", "--output", bundledContract],
    { cwd: root, encoding: "utf8" },
  );
  if (bundle.status !== 0) {
    process.stderr.write(bundle.stdout);
    process.stderr.write(bundle.stderr);
    process.exit(bundle.status ?? 1);
  }

  const api = JSON.parse(await readFile(bundledContract, "utf8"));
  assert.equal(api.openapi, "3.1.0", "The baseline must remain OpenAPI 3.1.0");
  assert.equal(Object.keys(api.paths).length, 57, "Unexpected path inventory drift");
  assert.equal(Object.keys(api.components.schemas).length, 48, "Unexpected schema inventory drift");
  assert(api.components.schemas.Error, "The shared Error schema is required");

  const operations = [];
  for (const [path, pathItem] of Object.entries(api.paths)) {
    for (const [method, operation] of Object.entries(pathItem)) {
      if (!httpMethods.has(method)) continue;
      const label = `${method.toUpperCase()} ${path}`;
      operations.push({ path, method, operation, label });
      assert(operation.operationId, `${label} is missing operationId`);
      assert(
        Object.hasOwn(operation, "security"),
        `${label} must explicitly declare its public or authenticated security context`,
      );
      const errorResponses = Object.entries(operation.responses ?? {}).filter(([status]) =>
        /^4\d\d$/.test(status),
      );
      assert(errorResponses.length > 0, `${label} must document at least one 4xx response`);
      for (const [status, response] of errorResponses) {
        assert.equal(
          response.content?.["application/json"]?.schema?.$ref,
          "#/components/schemas/Error",
          `${label} ${status} must use the shared Error schema`,
        );
      }

      const usesSessionCookie = operation.security.some((requirement) =>
        Object.hasOwn(requirement, "sessionCookie"),
      );
      if (usesSessionCookie && ["post", "put", "patch", "delete"].includes(method)) {
        const parameters = [...(pathItem.parameters ?? []), ...(operation.parameters ?? [])];
        assert(
          parameters.some(
            (parameter) =>
              parameter.in === "header" &&
              parameter.name === "X-CSRF-Token" &&
              parameter.required,
          ),
          `${label} uses cookie authentication and must require X-CSRF-Token`,
        );
      }
    }
  }

  assert.equal(operations.length, 65, "Unexpected operation inventory drift");
  const operationIds = operations.map(({ operation }) => operation.operationId);
  assert.equal(new Set(operationIds).size, operationIds.length, "operationId values must be unique");

  for (const path of ["/payment-orders", "/renders"]) {
    const operation = api.paths[path]?.post;
    assert(operation, `POST ${path} is required by the baseline`);
    assert(
      operation.parameters?.some(
        (parameter) =>
          parameter.in === "header" && parameter.name === "Idempotency-Key" && parameter.required,
      ),
      `POST ${path} must require Idempotency-Key`,
    );
  }

  console.log(
    `OpenAPI policy validation: PASS (${Object.keys(api.paths).length} paths, ` +
      `${operations.length} operations, ${Object.keys(api.components.schemas).length} schemas)`,
  );
} finally {
  await rm(temporaryDirectory, { recursive: true, force: true });
}
