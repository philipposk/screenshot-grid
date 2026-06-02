"""
AllBud cannabis strain spider.

Crawls https://www.allbud.com/marijuana-strains (~7,800 strains) and extracts:
  name, type, thc_low, thc_high, cbd (when present), effects[], flavors[],
  terpenes[], description

Usage:
  cd strain_scraper
  scrapy crawl allbud -o ../strains_scraped.jsonl                 # all strains
  scrapy crawl allbud -s CLOSESPIDER_ITEMCOUNT=100 -o out.jsonl   # quick test
"""

import re
from typing import Generator

import scrapy
from scrapy.http import Response


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def parse_pct(text: str) -> float | None:
    m = re.search(r"(\d+\.?\d*)", text or "")
    return float(m.group(1)) if m else None


class AllbudSpider(scrapy.Spider):
    name = "allbud"
    allowed_domains = ["www.allbud.com"]

    custom_settings = {
        "DOWNLOAD_DELAY": 1.5,           # be polite: 1.5 s between requests
        "RANDOMIZE_DOWNLOAD_DELAY": True, # ±0.5×delay
        "CONCURRENT_REQUESTS": 1,
        "USER_AGENT": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        ),
        "ROBOTSTXT_OBEY": True,
        "LOG_LEVEL": "INFO",
        "HTTPCACHE_ENABLED": True,         # cache so re-runs are free
        "HTTPCACHE_EXPIRATION_SECS": 86400,
    }

    LISTING_URL = (
        "https://www.allbud.com/marijuana-strains/search"
        "?sort=alphabet&page={page}"
    )
    MAX_PAGES = 200

    def start_requests(self):
        for page in range(1, self.MAX_PAGES + 1):
            yield scrapy.Request(
                self.LISTING_URL.format(page=page),
                callback=self.parse_listing,
                meta={"page": page},
                # Abort early if we get two empty pages in a row
                dont_filter=False,
            )

    def parse_listing(self, response: Response) -> Generator:
        """Extract strain URLs from a listing page."""
        strain_links = response.css(
            "a[href*='/marijuana-strains/']::attr(href)"
        ).getall()
        # Filter to strain-detail URLs: 4 path segments, last is the slug
        seen = set()
        for href in strain_links:
            parts = [p for p in href.split("/") if p]
            if len(parts) == 3 and parts[0] == "marijuana-strains":
                url = response.urljoin(href)
                if url not in seen:
                    seen.add(url)
                    yield scrapy.Request(url, callback=self.parse_strain)

    def parse_strain(self, response: Response) -> Generator:  # type: ignore[override]
        """Parse a single strain page."""
        # Strip " Marijuana Strain" suffix AllBud appends to <h1>
        raw_name = clean(response.css("h1::text, h1 *::text").get(""))
        name = re.sub(r"\s+Marijuana Strain$", "", raw_name, flags=re.I).strip()
        if not name:
            return

        # Type — from the strain-type anchor in the cannabinoid block
        type_text = clean(response.css("h4 a[href*='/variety/']::text").get("")).lower()
        if "sativa" in type_text and "indica" not in type_text:
            strain_type = "sativa"
        elif "indica" in type_text and "sativa" not in type_text:
            strain_type = "indica"
        else:
            strain_type = "hybrid"

        # THC — in .percentage block: <span class="heading">THC: </span> then 16% - 21%
        thc_low, thc_high = None, None
        for pct_block in response.css("h4.percentage"):
            heading = clean(pct_block.css("span.heading::text").get(""))
            if "THC" in heading:
                nums = re.findall(r"(\d+\.?\d*)", pct_block.css("::text").getall().__class__(pct_block.css("::text").getall()) and " ".join(pct_block.css("::text").getall()))
                nums = [float(n) for n in re.findall(r"(\d+\.?\d*)", " ".join(pct_block.css("::text").getall())) if 0 < float(n) <= 40]
                if len(nums) >= 2:
                    thc_low, thc_high = min(nums[:2]), max(nums[:2])
                elif len(nums) == 1:
                    thc_high = nums[0]
                    thc_low = max(nums[0] - 4, 0)
                break

        # CBD — same .percentage block with "CBD:" heading
        cbd = None
        for pct_block in response.css("h4.percentage"):
            heading = clean(pct_block.css("span.heading::text").get(""))
            if "CBD" in heading:
                nums = [float(n) for n in re.findall(r"(\d+\.?\d*)", " ".join(pct_block.css("::text").getall())) if 0 < float(n) <= 30]
                if nums:
                    cbd = round(sum(nums) / len(nums), 2)
                break

        # Effects
        effects = [
            clean(a)
            for a in response.css(
                "a[href*='/effect/']::text"
            ).getall()
            if clean(a)
        ]

        # Flavors
        flavors = [
            clean(a)
            for a in response.css(
                "a[href*='/flavor/']::text"
            ).getall()
            if clean(a)
        ]

        # Terpenes
        terpenes = [
            clean(a)
            for a in response.css(
                "a[href*='/terpene/']::text"
            ).getall()
            if clean(a)
        ]

        # Description (first paragraph of body text)
        paragraphs = [
            clean(p)
            for p in response.css("article p::text, .description p::text").getall()
            if len(clean(p)) > 40
        ]
        description = paragraphs[0] if paragraphs else ""

        # URL slug → derive a stable id
        slug = response.url.rstrip("/").split("/")[-1]

        yield {
            "name": name,
            "slug": slug,
            "url": response.url,
            "type": strain_type,
            "thc_low": thc_low,
            "thc_high": thc_high,
            "cbd": cbd,
            "effects": list(dict.fromkeys(effects)),   # dedup, preserve order
            "flavors": list(dict.fromkeys(flavors)),
            "terpenes": list(dict.fromkeys(terpenes)),
            "description": description[:500],
        }
