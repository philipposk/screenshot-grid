// Build README.md with a clickable grid of app screenshots.
// Each cell: a small image that links to the full-size PNG.
// Usage: node build-readme.mjs            (3 columns, default)
//        COLS=4 node build-readme.mjs     (override column count)
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const root = dirname(fileURLToPath(import.meta.url));
const { apps } = JSON.parse(readFileSync(join(root, "apps.json"), "utf8"));
const COLS = Number(process.env.COLS) || 3;
const CELL_W = 380; // px width of each thumbnail in the grid

const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

// Keep only apps whose screenshot actually exists.
const shots = apps
  .map((a) => ({ ...a, img: `shots/${slug(a.name)}.png` }))
  .filter((a) => existsSync(join(root, a.img)));

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

This repo screenshots a list of web apps and builds the grid above. No API keys, no cost.

\`\`\`bash
npm install
npx playwright install chromium   # one-time browser download
npm run build                      # screenshot every app + rebuild this README
\`\`\`

- Add apps in [\`apps.json\`](apps.json): \`{ "name": "...", "url": "https://..." }\`
- \`npm run shots\` — screenshot only (\`node capture.mjs greenpert\` for one app)
- \`npm run grid\` — rebuild README from existing screenshots (\`COLS=4\` to change columns)

Screenshots live in [\`shots/\`](shots/) at 1440×900, retina (2x).
`;

writeFileSync(join(root, "README.md"), md);
console.log(`README.md written: ${shots.length} app(s), ${COLS} columns.`);
