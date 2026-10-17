#!/usr/bin/env node

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

const root = process.cwd();
const sdd = resolve(root, "docs/sdd");
const requiredCategories = new Set([
  "Frontend",
  "Backend",
  "Database",
  "API Integration",
  "AI/LLM Integration",
  "Security",
  "Testing",
  "DevOps",
]);
const allowedPoints = new Set(["1", "2", "3", "5"]);
const allowedStatuses = new Set(["TODO", "IN_PROGRESS", "BLOCKED", "DONE"]);

function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = "";
  let quoted = false;

  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    if (quoted) {
      if (character === '"' && text[index + 1] === '"') {
        field += '"';
        index += 1;
      } else if (character === '"') {
        quoted = false;
      } else {
        field += character;
      }
    } else if (character === '"') {
      quoted = true;
    } else if (character === ",") {
      row.push(field);
      field = "";
    } else if (character === "\n") {
      row.push(field.replace(/\r$/, ""));
      rows.push(row);
      row = [];
      field = "";
    } else {
      field += character;
    }
  }

  if (field.length > 0 || row.length > 0) {
    row.push(field.replace(/\r$/, ""));
    rows.push(row);
  }

  const [rawHeaders, ...values] = rows.filter((entry) => entry.some(Boolean));
  const headers = rawHeaders.map((header) => header.replace(/^\uFEFF/, ""));
  return values.map((entry) =>
    Object.fromEntries(headers.map((header, index) => [header, entry[index] ?? ""])),
  );
}

function tableRows(text, firstColumnPattern) {
  return text
    .split(/\r?\n/)
    .filter((line) => firstColumnPattern.test(line))
    .map((line) => line.split("|").slice(1, -1).map((value) => value.trim()));
}

function expandIds(value, prefix, selectedIds = null) {
  const normalized = value.replaceAll("–", "-");
  const pattern = new RegExp(`${prefix}-(\\d{3})(?:-(?:${prefix}-)?(\\d{3}))?`, "g");
  const expanded = [];
  for (const match of normalized.matchAll(pattern)) {
    const start = Number(match[1]);
    const end = match[2] ? Number(match[2]) : start;
    if (selectedIds) {
      expanded.push(
        ...selectedIds.filter((id) => {
          const number = Number(id.slice(prefix.length + 1));
          return number >= start && number <= end;
        }),
      );
    } else {
      for (let number = start; number <= end; number += 1) {
        expanded.push(`${prefix}-${String(number).padStart(3, "0")}`);
      }
    }
  }
  return [...new Set(expanded)];
}

function findCycle(tasks) {
  const states = new Map();
  const stack = [];

  function visit(taskId) {
    if (states.get(taskId) === "visited") return null;
    if (states.get(taskId) === "visiting") {
      return [...stack.slice(stack.indexOf(taskId)), taskId];
    }
    states.set(taskId, "visiting");
    stack.push(taskId);
    for (const dependency of tasks.get(taskId).dependencies) {
      const cycle = visit(dependency);
      if (cycle) return cycle;
    }
    stack.pop();
    states.set(taskId, "visited");
    return null;
  }

  for (const taskId of tasks.keys()) {
    const cycle = visit(taskId);
    if (cycle) return cycle;
  }
  return null;
}

const [requirementsCsv, acceptanceCsv, epicsMd, storiesMd, tasksMd, dependenciesMd] =
  await Promise.all([
    readFile(resolve(sdd, "WR_Traceability_Matrix.csv"), "utf8"),
    readFile(resolve(sdd, "Acceptance_Test_Cases.csv"), "utf8"),
    readFile(resolve(sdd, "EPICS.md"), "utf8"),
    readFile(resolve(sdd, "USER_STORIES.md"), "utf8"),
    readFile(resolve(sdd, "TASKS.md"), "utf8"),
    readFile(resolve(sdd, "TASK_DEPENDENCIES.md"), "utf8"),
  ]);

const requirements = parseCsv(requirementsCsv);
const acceptanceTests = parseCsv(acceptanceCsv);
const requirementIds = requirements.map(({ wr_id: id }) => id);
const qaIds = acceptanceTests.map(({ qa_id: id }) => id);
const requirementIdSet = new Set(requirementIds);
const qaIdSet = new Set(qaIds);

