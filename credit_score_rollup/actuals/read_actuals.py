"""Read the supplied actuals CSV and shape it for the segment heat map.

The P&L is computed upstream now, so this file is already slim: one row per
cohort per month on book, carrying the numerators the heat map needs rather
than the ledger they came from.

Columns, as described:

  vintage, vintage date            the cohort
  account, account number          IGNORED - always "First Account" or null
  subchannel                       all Digital
  application credit score
  vantage range                    drives the heat map's <=600 / 601-639 / 640+
  annual fee group                 IGNORED - use annual fee
  annual fee, original credit line
  month on book                    only 12, 24 and 36 are kept = Yr 1, 2, 3
  new accounts                     total new accounts (boards)
  net unit charge off              numerator of the unit charge-off rate
  unwinds count
  net dollar                       numerator of the dollar charge-off rate
  cf pretax minus cost of funds    the last column
"""

from __future__ import annotations

import re

import pandas as pd

# ------------------------------------------------------------- the schema --
# canonical name -> the spellings it may arrive under. Matching ignores case,
# spaces, underscores and punctuation, so "Net Unit Charge Off",
# "net_unit_chargeoff" and "NetUnitChargeOff" all land on the same column.
ALIASES = {
    # Name the campaign column here if the file spells it differently - this
    # is what matches a row to a workbook tab.
    "Campaign":       ["campaign", "brand", "branding", "source", "partner",
                       "acquisition source", "marketing source"],
    "Vintage":        ["vintage"],
    "VintageDate":    ["vintage date", "vintagedate"],
    "Subchannel":     ["subchannel", "sub channel"],
    "AppCreditScore": ["application credit score", "app credit score",
                       "applicationcreditscore"],
    "VantageRange":   ["vantage range", "vantagerange", "vantage band"],
    "AnnualFee":      ["annual fee", "annualfee", "fee"],
    "OriginalCreditLine": ["original credit line", "originalcreditline",
                           "orig credit line"],
    "MOB":            ["month on book", "months on book", "months on books",
                       "monthonbook", "monthsonbooks", "mob"],
    "NewAccounts":    ["new accounts", "newaccounts", "total new accounts",
                       "boards"],
    "NetUnitChargeOff": ["net unit charge off", "net unit chargeoff",
                         "netunitchargeoff", "net unit c/o", "net unit co"],
    "UnwindCount":    ["unwinds count", "unwind count", "unwindcount",
                       "unwinds", "unwind"],
    "NetDollar":      ["net dollar", "netdollar", "net dollar charge off",
                       "net dollars"],
    # The denominator of both the dollar charge-off rate and the ROA.
    "Receivables":    ["average gross receivables", "avg gross receivables",
                       "avg receivables", "average receivables",
                       "gross receivables", "ending receivable",
                       "endingreceivable", "receivables", "balance",
                       "ending balance"],
    "PretaxLessCoF":  ["cf pretax minus cost of funds",
                       "cf pretax less cost of funds",
                       "cfpretaxminuscostoffunds", "cf pretax - cost of funds",
                       "pretax minus cost of funds"],
}

# Named by the brief as not to be used.
IGNORE = ["account", "account number", "accountnumber", "annual fee group",
          "annualfeegroup"]

# Only these months on book are kept, and this is what each one means.
MOB_YEARS = {12: "Yr 1", 24: "Yr 2", 36: "Yr 3"}

# The cohort. Anything not here and not a measure is carried but not grouped on.
DIMENSIONS = ["Campaign", "Vintage", "VintageDate", "Subchannel",
              "VantageRange", "AnnualFee", "OriginalCreditLine"]
AVG_REC = "Avg Gross Receivables"
MEASURES = ["NewAccounts", "NetUnitChargeOff", "UnwindCount", "NetDollar",
            "PretaxLessCoF", AVG_REC]

