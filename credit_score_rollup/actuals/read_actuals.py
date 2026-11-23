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
DIMENSIONS = ["Vintage", "VintageDate", "Subchannel", "VantageRange",
              "AnnualFee", "OriginalCreditLine"]
MEASURES = ["NewAccounts", "NetUnitChargeOff", "UnwindCount", "NetDollar",
            "PretaxLessCoF"]

# Output names
BOARDS       = "Booked Accounts"
UNIT_DEN     = "Unit C/O Denominator"
UNIT_RATE    = "Unit Charge-Off Rate"
DOLLAR_RATE  = "Dollar Charge-Off Rate"
ROA          = "ROA"
YEAR         = "Year"


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


def add_rates(df, *, dollar_denominator=None, roa_denominator=None,
              report=None):
    """The heat map's four measures.

    The unit rate is settled: net unit charge-off over new accounts less
    unwinds. The dollar rate and the ROA each need a denominator this file does
    not obviously carry, so they are left blank until one is named - pass a
    column name, or a callable taking the frame and returning a series.
    """
    notes = report if report is not None else []
    out = df.copy()
    boards = _num(out, "NewAccounts")
    unwinds = _num(out, "UnwindCount")

    out[BOARDS] = boards
    out[UNIT_DEN] = boards - unwinds
    out[UNIT_RATE] = _div(_num(out, "NetUnitChargeOff"), out[UNIT_DEN])
    notes.append(f"{UNIT_RATE} = NetUnitChargeOff / (NewAccounts - UnwindCount)")

    out[DOLLAR_RATE] = _resolve_rate(out, "NetDollar", dollar_denominator,
                                     DOLLAR_RATE, notes)
    out[ROA] = _resolve_rate(out, "PretaxLessCoF", roa_denominator, ROA, notes)
    return out


def _resolve_rate(out, numerator, denominator, label, notes):
    num = _num(out, numerator)
    if denominator is None:
        notes.append(f"{label}: no denominator given, so the column is blank. "
                     f"Numerator is {numerator}.")
        return pd.Series(pd.NA, index=out.index, dtype="Float64")
    if callable(denominator):
        den = pd.Series(denominator(out), index=out.index).astype(float)
        notes.append(f"{label} = {numerator} / (supplied)")
        return _div(num, den)
    if denominator not in out.columns:
        raise SchemaGap(f"{label}: denominator {denominator!r} is not a column")
    notes.append(f"{label} = {numerator} / {denominator}")
    return _div(num, out[denominator])


def _num(df, name):
    if name not in df.columns:
        raise SchemaGap(f"{name} is not in the file")
    return pd.to_numeric(df[name], errors="coerce").fillna(0.0)


def _div(num, den):
    den = pd.to_numeric(den, errors="coerce")
    return num / den.where(den.notna() & (den != 0))


def build(csv_path, *, by=None, dollar_denominator=None, roa_denominator=None,
          report=None):
    notes = report if report is not None else []
    df = pd.read_csv(csv_path, low_memory=False)
    notes.append(f"{len(df):,} rows, {len(df.columns)} columns from {csv_path}")
    df = resolve_columns(df, report=notes)
    df = keep_year_mobs(df, report=notes)
    df = aggregate(df, by=by, report=notes)
    df = add_rates(df, dollar_denominator=dollar_denominator,
                   roa_denominator=roa_denominator, report=notes)
    return df