assert.equal(requirements.length, 90, "The selected MVP requirement count must be 90");
assert.equal(requirementIdSet.size, 90, "MVP requirement IDs must be unique");
assert.equal(
  requirements.filter(({ priority }) => priority === "P0").length,
  59,
  "P0 count must remain 59",
);
assert.equal(
  requirements.filter(({ priority }) => priority === "P1").length,
  31,
  "P1 count must remain 31",
);
assert.equal(
  requirements.filter(({ mvp_treatment: treatment }) => treatment === "FULL").length,
  29,
  "FULL count must remain 29",
);
assert.equal(
  requirements.filter(({ mvp_treatment: treatment }) => treatment === "BOUNDED").length,
  61,
  "BOUNDED count must remain 61",
);
assert.equal(acceptanceTests.length, 36, "Acceptance-test count must be 36");
assert.equal(qaIdSet.size, 36, "Acceptance-test IDs must be unique");

const epicRows = tableRows(epicsMd, /^\| EP-\d{2} /);
const storyRows = tableRows(storiesMd, /^\| ST-\d{2}\.\d /);
const taskRows = tableRows(tasksMd, /^\| T-\d{3} /);
const traceRows = tableRows(dependenciesMd, /^\| WR-\d{3} /);
const epics = new Map(epicRows.map((row) => [row[0].match(/EP-\d{2}/)?.[0], row]));
const stories = new Map(storyRows.map((row) => [row[0], row]));
const tasks = new Map();

for (const row of taskRows) {
  assert.equal(row.length, 10, `${row[0]} must contain every required task field`);
  const [id, category, parent, description, wrs, dependencyText, points, acceptance, done, status] = row;
  assert(!tasks.has(id), `Duplicate task ID: ${id}`);
  assert(requiredCategories.has(category), `${id} has invalid category: ${category}`);
  assert(allowedPoints.has(points), `${id} has invalid story points: ${points}`);
  assert(allowedStatuses.has(status), `${id} has invalid status: ${status}`);
  assert(description.length > 0, `${id} is missing a description`);
  assert(wrs.length > 0, `${id} is missing original WR IDs`);
  assert(acceptance.length > 0, `${id} is missing acceptance criteria`);
  assert(done.length > 0, `${id} is missing a Definition of Done`);
  const epicId = parent.match(/EP-\d{2}/)?.[0];
  const storyId = parent.match(/ST-\d{2}\.\d/)?.[0];
  assert(epics.has(epicId), `${id} references unknown epic ${epicId}`);
  assert(stories.has(storyId), `${id} references unknown story ${storyId}`);
  const decisions = dependencyText.match(/DEC-\d{2}/g) ?? [];
  assert(
    decisions.length === 0 || status === "BLOCKED",
    `${id} has unresolved decision dependencies but is not BLOCKED`,
  );
  assert(
    status !== "BLOCKED" || decisions.length > 0,
    `${id} is BLOCKED without an explicit decision dependency`,
  );
  tasks.set(id, {
    id,
    category,
    epicId,
    storyId,
    requirementIds:
      wrs.includes("All selected WRs") || wrs.includes("All 90 selected WRs")
        ? requirementIds
        : expandIds(wrs, "WR", requirementIds),
    dependencies: expandIds(dependencyText, "T"),
    decisions,
    status,
  });
}

assert.equal(new Set(taskRows.map((row) => row[0])).size, taskRows.length, "Task IDs must be unique");
assert.deepEqual(
  new Set(taskRows.map((row) => row[1])),
  requiredCategories,
  "All eight required task categories must be represented",
);

const orderedTaskIds = [...tasks.keys()];
for (const task of tasks.values()) {
  for (const dependency of task.dependencies) {
    assert(tasks.has(dependency), `${task.id} references unknown dependency ${dependency}`);
    assert(
      orderedTaskIds.indexOf(dependency) < orderedTaskIds.indexOf(task.id),
      `${task.id} must be listed after dependency ${dependency}`,
    );
  }
}
const cycle = findCycle(tasks);
assert.equal(cycle, null, `Task dependency cycle found: ${cycle?.join(" -> ")}`);

assert.equal(traceRows.length, 90, "Trace table must contain exactly 90 requirement rows");
const tracedRequirementIds = traceRows.map((row) => row[0]);
assert.equal(new Set(tracedRequirementIds).size, 90, "Trace requirement rows must be unique");
assert.deepEqual(
  new Set(tracedRequirementIds),
  requirementIdSet,
  "Trace table must contain exactly the selected MVP requirement IDs",
);

