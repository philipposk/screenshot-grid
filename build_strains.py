"""
build_strains.py
----------------
Convert the Kushy App cannabis dataset (MIT license, 9,524 strains) into
Greenpert's strain format. Outputs:
  strains_patch.json — Greenpert-ready strain data

Source:
  https://github.com/kushyapp/cannabis-dataset (MIT License)
  Downloaded from Dataset/Strains/strains-kushy_api.2017-11-14.csv

Usage:
  python3 build_strains.py [--input PATH] [--top N]

What this gives you:
  - Strain names, slugs, types (indica/sativa/hybrid)
  - Effect intensities mapped from Leafly/Kushy effect tags
  - Terpene dominant mapped to intensity
  - THC/CBD % for ~166 strains with real data (rest get type-median estimates)
  - Flavor tags → terpene hints
"""

import argparse
import json
import re
from pathlib import Path

import pandas as pd


parser = argparse.ArgumentParser()
parser.add_argument("--input", default="/tmp/kushy_strains.csv")
parser.add_argument("--top", type=int, default=200, help="Top N strains by data quality")
args = parser.parse_args()

# ── Effect tag → Greenpert effect key mapping ──────────────────────────────
EFFECT_MAP: dict[str, str] = {
    "relaxed":    "relaxed",
    "happy":      "happy",
    "euphoric":   "euphoric",
    "uplifted":   "uplifted",
    "creative":   "creative",
    "energetic":  "energetic",
    "focused":    "focused",
    "sleepy":     "sleepy",
    "hungry":     "hungry",
    "talkative":  "talkative",
}

# ── Flavor/terpene tag → Greenpert terpene key mapping ────────────────────
FLAVOR_TERPENE: dict[str, str] = {
    "citrus":      "limonene",
    "lemon":       "limonene",
    "orange":      "limonene",
    "lime":        "limonene",
    "earthy":      "myrcene",
    "herbal":      "myrcene",
    "musky":       "myrcene",
    "mango":       "myrcene",
    "pepper":      "caryophyllene",
    "spicy":       "caryophyllene",
    "woody":       "caryophyllene",
    "pine":        "pinene",
    "piney":       "pinene",
    "forest":      "pinene",
    "floral":      "linalool",
    "lavender":    "linalool",
    "sweet":       "linalool",
    "berry":       "linalool",
    "hop":         "humulene",
    "hops":        "humulene",
}
NAMED_TERPENE: dict[str, str] = {
    "limonene":     "limonene",
    "myrcene":      "myrcene",
    "caryophyllene": "caryophyllene",
    "pinene":       "pinene",
    "linalool":     "linalool",
    "humulene":     "humulene",
    "terpinolene":  "terpinolene",
    "ocimene":      "ocimene",
    "bisabolol":    "bisabolol",
}

# Type medians (% THC) — estimated from published cannabis data.
# THC-dominant strains: indica ~20%, sativa ~19%, hybrid ~20%
TYPE_THC: dict[str, float] = {"Indica": 19.5, "Sativa": 19.0, "Hybrid": 20.0}
TYPE_CBD: dict[str, float] = {"Indica": 0.2, "Sativa": 0.2, "Hybrid": 0.2}
TYPE_INDICA: dict[str, float] = {"Indica": 80.0, "Sativa": 15.0, "Hybrid": 50.0}
TYPE_FLOWER: dict[str, int] = {"Indica": 60, "Sativa": 72, "Hybrid": 63}
TYPE_YIELD: dict[str, float] = {"Indica": 72.0, "Sativa": 65.0, "Hybrid": 70.0}


