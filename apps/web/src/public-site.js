const navItems = [
  ["Home", "/"],
  ["Experiences", "/experiences"],
  ["For Businesses", "/for-business"],
  ["About Us", "/about"],
  ["Contact", "/contact"],
];

const heroJewelleryImages = [
  "/wearo-hero-campaign.webp",
  ...Array.from({ length: 10 }, (_, index) => `/hero-jewellery/jewellery-${index + 1}.webp`),
];

function publicBrand() {
  return `
    <a class="public-brand" href="/" aria-label="Wearo.ai home" data-public-route>
      <img src="/wearo-brand.png" alt="Wearo.ai" />
    </a>`;
}

function star(size = "") {
  return `<span class="gold-star ${size}" aria-hidden="true"><i></i></span>`;
}

function publicHeader(active = "Home", options = {}) {
  const primaryCtaHref = options.primaryCtaHref || "/app/";
  const primaryCtaLabel = options.primaryCtaLabel || "Try Wearo";
  return `
    <header class="public-header" data-public-header>
      <div class="public-header__inner">
        ${publicBrand()}
        <nav class="desktop-nav" aria-label="Primary navigation">
          ${navItems.map(([label, href, upcoming]) => `<a href="${href}"${label === active ? ' aria-current="page"' : ""}${upcoming ? ` data-coming-soon="${label}"` : " data-public-route"}>${label}</a>`).join("")}
        </nav>
        <div class="public-header__actions">
          <a class="public-login" href="/business/sign-in">Business login</a>
          <a class="luxury-button luxury-button--compact" href="${primaryCtaHref}">${primaryCtaLabel} ${star("gold-star--button")}</a>
          <button class="menu-toggle" type="button" aria-expanded="false" aria-controls="mobile-menu" aria-label="Open menu">
            <span></span><span></span>
          </button>
        </div>
      </div>
      <div class="mobile-menu" id="mobile-menu" hidden>
        <nav aria-label="Mobile navigation">
          ${navItems.map(([label, href, upcoming]) => `<a href="${href}"${label === active ? ' aria-current="page"' : ""}${upcoming ? ` data-coming-soon="${label}"` : " data-public-route"}>${label}<span aria-hidden="true">↗</span></a>`).join("")}
          <a class="mobile-menu__login" href="/business/sign-in">Business login</a>
          <a class="luxury-button" href="${primaryCtaHref}">${primaryCtaLabel} ${star("gold-star--button")}</a>
        </nav>
      </div>
      <div class="public-coming-soon" role="status" aria-live="polite" data-coming-soon-message hidden></div>
    </header>`;
}

function wirePublicHeader(root) {
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
  const comingSoonMessage = root.querySelector("[data-coming-soon-message]");
  let comingSoonTimer;
  root.querySelectorAll("[data-coming-soon]").forEach((link) => link.addEventListener("click", (event) => {
    event.preventDefault();
    window.clearTimeout(comingSoonTimer);
    comingSoonMessage.textContent = `${link.dataset.comingSoon} — coming soon`;
    comingSoonMessage.hidden = false;
    requestAnimationFrame(() => comingSoonMessage.classList.add("is-visible"));
    comingSoonTimer = window.setTimeout(() => {
      comingSoonMessage.classList.remove("is-visible");
      window.setTimeout(() => { comingSoonMessage.hidden = true; }, 250);
    }, 2400);
  }));
  root.querySelectorAll("[data-public-route]").forEach((link) => link.addEventListener("click", (event) => {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    const nextUrl = new URL(link.href, window.location.href);
    if (`${nextUrl.pathname}${nextUrl.search}` === `${window.location.pathname}${window.location.search}`) return;
    window.history.pushState({}, "", nextUrl);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }));
  window.addEventListener("scroll", () => header.classList.toggle("is-scrolled", window.scrollY > 24), { passive: true });
}

