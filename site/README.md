# Maily product page

The static page published at `https://maily.thanaelfontaine.eu/`. Plain HTML and CSS, no framework,
no build step, no JavaScript, no third-party scripts, fonts or trackers: every file it needs is in
this folder.

| File | Role |
|---|---|
| `index.html` | The page itself, with SEO tags, Open Graph, Twitter card and JSON-LD `SoftwareApplication` |
| `styles.css` | Styles, built on the colors of the app's Classic theme, with automatic dark mode |
| `404.html` | Page served for unknown addresses |
| `robots.txt`, `sitemap.xml` | Crawling hints |
| `favicon.ico`, `apple-touch-icon.png` | Icons, derived from `packaging/maily.png` |
| `assets/` | Screenshots (same names as `docs/images/`), icons and the 1200x630 Open Graph image |

## Preview locally

From the repository root:

```bash
python3 -m http.server 8790 --directory site
```

Then open `http://127.0.0.1:8790/`. In Claude Code, the `maily-site` configuration of
`.claude/launch.json` starts the same server. Links are root-relative (`/styles.css`), so open the
page through a server, not as a `file://` URL.

## Refresh the assets

Screenshots come from `docs/images/`. After they change, regenerate the copies, the icons and the
Open Graph image:

```bash
uv run --group build python scripts/site_assets.py
```

## Deployment (not configured yet)

The plan is to serve this folder as static assets with Cloudflare, on the `maily.thanaelfontaine.eu`
subdomain, with `404.html` as the not-found page. Nothing is deployed today: no Cloudflare project,
DNS record or workflow exists yet for this page.
