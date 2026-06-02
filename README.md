# screenshot-grid

Screenshot a list of web apps and build a **clickable 3×N grid** for any GitHub README. No API keys, no cost — pure [Playwright](https://playwright.dev) headless browser.

```bash
npm install
npx playwright install chromium   # one-time, ~120 MB
npm run build                      # screenshot all apps + generate README
```

## Usage

**1. Edit `apps.json`** — one entry per app:

```json
{
  "apps": [
    { "name": "My App",   "url": "https://myapp.com" },
    { "name": "Other",    "url": "https://other.io",  "dismiss": ["Accept cookies"] }
  ]
}
```

`dismiss` is optional — list button text or CSS selectors to click before snapping (age gates, cookie banners).

**2. Run:**

| Command | Does |
|---------|------|
| `npm run build` | Screenshot all apps + rebuild README |
| `npm run shots` | Screenshot only |
| `npm run grid`  | Rebuild README from existing shots |
| `node capture.mjs myapp` | Screenshot one app by name |
| `COLS=4 npm run grid` | Change grid columns (default 3) |

**3. Paste the generated `README.md` grid** wherever you want it.

## Reuse in another project

Point the tool at your project's directory with env vars:

```bash
APPS_FILE=./myproject/docs/screenshots/apps.json \
SHOTS_DIR=./myproject/docs/screenshots \
node capture.mjs
```

Then run `build-readme.mjs` with the same vars to write the grid into a file you include.

## Features

- **Auto-fallback http↔https** — if HTTPS handshake fails, retries over HTTP
- **Dismiss popups** before snapping (age gates, cookie banners, GDPR dialogs)
- **Retina-quality** — 1440×900 viewport at 2× device pixel ratio
- Reproducible: same `apps.json` → same grid

## Requirements

Node ≥ 18, `npm`, internet access to the target URLs.