export function renderPublicSite(root) {
  document.documentElement.dataset.experience = "public";
  document.title = "Wearo.ai — Before You Wear It, Wearo It.";

  root.innerHTML = `
    <div class="public-site" id="home">
      ${publicHeader("Home")}

      <main id="main">
        <section class="public-hero" aria-labelledby="hero-title">
          <div class="hero-media" aria-hidden="true" data-hero-jewellery>
            ${heroJewelleryImages.map((src, index) => `<img class="hero-media__slide${index === 0 ? " is-active" : ""}" src="${src}" alt="" ${index === 0 ? 'fetchpriority="high"' : 'loading="lazy"'} decoding="async" />`).join("")}
          </div>
          <div class="hero-shade" aria-hidden="true"></div>
          <div class="hero-orbit" aria-hidden="true">${star("gold-star--hero")}</div>
          <div class="public-hero__content">
            <p class="hero-kicker reveal-item">AI-powered virtual try-on <span></span> Made for your moment</p>
            <h1 id="hero-title" class="reveal-item">Before You<br /><em>Wear It,</em><br />Wearo It.</h1>
            <p class="hero-copy reveal-item">Experience the magic of AI-powered virtual try-on. Discover how your favourite styles look on you before you decide.</p>
            <div class="hero-ctas reveal-item">
              <a class="luxury-button" href="/app/">Try Wearo ${star("gold-star--button")}</a>
              <a class="text-link" href="/business/signup">Explore for Business <span aria-hidden="true">↗</span></a>
            </div>
          </div>
          <div class="hero-signature" aria-hidden="true">
            <span>Discover</span><i></i><span>Try</span><i></i><span>Shine</span>
          </div>
          <a class="scroll-cue" href="/experiences" aria-label="Explore Wearo experiences" data-public-route>
            <span>Experiences</span><i aria-hidden="true"></i>
          </a>
        </section>
      </main>
      <footer class="about-footer">© 2026 All rights reserved · <a href="https://bitaddlabs.com" target="_blank" rel="noopener noreferrer">bitaddlabs.com</a></footer>
    </div>`;

  const heroSlides = [...root.querySelectorAll(".hero-media__slide")];
  if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches && heroSlides.length > 1) {
    let activeHeroSlide = 0;

    window.setInterval(() => {
      if (document.hidden) return;
      const nextHeroSlide = (activeHeroSlide + 1) % heroSlides.length;
      heroSlides[nextHeroSlide].classList.add("is-active");
      heroSlides[activeHeroSlide].classList.remove("is-active");
      activeHeroSlide = nextHeroSlide;
    }, 5000);
  }

  wirePublicHeader(root);
}

