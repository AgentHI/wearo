import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);
const css = await readFile(new URL("src/styles.css", root), "utf8");
const html = await readFile(new URL("index.html", root), "utf8");
const main = await readFile(new URL("src/main.js", root), "utf8");
const business = await readFile(new URL("src/business-app.js", root), "utf8");
const agent = await readFile(new URL("src/agent-app.js", root), "utf8");
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
  for (const route of ["dashboard", "experience", "customers", "billing", "settings"]) {
    assert.match(business, new RegExp(route));
  }
  for (const route of ["/app/sign-in", "/app/try-on", "/app/history", "/app/profile"]) {
    assert.match(consumer, new RegExp(route));
  }
  assert.match(business, /BUSINESS_AUTH_KEY/);
  assert.match(business, /BUSINESS_SIGN_IN/);
  assert.match(business, /\/business\/workspaces/);
  assert.match(business, /replaceState\(\{\}, "", "\/business\/sign-in"\)/);
  assert.match(business, /business-logout/);
  assert.match(business, /\/auth\/logout/);
});

test("business app exposes onboarding, billing, dashboard, and honest payment state", () => {
  for (const text of [
    "Create your business workspace",
    "Plans & billing",
    "Wearo experience",
    "no charge was made",
    "Payment method",
  ]) {
    assert.match(business, new RegExp(text, "i"));
  }
  assert.match(business, /\/business\/register/);
  assert.match(business, /wearo_business_registration_key/);
  assert.match(business, /Total tokens/);
  assert.match(business, /Tokens consumed/);
  assert.match(business, /Average tokens per try-on/);
  assert.match(business, /Tokens remaining/);
  assert.match(business, /Estimated try-ons remaining/);
  assert.match(business, /Average try-ons/);
  assert.match(business, /Unique users/);
  assert.match(business, /Try-ons today/);
  assert.match(business, /Try-ons in selected period/);
  assert.match(business, /Try-ons from \$\{dateRange\.label\}/);
  assert.match(business, /usage\.previews_today \?\? 0/);
  assert.match(business, /Token overview/);
  assert.match(business, /Try-on performance/);
  assert.match(css, /metric-card--tokens/);
  assert.match(css, /metric-card--activity/);
  assert.match(css, /Shared Wearo card theme across business, consumer, and agent screens/);
  assert.match(css, /rgb\(201 164 107 \/ 42%\)/);
  assert.doesNotMatch(business, /Actual LLM tokens/);
  assert.match(business, /function dashboardGreeting/);
  assert.match(business, /Good afternoon\./);
  assert.match(business, /Good evening\./);
  assert.match(business, /\/business\/billing#token-topup/);
  assert.match(business, /Today/);
  assert.match(business, /Past week/);
  assert.match(business, /Past month/);
  assert.match(business, /Custom duration/);
  assert.match(business, /date_from/);
  assert.match(business, /signup-verify-code/);
  assert.match(business, /Resend in \$\{remaining\}s/);
  assert.match(business, /2 \* 60 \* 60 \* 1000/);
  assert.match(business, /3 - failedSignupOtpAttempts/);
  assert.match(business, /VERIFY_EMAIL_OTP|Verify your email/);
  assert.match(business, /tax_invoice_requested/);
  assert.match(business, /I need tax-ready business invoices/);
  assert.match(business, /invoice-details/);
  assert.match(business, /operating-profile-guidance/);
  assert.match(business, /No generation offering until jewellery quality approval/);
  assert.doesNotMatch(business, /Add product|Add item|Catalogue/);
  assert.match(business, /\/billing-profile/);
  assert.match(business, /Save for future invoices/);
  assert.match(business, /Issued invoices were not changed/);
  assert.match(business, /X-CSRF-Token/);
  assert.match(business, /\/owner-contacts/);
  assert.match(business, /Owner sign-in contacts/);
  assert.match(business, /Current email/);
  assert.match(business, /Current mobile/);
  assert.match(business, /SMS sent/);
  assert.match(business, /Verify and update/);
  assert.match(business, /aria-current="page"/);
  assert.match(business, /\/usage\?action_code=TRY_ON/);
  assert.match(business, /previews used/);
  assert.match(business, /After one try-on/);
  assert.match(business, /Wearo Tokens price product actions/);
  assert.match(business, /\/platform\/pricing/);
  assert.match(business, /\/platform\/recredit-policy/);
  assert.match(business, /Token transaction history/);
  assert.match(business, /token-transactions\.csv/);
  assert.match(business, /Secure token top-up/);
  assert.match(business, /topup-orders/);
  assert.match(business, /Payment reconciliation/);
  assert.match(business, /Sensitive action audit/);
  assert.match(business, /Request profile change/);
  assert.match(business, /actual token costs vary by action/i);
  assert.match(business, /verified work email or primary mobile/i);
  assert.match(business, /Business agents/);
  assert.match(business, /Agent app URL/);
  assert.match(business, /Copy app URL/);
  assert.match(business, /result\.agent_url/);
  assert.doesNotMatch(business, /url\.pathname\.replace\(\/\^\\\/shop/);
  assert.match(business, /Download QR poster/);
  assert.match(business, /id="shop-url"[^>]*target="_blank"[^>]*rel="noopener"/);
  assert.match(business, /General try-on allowance/);
  assert.match(business, /resets every 24 hours/);
  assert.doesNotMatch(business, /user-allowance-form/);
  assert.match(business, /Communications and legal history/);
  assert.match(business, /Financial reconciliation/);
  assert.match(business, /Support and billing issues/);
  assert.match(business, /Support data access/);
  assert.match(business, /Eligible reversals restore Wearo Tokens/);
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
    "Your photo library",
    "0 of 10 photos",
    "Choose a photo",
    "3 successful previews per day",
    "Refresh try-on balance",
    "Allotted",
    "Available",
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
  assert.match(consumer, /const isShopEntry = pathname\.startsWith\("\/shop\/"\)/);
  assert.match(consumer, /Uploading your wearable item/);
  assert.match(consumer, /elements\.namedItem\("item_upload"\)/);
  assert.match(consumer, /id="open-camera"/);
  assert.match(consumer, /navigator\.mediaDevices\.getUserMedia/);
  assert.match(consumer, /facingMode: \{ ideal: "environment" \}/);
  assert.match(consumer, /canvas\.toBlob\(resolve, "image\/jpeg", 0\.92\)/);
  assert.match(consumer, /wearo-tryon-complete\.wav/);
  assert.match(consumer, /unlockCompletionSound\(\)/);
  assert.match(consumer, /playCompletionSound\(\)/);
  assert.match(consumer, /showGeneratingPreview\(\)/);
  assert.match(consumer, /Creating your Wearo look/);
  assert.match(css, /@keyframes tryon-twinkle/);
  assert.doesNotMatch(css, /@keyframes tryon-orbit/);
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
  assert.doesNotMatch(consumer, /actual LLM tokens/i);
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
  assert.match(consumer, /loadLatestPreview/);
  assert.match(consumer, /result\.items\?\.\[0\]/);
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
  assert.match(css, /\.selected-person-photo/);
  assert.match(css, /\.photo-picker-dialog/);
  assert.match(css, /\.profile-library__grid/);
  assert.match(css, /\.profile-photo-grid/);
  assert.match(css, /\.profile-camera-button/);
  assert.match(css, /\.wearable-source-actions/);
  assert.match(css, /\.camera-dialog/);
  assert.match(consumer, /aria-live="polite"/);
  assert.match(consumer, /function normalizeShopMobile/);
  assert.match(consumer, /return `\+91\$\{digits\}`/);
  assert.match(consumer, /<h1>Wearo\.ai<\/h1>/);
  assert.match(consumer, /shop-welcome__wearo-logo/);
  assert.doesNotMatch(consumer, /<h1>\$\{escapeHtml\(shopName\)\}<\/h1>/);
});

test("PWA is scoped to the consumer app and never caches private API traffic", () => {
  assert.match(html, /manifest\.webmanifest/);
  assert.equal(manifest.start_url, "/app/");
  assert.equal(manifest.scope, "/");
  assert.equal(manifest.display, "standalone");
  assert.equal(manifest.name, "Wearo");
  assert.equal(manifest.short_name, "Wearo");
  assert.ok(
    manifest.icons.some(
      (icon) => icon.src === "/wearo-brand.png" && icon.purpose.includes("maskable"),
    ),
  );
  assert.match(worker, /wearo-shell-v22/);
  assert.match(main, /updateViaCache: "none"/);
  assert.match(main, /registration\.update\(\)/);
  assert.match(worker, /fetch\(request, \{ cache: "no-store" \}\)/);
  assert.match(worker, /url\.pathname\.startsWith\("\/api\/"\)/);
  assert.match(worker, /wearo-tryon-complete\.wav/);
  assert.doesNotMatch(worker, /cache\.put\([^)]*\/api\//);
});

test("agent PWA supports mobile OTP, business QR, and customer allowance top-ups", () => {
  assert.match(main, /pathname\.startsWith\("\/agent"\)/);
  assert.match(main, /renderAgentApp/);
  assert.match(agent, /BUSINESS_SIGN_IN/);
  assert.match(agent, /\/auth\/agent-otp\/verify/);
  assert.match(agent, /\/agent\/logout/);
  assert.match(agent, /Resend OTP/);
  assert.match(agent, /30 days/);
  assert.match(agent, /\/agent\/shop-qr\.png/);
  assert.match(agent, /\/agent\/allowances/);
  assert.match(agent, /<span>Remaining<\/span>/);
  assert.match(agent, /<span>Allotted<\/span>/);
  assert.match(agent, /<span>Used<\/span>/);
  assert.doesNotMatch(agent, /Open customer app/);
  assert.match(agent, /beforeinstallprompt/);
  assert.match(agent, />Install<\/button>/);
  assert.match(agent, /agent-invite-screen/);
  assert.match(agent, /agent-open-tryons/);
  assert.match(agent, /agent-tryons-screen/);
  assert.match(agent, /agent-back/);
  assert.match(agent, /View customer balance/);
  assert.match(agent, /Welcome back,/);
  assert.match(agent, /agent-wordmark-name">Wearo\.ai/);
  assert.match(agent, /\/public\/shops\/\$\{encodeURIComponent\(launch\.business\)\}\/logo/);
  assert.match(agent, /result\.customer \|\| \(result\.user/);
  assert.match(agent, /customer app now shows the updated balance/i);
  assert.match(worker, /"\/agent\/"/);
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
