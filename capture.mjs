// Screenshot each app in apps.json into shots/<slug>.png
// No API keys, no network cost beyond loading the pages.
// Usage: node capture.mjs            (all apps)
//        node capture.mjs greenpert  (only matching name/slug)
import { chromium } from "playwright";
import { readFileSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const root = dirname(fileURLToPath(import.meta.url));
const { apps } = JSON.parse(readFileSync(join(root, "apps.json"), "utf8"));
const filter = process.argv[2]?.toLowerCase();

const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
const shotsDir = join(root, "shots");
mkdirSync(shotsDir, { recursive: true });

// Viewport = the "hero" view most people screenshot a site at.
const VIEWPORT = { width: 1440, height: 900 };

const targets = apps.filter(
  (a) => !filter || a.name.toLowerCase().includes(filter) || slug(a.name) === filter
);
if (!targets.length) {
  console.error(`No apps match "${filter}". Edit apps.json.`);
  process.exit(1);
}

const browser = await chromium.launch();
const ctx = await browser.newContext({
  viewport: VIEWPORT,
  deviceScaleFactor: 2, // retina-crisp images
});

for (const app of targets) {
  const out = join(shotsDir, `${slug(app.name)}.png`);
  const page = await ctx.newPage();
  // Try the given URL; if https handshake fails, retry once over http.
  const tries = [app.url];
  if (app.url.startsWith("https://")) tries.push("http://" + app.url.slice(8));
  let done = false;
  for (const url of tries) {
    try {
      await page.goto(url, { waitUntil: "networkidle", timeout: 45000 });
      await page.waitForTimeout(1500); // let fonts/animations settle
      // Optional: dismiss age-gates / cookie banners. Each entry is button text or a CSS selector.
      for (const d of app.dismiss ?? []) {
        try {
          const btn = d.startsWith(".") || d.startsWith("#") || d.includes("[")
            ? page.locator(d).first()
            : page.getByRole("button", { name: d }).first();
          await btn.click({ timeout: 4000 });
          await page.waitForTimeout(800);
        } catch { /* not present, fine */ }
      }
      await page.screenshot({ path: out, fullPage: false });
      console.log(`ok   ${app.name} -> ${out}${url !== app.url ? ` (via ${url})` : ""}`);
      done = true;
      break;
    } catch (err) {
      if (url === tries[tries.length - 1]) console.error(`FAIL ${app.name} (${url}): ${err.message}`);
    }
  }
  void done;
  {
    await page.close();
  }
}

await browser.close();
