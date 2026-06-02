"""
scrape_strains.py
-----------------
Pull real cannabis lab COA results from the Cannlytics dataset on Hugging Face
(CC BY 4.0 — https://huggingface.co/datasets/cannlytics/cannabis_results)
and aggregate by strain name into per-strain mean THC %, CBD %, and terpene %.

Outputs:
  strains_lab_data.json   — full aggregated data (all strains with ≥MIN_SAMPLES)
  strains_seed_patch.json — top N strains formatted to patch Greenpert's seed data

Usage:
  python3 scrape_strains.py
  python3 scrape_strains.py --states wa or --min-samples 5 --top 60

Source: Cannlytics cannabis_results, CC BY 4.0
        https://huggingface.co/datasets/cannlytics/cannabis_results
"""

import argparse
import json
import re
from collections import defaultdict

import pandas as pd
from datasets import load_dataset


# ── CLI ──────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("--states", nargs="+", default=["wa", "or"],
                    help="State subsets to pull (wa, or, ca, co, ma, …)")
parser.add_argument("--min-samples", type=int, default=3,
                    help="Drop strains with fewer lab tests than this")
parser.add_argument("--top", type=int, default=80,
                    help="Number of top strains (by sample count) to keep")
args = parser.parse_args()

# ── Known terpene column names in the dataset ─────────────────────────────────
TERPENE_COLS = [
    "caryophyllene", "myrcene", "limonene", "pinene", "linalool",
    "humulene", "terpinolene", "ocimene", "bisabolol", "camphene",
    "geraniol", "nerolidol", "guaiol", "eucalyptol",
    # also try with prefixes the dataset uses
    "beta_caryophyllene", "beta_myrcene", "alpha_pinene", "beta_pinene",
    "d_limonene",
]

CANNABINOID_COLS = ["total_thc", "total_cbd", "total_cannabinoids", "thc", "cbd"]


def normalise_name(name: str) -> str:
    """Lower-case, strip punctuation, collapse spaces."""
    if not isinstance(name, str):
        return ""
    n = name.lower()
    n = re.sub(r"[''`]", "", n)          # apostrophes
    n = re.sub(r"[^a-z0-9 #]+", " ", n)  # everything except letters/numbers/#
    n = re.sub(r"\s+", " ", n).strip()
    return n


def load_state(state: str) -> pd.DataFrame:
    print(f"  Downloading {state.upper()}…")
    try:
        ds = load_dataset("cannlytics/cannabis_results", state, split="data",
                          trust_remote_code=True)
        df = ds.to_pandas()
        print(f"  {state.upper()}: {len(df):,} rows, columns: {list(df.columns[:10])}…")
        return df
    except Exception as e:
        print(f"  WARN: could not load {state}: {e}")
        return pd.DataFrame()


# ── Load ──────────────────────────────────────────────────────────────────────
print("Loading states:", args.states)
frames = [load_state(s) for s in args.states]
df = pd.concat([f for f in frames if not f.empty], ignore_index=True)
print(f"\nTotal rows: {len(df):,}")

if df.empty:
    print("No data loaded. Check state codes or internet connection.")
    raise SystemExit(1)

# ── Find usable columns ───────────────────────────────────────────────────────
cols = set(df.columns.str.lower())

def find_col(candidates: list[str]) -> str | None:
    for c in candidates:
        if c in cols:
            return c
        # try with prefix/suffix
        matches = [x for x in cols if c in x]
        if matches:
            return matches[0]
    return None

thc_col = find_col(["total_thc", "thc"])
cbd_col = find_col(["total_cbd", "cbd"])
name_col = find_col(["strain_name", "strain", "product_name", "sample_name"])
terp_cols = {t: find_col([t]) for t in TERPENE_COLS}
terp_cols = {k: v for k, v in terp_cols.items() if v is not None}

print(f"\nColumns found:")
print(f"  THC: {thc_col}  CBD: {cbd_col}  Name: {name_col}")
print(f"  Terpenes ({len(terp_cols)}): {list(terp_cols.keys())[:8]}…")

if not name_col or not thc_col:
    print("ERROR: couldn't find strain name or THC column. Available columns:")
    print(list(df.columns))
    raise SystemExit(1)

# ── Clean ─────────────────────────────────────────────────────────────────────
df["_name"] = df[name_col].apply(normalise_name)
df = df[df["_name"].str.len() > 2]  # drop blank/very-short names

