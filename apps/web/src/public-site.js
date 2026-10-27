const navItems = [
  ["Home", "#home"],
  ["Experiences", "#experiences"],
  ["For Businesses", "#businesses"],
  ["Gallery", "#gallery"],
  ["About Us", "#about"],
  ["Contact", "#contact"],
];

function publicBrand() {
  return `
    <a class="public-brand" href="#home" aria-label="Wearo.ai home">
      <img src="/wearo-brand.png" alt="Wearo.ai" />
    </a>`;
}

function star(size = "") {
  return `<span class="gold-star ${size}" aria-hidden="true"><i></i></span>`;
}

export function renderPublicSite(root) {
  document.documentElement.dataset.experience = "public";
  document.title = "Wearo.ai — Before You Wear It, Wearo It.";

  root.innerHTML = `
    <div class="public-site" id="home">
      <header class="public-header" data-public-header>
        <div class="public-header__inner">
          ${publicBrand()}
          <nav class="desktop-nav" aria-label="Primary navigation">
            ${navItems.map(([label, href], index) => `<a href="${href}"${index === 0 ? ' aria-current="page"' : ""}>${label}</a>`).join("")}
          </nav>
          <div class="public-header__actions">
            <a class="public-login" href="/business/sign-in">Business login</a>
            <a class="luxury-button luxury-button--compact" href="/app/">Try Wearo ${star("gold-star--button")}</a>
            <button class="menu-toggle" type="button" aria-expanded="false" aria-controls="mobile-menu" aria-label="Open menu">
              <span></span><span></span>
            </button>
          </div>
        </div>
        <div class="mobile-menu" id="mobile-menu" hidden>
          <nav aria-label="Mobile navigation">
            ${navItems.map(([label, href]) => `<a href="${href}">${label}<span aria-hidden="true">↗</span></a>`).join("")}
            <a class="mobile-menu__login" href="/business/sign-in">Business login</a>
            <a class="luxury-button" href="/app/">Try Wearo ${star("gold-star--button")}</a>
          </nav>
        </div>
      </header>

      <main id="main">
        <section class="public-hero" aria-labelledby="hero-title">
          <div class="hero-media" aria-hidden="true">
            <img src="/wearo-hero-campaign.webp" alt="" fetchpriority="high" />
          </div>
          <div class="hero-shade" aria-hidden="true"></div>
          <div class="hero-orbit" aria-hidden="true">${star("gold-star--hero")}</div>
          <div class="public-hero__content">
            <p class="hero-kicker reveal-item">AI-powered virtual try-on <span></span> Made for your moment</p>
            <h1 id="hero-title" class="reveal-item">Before You<br /><em>Wear It,</em><br />Wearo It.</h1>
            <p class="hero-copy reveal-item">Experience the magic of AI-powered virtual try-on. Discover how jewellery, blouses, and beautiful styles look on you before you decide.</p>
            <div class="hero-ctas reveal-item">
              <a class="luxury-button" href="/app/">Try Wearo ${star("gold-star--button")}</a>
              <a class="text-link" href="/business/signup">Explore for Business <span aria-hidden="true">↗</span></a>
            </div>
          </div>
          <div class="hero-signature" aria-hidden="true">
            <span>Discover</span><i></i><span>Try</span><i></i><span>Shine</span>
          </div>
          <a class="scroll-cue" href="#phase-roadmap" aria-label="Scroll to discover more">
            <span>Discover</span><i aria-hidden="true"></i>
          </a>
        </section>

        <section class="phase-roadmap" id="phase-roadmap" aria-label="Wearo website preview">
          <div class="phase-roadmap__star">${star("gold-star--section")}</div>
          <p class="phase-roadmap__eyebrow">The Wearo experience</p>
          <h2>A new way to discover<br /><em>what feels like you.</em></h2>
          <p>More of the Wearo story is being thoughtfully composed. Experiences, transformations, business showcases, and our visual gallery arrive in the next phase.</p>
          <div class="phase-roadmap__chapters" aria-label="Upcoming website chapters">
            <span id="experiences">Experiences <small>02</small></span>
            <span id="businesses">For Businesses <small>03</small></span>
            <span id="gallery">Gallery <small>04</small></span>
            <span id="about">About Us <small>05</small></span>
            <span id="contact">Contact <small>06</small></span>
          </div>
        </section>
      </main>
      <footer class="business-footer">© 2026 All rights reserved · <a href="https://bitaddlabs.com" target="_blank" rel="noopener noreferrer">bitaddlabs.com</a></footer>
    </div>`;

  const header = root.querySelector("[data-public-header]");
  const menuButton = root.querySelector(".menu-toggle");
  const mobileMenu = root.querySelector("#mobile-menu");

  const closeMenu = () => {
    menuButton.setAttribute("aria-expanded", "false");
    menuButton.setAttribute("aria-label", "Open menu");
    mobileMenu.hidden = true;
    document.body.classList.remove("menu-open");
  };

  menuButton.addEventListener("click", () => {
    const willOpen = menuButton.getAttribute("aria-expanded") !== "true";
    menuButton.setAttribute("aria-expanded", String(willOpen));
    menuButton.setAttribute("aria-label", willOpen ? "Close menu" : "Open menu");
    mobileMenu.hidden = !willOpen;
    document.body.classList.toggle("menu-open", willOpen);
  });

  mobileMenu.querySelectorAll("a").forEach((link) => link.addEventListener("click", closeMenu));
  window.addEventListener("scroll", () => header.classList.toggle("is-scrolled", window.scrollY > 24), { passive: true });
}