export function renderExperiencesSite(root) {
  document.documentElement.dataset.experience = "public";
  document.title = "Experiences — Wearo.ai";

  root.innerHTML = `
    <div class="public-site experiences-site">
      ${publicHeader("Experiences")}
      <main id="main">
        <section class="experience-studio" aria-labelledby="experiences-title">
          <div class="experience-intro">
            <div class="experience-intro__title">
              <p class="phase-roadmap__eyebrow">The Try-On Studio</p>
              <h1 id="experiences-title">Experiences</h1>
              <h2>Your style. Your moment.<br /><em>Your confidence.</em></h2>
            </div>
            <div class="experience-intro__aside"><span aria-hidden="true">✦</span><p>Imagine it. Try it virtually. Fall in love with your look before you make it yours.</p></div>
          </div>

          <section class="experience-showcase" aria-labelledby="showcase-title">
            <div class="experience-showcase__heading"><h2 id="showcase-title">Experience the Magic of Try-On</h2></div>
            <article class="experience-showcase__row experience-showcase__row--jewellery" data-jewellery-tryon>
              <div class="jewellery-tryon">
                <div class="jewellery-tryon__portrait">
                  <img class="is-selected" src="/experiences/jewellery/model-neutral-v2.webp" alt="Model ready for a jewellery selection" loading="eager" data-jewellery-model="" />
                  <img src="/experiences/jewellery/model-classic-gold-v2.webp" alt="Model wearing the classic gold jewellery set" loading="eager" data-jewellery-model="Classic Gold" />
                  <img src="/experiences/jewellery/model-kundan-v2.webp" alt="Model wearing the ivory kundan jewellery set" loading="eager" data-jewellery-model="Ivory Kundan" />
                  <img src="/experiences/jewellery/model-temple-v2.webp" alt="Model wearing the South Indian temple jewellery set" loading="eager" data-jewellery-model="Temple Gold" />
                  <img src="/experiences/jewellery/model-emerald-v2.webp" alt="Model wearing the emerald jewellery set" loading="eager" data-jewellery-model="Emerald" />
                  <img src="/experiences/jewellery/model-pearl-v2.webp" alt="Model wearing the pearl jewellery set" loading="eager" data-jewellery-model="Pearl" />
                  <span class="sr-only" aria-live="polite" data-jewellery-selection>No jewellery selected. Choose a style to preview it.</span>
                </div>
                <div class="jewellery-tryon__choices" role="group" aria-label="Choose a jewellery style">
                  <button type="button" aria-label="Try Classic Gold" aria-pressed="false" data-jewellery-option data-model="Classic Gold"><img src="/experiences/jewellery/product-classic-gold-v2.webp" alt="" /></button>
                  <button type="button" aria-label="Try Ivory Kundan" aria-pressed="false" data-jewellery-option data-model="Ivory Kundan"><img src="/experiences/jewellery/product-kundan-v2.webp" alt="" /></button>
                  <button type="button" aria-label="Try Temple Gold" aria-pressed="false" data-jewellery-option data-model="Temple Gold"><img src="/experiences/jewellery/product-temple-v2.webp" alt="" /></button>
                  <button type="button" aria-label="Try Emerald" aria-pressed="false" data-jewellery-option data-model="Emerald"><img src="/experiences/jewellery/product-meenakari-v2.webp" alt="" /></button>
                  <button type="button" aria-label="Try Pearl" aria-pressed="false" data-jewellery-option data-model="Pearl"><img src="/experiences/jewellery/product-silver-v2.webp" alt="" /></button>
                </div>
              </div>
              <div class="experience-showcase__copy"><p class="experience-showcase__status">Available now · Five styles</p><h3>Jewellery Try-On</h3><p>Choose a jewellery set and see the look instantly on the same model.</p><strong>Select. Preview. Find your sparkle.</strong></div>
            </article>
            <article class="experience-showcase__row experience-showcase__row--blouse" data-blouse-tryon>
              <div class="blouse-tryon">
                <div class="blouse-tryon__stage">
                  <img class="is-selected" src="/experiences/blouse/royal-jewel.webp" alt="Standing model showcasing the Royal Jewel blouse from the front and back" loading="eager" data-blouse-model="Royal Jewel" />
                  <img src="/experiences/blouse/lotus-muse.webp" alt="Standing model showcasing the Lotus Muse blouse from the front and back" loading="lazy" data-blouse-model="Lotus Muse" />
                  <img src="/experiences/blouse/midnight-pearl.webp" alt="Standing model showcasing the Midnight Pearl blouse from the front and back" loading="lazy" data-blouse-model="Midnight Pearl" />
                  <div class="blouse-tryon__views" aria-hidden="true"><span>Front</span><span>Back</span></div>
                  <span class="sr-only" aria-live="polite" data-blouse-selection>Royal Jewel selected, front and back views shown</span>
                </div>
                <div class="blouse-tryon__choices" role="group" aria-label="Choose a blouse design">
                  <button class="is-selected" type="button" aria-label="Try Royal Jewel blouse" aria-pressed="true" data-blouse-option data-model="Royal Jewel"><img src="/experiences/blouse/product-royal-jewel.webp" alt="Ruby zardozi blouse" loading="lazy" /></button>
                  <button type="button" aria-label="Try Lotus Muse blouse" aria-pressed="false" data-blouse-option data-model="Lotus Muse"><img src="/experiences/blouse/product-lotus-muse.webp" alt="Emerald lotus silk blouse" loading="lazy" /></button>
                  <button type="button" aria-label="Try Midnight Pearl blouse" aria-pressed="false" data-blouse-option data-model="Midnight Pearl"><img src="/experiences/blouse/product-midnight-pearl.webp" alt="Midnight navy pearl blouse" loading="lazy" /></button>
                </div>
              </div>
              <div class="experience-showcase__copy"><p class="experience-showcase__status">Available now · Three designs</p><h3>Boutique &amp; Blouse Try-On</h3><p>Explore every blouse from both angles. Compare necklines, sleeves, embroidery, and back details with the same ivory saree.</p><strong>Your saree. Your style. Beautifully matched.</strong></div>
            </article>
            <article class="experience-showcase__row experience-showcase__row--upcoming">
              <img src="/hero-jewellery/jewellery-10.webp" alt="An editorial Indian fashion look" loading="lazy" />
              <div><p class="experience-showcase__status">Coming soon</p><h3>Fashion Try-On</h3><p>Experiment with outfits and discover new looks without the uncertainty of imagining how they might fit your style.</p><strong>Explore more. Choose confidently.</strong></div>
            </article>
          </section>
        </section>

        <section class="experience-finale" aria-labelledby="experience-finale-title">
          <div class="experience-finale__star">${star("gold-star--hero")}</div><p>Ready when you are</p>
          <h2 id="experience-finale-title">Your next favourite<br /><em>look awaits.</em></h2><p>Why just imagine it when you can see it?</p>
          <a class="luxury-button" href="/app/">Experience Wearo ${star("gold-star--button")}</a>
        </section>
      </main>
      <footer class="business-footer">© 2026 All rights reserved · <a href="https://bitaddlabs.com" target="_blank" rel="noopener noreferrer">bitaddlabs.com</a></footer>
    </div>`;

  const jewellerySelection = root.querySelector("[data-jewellery-selection]");
  root.querySelectorAll("[data-jewellery-option]").forEach((option) => {
    option.addEventListener("click", () => {
      root.querySelectorAll("[data-jewellery-option]").forEach((candidate) => {
        const selected = candidate === option;
        candidate.classList.toggle("is-selected", selected);
        candidate.setAttribute("aria-pressed", String(selected));
      });
      root.querySelectorAll("[data-jewellery-model]").forEach((model) => model.classList.toggle("is-selected", model.dataset.jewelleryModel === option.dataset.model));
      jewellerySelection.textContent = `${option.dataset.model} selected`;
    });
  });
  const blouseSelection = root.querySelector("[data-blouse-selection]");
  root.querySelectorAll("[data-blouse-option]").forEach((option) => {
    option.addEventListener("click", () => {
      root.querySelectorAll("[data-blouse-option]").forEach((candidate) => {
        const selected = candidate === option;
        candidate.classList.toggle("is-selected", selected);
        candidate.setAttribute("aria-pressed", String(selected));
      });
      root.querySelectorAll("[data-blouse-model]").forEach((model) => model.classList.toggle("is-selected", model.dataset.blouseModel === option.dataset.model));
      blouseSelection.textContent = `${option.dataset.model} selected, front and back views shown`;
    });
  });
  wirePublicHeader(root);
}

