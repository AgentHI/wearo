const ENGLISH_MESSAGES = {
  codes: {
    AUTHENTICATION_REQUIRED: "Please sign in to continue.",
    ADMIN_AUTHENTICATION_REQUIRED: "Please sign in to the admin workspace to continue.",
    SESSION_EXPIRED: "Your session has expired. Please sign in again.",
    INVALID_OTP: "That verification code is incorrect or has expired. Request a new code and try again.",
    INVALID_CONTACT_OTP: "That verification code is incorrect. Check the code and try again.",
    INVALID_ADMIN_CREDENTIALS: "The email or password is incorrect. Please try again.",
    INVALID_EMAIL: "Enter a valid email address.",
    INVALID_CONTACT_EMAIL: "Enter a valid email address.",
    INVALID_MOBILE: "Enter a valid mobile number, including the country code.",
    INVALID_CONTACT_MOBILE: "Enter a valid mobile number, including the country code.",
    INVALID_IMAGE_SIZE: "This photo is too large. Choose a photo smaller than 15 MB.",
    PROVIDER_IMAGE_TOO_LARGE: "This photo is too large to process. Choose a smaller photo.",
    INVALID_IMAGE_CONTENT: "We could not read this photo. Choose a clear JPEG, PNG, or WebP image.",
    UNSUPPORTED_IMAGE: "Choose a JPEG, PNG, or WebP image.",
    ASSET_UNAVAILABLE: "This photo is no longer available. Please upload it again.",
    PROFILE_NOT_FOUND: "Create your profile and add a photo before continuing.",
    PROFILE_OR_CONSENT_REQUIRED: "Add a profile photo and accept the consent options before continuing.",
    INSUFFICIENT_TOKENS: "You do not have enough try-on credits. Add credits to continue.",
    EMAIL_DELIVERY_UNAVAILABLE: "We could not send the email right now. Please try again shortly.",
    PAYMENT_GATEWAY_UNAVAILABLE: "Payments are temporarily unavailable. Please try again shortly.",
    RENDER_UNAVAILABLE: "The virtual try-on service is temporarily unavailable. Please try again shortly.",
    QUOTE_UNAVAILABLE: "We could not prepare this try-on. Please try again.",
    JOB_STATE_CONFLICT: "This try-on has already changed. Refresh the page to see its latest status.",
    CONTACT_ORIGIN_REJECTED: "This form cannot be submitted from this page. Refresh the page and try again.",
    CONTACT_ENQUIRIES_UNAVAILABLE: "We could not send your enquiry right now. Please try again shortly.",
  },
  statuses: {
    400: "Some information is missing or invalid. Check your entries and try again.",
    401: "Please sign in again to continue.",
    403: "You do not have permission to do that.",
    404: "We could not find what you requested. It may have been moved or removed.",
    408: "The request took too long. Check your connection and try again.",
    409: "This information changed while you were working. Refresh the page and try again.",
    413: "This photo is too large to upload. Choose a smaller photo or take a screenshot and upload that.",
    415: "This file type is not supported. Choose a JPEG, PNG, or WebP image.",
    422: "Some information is not valid. Check your entries and try again.",
    429: "Too many attempts were made. Wait a moment, then try again.",
    500: "Something went wrong on our side. Please try again shortly.",
    502: "The service is temporarily unavailable. Please try again shortly.",
    503: "The service is temporarily unavailable. Please try again shortly.",
    504: "The service took too long to respond. Please try again shortly.",
  },
  network: "We could not connect to Wearo. Check your internet connection and try again.",
  fallback: "We could not complete your request. Please try again.",
};

// Keeping locale at this boundary makes additional language catalogs a contained change later.
export function apiMessage({ code, status } = {}, locale = "en") {
  const messages = locale === "en" ? ENGLISH_MESSAGES : ENGLISH_MESSAGES;
  if (code && messages.codes[code]) return messages.codes[code];
  return messages.statuses[status] || messages.fallback;
}

export async function readApiBody(response) {
  const responseText = await response.text();
  if (!responseText) return {};
  try { return JSON.parse(responseText); } catch { return {}; }
}

export function apiError(response, body = {}, locale = "en") {
  const error = new Error(apiMessage({ code: body?.code, status: response.status }, locale));
  error.code = body?.code || "REQUEST_FAILED";
  error.status = response.status;
  return error;
}

export function networkError(locale = "en") {
  const messages = locale === "en" ? ENGLISH_MESSAGES : ENGLISH_MESSAGES;
  const error = new Error(messages.network);
  error.code = "NETWORK_ERROR";
  return error;
}