const requirementsById = new Map(requirements.map((requirement) => [requirement.wr_id, requirement]));
for (const [wrId, epicId, storyId, taskText, qaText] of traceRows) {
  assert(epics.has(epicId), `${wrId} references unknown epic ${epicId}`);
  assert(stories.has(storyId), `${wrId} references unknown story ${storyId}`);
  assert.equal(stories.get(storyId)[1], epicId, `${wrId} story/epic ownership is inconsistent`);
  const storyRequirementIds = stories.get(storyId)[3].includes("All selected WRs")
    ? requirementIds
    : expandIds(stories.get(storyId)[3], "WR", requirementIds);
  assert(storyRequirementIds.includes(wrId), `${storyId} does not cite ${wrId}`);
  const primaryTaskIds = expandIds(taskText, "T");
  assert(primaryTaskIds.length > 0, `${wrId} has no primary task`);
  for (const taskId of primaryTaskIds) {
    assert(tasks.has(taskId), `${wrId} references unknown primary task ${taskId}`);
  }
  assert(
    primaryTaskIds.some((taskId) => tasks.get(taskId).requirementIds.includes(wrId)),
    `${wrId} is not cited by any of its primary tasks`,
  );
  const expectedQa = [...requirementsById.get(wrId).test_cases.matchAll(/QA-\d{3}/g)].map(
    ([qaId]) => qaId,
  );
  const tracedQa = [...qaText.matchAll(/QA-\d{3}/g)].map(([qaId]) => qaId);
  assert.deepEqual(tracedQa.sort(), expectedQa.sort(), `${wrId} QA mapping differs from the source`);
  for (const qaId of tracedQa) {
    assert(qaIdSet.has(qaId), `${wrId} references unknown test ${qaId}`);
  }
}

const deferredPositivePatterns = [
  /implement(?:s|ing)? (?:a )?native app/i,
  /build(?:s|ing)? (?:a )?(?:3d )?avatar customi[sz]ation/i,
  /implement(?:s|ing)? live (?:ar|video)/i,
  /support(?:s|ing)? rings? or bangles?/i,
  /build(?:s|ing)? (?:an )?appointment booking engine/i,
  /implement(?:s|ing)? inventory synchroni[sz]ation/i,
  /implement(?:s|ing)? subscription tiers?/i,
  /implement(?:s|ing)? model fine-tuning/i,
  /build(?:s|ing)? (?:a )?public service-status portal/i,
];
for (const row of taskRows) {
  const implementationText = `${row[3]} ${row[7]}`;
  for (const pattern of deferredPositivePatterns) {
    assert(!pattern.test(implementationText), `${row[0]} appears to implement deferred scope: ${pattern}`);
  }
}

const summary = {
  result: "PASS",
  requirements: requirements.length,
  priority: { P0: 59, P1: 31 },
  treatment: { FULL: 29, BOUNDED: 61 },
  epics: epics.size,
  stories: stories.size,
  tasks: tasks.size,
  acceptanceTests: acceptanceTests.length,
  categories: Object.fromEntries(
    [...requiredCategories].map((category) => [
      category,
      [...tasks.values()].filter((task) => task.category === category).length,
    ]),
  ),
  statuses: Object.fromEntries(
    [...allowedStatuses].map((status) => [
      status,
      [...tasks.values()].filter((task) => task.status === status).length,
    ]),
  ),
  blockedDecisions: [...new Set([...tasks.values()].flatMap((task) => task.decisions))].sort(),
};

if (process.argv.includes("--json")) {
  process.stdout.write(`${JSON.stringify(summary, null, 2)}\n`);
} else {
  console.log("Wearo.ai SDD backlog validation: PASS");
  console.log(
    `Requirements ${summary.requirements}/90 | QA ${summary.acceptanceTests}/36 | ` +
      `Epics ${summary.epics} | Stories ${summary.stories} | Tasks ${summary.tasks}`,
  );
  console.log(
    `P0/P1 ${summary.priority.P0}/${summary.priority.P1} | ` +
      `FULL/BOUNDED ${summary.treatment.FULL}/${summary.treatment.BOUNDED}`,
  );
  console.log(`Blocked decisions: ${summary.blockedDecisions.join(", ")}`);
}