export function renderForBusinessSite(root) {
  document.documentElement.dataset.experience = "public";
  document.title = "For Businesses - Wearo.ai";

  root.innerHTML = `
    <div class="public-site for-business-site">
      ${publicHeader("For Businesses")}
      <main id="main">
        <section class="business-marketing-hero" aria-labelledby="business-marketing-title">
          <div class="business-marketing-hero__media" aria-hidden="true">
            <img src="/hero-jewellery/jewellery-6.webp" alt="" fetchpriority="high" />
          </div>
          <div class="business-marketing-hero__shade" aria-hidden="true"></div>
          <div class="business-marketing-hero__inner">
            <p class="hero-kicker reveal-item">Virtual try-on for modern retail <span></span> Built for your customers</p>
            <h1 id="business-marketing-title" class="reveal-item">Turn “Will it suit me?”<br />into <em>“I’ll take it.”</em></h1>
            <p class="business-marketing-hero__copy reveal-item">Help every customer see the look before they buy - so decisions feel easier, conversations move faster, and confidence follows them to checkout.</p>
            <div class="hero-ctas reveal-item">
              <a class="luxury-button" href="/business/signup">Bring Wearo to your store ${star("gold-star--button")}</a>
              <a class="text-link" href="#how-it-helps">See how it helps <span aria-hidden="true">↓</span></a>
            </div>
          </div>
          <div class="business-hero-proof" aria-label="Designed for four retail categories">
            <span>Jewellery</span><i></i><span>Boutiques</span><i></i><span>Sarees</span><i></i><span>Retail</span>
          </div>
        </section>

        <section class="business-confidence" id="how-it-helps" aria-labelledby="business-confidence-title">
          <div class="business-section-heading">
            <div>
              <p class="phase-roadmap__eyebrow">Confidence is the conversion</p>
              <h2 id="business-confidence-title">Your products already catch their eye.<br /><em>Wearo helps them decide.</em></h2>
            </div>
            <p>Customers hesitate when they cannot picture the final look. Wearo closes that imagination gap with a personal, visual try-on moment.</p>
          </div>
          <div class="business-benefit-grid">
            <article><span>01</span><div class="business-benefit-grid__icon" aria-hidden="true">✦</div><h3>Make the choice feel real</h3><p>Let customers see jewellery, blouse designs, sarees, and styles on a person - not only on a shelf or product card.</p></article>
            <article><span>02</span><div class="business-benefit-grid__icon" aria-hidden="true">↗</div><h3>Move from doubt to decision</h3><p>Give shoppers a clearer reason to say yes while their interest is highest, in store or while browsing online.</p></article>
            <article><span>03</span><div class="business-benefit-grid__icon" aria-hidden="true">◎</div><h3>Create a better sales conversation</h3><p>Help staff guide customers through alternatives visually, making recommendations feel personal and easy to compare.</p></article>
          </div>
        </section>

        <section class="business-journey" aria-labelledby="business-journey-title">
          <div class="business-journey__visual">
            <img src="/experiences/jewellery/model-temple-v2.webp" alt="Customer previewing a temple jewellery look with Wearo" loading="lazy" />
            <div class="business-journey__tag"><span>Live preview</span><strong>Temple Gold</strong></div>
          </div>
          <div class="business-journey__content">
            <p class="phase-roadmap__eyebrow">A simpler path to purchase</p>
            <h2 id="business-journey-title">See it. Believe it.<br /><em>Buy confidently.</em></h2>
            <div class="business-journey__steps">
              <article><span>01</span><div><h3>Discover</h3><p>Your customer finds a piece, blouse, saree, or style that catches their attention.</p></div></article>
              <article><span>02</span><div><h3>Try</h3><p>They preview the look virtually and compare the options that suit them best.</p></div></article>
              <article><span>03</span><div><h3>Choose</h3><p>They move forward with a clearer picture and greater confidence in the purchase.</p></div></article>
            </div>
          </div>
        </section>

        <section class="business-segments" aria-labelledby="business-segments-title">
          <div class="business-segments__heading">
            <p class="phase-roadmap__eyebrow">Made for the way you sell</p>
            <h2 id="business-segments-title">One experience.<br /><em>Many storefronts.</em></h2>
          </div>
          <div class="business-vertical-list">
            <article class="business-vertical-card">
              <figure><img src="/for-business/jewellery-phone-tryon.webp" alt="A necklace photographed on a phone and shown virtually on the customer" loading="lazy" /><figcaption><span>Capture</span><i></i><span>Preview</span></figcaption></figure>
              <div class="business-vertical-card__copy"><span>01 · Jewellery shops</span><h3>Let every piece be tried<br />without leaving the counter.</h3><p>Photograph a necklace or set, then help the customer see that same piece on herself.</p><ul><li>Compare high-value pieces with less repeated handling</li><li>Keep the sales conversation moving while stock stays organised</li><li>Show more of the catalogue than the counter can hold at once</li></ul></div>
            </article>
            <article class="business-vertical-card business-vertical-card--reverse">
              <figure><img src="/for-business/boutique-phone-tryon.webp" alt="A Punjabi dress photographed on a phone and shown virtually on the customer" loading="lazy" /><figcaption><span>Photograph</span><i></i><span>See it worn</span></figcaption></figure>
              <div class="business-vertical-card__copy"><span>02 · Women’s boutiques</span><h3>Turn a new arrival into<br />a personal fitting moment.</h3><p>Capture a Punjabi dress, kurta, or blouse and present it on the customer before she changes outfits.</p><ul><li>Browse the catalogue easily</li><li>Try a selected design with virtual try-on</li><li>Create a new design based on customer requirements</li></ul></div>
            </article>
            <article class="business-vertical-card">
              <figure><img src="/for-business/saree-phone-tryon.webp" alt="A saree and blouse photographed on a phone and shown as a complete virtual look" loading="lazy" /><figcaption><span>Pair</span><i></i><span>Complete the look</span></figcaption></figure>
              <div class="business-vertical-card__copy"><span>03 · Saree sellers</span><h3>Show the complete look<br />before the first drape.</h3><p>Photograph the saree and matching blouse, then reveal how the combination comes together on the customer.</p><ul><li>Present blouse pairings before opening multiple sarees</li><li>Compare borders, colours, and combinations side by side</li><li>Make coordinated blouse and jewellery suggestions feel natural</li></ul></div>
            </article>
            <article class="business-vertical-card business-vertical-card--reverse">
              <figure><img src="/for-business/retail-phone-tryon.webp" alt="A traditional children’s dress photographed on a phone and shown virtually on a young shopper" loading="lazy" /><figcaption><span>Select</span><i></i><span>Try virtually</span></figcaption></figure>
              <div class="business-vertical-card__copy"><span>04 · Family retail</span><h3>Make family shopping<br />quicker and more engaging.</h3><p>Capture a traditional outfit and let families preview the same design on the young shopper.</p><ul><li>Explore festive options without repeated outfit changes</li><li>Help parents compare colours and designs in one place</li><li>Bring less-visible catalogue choices into the conversation</li></ul></div>
            </article>
          </div>
        </section>

        <section class="business-outcomes" aria-labelledby="business-outcomes-title">
          <p class="phase-roadmap__eyebrow">What changes for your business</p>
          <h2 id="business-outcomes-title">A customer who can see the choice<br /><em>can make the choice.</em></h2>
          <div class="business-outcomes__list">
            <div><span>01</span><strong>More confident purchase decisions</strong></div>
            <div><span>02</span><strong>More engaging in-store conversations</strong></div>
            <div><span>03</span><strong>Better product discovery and comparison</strong></div>
            <div><span>04</span><strong>A modern experience customers remember</strong></div>
          </div>
        </section>

        <section class="business-marketing-cta" aria-labelledby="business-cta-title">
          <div class="business-marketing-cta__star">${star("gold-star--hero")}</div>
          <p>Let customers picture the yes</p>
          <h2 id="business-cta-title">Bring confident buying<br /><em>to your business.</em></h2>
          <p>Tell us about your store, catalogue, and customers. We’ll help you explore the right Wearo experience.</p>
          <a class="luxury-button" href="/contact">Talk to Wearo ${star("gold-star--button")}</a>
        </section>
      </main>
      <footer class="business-footer">© 2026 Wearo.ai · All rights reserved · <a href="https://bitaddlabs.com" target="_blank" rel="noopener noreferrer">bitaddlabs.com</a></footer>
    </div>`;

  wirePublicHeader(root);
}

