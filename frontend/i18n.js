"use strict";

/* Interface translations, without any dependency.

   Each language lives in frontend/i18n/<code>.json, a flat object whose keys
   are English identifiers ("composer.send") and whose values are the text.
   English is the reference: every other file must have exactly the same keys
   (checked by tests/test_i18n.py). A key missing from the active language
   falls back to English, then to the key itself, so the interface never
   breaks.

   Plurals use Intl.PluralRules: a key "x" with plural forms is stored as
   "x.one" and "x.other" (".other" is used for any category that has no key).
   Placeholders are written {name} and filled from the `vars` object. */

const I18N = (() => {
  const LANGUAGES = [
    { code: "en", name: "English", locale: "en" },
    { code: "fr", name: "Français", locale: "fr" },
    { code: "de", name: "Deutsch", locale: "de" },
    { code: "es", name: "Español", locale: "es" },
    { code: "pt", name: "Português", locale: "pt-BR" },
  ];
  const DEFAULT = "en";
  const tables = {};
  let current = DEFAULT;

  function supported(code) {
    return LANGUAGES.some((l) => l.code === code);
  }

  // First supported language among the system/browser preferences, else English.
  function detect(list) {
    const prefs = list || (typeof navigator !== "undefined"
      ? (navigator.languages && navigator.languages.length ? navigator.languages : [navigator.language])
      : []);
    for (const tag of prefs) {
      const base = String(tag || "").toLowerCase().split(/[-_]/)[0];
      if (supported(base)) return base;
    }
    return DEFAULT;
  }

  async function fetchTable(code) {
    if (tables[code]) return tables[code];
    const r = await fetch(`/static/i18n/${code}.json`);
    if (!r.ok) throw new Error(`i18n ${code}: HTTP ${r.status}`);
    tables[code] = await r.json();
    return tables[code];
  }

  async function setLanguage(code) {
    if (!supported(code)) code = DEFAULT;
    try { await fetchTable(DEFAULT); } catch { tables[DEFAULT] = tables[DEFAULT] || {}; }
    if (code !== DEFAULT) {
      try { await fetchTable(code); } catch { code = DEFAULT; }
    }
    current = code;
    document.documentElement.lang = code;
    return code;
  }

  function lookup(key) {
    const own = tables[current] || {};
    if (Object.prototype.hasOwnProperty.call(own, key)) return own[key];
    const en = tables[DEFAULT] || {};
    if (Object.prototype.hasOwnProperty.call(en, key)) return en[key];
    return undefined;
  }

  function has(key) { return lookup(key) !== undefined; }

  function locale() {
    return (LANGUAGES.find((l) => l.code === current) || LANGUAGES[0]).locale;
  }

  function fill(text, vars) {
    if (!vars) return text;
    return text.replace(/\{(\w+)\}/g, (m, name) =>
      Object.prototype.hasOwnProperty.call(vars, name) ? String(vars[name]) : m);
  }

  function t(key, vars) {
    let text;
    if (vars && typeof vars.count === "number" && lookup(key + ".other") !== undefined) {
      let cat = "other";
      try { cat = new Intl.PluralRules(locale()).select(vars.count); } catch { /* keep "other" */ }
      text = lookup(`${key}.${cat}`);
      if (text === undefined) text = lookup(key + ".other");
      vars = { ...vars, count: formatNumber(vars.count) };
    } else {
      text = lookup(key);
    }
    if (text === undefined) return key;
    return fill(text, vars);
  }

  function formatNumber(n, options) {
    try { return new Intl.NumberFormat(locale(), options).format(n); }
    catch { return String(n); }
  }

  // Static markup: data-i18n (text), data-i18n-placeholder, data-i18n-title,
  // data-i18n-aria-label. The English text in index.html is only a fallback.
  function applyDom(root) {
    const scope = root || document;
    scope.querySelectorAll("[data-i18n]").forEach((n) => { n.textContent = t(n.dataset.i18n); });
    const attrs = { i18nPlaceholder: "placeholder", i18nTitle: "title", i18nAriaLabel: "aria-label" };
    for (const [data, attr] of Object.entries(attrs)) {
      const sel = "[data-" + data.replace(/[A-Z]/g, (c) => "-" + c.toLowerCase()) + "]";
      scope.querySelectorAll(sel).forEach((n) => n.setAttribute(attr, t(n.dataset[data])));
    }
  }

  return {
    LANGUAGES, DEFAULT, detect, setLanguage, t, has, locale, formatNumber, applyDom,
    get language() { return current; },
  };
})();

// Short alias used everywhere in app.js (named `tr` so that local variables
// called `t` never shadow it).
const tr = I18N.t;
