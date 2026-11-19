import assert from "node:assert/strict";
import test from "node:test";

import { normalizeGalleryResponse } from "../src/gallery-response.js";

const look = { result_asset_id: "asset-1" };

test("keeps valid looks when an older API response has no backend count", () => {
  const result = normalizeGalleryResponse({ items: [look], queue: [] });

  assert.deepEqual(result.items, [look]);
  assert.equal(result.savedLookCount, null);
  assert.equal(result.hasNext, false);
});

test("does not suppress valid looks when count metadata is inconsistent", () => {
  const result = normalizeGalleryResponse({
    items: [look],
    queue: [],
    saved_look_count: 0,
    page: 1,
    has_next: false,
  });

  assert.deepEqual(result.items, [look]);
  assert.equal(result.savedLookCount, null);
});

test("uses the backend count and pagination metadata when available", () => {
  const result = normalizeGalleryResponse({
    items: [look],
    queue: [{ status: "QUEUED" }],
    saved_look_count: 6,
    page: 2,
    has_next: true,
  });

  assert.equal(result.savedLookCount, 6);
  assert.equal(result.page, 2);
  assert.equal(result.hasNext, true);
  assert.equal(result.queue.length, 1);
});
