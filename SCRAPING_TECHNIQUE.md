# Scraping technique — how to extract structured data from a website

This doc describes the exact workflow used to build the AllBud Scrapy spider in this repo. Hand it to another agent with "follow SCRAPING_TECHNIQUE.md" and they can replicate it against any target.

---

## Step 1 — Find the best data source

Before writing a line of scraping code, survey what's available:

1. **Open datasets first** (Kaggle, HuggingFace, GitHub). Downloading a CSV beats scraping every time. Search `"[topic] dataset site:kaggle.com OR site:huggingface.co OR site:github.com"`.
2. **Check for a public API**. Look for `/api/`, `/v1/`, or `graphql` in page source. A JSON endpoint is faster and more stable than HTML scraping.
3. **Fall back to scraping** only when no clean dataset or API exists.

For cannabis strain data we found:
- Kushy (GitHub, MIT): good names/effects, but cannabinoid data is fake placeholders
- Cannlytics (HuggingFace, CC BY 4.0): real lab COAs, but deprecated loading script, indexed by lab ID not strain name
- **AllBud**: real THC ranges, 7,800+ strains, accessible HTML → scraping target

---

## Step 2 — Legality / robots check

```bash
curl -s https://TARGET.com/robots.txt | head -40
```

If `Disallow: /` or the specific path is disallowed, stop. AllBud's robots.txt allows the strain pages.

Check terms of service for "no automated access" clauses. Public facts (strain names, THC%) are generally not copyrightable; structured databases sometimes are — know the difference.

---

## Step 3 — Probe page structure with curl before writing any code

Never open a browser. `curl` is faster and shows exactly what a bot sees.

```bash
# Does the page return 200? Any redirects? Cloudflare?
curl -sI --max-time 10 "https://www.allbud.com/marijuana-strains/indica/northern-lights" \
  | grep -iE "HTTP|location|cf-ray|server"

# Is the data in the HTML (server-rendered) or loaded by JS (client-rendered)?
curl -s --max-time 15 "https://TARGET.com/page" | grep -i "THC\|data-thc\|__NEXT_DATA__" | head -5
```

**If `curl` returns the data** → normal HTML scraping works (Scrapy, BeautifulSoup).
**If `curl` returns an empty shell** → page is JS-rendered → need Playwright or Splash.

AllBud returned the THC text in the initial HTML response, so normal Scrapy works.

---

## Step 4 — Map the exact HTML selectors

```bash
curl -s "https://TARGET.com/page" | python3 -c "
import sys, re, json
html = sys.stdin.read()

# Find data near the target field
print(re.findall(r'.{60}THC.{60}', html, re.I)[:3])

# Find JSON-LD structured data (often the cleanest source)
for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S):
    try: print(list(json.loads(m.group(1)).keys()))
    except: pass

# Find URL patterns for listing pages
print(re.findall(r'href=\"(/strain[^\"]{5,50})\"', html)[:10])
"
```

For AllBud we found:
- THC in `h4.percentage` → `span.heading` (label) + text nodes (values)  
- Effects as `a[href*='/effect/']` links
- Listing: `/marijuana-strains/search?sort=alphabet&page=N`, ~39 strains/page, 200 pages

---

## Step 5 — Find the listing/pagination pattern

```bash
# How many items per page?
curl -s "https://TARGET.com/list?page=1" | grep -oP 'href="/item/[a-z0-9-]+"' | sort -u | wc -l

# How many pages?
curl -s "https://TARGET.com/list?page=999" | grep -oP 'page=\d+' | sort -n | tail -3
# If page 999 returns content → binary search for the real last page
# If it returns 404 → last page is somewhere below 999
```

AllBud: 39 strains/page, last page visible in pagination = 200 → ~7,800 strains total.

---

## Step 6 — Write the Scrapy spider

### Project setup

```bash
pip install scrapy
scrapy startproject myproject
cd myproject
scrapy genspider myspider target.com
```

### Always include these settings