export function renderAboutSite(root) {
  document.documentElement.dataset.experience = "public";
  document.title = "About Us — Wearo.ai";

  root.innerHTML = `
    <div class="public-site about-site">
      ${publicHeader("About Us")}
      <main id="main">
        <section class="about-hero" aria-labelledby="about-title">
          <div class="about-hero__glow" aria-hidden="true"></div>
          <div class="about-hero__inner">
            <div class="about-hero__copy">
              <p class="hero-kicker reveal-item">Our story <span></span> Confidence, made visible</p>
              <h1 id="about-title" class="reveal-item">See it.<br /><em>Love it.</em><br />Wear it.</h1>
              <p class="about-hero__lede reveal-item">At <strong>Wearo.ai</strong>, we believe AI should become a natural part of everyday life — helping people make choices with greater confidence.</p>
            </div>
            <figure class="about-portrait reveal-item">
              <img src="/hero-jewellery/jewellery-4.webp" alt="A woman wearing elegant jewellery, illustrating the Wearo virtual try-on experience" fetchpriority="high" />
              <figcaption><span>01</span> Imagination, made tangible</figcaption>
            </figure>
          </div>
          <a class="scroll-cue" href="#our-belief" aria-label="Read our story"><span>Our belief</span><i aria-hidden="true"></i></a>
        </section>

        <section class="about-belief" id="our-belief" aria-labelledby="belief-title">
          <div class="about-belief__marker">${star("gold-star--section")}</div>
          <p class="phase-roadmap__eyebrow">What we are building</p>
          <h2 id="belief-title">From imagination<br />to <em>experience.</em></h2>
          <div class="about-belief__copy">
            <p>We are building experiences that let you <strong>see how something looks on you before you buy it.</strong></p>
            <p>Whether it is jewellery, fashion, or a new style, we want to turn imagination into something you can actually see and experience.</p>
          </div>
        </section>

        <section class="about-confidence" aria-labelledby="confidence-title">
          <div class="about-confidence__image" aria-hidden="true">
            <img src="/hero-jewellery/jewellery-8.webp" alt="" loading="lazy" />
          </div>
          <div class="about-confidence__content">
            <p class="phase-roadmap__eyebrow">Why it matters</p>
            <h2 id="confidence-title">Confidence changes<br /><em>everything.</em></h2>
            <p>Because when you can <strong>try before you buy</strong>, you choose with confidence, feel better about your decision, and enjoy the way you shine.</p>
            <div class="about-steps" aria-label="The Wearo experience">
              <div><span>01</span><strong>Discover</strong><small>Find what catches your eye.</small></div>
              <div><span>02</span><strong>Try</strong><small>See it become part of you.</small></div>
              <div><span>03</span><strong>Shine</strong><small>Choose with true confidence.</small></div>
            </div>
          </div>
        </section>

        <section class="about-finale" aria-labelledby="finale-title">
          <div class="about-finale__star">${star("gold-star--hero")}</div>
          <p>Wearo.ai</p>
          <h2 id="finale-title">Discover <i></i> try <i></i> shine.</h2>
          <a class="luxury-button" href="/app/">Try Wearo ${star("gold-star--button")}</a>
        </section>
      </main>
      <footer class="about-footer">© 2026 Wearo.ai · All rights reserved · <a href="https://bitaddlabs.com" target="_blank" rel="noopener noreferrer">bitaddlabs.com</a></footer>
    </div>`;

  wirePublicHeader(root);
}

