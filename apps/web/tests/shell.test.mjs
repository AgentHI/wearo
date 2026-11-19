import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);
const css = await readFile(new URL("src/styles.css", root), "utf8");
const html = await readFile(new URL("index.html", root), "utf8");
const main = await readFile(new URL("src/main.js", root), "utf8");
const brand = await readFile(new URL("src/brand.js", root), "utf8");
const business = await readFile(new URL("src/business-app.js", root), "utf8");
const store = await readFile(new URL("src/store-app.js", root), "utf8");
const agent = await readFile(new URL("src/agent-app.js", root), "utf8");
const admin = await readFile(new URL("src/admin-app.js", root), "utf8");
const consumer = await readFile(new URL("src/consumer-app.js", root), "utf8");
const apiMessages = await readFile(new URL("src/api-messages.js", root), "utf8");
const imageOptimizer = await readFile(new URL("src/image-optimizer.js", root), "utf8");
const wearoDialog = await readFile(new URL("src/wearo-dialog.js", root), "utf8");
const publicSite = await readFile(new URL("src/public-site.js", root), "utf8");
const worker = await readFile(new URL("public/sw.js", root), "utf8");
const manifest = JSON.parse(await readFile(new URL("public/manifest.webmanifest", root), "utf8"));

test("notification templates keep SMS manual and filter versions by channel", () => {
  assert.match(admin, /const otpPurpose = '<option value="OTP"/);
  assert.match(admin, /form\.querySelector\("\.notification-editor__ai"\)\.hidden = isSms/);
  assert.match(admin, /Enter the OTP message exactly as it should be sent/);
  assert.match(admin, /id="notification-channel-filter"/);
  assert.match(admin, /item\.channel === "EMAIL"[\s\S]*? : ""\}\$\{item\.status === "DRAFT"/);
  for (const channel of ["SMS", "EMAIL", "WHATSAPP"]) {
    assert.match(admin, new RegExp(`<option value="${channel}">`));
  }
});

test("brand and typography tokens remain explicit", () => {
  for (const token of ["#3b1746", "#c9a46b", "#faf7f2", "#f1eaf1", '"Inter"']) {
    assert.match(css, new RegExp(token, "i"));
  }
  assert.match(css, /h1[^}]*font-size:\s*2rem/s);
  assert.match(css, /\.button[^}]*font-size:\s*1rem/s);
  assert.match(html, /wearo-(?:brand|checkout-logo)\.png/);
  assert.match(css, /\.wordmark img[^}]*object-fit:\s*contain/s);
  assert.match(css, /\.app-brand img[^}]*object-fit:\s*contain/s);
  assert.match(css, /\.app-brand[^}]*width:\s*6rem/s);
  assert.doesNotMatch(css, /\.wordmark__symbol img/);
  assert.doesNotMatch(css, /\.app-brand__crop/);
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
  assert.match(publicSite, /wearo-brand_white_bg\.png/);
  assert.match(publicSite, /wearo-hero-campaign\.webp/);
  assert.match(publicSite, /About Us/);
  assert.match(publicSite, /helping people make choices with greater confidence/);
  assert.match(publicSite, /try before you buy/);
  assert.match(main, /pathname === "\/about"/);
  assert.match(main, /pathname === "\/experiences"/);
  assert.match(main, /renderExperiencesSite/);
  assert.match(main, /addEventListener\("popstate", renderCurrentRoute\)/);
  assert.match(publicSite, /href="\/experiences"/);
  assert.match(publicSite, /aria-label="Explore Wearo experiences"/);
  assert.match(publicSite, /\/tryon-assets\/jewellery\//);
  assert.match(publicSite, /\/tryon-assets\/blouse\//);
  assert.match(publicSite, /\/tryon-assets\/fashion\//);
  assert.doesNotMatch(publicSite, /\/experiences\/(?:jewellery|blouse|fashion)\//);
  assert.doesNotMatch(worker, /\/experiences\/(?:jewellery|blouse|fashion)\//);
  assert.match(publicSite, /data-public-route/);
  assert.match(publicSite, /data-coming-soon="\$\{label\}"/);
  assert.match(publicSite, /For Businesses/);
  assert.doesNotMatch(publicSite, /\["Gallery",/);
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
  assert.match(publicSite, /data-fashion-tryon/);
  assert.match(publicSite, /data-fashion-option/);
  assert.match(publicSite, /data-fashion-model/);
  assert.match(publicSite, /product-banarasi-saree\.webp/);
  assert.doesNotMatch(publicSite, /data-fashion-option[^>]*>[\s\S]*?model-banarasi-saree\.webp/);
  for (const look of ["Banarasi Saree", "Emerald Anarkali", "Midnight Lehenga", "Punjabi Suit", "Indo-Western"]) assert.match(publicSite, new RegExp(look));
  assert.match(publicSite, /model-everyday-kurta\.webp/);
  assert.doesNotMatch(publicSite, /data-fashion-option[^>]*data-model="Everyday Kurta"/);
  assert.match(publicSite, /No dress selected/);
  assert.doesNotMatch(publicSite, /<p class="experience-showcase__status">Coming soon<\/p><h3>Fashion Try-On/);
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
  assert.match(publicSite, /Wearo\.ai · A product of Bitadd Labs India Private Limited/);
  assert.match(publicSite, /bitaddlabs\.com/);
  assert.match(css, /prefers-reduced-motion:\s*reduce/);
  assert.match(css, /\.public-hero/);
  assert.match(css, /\.mobile-menu/);
  assert.match(worker, /const APP_SHELL = \[\s*"\/"/);
  assert.match(worker, /return caches\.match\("\/"\)/);
});

test("business and consumer route families are separated", () => {
  assert.match(business, /brandMarkup\("\/business", "white"\)/);
  assert.match(brand, /wearo-brand_white_bg\.png\?v=20261108-white-2/);
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
  assert.match(business, /brandMarkup\("\/business", "white"\)/);
  assert.match(css, /\.business-sidebar__brand \.wordmark \{ width: 6\.5rem; min-height: 0; aspect-ratio: 1;/);
  assert.match(css, /\.wordmark--white-bg, \.brand-white-bg \{ padding: 0; border: 0; background: transparent; box-shadow: none; \}/);
  assert.match(css, /img\.brand-white-bg \{ clip-path: inset\(1\.4% round 6\.5%\); \}/);
  assert.match(css, /\.business-sidebar \.wordmark--white-bg img,[^}]*transform: none;/s);
  assert.match(css, /\.business-public__header \.wordmark \{ width: 11rem;/);
  assert.match(css, /\.business-auth__brand \.wordmark \{ position: relative; top: 10px; width: 11rem; padding: 0; border: 0; background: transparent;/);
  assert.match(css, /\.admin-sidebar \.brand-white-bg \{ width: 6\.5rem; overflow: visible; aspect-ratio: 1; flex: 0 0 6\.5rem; border: 0; border-radius: 0; \}/);
  assert.match(business, /\/auth\/logout/);
});

test("consumer try-on restores an active render before the previous result", () => {
  assert.match(consumer, /result\.queue\?\.find\(\(item\) => \["QUEUED", "PROCESSING"\]\.includes\(item\.status\)\)/);
  assert.ok(consumer.indexOf("if (activeRender)") < consumer.indexOf("const latest = result.items?.[0]"));
  assert.match(consumer, /waitForRender\(activeRender\.render_id\)/);
  assert.match(consumer, /updateSubmitAvailability/);
  assert.match(consumer, /\|\| !selectedItemFile/);
  assert.match(consumer, /\|\| !selectedPersonAssetId/);
});

test("consumer authentication persists for the backend session lifetime", () => {
  assert.match(consumer, /const persisted = localStorage\.getItem\(AUTH_KEY\)/);
  assert.match(consumer, /auth\?\.expiresAt.*Date\.now\(\)/s);
  assert.match(consumer, /localStorage\.setItem\(AUTH_KEY, JSON\.stringify\(auth\)\)/);
  assert.match(consumer, /expiresAt: result\.expires_at/);
  assert.match(consumer, /localStorage\.removeItem\(AUTH_KEY\)/);
});

test("platform admin login is isolated and protects dashboard routes", () => {
  assert.ok(
    main.indexOf('pathname.startsWith("/admin/cost-lab")') <
      main.indexOf('pathname.startsWith("/admin")'),
    "Cost Lab must be routed before the general admin prefix",
  );
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
  assert.match(business, /Total try-ons/);
  assert.match(business, /Try-ons consumed/);
  assert.match(business, /Average cost per try-on/);
  assert.match(business, /Try-ons remaining/);
  assert.match(business, /Average try-ons/);
  assert.match(business, /Unique users/);
  assert.match(business, /Try-ons today/);
  assert.match(business, /Try-ons in selected period/);
  assert.match(business, /Try-ons from \$\{dateRange\.label\}/);
  assert.match(business, /usage\.previews_today \?\? 0/);
  assert.match(business, /Try-on overview/);
  assert.doesNotMatch(business, /Generation tokens and cost/);
  assert.doesNotMatch(business, /Total provider tokens/);
  assert.match(business, /AI provider usage/);
  assert.match(business, /Total input/);
  assert.match(business, /Total output/);
  assert.match(business, /Cost for all try-ons/);
  assert.match(business, /average_provider_cost_usd_micros/);
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
  assert.doesNotMatch(business, /id="shop-qr-download"/);
  assert.match(store, /Download QR poster/);
  assert.match(admin, /<th>Input tokens<\/th><th>Output tokens<\/th>/);
  assert.match(admin, /item\.input_tokens/);
  assert.match(admin, /item\.output_tokens/);
  assert.match(admin, /AI advertisements generated/);
  assert.match(admin, /Advertisement generations by store/);
  assert.doesNotMatch(store, /latestAiCard/);
  assert.match(store, /id="advertisement-save-edit"[^>]*data-action="save"[^>]*hidden>Save changes/);
  assert.match(store, /Saving without regenerating the card/);
  assert.match(store, /Changes saved without regenerating the card/);
  assert.match(store, /resetAdvertisementEditor\("✦ Generate new card"\)/);
  assert.match(store, /Advertisement saved\. You can create a new card below\./);
  assert.match(store, /id="store-shop-url"[^>]*target="_blank"[^>]*rel="noopener"/);
  assert.match(store, /\/store\/shop-link/);
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
    "Choose what you want to wear",
    "Generate try-on",
    "See It On You",
    "not a fit",
    "Full-body photo",
    "Close-up face photo",
    "Use person photo",
    "Add wearable",
    "Upload",
    "Take photo",
    "Take full-body photo",
    "Take close-up photo",
    "Your photo library",
    "0 of 10 photos",
    "Choose a photo",
    "Checking your available balance",
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
  assert.match(consumer, /readApiBody\(response\)/);
  assert.match(consumer, /throw apiError\(response, body\)/);
  assert.match(consumer, /attempt < 165/);
  assert.match(consumer, /did not finish within 5 minutes/);
  assert.match(apiMessages, /This photo is too large to upload/);
  assert.match(consumer, /optimizeImageForUpload\(file, kind\)/);
  assert.match(imageOptimizer, /DEFAULT_MAX_EDGE = 2048/);
  assert.match(imageOptimizer, /DEFAULT_TARGET_BYTES = 900 \* 1024/);
  assert.doesNotMatch(consumer, /backend is running on 127\.0\.0\.1:8000|unreadable response/);
  assert.match(consumer, /result\.has_person_profile/);
  assert.match(consumer, /localStorage\.setItem\(AUTH_KEY/);
  assert.match(consumer, /auth\.hasProfile \? "home" : "profile"/);
  assert.match(consumer, /const isShopEntry = pathname\.startsWith\("\/shop\/"\)/);
  assert.match(consumer, /id="open-cancellation"/);
  assert.match(consumer, /id="cancellation-dialog"/);
  assert.match(consumer, /preview\.dataset\.advertisement = "true"/);
  assert.match(consumer, /<section id="tryon-composer" class="tryon-studio tryon-composer--reference"/);
  assert.doesNotMatch(consumer, /<dialog id="tryon-composer"|id="open-tryon-composer"|id="close-tryon-composer"/);
  assert.doesNotMatch(consumer, /openComposerButton|closeComposerButton|composer\.showModal/);
  assert.doesNotMatch(consumer, /recent-tryons|loadRecentTryOns|recentTryOnsList/);
  assert.doesNotMatch(consumer, /Camera permission is controlled by your browser or device/);
  assert.doesNotMatch(css, /recent-tryons|recent-tryon-card/);
  assert.match(css, /mobile-preview__canvas\[data-advertisement="true"\][^{]*\{[^}]*aspect-ratio:\s*3\s*\/\s*4/s);
  assert.match(css, /\.sponsored-advertisement-progress img[^}]*object-fit:\s*contain/s);
  assert.match(css, /\.tryon-composer--reference \.mobile-preview__canvas \.tryon-result-image[^}]*width:\s*auto\s*!important[^}]*height:\s*auto\s*!important[^}]*max-width:\s*100%[^}]*max-height:\s*100%[^}]*object-fit:\s*contain\s*!important/s);
  assert.match(css, /\.tryon-composer--reference \.tryon-workspace[^}]*grid-template-columns:\s*minmax\(0,\s*1\.7fr\)\s*minmax\(9\.25rem,\s*\.68fr\)/s);
  assert.match(css, /\.tryon-composer--reference \.wearable-dock[^}]*grid-template-rows:\s*minmax\(6rem,\s*\.7fr\)\s*minmax\(11rem,\s*1\.35fr\)\s*auto\s*auto/s);
  assert.match(css, /\.tryon-composer--reference \.mobile-preview__canvas[^}]*aspect-ratio:\s*2\s*\/\s*3/s);
  assert.match(css, /@media \(max-width:\s*28rem\)[\s\S]*?\.tryon-composer--reference \.tryon-workspace\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1\.72fr\)\s*minmax\(5\.75rem,\s*\.78fr\)/s);
  assert.doesNotMatch(css, /\.tryon-composer--reference \.tryon-workspace\s*\{\s*grid-template-columns:\s*1fr/);
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
  assert.match(consumer, /id="home-caption"/);
  assert.match(consumer, /HOME_CAPTION_FALLBACKS/);
  assert.match(consumer, /randomLocalHomeCaption\(previousHomeCaption\)/);
  assert.match(consumer, /api\("\/me\/home-caption", \{ cache: "no-store" \}, auth\)/);
  assert.match(consumer, /homeCaption\.textContent = caption/);
  assert.match(css, /\.consumer-app--home \.home-caption[^}]*linear-gradient/s);
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
  assert.match(consumer, /showEmptyPreview\(\)/);
  assert.match(consumer, /emptyTryOnPlaceholderMarkup\(\)/);
  assert.match(consumer, /result_asset_id/);
  assert.match(consumer, /formatRetentionCountdown/);
  assert.match(consumer, /Auto-deletes in 1 day/);
  assert.match(consumer, /Auto-deletes today/);
  assert.match(consumer, /Download before/);
  assert.match(consumer, /navigator\.share/);
  assert.match(consumer, /navigator\.canShare/);
  assert.match(consumer, /data-share-look/);
  assert.match(consumer, /data-download-look/);
  assert.match(consumer, /id="look-preview-dialog"/);
  assert.match(consumer, /previewDialog\.showModal\(\)/);
  assert.match(consumer, /id="tryon-preview-dialog"/);
  assert.match(consumer, /preview\.dataset\.previewUrl = assetUrl/);
  assert.match(consumer, /resultPreviewDialog\.showModal\(\)/);
  assert.match(consumer, /Open try-on preview/);
  assert.doesNotMatch(consumer, /AI-generated try-on/i);
  assert.match(consumer, /data-look-image/);
  assert.match(consumer, /gallery\.addEventListener\("error"/);
  assert.match(consumer, /gallery\.append\(card\)/);
  assert.doesNotMatch(consumer, /class="look-card__image"[^>]*target="_blank"/);
  assert.match(css, /\.look-preview-dialog::backdrop/);
  assert.match(css, /\.mobile-preview__canvas\[data-preview-url\][^}]*cursor:\s*zoom-in/s);
  assert.match(consumer, /Saved look downloaded/);
  assert.match(consumer, /data-delete-look/);
  assert.match(consumer, /\/result/);
  assert.match(css, /\.looks-gallery/);
  assert.match(consumer, /class="mobile-title looks-title"/);
  assert.match(css, /\.looks-title h1[^}]*font-size:\s*1\.75rem/s);
  assert.match(css, /\.looks-title h1::selection[^}]*background:\s*var\(--state-lilac\)/s);
  assert.match(css, /\.looks-gallery\s*\{[^}]*grid-template-columns:\s*repeat\(3,\s*minmax\(0,\s*1fr\)\)/s);
  assert.match(consumer, /lookPlaceholders\(Math\.max\(0, 6 - result\.items\.length\)\)/);
  assert.match(consumer, /gallery\.innerHTML = `\$\{savedLooks\}\$\{lookPlaceholders/);
  assert.match(consumer, /look-card--placeholder/);
  assert.match(css, /\.tryon-placeholder--empty img/);
  assert.match(css, /\.look-card__image/);
  assert.match(css, /\.queue-card/);
  assert.match(css, /\.queue-card__remove/);
  assert.match(css, /\.look-card__actions/);
  assert.match(css, /\.look-card__retention span/);
  assert.match(css, /\.selected-person-photo/);
  assert.match(css, /\.photo-picker-dialog/);
  assert.match(css, /\.profile-library__grid/);
  assert.match(css, /\.profile-title h1[^}]*font-size:\s*1\.75rem/s);
  assert.match(css, /\.profile-photo-slot[^}]*grid-template-rows:\s*12rem\s+9\.5rem\s+auto/s);
  assert.match(css, /\.profile-photo-card \.person-preview[^}]*height:\s*12rem/s);
  assert.match(css, /\.profile-photo-card \.person-preview img[^}]*object-fit:\s*contain\s*!important/s);
  assert.match(css, /\.profile-photo-card \.person-preview img[^}]*width:\s*auto\s*!important[^}]*height:\s*auto\s*!important/s);
  assert.match(css, /\.profile-library__item img[^}]*object-fit:\s*contain/s);
  assert.match(consumer, /profile-library__note/);
  assert.match(css, /\.profile-library__note[^}]*font-size:\s*\.68rem/s);
  assert.match(css, /\.photo-picker-option img[^}]*object-fit:\s*contain/s);
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

test("B2C checkout and B2B payment information stay backend-priced", () => {
  assert.match(consumer, /\/app\/payments/);
  assert.doesNotMatch(consumer, /consumer-header__price/);
  assert.doesNotMatch(consumer, /consumer-tryon-rate/);
  assert.doesNotMatch(consumer, /consumer-pricing-hero/);
  assert.doesNotMatch(consumer, /consumer-rate-detail/);
  assert.match(consumer, /api\("\/public\/try-on-pricing"\)/);
  assert.doesNotMatch(consumer, /Equivalent to ₹/);
  assert.match(consumer, /data-retail-package-id/);
  assert.match(consumer, /id="consumer-buy-button"[^>]*disabled/);
  assert.match(consumer, /id="consumer-billing-history-toggle"[^>]*aria-label="View payment history"/);
  assert.match(consumer, /id="consumer-billing-history-more"[^>]*hidden>Load more<\/button>/);
  assert.match(consumer, /href="\/api\/v1\/me\/billing-history\.pdf"[^>]*download="wearo-billing-history\.pdf"/);
  assert.doesNotMatch(consumer, /consumer-billing-history-toggle[^>]*>[\s\S]*?<span>Payment history<\/span>/);
  assert.match(consumer, /page_size:\s*"10"/);
  assert.match(consumer, /loadConsumerBillingHistory\(auth, \{ page, append: true \}\)/);
  assert.doesNotMatch(consumer, /Receipt issued after successful capture/);
  assert.match(consumer, /purchaseButton\.disabled = false/);
  assert.match(consumer, /classList\.toggle\("is-selected", selected\)/);
  assert.match(consumer, /setAttribute\("aria-pressed", String\(selected\)\)/);
  assert.match(consumer, /\/me\/topup-orders/);
  assert.match(consumer, /\/me\/verify-payment/);
  assert.match(consumer, /window\.Razorpay/);
  assert.match(consumer, /razorpayCheckoutLogo/);
  assert.match(consumer, /prefill: \{ email: destination/);
  assert.match(consumer, /hidden: \{ contact: true \}/);
  assert.match(consumer, /prefill: \{ contact/);
  assert.match(consumer, /`\+91\$\{compactContact\}`/);
  assert.match(consumer, /backdrop_color: "#f4edf6"/);
  assert.match(consumer, /<span>Buy<\/span>/);
  assert.doesNotMatch(consumer, /₹3(?:\.00)?\b/);
  assert.match(business, /Platform access and try-on usage stay separate/);
  assert.match(business, /15%/);
  assert.match(business, /seven-calendar-day grace period/);
  assert.match(business, /No subscription or checkout yet/);
  assert.doesNotMatch(business, /tokens_per_tryon[^\n]*price_minor/);
  assert.match(admin, /Publish retail try-on price/);
  assert.match(admin, /admin\/pricing\/retail-tryon/);
  assert.match(admin, /Create try-on package/);
  assert.match(admin, /retail-tryon\/packages/);
  assert.match(admin, /data-package-edit/);
  assert.match(admin, /data-package-delete/);
  assert.match(admin, /admin-icon-action--edit/);
  assert.match(admin, /admin-icon-action--delete/);
  assert.match(admin, /aria-label="Edit/);
  assert.match(admin, /aria-label="Delete/);
  assert.match(admin, /method: editingPackageId \? "PUT" : "POST"/);
  assert.match(admin, /method: "DELETE"/);
  assert.match(admin, /<span>Save changes<\/span>/);
  assert.match(admin, /<span>Cancel edit<\/span>/);
  assert.match(admin, /admin-action-with-icon/);
  assert.match(consumer, /consumer-package-list/);
  assert.match(consumer, /item\.number_of_tryons/);
  assert.match(consumer, /item\.final_amount_minor/);
  assert.match(consumer, /Including GST/);
  assert.match(admin, /gst_basis_points/);
  assert.match(consumer, /consumer-package-card--\$\{tier\}/);
  assert.match(css, /consumer-package-card--silver/);
  assert.match(css, /consumer-package-card--gold/);
  assert.match(css, /\.consumer-package-grid[^}]*grid-template-columns:\s*repeat\(3,\s*minmax\(0,\s*1fr\)\)/s);
  assert.match(css, /\.consumer-package-card\.is-selected[^}]*animation:\s*consumer-package-focus/s);
  assert.match(css, /@keyframes consumer-package-focus/);
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
  assert.match(consumer, /api\("\/me\/person-profile", \{ method: "DELETE" \}, auth\)/);
  assert.match(consumer, /\/assets\/\$\{encodeURIComponent\(assetId\)\}/);
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
      (icon) => icon.src.startsWith("/pwa-icon-512.png") && icon.purpose === "any",
    ),
  );
  assert.equal(manifest.icons.some((icon) => icon.purpose.includes("maskable")), false);
  assert.match(html, /apple-touch-icon" href="\/pwa-icon-512\.png\?v=20261118-pwa-2/);
  assert.match(worker, /wearo-shell-v\d+/);
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
  assert.match(consumer, /updateSubmitAvailability\(\)/);
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

test("platform support can find every customer realm and add audited tokens", () => {
  assert.match(admin, /slug: "support"/);
  assert.match(admin, /Search a verified email address or phone number to review identity, balance, and payment activity/);
  assert.match(admin, /\/admin\/support\/customers\?identity=/);
  assert.match(admin, /\/token-credits/);
  assert.match(admin, /Try-ons included/);
  assert.match(admin, /Issue an append-only, audited credit without changing payment history/);
  assert.match(admin, /admin-action-with-icon/);
});

test("consumer PWA has a three-second animated branded launch splash", () => {
  assert.match(main, /showConsumerSplash/);
  assert.match(main, /wearo_consumer_splash_seen/);
  assert.match(main, /launch-splash__logo"><img src="\/wearo-mark\.png\?v=20261118-pwa-2"/);
  assert.doesNotMatch(main, /launch-splash__logo"><img src="\/wearo-brand_white_bg\.png"/);
  assert.match(main, /Private AI-powered virtual try-on/);
  assert.match(main, /setTimeout\(\(\) => splash\.remove\(\), 3000\)/);
  assert.match(css, /@keyframes launch-logo-rise/);
  assert.match(css, /translateY\(48vh\)/);
  assert.match(css, /\.launch-splash p \{ margin: \.75rem 0 0;/);
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

test("all application confirmations use the accessible Wearo dialog", () => {
  for (const application of [admin, business, store, agent, consumer]) {
    assert.doesNotMatch(application, /window\.(?:alert|confirm)\s*\(/);
  }
  assert.match(wearoDialog, /showModal\(\)/);
  assert.match(wearoDialog, /aria-labelledby="wearo-dialog-title"/);
  assert.match(css, /\.wearo-confirm-dialog\[data-tone="info"\]/);
});