def to_float(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")

df["_thc"] = to_float(df[thc_col])
df["_cbd"] = to_float(df[cbd_col]) if cbd_col else 0.0

# Convert mg/g → % if values look like mg/g (most are already %)
if df["_thc"].median() > 50:
    print("Values look like mg/g — converting to % (÷10)")
    df["_thc"] /= 10
    df["_cbd"] /= 10

# Drop implausible outliers
df = df[(df["_thc"] >= 0) & (df["_thc"] <= 40)]
df = df[(df["_cbd"] >= 0) & (df["_cbd"] <= 30)]

for nice, real in terp_cols.items():
    df[f"_t_{nice}"] = to_float(df[real])
    # terpenes usually < 5%; values > 30 are likely mg/g
    mask = df[f"_t_{nice}"] > 30
    df.loc[mask, f"_t_{nice}"] /= 10

# ── Aggregate by strain ───────────────────────────────────────────────────────
print("\nAggregating…")
agg: dict[str, dict] = defaultdict(lambda: {
    "thc_vals": [], "cbd_vals": [],
    "terpenes": defaultdict(list),
})

for _, row in df.iterrows():
    name = row["_name"]
    if not name:
        continue
    if 0 < row["_thc"] <= 40:
        agg[name]["thc_vals"].append(float(row["_thc"]))
    if 0 <= row["_cbd"] <= 30:
        agg[name]["cbd_vals"].append(float(row["_cbd"]))
    for nice in terp_cols:
        v = row.get(f"_t_{nice}", float("nan"))
        if pd.notna(v) and 0 < v < 20:
            agg[name]["terpenes"][nice].append(float(v))

def safe_mean(vals: list) -> float | None:
    v = [x for x in vals if pd.notna(x)]
    return round(sum(v) / len(v), 2) if v else None

# Flatten
results = []
for name, data in agg.items():
    n = len(data["thc_vals"])
    if n < args.min_samples:
        continue
    thc = safe_mean(data["thc_vals"])
    cbd = safe_mean(data["cbd_vals"])
    if thc is None:
        continue
    terpenes = {
        t: round(safe_mean(vals), 3)
        for t, vals in data["terpenes"].items()
        if len(vals) >= 2 and safe_mean(vals) is not None
    }
    results.append({
        "name": name,
        "samples": n,
        "thc": thc,
        "cbd": cbd or 0.0,
        "terpenes": terpenes,
    })

results.sort(key=lambda x: -x["samples"])
print(f"Strains with ≥{args.min_samples} samples: {len(results)}")

# Save full data
with open("strains_lab_data.json", "w") as f:
    json.dump(results, f, indent=2)
print("Written: strains_lab_data.json")

# ── Top-N patch file (Greenpert format) ───────────────────────────────────────
TERPENE_MAP = {
    "myrcene": "myrcene", "caryophyllene": "caryophyllene",
    "beta_caryophyllene": "caryophyllene", "limonene": "limonene",
    "d_limonene": "limonene", "linalool": "linalool",
    "alpha_pinene": "pinene", "beta_pinene": "pinene", "pinene": "pinene",
    "humulene": "humulene", "terpinolene": "terpinolene",
    "ocimene": "ocimene", "bisabolol": "bisabolol",
}

def terps_to_gp(raw: dict) -> dict:
    """Convert raw terpene averages to 0..1 intensity scale for Greenpert."""
    out: dict[str, float] = {}
    for raw_name, val in raw.items():
        gp_name = TERPENE_MAP.get(raw_name)
        if not gp_name or val is None:
            continue
        # terpenes in cannabis flower typically 0.1–3%; map to 0..1 scale
        # clamp at 3% = 1.0
        intensity = round(min(1.0, val / 3.0), 2)
        if intensity > 0.02:
            out[gp_name] = max(out.get(gp_name, 0), intensity)
    return out

patch = []
for s in results[:args.top]:
    patch.append({
        "name": s["name"],
        "samples": s["samples"],
        "thc": s["thc"],
        "cbd": s["cbd"],
        "terpenes": terps_to_gp(s.get("terpenes", {})),
        "source": "cannlytics/cannabis_results (CC BY 4.0)",
    })

with open("strains_seed_patch.json", "w") as f:
    json.dump(patch, f, indent=2)
print(f"Written: strains_seed_patch.json ({len(patch)} strains)")
print("\nTop 10 strains by sample count:")
for s in patch[:10]:
    print(f"  {s['name']:30s}  THC {s['thc']:5.1f}%  CBD {s['cbd']:4.2f}%  n={s['samples']}")
