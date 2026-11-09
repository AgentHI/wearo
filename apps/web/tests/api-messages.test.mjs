import test from "node:test";
import assert from "node:assert/strict";
import { apiError, apiMessage, networkError, readApiBody } from "../src/api-messages.js";

test("maps upload failures to a clear instruction", () => {
  assert.equal(apiMessage({ status: 413 }), "This photo is too large to upload. Choose a smaller photo or take a screenshot and upload that.");
});

test("prefers a known API code over a generic status message", () => {
  assert.equal(apiMessage({ code: "INVALID_OTP", status: 401 }), "That verification code is incorrect or has expired. Request a new code and try again.");
});

test("never exposes an unreadable proxy response", async () => {
  const response = new Response("<html>request too large</html>", { status: 413 });
  const error = apiError(response, await readApiBody(response));
  assert.match(error.message, /photo is too large/i);
  assert.doesNotMatch(error.message, /413|html|unreadable/i);
});

test("provides friendly fallbacks for unknown and network failures", () => {
  assert.equal(apiMessage({ status: 418 }), "We could not complete your request. Please try again.");
  assert.match(networkError().message, /internet connection/i);
});
