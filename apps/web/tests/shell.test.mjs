import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);
const css = await readFile(new URL("src/styles.css", root), "utf8");
const html = await readFile(new URL("index.html", root), "utf8");
const main = await readFile(new URL("src/main.js", root), "utf8");
const business = await readFile(new URL("src/business-app.js", root), "utf8");
const consumer = await readFile(new URL("src/consumer-app.js", root), "utf8");
const worker = await readFile(new URL("public/sw.js", root), "utf8");
const manifest = JSON.parse(await readFile(new URL("public/manifest.webmanifest", root), "utf8"));

test("brand and typography tokens remain explicit", () => {
  for (const token of ["#3b1746", "#c9a46b", "#faf7f2", "#f1eaf1", '"Inter"']) {
    assert.match(css, new RegExp(token, "i"));
  }
  assert.match(css, /h1[^}]*font-size:\s*2rem/s);
  assert.match(css, /\.button[^}]*font-size:\s*1rem/s);
  assert.match(html, /wearo-brand\.png/);
});

test("business and consumer route families are separated", () => {
  assert.match(main, /pathname\.startsWith\("\/business"\)/);
  assert.match(main, /renderBusinessApp/);
  assert.match(main, /renderConsumerApp/);
  for (const route of ["dashboard", "catalog", "customers", "billing", "settings"]) {
    assert.match(business, new RegExp(route));
  }
  for (const route of ["/app/sign-in", "/app/try-on", "/app/history", "/app/profile"]) {
    assert.match(consumer, new RegExp(route));
  }
});