# Output names
BOARDS       = "Booked Accounts"
UNIT_DEN     = "Unit C/O Denominator"
UNIT_RATE    = "Unit Charge-Off Rate"
DOLLAR_RATE  = "Dollar Charge-Off Rate"
ROA          = "ROA"
YEAR         = "Year"


# True  - the receivables column is already the average to date at that MOB
# False - it is the end-of-period balance, so the average is taken across every
#         month on book up to 12 / 24 / 36, before those rows are selected
RECEIVABLES_IS_AVERAGE = False


class SchemaGap(Exception):
    """A column the heat map needs is not in the file."""


def _key(name):
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


_LOOKUP = {_key(a): canon for canon, aliases in ALIASES.items()
           for a in aliases}
_IGNORE = {_key(c) for c in IGNORE}


def resolve_columns(df, *, report=None):
    """Rename the file's columns to canonical names and drop the ignored ones.

    Returns the renamed frame. Columns that match nothing are kept under their
    own name and listed in the report.
    """
    notes = report if report is not None else []
    rename, ignored, unknown = {}, [], []
    for col in df.columns:
        k = _key(col)
        if k in _IGNORE:
            ignored.append(col)
        elif k in _LOOKUP:
            rename[col] = _LOOKUP[k]
        else:
            unknown.append(col)

    out = df.drop(columns=ignored).rename(columns=rename)
    dupes = [c for c in out.columns if list(out.columns).count(c) > 1]
    if dupes:
        raise SchemaGap(f"two columns resolved to the same name: {set(dupes)}")

    if ignored:
        notes.append("ignored as instructed: " + ", ".join(map(str, ignored)))
    if unknown:
        notes.append(f"{len(unknown)} columns not named in the brief, carried "
                     f"as they are: " + ", ".join(map(str, unknown)))
    missing = [c for c in ALIASES if c not in out.columns]
    if missing:
        notes.append("NOT FOUND in the file: " + ", ".join(missing))
    return out


def add_avg_receivables(df, *, already_average=None, report=None):
    """Average gross receivables to date - the denominator of both rates.

    This runs BEFORE the MOB 12/24/36 rows are selected. An average to date is
    taken over every month up to that point, so months 1-11 have to still be
    in the frame when it is computed.
    """
    notes = report if report is not None else []
    if already_average is None:
        already_average = RECEIVABLES_IS_AVERAGE
    if "Receivables" not in df.columns:
        notes.append(f"NOT FOUND - no receivables column, so {DOLLAR_RATE} and "
                     f"{ROA} cannot be computed. Name it in ALIASES.")
        return df
    out = df.copy()
    rec = pd.to_numeric(out["Receivables"], errors="coerce").fillna(0.0)
    if already_average:
        out[AVG_REC] = rec
        notes.append(f"{AVG_REC}: taken from the file as supplied")
        return out

    dims = [c for c in DIMENSIONS if c in out.columns]
    mob = pd.to_numeric(out["MOB"], errors="coerce")
    out = out.assign(_rec=rec, _mob=mob).sort_values(dims + ["_mob"])
    out[AVG_REC] = (out.groupby(dims, dropna=False, observed=True)["_rec"]
                       .expanding().mean()
                       .reset_index(level=list(range(len(dims))), drop=True))
    out = out.drop(columns=["_rec", "_mob"])
    notes.append(f"{AVG_REC}: running mean of Receivables across every month "
                 f"on book, read at 12 / 24 / 36")
    return out


def keep_year_mobs(df, *, report=None):
    """Keep only MOB 12, 24 and 36, and label each Yr 1 / Yr 2 / Yr 3."""
    notes = report if report is not None else []
    if "MOB" not in df.columns:
        raise SchemaGap("no month-on-book column found")
    mob = pd.to_numeric(df["MOB"], errors="coerce")
    keep = mob.isin(MOB_YEARS)
    out = df[keep].copy()
    out["MOB"] = mob[keep].astype(int)
    out[YEAR] = out["MOB"].map(MOB_YEARS)
    notes.append(f"kept {len(out):,} of {len(df):,} rows at MOB "
                 f"{', '.join(map(str, MOB_YEARS))}")
    dropped = sorted(set(mob.dropna().astype(int)) - set(MOB_YEARS))
    if dropped:
        notes.append(f"other months on book in the file: "
                     f"{', '.join(map(str, dropped[:12]))}"
                     + (" ..." if len(dropped) > 12 else ""))
    return out


