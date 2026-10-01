# Maily product page

The static page published at `https://maily.thanaelfontaine.eu/`. Plain HTML, CSS and a few lines of
JavaScript, no framework, no build step, no third-party scripts, fonts or trackers: every file it
needs is in this folder. The page is complete without JavaScript; `main.js` only adds the scroll
reveal and the full-size screenshot viewer.

| File | Role |
|---|---|
| `index.html` | The page itself, with SEO tags, Open Graph, Twitter card and JSON-LD `SoftwareApplication` |
| `styles.css` | Styles, built on the colors of the app's Classic theme, with automatic dark mode and motion that stops under `prefers-reduced-motion: reduce` |
| `main.js` | Scroll reveal (IntersectionObserver) and the `<dialog>` that shows a screenshot full size |
| `404.html` | Page served for unknown addresses |
| `robots.txt`, `sitemap.xml` | Crawling hints |
| `favicon.ico`, `apple-touch-icon.png` | Icons, derived from `packaging/maily.png` |
| `assets/shots/` | Screenshots captured at 2x, in AVIF and WebP, 640, 1280 and 2560 pixels wide (plus 1920 for the hero) |
| `assets/` | Icons and the 1200x630 Open Graph image |

## Preview locally

From the repository root:

```bash
python3 -m http.server 8790 --directory site
```

Then open `http://127.0.0.1:8790/`. In Claude Code, the `maily-site` configuration of
`.claude/launch.json` starts the same server. Links are root-relative (`/styles.css`), so open the
page through a server, not as a `file://` URL.

## Refresh the assets

The script captures the app at 2x (a 1280x800 window, so 2560x1600 pixels) on the fictitious data
of `scripts/demo.py` with headless Chromium, never on real data, then encodes every size and
format, the icons and the Open Graph image:

```bash
uv run --group build --with playwright python scripts/site_assets.py
```

The first time, install the browser with `uv run --with playwright playwright install chromium`.
To encode captures you already have (2560x1600 PNG files named as in `assets/shots/`), add
`--from FOLDER`.

## Remove a system from the install section

Each system has its own card in `index.html`, between `<!-- OS:macos -->`, `<!-- OS:windows -->` or
`<!-- OS:linux -->` and the matching closing comment, and the "Also for" links of the hero and of the
final call to action are marked the same way. Delete the marked blocks of that system, then adjust
the FAQ answer "Does it work on Windows or Linux?", the `operatingSystem` of the JSON-LD and the meta
description. The grid of cards adapts by itself.

## Deployment

The page is served by Cloudflare Workers static assets (Worker `maily-thanaelfontaine-eu`, configured
in `wrangler.jsonc` at the repository root) on the custom domain `maily.thanaelfontaine.eu`, with
`404.html` as the not-found page. To publish a change, from the repository root:

```bash
npx wrangler deploy
```

`_headers` sets the security headers (a strict Content Security Policy that allows the one inline
script by its hash) and the cache rules; if that inline script changes, update its hash.
`.assetsignore` keeps this README out of the published files.
