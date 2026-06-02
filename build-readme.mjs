// Build README.md with a clickable grid of app screenshots.
// Each cell: a small image that links to the full-size PNG.
// Usage: node build-readme.mjs            (3 columns, default)
//        COLS=4 node build-readme.mjs     (override column count)
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const root = dirname(fileURLToPath(import.meta.url));
const { apps } = JSON.parse(readFileSync(join(root, "apps.json"), "utf8"));

const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
const shots = apps
  .map((a) => ({ ...a, img: `shots/${slug(a.name)}.png` }))
  .filter((a) => existsSync(join(root, a.img)));

// Auto-pick columns based on screenshot count so the grid stays dense.
// A manual COLS env override always wins.
function autoCols(n) {
  if (n <= 2) return n;
  if (n <= 4) return 2;
  if (n <= 9) return 3;
  if (n <= 16) return 4;
  return 5;
}
const COLS = Number(process.env.COLS) || autoCols(shots.length);

// Cell width shrinks a bit as columns increase so the grid fits GitHub's ~900px preview.
const CELL_W = COLS <= 2 ? 560 : COLS === 3 ? 380 : COLS === 4 ? 280 : 220;

const cell = (a) =>
  `<a href="${a.img}"><img src="${a.img}" alt="${a.name}" width="${CELL_W}"></a><br><sub><b>${a.name}</b> — <a href="${a.url}">${a.url}</a></sub>`;

// Build an HTML table so columns stay aligned and images stay clickable.
let rows = "";
for (let i = 0; i < shots.length; i += COLS) {
  const cells = shots
    .slice(i, i + COLS)
    .map((a) => `    <td align="center" valign="top">${cell(a)}</td>`)
    .join("\n");
  rows += `  <tr>\n${cells}\n  </tr>\n`;
}

const md = `# App Screenshot Gallery

Click any screenshot to open the full-size image.

<table>
${rows}</table>

---

## How this works (reusable tool)

Screenshots multiple pages of a web app and builds the clickable grid above. No API keys, no cost — pure headless browser.

\`\`\`bash
npm install
npx playwright install chromium   # one-time browser download
npm run build                      # screenshot every page + rebuild this README
\`\`\`

- Edit [\`apps.json\`](apps.json) to list the pages you want: \`{ "name": "...", "url": "https://..." }\`
- Add a \`"dismiss"\` array to click through age-gates or cookie banners before snapping
- \`npm run shots\` — re-screenshot only
- \`npm run grid\` — rebuild README from existing shots (\`COLS=4\` to force column count)
- Grid columns auto-scale: 1–2 shots → match count, 3–4 → 2 cols, 5–9 → 3 cols, 10–16 → 4 cols, 17+ → 5 cols

Screenshots live in [\`shots/\`](shots/) at 1440×900, retina (2×).
`;

writeFileSync(join(root, "README.md"), md);
console.log(`README.md written: ${shots.length} shot(s) → ${COLS} columns (auto: ${autoCols(shots.length)}, used: ${COLS}).`);
