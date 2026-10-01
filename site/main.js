// Maily product page: two small enhancements. The page is complete without them.
(() => {
  "use strict";
  const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // 1. Sections fade and slide in as they scroll into view.
  const selector = [
    ".section h2", ".band h2", ".section-lead", ".benefit", ".card", ".why-quote",
    ".feature", ".sub", ".sub-lead", ".gallery figure", ".table-wrap", ".flow > li", ".note",
    ".step > h3", ".step > p", ".step > pre", ".os-card", ".os-source", ".grid2 > *", "details", ".final .wrap > *",
  ].join(",");
  if (!calm && "IntersectionObserver" in window) {
    const items = [...document.querySelectorAll(selector)].filter((el) => !el.closest(".hero"));
    const seen = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        entry.target.classList.add("in");
        seen.unobserve(entry.target);
      }
    }, { rootMargin: "0px 0px -6% 0px" });
    for (const el of items) {
      const top = el.getBoundingClientRect().top;
      if (top < window.innerHeight) continue; // already on screen: no flash
      const siblings = [...el.parentElement.children].filter((c) => c.matches(selector));
      el.style.setProperty("--delay", `${(siblings.indexOf(el) % 4) * 70}ms`);
      el.classList.add("reveal");
      seen.observe(el);
    }
  }

  // 2. Screenshots open full size in a dialog (without JavaScript, the link opens the image).
  const viewer = document.getElementById("viewer");
  if (!viewer || typeof viewer.showModal !== "function") return;
  const big = viewer.querySelector("img");
  const caption = viewer.querySelector(".viewer-cap");
  const sizeButton = viewer.querySelector('[data-viewer="size"]');
  const setActual = (on) => {
    viewer.classList.toggle("actual", on);
    sizeButton.setAttribute("aria-pressed", String(on));
    sizeButton.textContent = on ? "Fit to screen" : "Actual size";
  };
  document.addEventListener("click", (event) => {
    const link = event.target.closest("a.zoom");
    if (!link || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    const thumb = link.querySelector("img");
    // Same theme and format as the thumbnail the browser picked, at full resolution.
    const shown = thumb.currentSrc || link.href;
    big.src = shown.replace(/-\d+\.(avif|webp)$/, "-2560.$1");
    big.alt = thumb.alt;
    caption.textContent = thumb.alt;
    setActual(false);
    viewer.showModal();
  });
  sizeButton.addEventListener("click", () => setActual(!viewer.classList.contains("actual")));
  big.addEventListener("click", () => setActual(!viewer.classList.contains("actual")));
  viewer.addEventListener("click", (event) => {
    if (event.target === viewer || event.target.classList.contains("viewer-body")) viewer.close();
  });
  viewer.addEventListener("close", () => big.removeAttribute("src"));
})();
