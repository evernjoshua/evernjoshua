#!/usr/bin/env python3
"""Check an actuals.csv against the heat map before you run it.

Applies the notebook's own rules - the ACTUALS_ROLLUP_ALL filter, the
segment/fee/branding key, the dollar-and-space-insensitive match - and says
which roll-up rows will find actuals and which will not, so a silent miss turns
into a line of output.

    python check_actuals.py [actuals.csv] [-n 02_heatmap_23.ipynb]
"""
import argparse, csv, json, os, re, sys
from collections import Counter

MOBS = (12, 24, 36)
METRICS = ["CumUnitRate", "CumNetDollar", "CumulativeROA", "Boards",
           "Avg_InitialLinePerBooked", "CumPTI"]

def akey(name):
    """the notebook's _akey: case, spaces and the dollar sign all ignored"""
    return "".join(str(name).split()).replace("$", "").lower()

def wanted_tabs(nb_path):
    """Every roll-up tab the heat map will look for, read out of the notebook.

    Three sources: the names mapped in ROLLUP_SHEETS, the ROLLUP_ONLY and
    CAMPAIGN_TOTALS blocks, and the families in EXTRA_SEGMENTS that are NOT
    mapped - those fall back to family + "_ALL". Families swept out of the
    workbook cannot be known from the notebook alone, so a name in the file that
    is not listed here may still be one of those and perfectly fine.
    """
    src = "".join(json.load(open(nb_path))["cells"][1]["source"])
    def block(start, close):
        i = src.index(start)
        return src[i:src.index(close, i) + 1]
    ns = {}
    for b, c in (("ROLLUP_SHEETS = {", "}"), ("ROLLUP_ONLY = [", "]"),
                 ("CAMPAIGN_TOTALS = [", "]"), ("EXTRA_SEGMENTS = [", "]"),
                 ("BANDS = [", "]"), ('ROLLUP_SUFFIX = "', "\n")):
        try:
            exec(block(b, c), ns)
        except (ValueError, SyntaxError):
            pass
    suffix = ns.get("ROLLUP_SUFFIX", "_ALL")

    def family(tab):
        s = " ".join(str(tab).split())
        for b in sorted(ns.get("BANDS", []), key=len, reverse=True):
            if s.lower().endswith(b.lower()):
                return s[:len(s) - len(b)].strip()
        return None

    mapped = ns.get("ROLLUP_SHEETS", {})
    tabs = list(dict.fromkeys(mapped.values()))
    for tab in ns.get("EXTRA_SEGMENTS", []):
        fam = family(tab)
        if fam and fam not in mapped:
            tabs.append(f"{fam}{suffix}")
    return (list(dict.fromkeys(tabs)) + ns.get("ROLLUP_ONLY", [])
            + [t for _, t in ns.get("CAMPAIGN_TOTALS", [])])

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv_path", nargs="?", default="actuals.csv")
    ap.add_argument("-n", "--notebook",
                    default=os.path.join(os.path.dirname(__file__), os.pardir,
                                         "02_heatmap_23.ipynb"))
    ap.add_argument("--rollup-all", nargs="*",
                    default=["Branding", "OriginalCreditLine"])
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.csv_path, newline="", encoding="utf-8-sig")))
    if not rows:
        sys.exit(f"{args.csv_path} has no rows")
    cols = list(rows[0])
    print(f"{args.csv_path}: {len(rows):,} rows, {len(cols)} columns")

    missing = [c for c in ["Vintage", "segment", "Fee", "mob"] + args.rollup_all
               + METRICS if c not in cols]
    if missing:
        print(f"  MISSING COLUMNS: {missing}")

    # the roll-up filter
    kept = [r for r in rows
            if all(str(r.get(c, "")).strip().lower() == "all" for c in args.rollup_all)]
    print(f"  roll-up level ({' and '.join(c + '=All' for c in args.rollup_all)}): "
          f"{len(kept):,} kept, {len(rows) - len(kept):,} dropped")
    if not kept:
        sys.exit("  nothing is at roll-up level - the heat map would show no actuals")

    # build the keys the heat map will look them up by
    index = {}
    for r in kept:
        seg, fee, br = (str(r.get(k, "")).strip() for k in ("segment", "Fee", "Branding"))
        key = akey(f"{seg}_{br}" if fee.lower() in ("", "all", "n/a")
                   else f"{seg} {fee}_{br}")
        index.setdefault(key, []).append(r)

    tabs = wanted_tabs(args.notebook)
    hit = [t for t in tabs if akey(t) in index]
    miss = [t for t in tabs if akey(t) not in index]
    print(f"\n  {len(hit)} of {len(tabs)} roll-up rows will find actuals")

    # a tab with no _ALL on the end can never be built from segment/fee/branding,
    # so it is not something the query can fix
    unmatchable = [t for t in miss if not t.upper().endswith("_ALL")]
    fixable = [t for t in miss if t.upper().endswith("_ALL")]
    if fixable:
        print("\n  NO ACTUALS - add these to the query's name_map:")
        for t in fixable:
            print(f"    {t}")
    if unmatchable:
        print("\n  these cannot be matched by segment/fee/branding at all, so they "
              "stay\n  blank unless you add an ACTUALS_ALIASES entry in the notebook:")
        for t in unmatchable:
            print(f"    {t}")
    spare = sorted(set(index) - {akey(t) for t in tabs})
    if spare:
        print(f"\n  in the file, not named in the notebook ({len(spare)}) - these "
              f"are fine if they are families\n  swept out of the workbook, which "
              f"use the plain family + _ALL name:")
        for k in spare[:12]:
            r = index[k][0]
            print(f"    segment={r['segment']!r} Fee={r['Fee']!r}")
        if len(spare) > 12:
            print(f"    ... and {len(spare) - 12} more")

    # MOB cover and whether the rates look like rates
    print("\n  MOB cover per matched roll-up:")
    thin = []
    for t in hit:
        got = Counter(int(float(r["mob"])) for r in index[akey(t)]
                      if str(r.get("mob", "")).strip())
        line = "  ".join(f"mob {m}: {got.get(m, 0):>3}" for m in MOBS)
        if any(got.get(m, 0) == 0 for m in MOBS):
            thin.append(t)
        print(f"    {t:<34} {line}")
    if thin:
        print(f"\n  these have no rows at one or more MOBs, so that year will be "
              f"blank:\n    " + "\n    ".join(thin))

    print("\n  scale check - a rate should sit near 0.05, not 5:")
    for c in ("CumUnitRate", "CumNetDollar", "CumulativeROA"):
        vals = [float(r[c]) for r in kept
                if str(r.get(c, "")).strip() not in ("", "None")]
        if not vals:
            print(f"    {c:<16} no values")
            continue
        lo, hi = min(vals), max(vals)
        flag = "  <- looks like percent; set ACTUALS_SCALE[%r] = 0.01" % c \
               if max(abs(lo), abs(hi)) > 1.5 else ""
        print(f"    {c:<16} {lo:.4f} to {hi:.4f}{flag}")

    vint = sorted({str(r["Vintage"]).strip() for r in kept})
    bad = [v for v in vint if not re.match(r"^\d{4}[-/ ]?\d{1,2}", v)]
    print(f"\n  vintages: {len(vint)} from {vint[0]} to {vint[-1]}")
    if bad:
        print(f"    NOT a recognisable date, so the seasoning guard will let them "
              f"through: {bad[:5]}")
    verdict = ("looks ready" if not fixable and not bad
               else "fix the points above, then re-run")
    if not fixable and unmatchable and not bad:
        verdict += f" ({len(unmatchable)} tab(s) can only be matched by alias)"
    print("\n" + verdict)

if __name__ == "__main__":
    main()
