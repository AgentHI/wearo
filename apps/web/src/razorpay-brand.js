let cachedCheckoutLogo = null;

export async function razorpayCheckoutLogo() {
  if (cachedCheckoutLogo) return cachedCheckoutLogo;
  const response = await fetch("/wearo-checkout-logo.png", { cache: "force-cache" });
  if (!response.ok) throw new Error("Wearo checkout branding could not be loaded.");
  const blob = await response.blob();
  cachedCheckoutLogo = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener("load", () => resolve(reader.result), { once: true });
    reader.addEventListener("error", () => reject(reader.error), { once: true });
    reader.readAsDataURL(blob);
  });
  return cachedCheckoutLogo;
}
