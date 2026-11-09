import test from "node:test";
import assert from "node:assert/strict";
import { containedImageSize } from "../src/image-optimizer.js";

test("bounds a portrait image at 2048 pixels without changing its aspect ratio", () => {
  assert.deepEqual(containedImageSize(3024, 4032), { width: 1536, height: 2048 });
});

test("bounds a landscape image without changing its aspect ratio", () => {
  assert.deepEqual(containedImageSize(6000, 4000), { width: 2048, height: 1365 });
});

test("does not enlarge an image that is already within the detail limit", () => {
  assert.deepEqual(containedImageSize(1200, 1600), { width: 1200, height: 1600 });
});

test("rejects invalid dimensions with an understandable message", () => {
  assert.throws(() => containedImageSize(0, 100), /photo could not be read/i);
});