def aggregate(df, *, by=None, report=None):
    """Sum the measures to one row per cohort x year."""
    notes = report if report is not None else []
    dims = [c for c in (by or DIMENSIONS) if c in df.columns]
    if not dims:
        raise SchemaGap("none of the cohort columns are in the file")
    keys = dims + ["MOB", YEAR]
    measures = [c for c in MEASURES if c in df.columns]
    out = (df.groupby(keys, dropna=False, observed=True)[measures]
             .sum().reset_index())
    notes.append(f"grouped on {', '.join(dims)} x MOB -> {len(out):,} rows")
    lost = [c for c in df.columns if c not in keys and c not in measures]
    if lost:
        notes.append("dropped by the grouping (neither a cohort column nor a "
                     "measure): " + ", ".join(map(str, lost)))
    return out


def add_rates(df, *, report=None):
    """The heat map's measures.

      Unit Charge-Off Rate   net unit charge-off / (new accounts - unwinds)
      Dollar Charge-Off Rate net dollar / average gross receivables
      ROA                    (cf pretax less cost of funds
                              / average gross receivables) / MOB x 12
    """
    notes = report if report is not None else []
    out = df.copy()
    boards = _num(out, "NewAccounts")

    out[BOARDS] = boards
    out[UNIT_DEN] = boards - _num(out, "UnwindCount")
    out[UNIT_RATE] = _div(_num(out, "NetUnitChargeOff"), out[UNIT_DEN])
    notes.append(f"{UNIT_RATE} = NetUnitChargeOff / (NewAccounts - UnwindCount)")

    if AVG_REC not in out.columns:
        notes.append(f"no {AVG_REC}, so {DOLLAR_RATE} and {ROA} are blank")
        out[DOLLAR_RATE] = pd.Series(pd.NA, index=out.index, dtype="Float64")
        out[ROA] = pd.Series(pd.NA, index=out.index, dtype="Float64")
        return out

    avg_rec = _num(out, AVG_REC)
    out[DOLLAR_RATE] = _div(_num(out, "NetDollar"), avg_rec)
    notes.append(f"{DOLLAR_RATE} = NetDollar / {AVG_REC}")

    mob = pd.to_numeric(out["MOB"], errors="coerce")
    out[ROA] = _div(_num(out, "PretaxLessCoF"), avg_rec) / mob.where(mob > 0) * 12
    notes.append(f"{ROA} = (PretaxLessCoF / {AVG_REC}) / MOB x 12")
    return out


def _num(df, name):
    if name not in df.columns:
        raise SchemaGap(f"{name} is not in the file")
    return pd.to_numeric(df[name], errors="coerce").fillna(0.0)


def _div(num, den):
    den = pd.to_numeric(den, errors="coerce")
    return num / den.where(den.notna() & (den != 0))


def build(csv_path, *, by=None, receivables_is_average=None, report=None):
    """Read the actuals CSV and return one row per cohort per year.

    The order matters: the average receivables are taken across every month on
    book, so that happens before the 12 / 24 / 36 rows are selected.
    """
    notes = report if report is not None else []
    df = pd.read_csv(csv_path, low_memory=False)
    notes.append(f"{len(df):,} rows, {len(df.columns)} columns from {csv_path}")
    df = resolve_columns(df, report=notes)
    df = add_avg_receivables(df, already_average=receivables_is_average,
                             report=notes)
    df = keep_year_mobs(df, report=notes)
    df = aggregate(df, by=by, report=notes)
    df = add_rates(df, report=notes)
    return df
