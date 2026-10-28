import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);
const css = await readFile(new URL("src/styles.css", root), "utf8");
const html = await readFile(new URL("index.html", root), "utf8");
const main = await readFile(new URL("src/main.js", root), "utf8");
const business = await readFile(new URL("src/business-app.js", root), "utf8");
const agent = await readFile(new URL("src/agent-app.js", root), "utf8");
const admin = await readFile(new URL("src/admin-app.js", root), "utf8");
const consumer = await readFile(new URL("src/consumer-app.js", root), "utf8");
const publicSite = await readFile(new URL("src/public-site.js", root), "utf8");
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

test("public marketing site is isolated and links into existing apps", () => {
  assert.match(main, /pathname === "\/"/);
  assert.match(main, /renderPublicSite/);
  assert.match(publicSite, /Before You/);
  assert.match(publicSite, /Wear It,/);
  assert.match(publicSite, /Wearo It\./);
  assert.match(publicSite, /href="\/app\/"/);
  assert.match(publicSite, /href="\/business\/signup"/);
  assert.match(publicSite, /href="\/business\/sign-in"/);
  assert.match(publicSite, /wearo-brand\.png/);
  assert.match(publicSite, /wearo-hero-campaign\.webp/);
  assert.match(publicSite, /About Us/);
  assert.match(publicSite, /helping people make choices with greater confidence/);
  assert.match(publicSite, /try before you buy/);
  assert.match(main, /pathname === "\/about"/);
  assert.match(main, /pathname === "\/experiences"/);
  assert.match(main, /renderExperiencesSite/);
  assert.match(publicSite, /href="\/experiences"/);
  assert.match(publicSite, /aria-label="Explore Wearo experiences"/);
  assert.match(publicSite, /data-coming-soon="\$\{label\}"/);
  assert.match(publicSite, /For Businesses/);
  assert.match(publicSite, /Gallery/);
  assert.match(publicSite, /coming soon/);
  assert.match(publicSite, /Experience the Magic of Try-On/);
  assert.match(publicSite, /data-jewellery-tryon/);
  assert.match(publicSite, /data-jewellery-option/);
  assert.match(publicSite, /data-model="Classic Gold"/);
  assert.match(publicSite, /model-neutral-v2\.webp/);
  assert.match(publicSite, /No jewellery selected/);
  assert.match(publicSite, /aria-pressed="true"/);
  assert.match(publicSite, /data-blouse-tryon/);
  assert.match(publicSite, /data-blouse-option/);
  for (const design of ["Royal Jewel", "Lotus Muse", "Midnight Pearl"]) assert.match(publicSite, new RegExp(design));
  assert.match(publicSite, /front and back views shown/);
  assert.match(main, /pathname === "\/contact"/);
  assert.match(publicSite, /For brands and businesses/);
  assert.match(publicSite, /name="name"[^>]*required/);
  assert.match(publicSite, /name="email"[^>]*required/);
  assert.match(publicSite, /name="mobile"[^>]*required/);
  assert.match(publicSite, /name="website"[^>]*type="url"/);
  assert.match(publicSite, /name="purpose"[^>]*required/);
  assert.match(publicSite, /data-contact-success/);
  assert.match(publicSite, /\/api\/v1\/public\/contact-enquiries/);
  assert.match(publicSite, /VITE_WEARO_CONTACT_FORM_TOKEN/);
  assert.match(publicSite, /X-Wearo-Contact-Token/);
  assert.match(publicSite, /© 2026 All rights reserved/);
  assert.match(publicSite, /bitaddlabs\.com/);
  assert.match(css, /prefers-reduced-motion:\s*reduce/);
  assert.match(css, /\.public-hero/);
  assert.match(css, /\.mobile-menu/);
  assert.match(worker, /const APP_SHELL = \[\s*"\/"/);
  assert.match(worker, /return caches\.match\("\/"\)/);
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

test("platform admin login is isolated and protects dashboard routes", () => {
  assert.match(main, /pathname\.startsWith\("\/admin"\)/);
  assert.match(main, /renderAdminApp/);
  assert.match(admin, /Super Admin sign in/);
  assert.match(admin, /name="email"/);
  assert.match(admin, /name="password"/);
  assert.match(admin, /API_ROOT.*\/api\/v1/);
  assert.match(admin, /\/admin\/login/);
  assert.match(admin, /\/admin\/session/);
  assert.match(admin, /\/admin\/logout/);
  assert.match(admin, /redirect\("\/admin"\)/);
  assert.match(admin, /redirect_to/);
  assert.doesNotMatch(admin, /localStorage|sessionStorage/);
  for (const section of [
    "Dashboard",
    "Businesses",
    "Enquiries",
    "Subscriptions",
    "Billing & Pricing",
    "Platform Operations",
    "Audit History",
  ]) {
    assert.match(admin, new RegExp(section.replace("&", "&")));
  }
  assert.match(admin, /Wearo Super Admin/);
  assert.match(admin, /\/admin\/enquiries/);
  assert.match(admin, /Total enquiries/);
  assert.match(admin, /New enquiries/);
  assert.match(admin, /\/admin\/enquiries\?/);
  assert.match(admin, /contact_enquiry_id/);
  assert.match(admin, /Platform administrator/);
  assert.match(admin, /pushState/);
  assert.match(admin, /popstate/);
  assert.match(admin, /aria-current="page"/);
  assert.match(css, /@media \(min-width: 48rem\)[\s\S]*\.admin-shell/);
  assert.match(css, /@media \(max-width: 55rem\)[\s\S]*\.admin-shell/);
  assert.match(css, /\.admin-navigation[\s\S]*overflow-x: auto/);
  assert.match(admin, /workspace-switcher/);
  assert.match(admin, /business-breadcrumb/);
  assert.match(admin, /business-app admin-app/);
  assert.match(admin, /Total businesses/);
  assert.match(admin, /Active businesses/);
  assert.match(admin, /Paused businesses/);
  assert.match(admin, /organization_name/);
  assert.match(admin, /business_type/);
  assert.match(admin, /onboarding_date/);
  assert.match(admin, /subscription_status/);
  assert.match(admin, /operational_status/);
  assert.match(admin, /business_type.*status/);
  assert.match(admin, /data-organization-link/);
  assert.match(admin, /Available tokens/);
  assert.match(admin, /Tokens consumed/);
  assert.match(admin, /Total try-ons/);
  assert.match(admin, /Payment history/);
  assert.match(admin, /Manual token adjustment/);
  for (const action of ["ACTIVATE", "PAUSE", "RESUME", "DEACTIVATE"]) assert.match(admin, new RegExp(action));
  assert.match(admin, /Status updated and audited|status updated and audited/i);
  for (const metric of ["Total registered consumers", "Successful try-ons", "Failed try-ons", "Average try-ons per business"]) assert.match(admin, new RegExp(metric));
  for (const period of ["Today", "Last 7 Days", "This Month", "Custom"]) assert.match(admin, new RegExp(period));
  assert.match(admin, /date_from/);
  assert.match(admin, /date_to/);
  assert.match(admin, /tenant_id/);
  assert.match(admin, /business_type/);
  for (const label of ["Purchased", "Consumed", "Adjusted", "Remaining", "Most active", "consumption history"]) assert.match(admin, new RegExp(label, "i"));
  assert.match(admin, /admin\/usage\/organizations/);
  assert.match(admin, /deduplicated by request/);
  for (const label of ["Total subscriptions", "Active subscriptions", "Trials", "Payment due", "Try-ons paused", "Cancelled subscriptions", "Expired subscriptions"]) assert.match(admin, new RegExp(label, "i"));
  assert.match(admin, /admin\/customers/);
  assert.match(admin, /data-customer-link/);
  for (const label of ["Subscription lifecycle", "Start date", "Next billing date", "Assign or change plan", "Extend trial", "Customer pause", "Reactivate", "Admin pause"]) assert.match(admin, new RegExp(label, "i"));
  assert.match(admin, /admin\/subscriptions/);
  for (const label of ["Monthly fee", "Tokens per try-on", "Free trial tokens", "Trial duration", "Payment grace period", "GST", "Bulk discount", "Business type"]) assert.match(admin, new RegExp(label, "i"));
  assert.match(admin, /admin\/pricing/);
  assert.match(admin, /Existing transactions were not changed/);
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
    "Cancel subscription",
    "No, Keep My Account",
    "Yes, Cancel",
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
  assert.match(consumer, /id="open-cancellation"/);
  assert.match(consumer, /id="cancellation-dialog"/);
  assert.match(consumer, /open-cancellation"\)\.addEventListener\("click", \(\) => \{/);
  assert.match(consumer, /cancellationDialog\.showModal\(\)/);
  assert.match(consumer, /confirmCancellation\.addEventListener\("click", async \(\) => \{/);
  assert.match(consumer, /api\("\/me\/account", \{ method: "DELETE" \}, auth\)/);
  assert.doesNotMatch(consumer, /\/me\/account\/\$\{/);
  assert.match(consumer, /profile: \(\) => profileView\(auth\)/);
  assert.match(consumer, /Boolean\(auth\)/);
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
  assert.match(consumer, /data-profile-camera="additional"/);
  assert.match(consumer, /Photo captured\. Review consent/);
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
  assert.match(consumer, /Email or mobile number/);
  assert.match(consumer, /const destination = form\.elements\.destination\.value\.trim\(\)/);
  assert.match(consumer, /<h1>Wearo\.ai<\/h1>/);
  assert.match(consumer, /shop-welcome__wearo-logo/);
  assert.doesNotMatch(consumer, /<h1>\$\{escapeHtml\(shopName\)\}<\/h1>/);
});

test("authenticated B2C and B2B2C users get an own-account cancellation entry point", () => {
  assert.match(consumer, /const shopContext = readShopContext\(\)/);
  assert.match(consumer, /profile: \(\) => profileView\(auth\)/);
  assert.match(consumer, /id="open-cancellation"[^>]*>.*Cancel subscription/s);
  assert.match(consumer, /id="cancellation-dialog"/);

  const entryHandler = consumer.match(
    /open-cancellation"\)\.addEventListener\("click", \(\) => \{(?<body>[\s\S]*?)\n  \}\);/,
  );
  assert.ok(entryHandler?.groups?.body);
  assert.match(entryHandler.groups.body, /cancellationDialog\.showModal\(\)/);
  assert.doesNotMatch(entryHandler.groups.body, /api\(|fetch\(/);

  assert.match(consumer, /api\("\/me\/account", \{ method: "DELETE" \}, auth\)/);
  assert.doesNotMatch(consumer, /\/me\/account\/\$\{|account_id.*method: "DELETE"/s);
});

test("destructive account action uses the recoverable 30-day lifecycle", () => {
  assert.match(
    consumer,
    /<strong>Sign out<\/strong>[\s\S]*id="open-cancellation"[\s\S]*<strong>Cancel subscription &amp; delete account<\/strong>/,
  );
  assert.match(consumer, /Account and photos remain recoverable for 30 days/);
  assert.match(consumer, /Cancel subscription and delete account\?/);
  assert.doesNotMatch(consumer, /id="delete-profile"|id="profile-deletion-dialog"/);
  assert.doesNotMatch(
    consumer,
    /api\("\/me\/person-profile", \{ method: "DELETE" \}, auth\)/,
  );
});

test("account cancellation requires explicit affirmative consent", () => {
  assert.match(
    consumer,
    /This will delete all your profile and try-on photos permanently after 30 days\. Do you want to continue\?/,
  );
  assert.match(consumer, />No, Keep My Account<\/button>/);
  assert.match(consumer, />Yes, Cancel<\/button>/);

  const declineHandler = consumer.match(
    /keep-subscription"\)\.addEventListener\("click", (?<handler>[^;]+)\);/,
  );
  assert.equal(declineHandler?.groups?.handler, "closeCancellation");

  const closeHandler = consumer.match(
    /close-cancellation"\)\.addEventListener\("click", (?<handler>[^;]+)\);/,
  );
  assert.equal(closeHandler?.groups?.handler, "closeCancellation");
  const closeFunction = consumer.match(
    /const closeCancellation = \(\) => \{(?<body>[\s\S]*?)\n  \};/,
  );
  assert.ok(closeFunction?.groups?.body);
  assert.doesNotMatch(closeFunction.groups.body, /api\(|fetch\(/);

  const dismissHandler = consumer.match(
    /cancellationDialog\.addEventListener\("cancel", \(\) => \{(?<body>[\s\S]*?)\n  \}\);/,
  );
  assert.ok(dismissHandler?.groups?.body);
  assert.doesNotMatch(dismissHandler.groups.body, /api\(|fetch\(/);

  const affirmativeHandler = consumer.match(
    /confirmCancellation\.addEventListener\("click", async \(\) => \{(?<body>[\s\S]*?)\n  \}\);/,
  );
  assert.ok(affirmativeHandler?.groups?.body);
  assert.match(
    affirmativeHandler.groups.body,
    /api\("\/me\/account", \{ method: "DELETE" \}, auth\)/,
  );
  assert.equal(
    consumer.match(/api\("\/me\/account", \{ method: "DELETE" \}, auth\)/g)?.length,
    1,
  );
});

test("pending cancellation status uses the backend date for B2C and B2B2C", () => {
  assert.match(consumer, /if \(auth\?\.accountStatus === "DELETION_PENDING"\) route = "account-status"/);
  assert.match(consumer, /!\["profile", "account-status"\]\.includes\(route\)/);
  assert.match(consumer, /"account-status": pendingDeletionView/);
  assert.match(consumer, /api\("\/me\/account", \{\}, auth\)/);
  assert.match(consumer, /new Date\(lifecycle\.deletion_at\)\.toLocaleDateString\(\)/);
  assert.match(
    consumer,
    /Your account is scheduled for permanent deletion on \$\{deletionDate\}\. Signing in before this date will restore your account\./,
  );
  assert.match(consumer, /result\.restored_from_deletion_at/);
  assert.match(consumer, /Account restored\. It had been scheduled for permanent deletion on/);
  const pendingFlow = consumer.match(
    /function attachPendingDeletionFlow\(auth\) \{(?<body>[\s\S]*?)\n\}\n\nexport function renderConsumerApp/,
  );
  assert.ok(pendingFlow?.groups?.body);
  assert.doesNotMatch(pendingFlow.groups.body, /Date\.now\(\)|30 \* 24/);
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
  assert.match(worker, /wearo-shell-v30/);
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
  assert.match(agent, /"Try-ons are paused"/);
  assert.match(agent, /"Subscription is cancelled"/);
  assert.match(agent, /statusMessage = `\$\{statusTitle\}\. Please contact your admin\.`/);
  assert.match(agent, /agent-business-status/);
  assert.match(agent, /agent-qr--locked/);
  assert.match(agent, /QR scanning unavailable/);
  assert.match(agent, /New try-ons are blocked/);
  assert.match(agent, /const qrContent = tryOnsActive/);
  assert.match(agent, /addForm\.setAttribute\("aria-disabled", "true"\)/);
  assert.match(agent, /for \(const control of addForm\.elements\) control\.disabled = true/);
  assert.match(worker, /"\/agent\/"/);
});

test("business try-on controls require explicit pause and cancellation confirmation", () => {
  assert.match(business, />Pause Try-ons</);
  assert.match(business, />Resume Try-ons</);
  assert.match(business, />Cancel Subscription</);
  assert.match(business, /Subscription Cancelled/);
  assert.match(business, /id="business-subscription-dialog"/);
  assert.match(business, /New try-ons will be disabled for your business and its users\. Existing data will remain available for viewing\./);
  assert.match(business, /keepSubscription\.textContent = "Keep Subscription"/);
  assert.match(business, /pendingTryOnStatus = "PAUSED"/);
  assert.match(business, /pendingTryOnStatus = "CANCELLED"/);
  assert.doesNotMatch(business, /Cancel this subscription\? New try-ons will be permanently blocked/);
});

test("business status blocks only new B2B2C try-ons and preserves end-user reads", () => {
  assert.match(consumer, /businessTryOnsAllowed/);
  assert.match(consumer, /TRYONS_PAUSED/);
  assert.match(consumer, /SUBSCRIPTION_CANCELLED/);
  assert.match(consumer, /Your profile, photos, saved data, and previous results remain available in Profile and Looks\./);
  assert.match(consumer, /\/sponsored-sessions\/\$\{encodeURIComponent\(existing\.session_id\)\}/);
  assert.match(consumer, /submit\.disabled = !businessTryOnsAllowed/);
  assert.match(consumer, />Try on your app<\/button>/);
  assert.match(consumer, /leaveBusinessExperience/);
  assert.match(consumer, /sessionStorage\.removeItem\(SHOP_CONTEXT_KEY\)/);
  assert.match(consumer, /studio\.hidden = true/);
  assert.match(consumer, /allowancePanel\.hidden = true/);
  assert.match(consumer, /api\("\/me\/person-profile", \{\}, auth\)/);
  assert.match(consumer, /api\("\/renders", \{\}, auth\)/);
});

test("B2B2C shoppers can reuse an email or mobile consumer account", () => {
  assert.match(consumer, /Use your existing email or mobile number to start this business-sponsored try-on session\./);
  assert.doesNotMatch(consumer, /Enter and verify your mobile number/);
  assert.doesNotMatch(consumer, /normalizeShopMobile/);
  assert.match(consumer, /sponsored_session_id: sponsoredSession\?\.session_id \|\| null/);
  assert.match(consumer, /\/sponsored-sessions\/\$\{encodeURIComponent\(sponsoredSession\.session_id\)\}\/try-ons/);
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