def slugify(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[''`]", "", s)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def parse_tags(raw: str | float) -> list[str]:
    if not isinstance(raw, str):
        return []
    return [t.strip().lower() for t in raw.split(",") if t.strip()]


def effects_map(tags: list[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for tag in tags:
        key = EFFECT_MAP.get(tag)
        if key:
            # Primary effect gets 0.8; secondary ones get 0.4–0.6
            val = 0.85 if tag == tags[0] else 0.55
            out[key] = max(out.get(key, 0.0), val)
    return out


def terpenes_map(flavor_tags: list[str], named_terp: str | float) -> dict[str, float]:
    out: dict[str, float] = {}
    # Named terpene column is the dominant one
    if isinstance(named_terp, str):
        key = NAMED_TERPENE.get(named_terp.strip().lower())
        if key:
            out[key] = 0.75
    # Supplement from flavor tags
    for tag in flavor_tags:
        key = FLAVOR_TERPENE.get(tag)
        if key and key not in out:
            out[key] = 0.4
    return out


# ── Load ──────────────────────────────────────────────────────────────────
df = pd.read_csv(args.input)
print(f"Loaded {len(df):,} strains")

thc_raw = pd.to_numeric(df["thc"], errors="coerce")
cbd_raw = pd.to_numeric(df["cbd"], errors="coerce")

# ── Score each strain for data quality ────────────────────────────────────
df["_thc_valid"] = (thc_raw >= 50) & (thc_raw <= 350)
df["_has_effects"] = df["effects"].notna()
df["_has_flavor"] = df["flavor"].notna()
df["_score"] = (
    df["_thc_valid"].astype(int) * 3
    + df["_has_effects"].astype(int) * 2
    + df["_has_flavor"].astype(int)
)
df["_thc_pct"] = thc_raw / 10.0
df["_cbd_pct"] = cbd_raw / 10.0

# Normalise type
df["_type"] = df["type"].where(df["type"].isin(["Indica", "Sativa", "Hybrid"]), "Hybrid")

# ── Build output ──────────────────────────────────────────────────────────
seen_slugs: set[str] = set()
results = []

# Sort: best-data strains first, then fill with remaining
df_sorted = df.sort_values("_score", ascending=False)

for _, row in df_sorted.iterrows():
    name = str(row["name"]).strip()
    if not name or name == "nan":
        continue
    slug = slugify(name)
    if slug in seen_slugs:
        continue
    seen_slugs.add(slug)

    t = str(row["_type"])
    has_thc = bool(row["_thc_valid"])
    thc = round(float(row["_thc_pct"]), 1) if has_thc else TYPE_THC.get(t, 20.0)
    cbd_v = float(row["_cbd_pct"]) if pd.notna(row["_cbd_pct"]) and row["_cbd_pct"] > 0 else TYPE_CBD.get(t, 0.2)
    cbd = round(min(cbd_v, 25.0), 2)

    effect_tags = parse_tags(row.get("effects"))
    flavor_tags = parse_tags(row.get("flavor"))
    effects = effects_map(effect_tags)
    terpenes = terpenes_map(flavor_tags, row.get("terpenes"))

    results.append({
        "name": name,
        "slug": slug,
        "type": t,
        "indicaPct": TYPE_INDICA.get(t, 50.0),
        "thc": thc,
        "cbd": cbd,
        "floweringDays": TYPE_FLOWER.get(t, 63),
        "yieldScore": TYPE_YIELD.get(t, 70.0),
        "difficulty": "intermediate",
        "effects": effects,
        "terpenes": terpenes,
        "flavor": flavor_tags[:4],
        "description": "",
        "_thc_from_lab": has_thc,
        "_source": "kushyapp/cannabis-dataset (MIT)",
    })

    if len(results) >= args.top:
        break

with open("strains_patch.json", "w") as f:
    json.dump(results, f, indent=2)

lab_count = sum(1 for r in results if r["_thc_from_lab"])
print(f"Output: {len(results)} strains → strains_patch.json")
print(f"  {lab_count} with real lab THC, {len(results)-lab_count} using type-median estimate")
print(f"\nTop 10:")
for r in results[:10]:
    flag = "💉" if r["_thc_from_lab"] else "~"
    effects_str = ",".join(list(r["effects"].keys())[:2])
    print(f"  {flag} {r['name']:30s}  {r['type']:6s}  THC={r['thc']}%  {effects_str}")
