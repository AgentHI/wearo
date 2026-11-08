export function brandMarkup(home = "/app/", variant = "transparent") {
  const source = variant === "white"
    ? "/wearo-brand_white_bg.png?v=20261108-white-2"
    : "/wearo-brand.png";
  const variantClass = variant === "white" ? " wordmark--white-bg" : "";
  return `
    <a class="wordmark${variantClass}" href="${home}" aria-label="Wearo.ai home">
      <img src="${source}" alt="" aria-hidden="true" />
    </a>`;
}

export function compactBrandMarkup(home = "/app/") {
  return `
    <a class="app-brand" href="${home}" aria-label="Wearo.ai home">
      <img src="/wearo-brand.png" alt="" aria-hidden="true" />
    </a>`;
}