test("business app exposes onboarding, billing, dashboard, and honest payment state", () => {
  for (const text of [
    "Create your business workspace",
    "Plans & billing",
    "Try-on activity",
    "Catalogue",
    "no charge was made",
    "Payment method",
  ]) {
    assert.match(business, new RegExp(text, "i"));
  }
  assert.match(business, /sessionStorage\.setItem\(\s*"wearo_business_draft"/);
  assert.match(business, /aria-current="page"/);
});

test("consumer PWA preserves profile, consent, item, and live render flow", () => {
  for (const text of [
    "Sign up or sign in",
    "Create your profile",
    "Update your profile",
    "I am at least 18",
    "not authorised for model training",
    "Wearable item",
    "Generate try-on",
    "not a fit",
    "Delete saved profile",
    "Full-body photo",
    "Close-up face photo",
    "Use person photo",
    "Upload image",
    "Take photo",
    "Take full-body photo",
    "Take close-up photo",
    "3 successful previews per day",
  ]) {
    assert.match(consumer, new RegExp(text, "i"));
  }
  assert.match(consumer, /\/auth\/email-otp\/request/);
  assert.match(consumer, /responseText = await response\.text\(\)/);
  assert.match(consumer, /INVALID_API_RESPONSE/);
  assert.match(consumer, /backend is running on 127\.0\.0\.1:8000/);
  assert.match(consumer, /result\.has_person_profile/);
  assert.match(consumer, /sessionStorage\.setItem\(AUTH_KEY/);
  assert.match(consumer, /auth\.hasProfile \? "home" : "profile"/);
  assert.match(consumer, /Uploading your wearable item/);
  assert.match(consumer, /elements\.namedItem\("item_upload"\)/);
  assert.match(consumer, /id="open-camera"/);
  assert.match(consumer, /navigator\.mediaDevices\.getUserMedia/);
  assert.match(consumer, /facingMode: \{ ideal: "environment" \}/);
  assert.match(consumer, /canvas\.toBlob\(resolve, "image\/jpeg", 0\.92\)/);
  assert.match(consumer, /stream\?\.getTracks\(\)\.forEach\(\(track\) => track\.stop\(\)\)/);
  assert.match(consumer, /data-profile-camera="full_body"/);
  assert.match(consumer, /data-profile-camera="close_up"/);
  assert.match(consumer, /id="profile-camera-dialog"/);
  assert.match(consumer, /selectedProfileFiles/);
  assert.match(consumer, /selectedItemFile/);
  assert.match(consumer, /Upload or take a wearable photo before generating/);
  assert.match(consumer, /person_asset_id: selectedPersonAssetId/);
  assert.match(consumer, /photo_type: "FULL_BODY"/);
  assert.match(consumer, /savePhoto\(closeUpFile, "CLOSE_UP"/);
  assert.match(consumer, /Local testing mode/);
  assert.match(consumer, /allowance\.unlimited/);
  assert.match(consumer, /Saving profile/);
  assert.match(consumer, /\/quotes/);
  assert.match(consumer, /\/renders/);
  assert.match(consumer, /attachHistoryFlow/);
  assert.match(consumer, /Queue details/);
  assert.match(consumer, /queueMarkup/);
  assert.match(consumer, /Processing/);
  assert.match(consumer, /attempts/);
  assert.match(consumer, /Remove from queue/);
  assert.match(consumer, /data-cancel-render-id/);
  assert.match(consumer, /method: "DELETE"/);
  assert.match(consumer, /\["QUEUED", "PROCESSING"\]\.includes\(item\.status\)/);
  assert.match(consumer, /watchProgressivePreview/);
  assert.match(consumer, /jobStatus === "PROCESSING"/);
  assert.match(consumer, /loadLatestPreview/);
  assert.match(consumer, /result\.items\?\.\[0\]/);
  assert.match(consumer, /partial virtual try-on preview/i);
  assert.match(consumer, /If-None-Match/);
  assert.match(consumer, /result_asset_id/);
  assert.match(consumer, /Available until/);
  assert.match(consumer, /navigator\.share/);
  assert.match(consumer, /navigator\.canShare/);
  assert.match(consumer, /data-share-look/);
  assert.match(consumer, /data-download-look/);
  assert.match(consumer, /Saved look downloaded/);
  assert.match(consumer, /data-delete-look/);
  assert.match(consumer, /\/result/);
  assert.match(css, /\.looks-gallery/);
  assert.match(css, /\.look-card__image/);
  assert.match(css, /\.queue-card/);
  assert.match(css, /\.queue-card__remove/);
  assert.match(css, /\.look-card__actions/);
  assert.match(css, /\.person-photo-options/);
  assert.match(css, /\.profile-photo-grid/);
  assert.match(css, /\.profile-camera-button/);
  assert.match(css, /\.wearable-source-actions/);
  assert.match(css, /\.camera-dialog/);
  assert.match(consumer, /aria-live="polite"/);
});

test("PWA is scoped to the consumer app and never caches private API traffic", () => {
  assert.match(html, /manifest\.webmanifest/);
  assert.equal(manifest.start_url, "/app/");
  assert.equal(manifest.scope, "/app/");
  assert.equal(manifest.display, "standalone");
  assert.equal(manifest.name, "Wearo");
  assert.equal(manifest.short_name, "Wearo");
  assert.ok(
    manifest.icons.some(
      (icon) => icon.src === "/wearo-brand.png" && icon.purpose.includes("maskable"),
    ),
  );
  assert.match(worker, /wearo-consumer-v2/);
  assert.match(main, /serviceWorker\.register\("\/sw\.js", \{ scope: "\/app\/" \}\)/);
  assert.match(worker, /url\.pathname\.startsWith\("\/api\/"\)/);
  assert.doesNotMatch(worker, /cache\.put\([^)]*\/api\//);
});

test("consumer PWA has a three-second animated branded launch splash", () => {
  assert.match(main, /showConsumerSplash/);
  assert.match(main, /wearo_consumer_splash_seen/);
  assert.match(main, /Private AI-powered virtual try-on/);
  assert.match(main, /setTimeout\(\(\) => splash\.remove\(\), 3000\)/);
  assert.match(css, /@keyframes launch-logo-rise/);
  assert.match(css, /translateY\(48vh\)/);
  assert.match(css, /prefers-reduced-motion/);
});

test("responsive and accessible interaction states exist for both experiences", () => {
  assert.match(css, /:focus-visible/);
  assert.match(css, /@media \(min-width: 48rem\)/);
  assert.match(css, /@media \(max-width: 55rem\)/);
  assert.match(css, /@media \(display-mode: standalone\)/);
  assert.match(css, /\.business-app/);
  assert.match(css, /\.consumer-app/);
  assert.match(html, /Skip to main content/);
});