export function renderContactSite(root) {
  document.documentElement.dataset.experience = "public";
  document.title = "Contact for Business — Wearo.ai";

  root.innerHTML = `
    <div class="public-site contact-site">
      ${publicHeader("Contact")}
      <main id="main">
        <section class="contact-hero" aria-labelledby="contact-title">
          <div class="contact-hero__orb" aria-hidden="true">${star("gold-star--hero")}</div>
          <div class="contact-hero__inner">
            <div class="contact-intro">
              <p class="hero-kicker reveal-item">Business enquiries <span></span> Let’s create what’s next</p>
              <h1 id="contact-title" class="reveal-item">Bring the<br /><em>try-on moment</em><br />to your brand.</h1>
              <p class="contact-intro__copy reveal-item">Tell us a little about your business and what you would like to explore with Wearo.ai. We’ll use these details to understand the right next conversation.</p>
              <aside class="contact-business-note reveal-item" aria-label="Who this form is for">
                <span aria-hidden="true">B2B</span>
                <div>
                  <strong>For brands and businesses</strong>
                  <p>This form is for retail, brand, partnership, and enterprise enquiries.</p>
                </div>
              </aside>
              <p class="contact-consumer-link reveal-item">Looking to try Wearo for yourself? <a href="/app/">Start your try-on <span aria-hidden="true">↗</span></a></p>
            </div>

            <div class="contact-form-card reveal-item">
              <div class="contact-form-card__heading">
                <p>Start a conversation</p>
                <span>Required fields are marked *</span>
              </div>
              <form class="contact-form" data-contact-form novalidate>
                <label for="contact-name">Name <span aria-hidden="true">*</span>
                  <input id="contact-name" name="name" type="text" autocomplete="name" maxlength="120" required />
                </label>
                <label for="contact-email">Business email <span aria-hidden="true">*</span>
                  <input id="contact-email" name="email" type="email" autocomplete="email" maxlength="254" required />
                </label>
                <label for="contact-mobile">Mobile number <span aria-hidden="true">*</span>
                  <input id="contact-mobile" name="mobile" type="tel" autocomplete="tel" inputmode="tel" maxlength="24" pattern="[0-9+() .-]{7,24}" aria-describedby="contact-mobile-help" required />
                  <small id="contact-mobile-help">Include your country code.</small>
                </label>
                <label for="contact-website">Business website <small>Optional</small>
                  <input id="contact-website" name="website" type="url" autocomplete="url" maxlength="300" placeholder="https://" />
                </label>
                <label for="contact-purpose">Purpose <span aria-hidden="true">*</span>
                  <select id="contact-purpose" name="purpose" required>
                    <option value="">Select a purpose</option>
                    <option value="BRAND_TRY_ON">Virtual try-on for my brand</option>
                    <option value="RETAIL_PARTNERSHIP">Retail partnership</option>
                    <option value="ENTERPRISE_DEMO">Enterprise demo</option>
                    <option value="TECHNOLOGY_PARTNERSHIP">Technology partnership</option>
                    <option value="PRESS">Press or media</option>
                    <option value="OTHER">Something else</option>
                  </select>
                </label>
                <button class="luxury-button contact-submit" type="submit"><span data-contact-submit-label>Submit enquiry</span> ${star("gold-star--button")}</button>
                <p class="contact-form__error" data-contact-error role="alert" hidden>Please check the highlighted fields and try again.</p>
              </form>

              <div class="contact-success" data-contact-success role="status" aria-live="polite" hidden>
                <div class="contact-success__star">${star("gold-star--section")}</div>
                <p>Thank you</p>
                <h2>Your business enquiry<br /><em>is with us.</em></h2>
                <p>Thank you for your interest in building with Wearo.ai. Our team will review your enquiry and follow up using the details you provided.</p>
                <button class="text-link contact-success__again" type="button" data-contact-again>Send another enquiry <span aria-hidden="true">↗</span></button>
              </div>
            </div>
          </div>
        </section>
      </main>
      <footer class="about-footer">© 2026 Wearo.ai · All rights reserved · <a href="https://bitaddlabs.com" target="_blank" rel="noopener noreferrer">bitaddlabs.com</a></footer>
    </div>`;

  wirePublicHeader(root);

  const form = root.querySelector("[data-contact-form]");
  const success = root.querySelector("[data-contact-success]");
  const error = root.querySelector("[data-contact-error]");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!form.checkValidity()) {
      form.classList.add("was-validated");
      error.hidden = false;
      form.reportValidity();
      return;
    }
    const submitButton = form.querySelector(".contact-submit");
    const submitLabel = form.querySelector("[data-contact-submit-label]");
    submitButton.disabled = true;
    submitLabel.textContent = "Sending…";
    error.hidden = true;
    try {
      const values = new FormData(form);
      const response = await fetch("/api/v1/public/contact-enquiries", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-Wearo-Contact-Token": import.meta.env.VITE_WEARO_CONTACT_FORM_TOKEN || "",
        },
        body: JSON.stringify({
          name: values.get("name"),
          email: values.get("email"),
          mobile: values.get("mobile"),
          website_url: values.get("website") || null,
          purpose: values.get("purpose"),
        }),
      });
      if (!response.ok) throw new Error("CONTACT_SUBMISSION_FAILED");
      form.hidden = true;
      root.querySelector(".contact-form-card__heading").hidden = true;
      success.hidden = false;
      success.setAttribute("tabindex", "-1");
      success.focus();
      form.reset();
    } catch {
      error.textContent = "We couldn’t send your enquiry right now. Please try again in a moment.";
      error.hidden = false;
    } finally {
      submitButton.disabled = false;
      submitLabel.textContent = "Submit enquiry";
    }
  });

  root.querySelector("[data-contact-again]").addEventListener("click", () => {
    success.hidden = true;
    form.hidden = false;
    root.querySelector(".contact-form-card__heading").hidden = false;
    form.classList.remove("was-validated");
    root.querySelector("#contact-name").focus();
  });
}