```python
custom_settings = {
    "DOWNLOAD_DELAY": 1.5,            # seconds between requests
    "RANDOMIZE_DOWNLOAD_DELAY": True,  # ±50% jitter — looks less bot-like
    "CONCURRENT_REQUESTS": 1,          # one at a time
    "ROBOTSTXT_OBEY": True,
    "USER_AGENT": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) ...",
    "HTTPCACHE_ENABLED": True,         # re-runs are free; cache doesn't expire for 24h
    "HTTPCACHE_EXPIRATION_SECS": 86400,
    "LOG_LEVEL": "INFO",
}
```

### Two-phase spider pattern (listing → detail)

```python
def start_requests(self):
    for page in range(1, MAX_PAGES + 1):
        yield scrapy.Request(LISTING_URL.format(page=page), callback=self.parse_listing)

def parse_listing(self, response):
    for href in response.css("a[href*='/strain/']::attr(href)").getall():
        yield response.follow(href, callback=self.parse_detail)

def parse_detail(self, response):
    yield {
        "name": response.css("h1::text").get("").strip(),
        "thc": ...,  # extract with CSS or regex
    }
```

### Validate extracted data immediately

```python
thc = float(thc_str or 0)
if not (0 < thc <= 40):   # implausible → don't store
    thc = None
```

---

## Step 7 — Test before full run

```bash
# Quick test: stop after 20 items
scrapy crawl myspider -s CLOSESPIDER_ITEMCOUNT=20 -o /tmp/test.jsonl -s LOG_LEVEL=WARNING

# Inspect
python3 -c "
import json
rows = [json.loads(l) for l in open('/tmp/test.jsonl') if l.strip()]
for r in rows[:5]: print(r)
"
```

Check:
- Names are clean (no HTML fragments, no " Marijuana Strain" suffixes)
- Numbers are in expected ranges (THC 5–35%, not 96% which is a review score)
- Types classified correctly (indica/sativa/hybrid)

---

## Step 8 — Full run

```bash
scrapy crawl myspider -o strains_scraped.jsonl
# runs at ~1.5s/page; 200 listing pages + ~7800 detail pages ≈ 3-4 hours
```

Monitor: `wc -l strains_scraped.jsonl` gives real-time item count.

---

## Step 9 — Post-process

Convert raw scraped data into the application's data format. See `build_strains.py` for a worked example:

- Normalise names (lowercase, strip punctuation, de-dup slugs)
- Map scraped tags to internal schema (e.g. "euphoria" → `effects.euphoric = 0.85`)
- Flag which fields came from real data vs. estimated defaults
- Attach source + license info to every record

---

## Common pitfalls

| Symptom | Cause | Fix |
|---------|-------|-----|
| All values the same (e.g. THC=12.7%) | Placeholder in dataset, not real measurement | Cross-check value distribution; flag or discard |
| Page returns empty HTML | JS-rendered content | Check `__NEXT_DATA__`, `window.__STATE__`, or switch to Playwright |
| 403 after N requests | Rate limiting or IP block | Increase `DOWNLOAD_DELAY`, add `AUTOTHROTTLE_ENABLED=True` |
| Numbers like 127 for a % field | Units are different (mg/g × 10 = %) | Check distribution; if median is 100-300, divide by 10 |
| Cloudflare challenge | Aggressive bot protection | Don't scrape that site — look for an official data export or API |
| Pagination goes to page 999 | Infinite/virtual pagination | Binary search for last real page; check for `rel="next"` links |

---

## Files in this repo

| File | Purpose |
|------|---------|
| `strain_scraper/strain_scraper/spiders/allbud.py` | Scrapy spider for AllBud (~7,800 strains) |
| `scrape_strains.py` | Download Cannlytics HuggingFace dataset (CC BY 4.0, real lab COAs) |
| `build_strains.py` | Convert Kushy CSV (MIT) → application format |

Run the AllBud spider:
```bash
cd strain_scraper
scrapy crawl allbud -o ../strains_scraped.jsonl
```
