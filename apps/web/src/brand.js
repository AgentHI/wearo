export function brandMarkup(home = "/app/") {
  return `
    <a class="wordmark" href="${home}" aria-label="Wearo.ai home">
      <span class="wordmark__symbol" aria-hidden="true"><img src="/wearo-brand.png" alt="" /></span>
      <span class="wordmark__name" aria-hidden="true"><img src="/wearo-brand.png" alt="" /></span>
    </a>`;
}

export function compactBrandMarkup(home = "/app/") {
  return `
    <a class="app-brand" href="${home}" aria-label="Wearo.ai home">
      <span class="app-brand__crop" aria-hidden="true"><img src="/wearo-brand.png" alt="" /></span>
    </a>`;
}
