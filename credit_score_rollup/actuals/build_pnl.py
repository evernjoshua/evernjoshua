"""Build the P&L columns for the heat map's actuals, from the VCR CSV.

Three stages:

  aggregate_to_cohort  sums the rows to one per cohort x MOB and derives the
                       average scores from each score sum and its matching
                       *ScoreIndicator count. The extract already arrives
                       aggregated, so this is normally a no-op that only
                       collapses repeats.
  add_pnl_lines(df)    the monthly P&L - revenues, provision, servicing and
                       other expenses, pretax income.
  add_cumulative(df)   the cumulative measures the heat map reads - cumulative
                       pretax income, cumulative net charge-off before
                       recoveries, cumulative ROA annualised, cumulative unit
                       charge-off rate.

Every line names the CSV column it comes from in pnl_spec.py. Nothing is
inferred: two inputs the spec asks for are not in the CSV (CPA and amex_share),
and they stay at zero, and are reported, until you give them a source.
"""

from __future__ import annotations

import pandas as pd

import pnl_spec as spec

# ----------------------------------------------------------- line labels ----
L_MISC  = spec.MISC_REVENUE_LINE
L_TGR   = "Total Gross Revenues"
L_PROV  = "(Provision for Loan Loss)"
L_TNR   = "Total Net Revenues"
L_TSE   = "Total Servicing Expenses"
L_CPA   = "One Time - Marketing Expense (CPA)"
L_FRAUD = "Fraud Loss Expense"
L_AMEX  = "Amex Incentive Expense"
L_TOE   = "Total Operating Expenses"
L_PTI   = "Pretax Income"

L_CUM_PTI   = "Cumul. Pre-Tax Income"
L_AVG_REC   = "Avg Total Gross Receivables - End of Period"
L_CUM_NCO   = "Cumul. Net Charge-Off Before Recoveries"
L_CUM_ROA   = "Cumul. ROA - Annualized"
L_CUM_UNIT  = "Cumul. Unit Charge-Off Rate"
L_BOARDS    = "Booked Accounts"
L_UNIT_DEN  = "Unit C/O Denominator"

# Dimensions that identify a cohort. A cumulative measure runs across MOB
# within one of these, so they must not include MonthsOnBooks.
# The extract's dimension columns, in file order. AccountNumber belongs here:
# it holds text like "First Account", not an account id.
GRAIN_KEYS = [
    "vintage", "VintageDate", "AccountNumber", "Branding", "Acquisitions",
    "Association", "source", "Subchannel", "AnnualFeeGroup", "Fee",
    "OriginalCreditLine", "VantageRange",
]
MOB_KEY = "MonthsOnBooks"


class SpecGap(Exception):
    """A column the spec document asks for is not in the CSV."""


def _col(df, name, *, missing):
    """The column as a float series, or zeros when it is absent."""
    if name in df.columns:
        return pd.to_numeric(df[name], errors="coerce").fillna(0.0)
    missing.append(name)
    return pd.Series(0.0, index=df.index)


def grain_keys(df):
    """The cohort keys actually present in this CSV, in spec order."""
    return [k for k in GRAIN_KEYS if k in df.columns]


def spec_columns():
    """Every CSV column the spec actually reads."""
    used = {spec.GROSS_REVENUE, spec.PROVISION, spec.RECEIVABLE_COLUMN,
            spec.BOARDS_COLUMN, spec.UNWIND_COLUMN, spec.CHARGE_OFF_UNITS,
            spec.CHARGE_OFF_PRIN, spec.ACTIVE_COLUMN, MOB_KEY}
    used.update(c for _l, c, _s in spec.REVENUE_LINES)
    used.update(c for _l, c in spec.SERVICING_EXPENSE_LINES)
    used.update(c for _l, c in spec.OTHER_EXPENSE_LINES)
    used.update(spec.FRAUD_LOSS_PARTS)
    for total, counter, _label in spec.SCORE_PAIRS:
        used.update((total, counter))
    if spec.CPA_COLUMN:
        used.add(spec.CPA_COLUMN)
    return used


def audit_columns(df, *, report=None):
    """Say which columns the spec reads, which it wants but the file lacks,
    and which the file carries that nothing reads."""
    notes = report if report is not None else []
    used = spec_columns()
    keys = grain_keys(df)
    present = [c for c in used if c in df.columns]
    absent = sorted(c for c in used if c not in df.columns)
    unread = [c for c in df.columns if c not in used and c not in keys]

    notes.append(f"dimensions: {', '.join(keys)}")
    notes.append(f"spec reads {len(present)} of its {len(used)} columns")
    if absent:
        notes.append("spec columns NOT in the file (read as zero): "
                     + ", ".join(absent))
    odd = [c for c in unread if str(c).startswith("Unnamed")
           or any(ch in str(c) for ch in "/:")]
    if odd:
        notes.append("unexpected column headers - check these are not a stray "
                     "date or blank column: " + ", ".join(map(str, odd)))
    if unread:
        notes.append(f"{len(unread)} columns carried through but not read by "
                     f"the spec (summed, kept in the output)")
    return dict(present=present, absent=absent, unread=unread)


# ------------------------------------------------------------- stage zero ----
def aggregate_to_cohort(df, *, report=None):
    """Sum the account-month rows to one row per cohort x MOB.

    ChargeOffIndicator and ActiveAccountIndicator already arrive as counts of
    accounts, which is what the rates below divide by. The score columns are
    sums, so they are summed too and the averages derived from each one's
    *ScoreIndicator count. Input already at cohort grain passes through.
    """
    notes = report if report is not None else []
    keys = grain_keys(df)
    if not keys:
        raise SpecGap("no cohort columns found; expected some of "
                      + ", ".join(GRAIN_KEYS))
    if MOB_KEY not in df.columns:
        raise SpecGap(f"{MOB_KEY} is not in the CSV")

    group_keys = keys + [MOB_KEY]
    measures = [c for c in df.columns
                if c not in group_keys and pd.api.types.is_numeric_dtype(df[c])]
    dropped = [c for c in df.columns
               if c not in group_keys and c not in measures]

    g = df.groupby(group_keys, dropna=False, observed=True)
    out = g.agg({c: "sum" for c in measures})
    out[spec.ROWS_COLUMN] = g.size()
    out = out.reset_index()

    # average score = the score sum over the count of accounts scored
    for total, counter, label in spec.SCORE_PAIRS:
        if total in out.columns and counter in out.columns:
            out[label] = _div(out[total], out[counter])

    if len(out) == len(df):
        notes.append(f"already one row per cohort x MOB ({len(df):,} rows); "
                     f"nothing to sum")
    else:
        per = len(df) / len(out)
        notes.append(f"summed {len(df):,} account-month rows to {len(out):,} "
                     f"cohort-month rows ({per:,.1f} accounts per cohort-month)")
    derived = [l for t, c, l in spec.SCORE_PAIRS if l in out.columns]
    if derived:
        notes.append("average scores derived from each score sum over its "
                     "*ScoreIndicator count: " + ", ".join(derived))
    if dropped:
        notes.append("non-numeric columns dropped by the sum: "
                     + ", ".join(dropped))
    return out


# ------------------------------------------------------------- stage one ----
def add_pnl_lines(df, *, cpa=None, amex_share=None, report=None):
    """Add the monthly P&L lines. Returns a new frame.

    cpa         a column name, a per-board dollar amount, or None. The spec's
                "One Time - Marketing Expense (CPA)" reads a CPA column the CSV
                does not have; pass one of these to fill the line in.
    amex_share  the amex_share the Amex Incentive line multiplies by. None
                leaves that line at zero.
    report      a list that collects notes about gaps and checks.
    """
    out = df.copy()
    notes = report if report is not None else []
    missing = []

    # -- revenues ------------------------------------------------------------
    named_total = pd.Series(0.0, index=out.index)
    for label, column, sign in spec.REVENUE_LINES:
        line = _col(out, column, missing=missing)
        out[label] = sign * line
        named_total = named_total + out[label]

    gross = _col(out, spec.GROSS_REVENUE, missing=missing)
    # Gross Revenue less the named revenue lines, so the block always adds
    # back to Gross Revenue exactly.
    out[L_MISC] = gross - named_total
    out[L_TGR] = named_total + out[L_MISC]

    # -- provision and net revenue ------------------------------------------
    provision = _col(out, spec.PROVISION, missing=missing)
    out[L_PROV] = spec.PROVISION_SIGN * provision
    out[L_TNR] = out[L_TGR] + out[L_PROV]

    # -- servicing expenses --------------------------------------------------
    servicing = pd.Series(0.0, index=out.index)
    for label, column in spec.SERVICING_EXPENSE_LINES:
        out[label] = _col(out, column, missing=missing)
        servicing = servicing + out[label]
    out[L_TSE] = servicing

    # -- other expenses ------------------------------------------------------
    other = pd.Series(0.0, index=out.index)
    for label, column in spec.OTHER_EXPENSE_LINES:
        out[label] = _col(out, column, missing=missing)
        other = other + out[label]

    # Fraud Loss Expense = FraudGrossAmount88 + FraudNetAmount52
    fraud = pd.Series(0.0, index=out.index)
    for column in spec.FRAUD_LOSS_PARTS:
        fraud = fraud + _col(out, column, missing=missing)
    out[L_FRAUD] = fraud
    other = other + fraud

    # One Time - Marketing Expense (CPA)
    out[L_CPA], cpa_note = _cpa_line(out, cpa, missing)
    other = other + out[L_CPA]
    if cpa_note:
        notes.append(cpa_note)

    # Amex Incentive Expense
    out[L_AMEX], amex_note = _amex_line(out, amex_share, missing)
    other = other + out[L_AMEX]
    if amex_note:
        notes.append(amex_note)

    out[L_TOE] = out[L_TSE] + other
    out[L_PTI] = out[L_TNR] - out[L_TOE]

    if missing:
        notes.append("columns not in the CSV, read as zero: "
                     + ", ".join(sorted(set(missing))))
    return out


def _cpa_line(out, cpa, missing):
    zero = pd.Series(0.0, index=out.index)
    if cpa is None:
        column = spec.CPA_COLUMN
        if column is None:
            return zero, ("CPA: the spec's One Time - Marketing Expense (CPA) "
                          "has no column in the CSV, so the line is zero. Pass "
                          "cpa=<column name> or cpa=<dollars per board>.")
        return _col(out, column, missing=missing), None
    if isinstance(cpa, str):
        if cpa not in out.columns:
            raise SpecGap(f"cpa column {cpa!r} is not in the CSV")
        return pd.to_numeric(out[cpa], errors="coerce").fillna(0.0), None
    # a flat dollar amount per booked account, charged in the booking month
    boards = _col(out, spec.BOARDS_COLUMN, missing=missing)
    return float(cpa) * boards, f"CPA: charged at {float(cpa):,.2f} per board."


def _amex_line(out, share, missing):
    """2.03 * amex_share * booked accounts / 24, negated, for vintages from
    Feb 2024 and MOB <= 24."""
    cfg = spec.AMEX_INCENTIVE
    zero = pd.Series(0.0, index=out.index)
    if share is None:
        share = cfg.get("share")
    if share is None:
        return zero, ("Amex Incentive: amex_share is not in the CSV, so the "
                      "line is zero. Pass amex_share=<fraction>.")
    keys = grain_keys(out)
    boards = _col(out, spec.BOARDS_COLUMN, missing=missing)
    cohort_boards = boards.groupby([out[k] for k in keys]).transform("sum") \
        if keys else boards
    mob = _col(out, MOB_KEY, missing=missing)
    vdate = _vintage_month(out)
    live = (vdate >= pd.Period(cfg["from_vintage"], freq="M")) \
        & (mob <= cfg["max_mob"]) & (mob >= 1)
    amount = -cfg["rate"] * float(share) * cohort_boards / cfg["months"]
    return amount.where(live, 0.0), (
        f"Amex Incentive: {cfg['rate']} x {share} x boards / {cfg['months']}, "
        f"negated, for vintages from {cfg['from_vintage']} and MOB <= "
        f"{cfg['max_mob']}.")


# The extract writes dates as "31-Jan-23" and vintages as "Jan-23".
DATE_FORMATS = ("%d-%b-%y", "%d-%b-%Y", "%b-%y", "%b-%Y",
                "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y")


def _vintage_month(df):
    for name in ("VintageDate", "vintage"):
        if name not in df.columns:
            continue
        col = df[name]
        if pd.api.types.is_datetime64_any_dtype(col):
            return col.dt.to_period("M")
        text = col.astype("string").str.strip()
        for fmt in DATE_FORMATS:
            parsed = pd.to_datetime(text, format=fmt, errors="coerce")
            if parsed.notna().any():
                return parsed.dt.to_period("M")
        parsed = pd.to_datetime(text, errors="coerce", format="mixed")
        if parsed.notna().any():
            return parsed.dt.to_period("M")
    return pd.Series(pd.NaT, index=df.index).dt.to_period("M")


# ------------------------------------------------------------- stage two ----
def add_cumulative(df, *, unit_co_denominator=None, report=None):
    """Add the cumulative measures, running across MOB within each cohort."""
    notes = report if report is not None else []
    missing = []
    if unit_co_denominator is None:
        unit_co_denominator = spec.UNIT_CO_DENOMINATOR
    keys = grain_keys(df)
    if not keys:
        raise SpecGap("no cohort columns found; expected some of "
                      + ", ".join(GRAIN_KEYS))
    if MOB_KEY not in df.columns:
        raise SpecGap(f"{MOB_KEY} is not in the CSV")

    out = df.sort_values(keys + [MOB_KEY]).copy()
    g = out.groupby(keys, sort=False, dropna=False)
    mob = _col(out, MOB_KEY, missing=missing)

    # cumulative pretax income
    out[L_CUM_PTI] = g[L_PTI].cumsum()

    # average end-of-period gross receivables, to date
    rec = _col(out, spec.RECEIVABLE_COLUMN, missing=missing)
    out["_rec"] = rec
    out[L_AVG_REC] = out.groupby(keys, sort=False, dropna=False)["_rec"] \
        .expanding().mean().reset_index(level=list(range(len(keys))), drop=True)
    del out["_rec"]

    # cumulative net charge-off before recoveries
    out["_co_prin"] = _col(out, spec.CHARGE_OFF_PRIN, missing=missing)
    cum_co_prin = out.groupby(keys, sort=False, dropna=False)["_co_prin"].cumsum()
    del out["_co_prin"]
    out[L_CUM_NCO] = _div(cum_co_prin, out[L_AVG_REC])

    # cumulative ROA, annualised
    out[L_CUM_ROA] = _div(out[L_CUM_PTI], out[L_AVG_REC]) / mob.where(mob > 0) * 12

    # cumulative unit charge-off rate
    out["_co_unit"] = _col(out, spec.CHARGE_OFF_UNITS, missing=missing)
    cum_co_unit = out.groupby(keys, sort=False, dropna=False)["_co_unit"].cumsum()
    del out["_co_unit"]
    out["Cumul. Charge-Off Accounts"] = cum_co_unit
    boards, denom = _unit_denominator(out, keys, unit_co_denominator, missing, notes)
    out[L_BOARDS] = boards
    out[L_UNIT_DEN] = denom
    out[L_CUM_UNIT] = _div(cum_co_unit, denom)

    if missing:
        notes.append("columns not in the CSV, read as zero: "
                     + ", ".join(sorted(set(missing))))
    return out.reset_index(drop=True)


def _unit_denominator(out, keys, mode, missing, notes):
    """Booked accounts less unwinds through MOB 4, or active accounts."""
    boards = _cohort_boards(out, keys, missing, notes)
    if mode == "active":
        active = _col(out, spec.ACTIVE_COLUMN, missing=missing)
        notes.append(f"Unit C/O rate = cumulative {spec.CHARGE_OFF_UNITS} / "
                     f"{spec.ACTIVE_COLUMN}, both counts of accounts at cohort "
                     f"level; the denominator moves with MOB.")
        if (active == 0).all():
            notes.append(f"WARNING - {spec.ACTIVE_COLUMN} is zero on every "
                         f"row, so the unit C/O rate is blank.")
        elif active.max() <= 1:
            notes.append(f"WARNING - {spec.ACTIVE_COLUMN} never exceeds 1, so "
                         f"these rows look like single accounts rather than "
                         f"cohorts. Run aggregate_to_cohort first.")
        return boards, active
    if mode != "boards_net_unwind":
        raise SpecGap(f"unknown unit_co_denominator {mode!r}")
    mob = _col(out, MOB_KEY, missing=missing)
    unwind = _col(out, spec.UNWIND_COLUMN, missing=missing)
    early = unwind.where(mob <= spec.UNWIND_THROUGH_MOB, 0.0)
    unwinds = early.groupby([out[k] for k in keys]).transform("sum")
    notes.append(f"Unit C/O rate over booked accounts less unwinds through MOB "
                 f"{spec.UNWIND_THROUGH_MOB}.")
    return boards, boards - unwinds


def _cohort_boards(out, keys, missing, notes):
    """Booked accounts: NewAccounts as at the cohort's earliest MOB.

    Summing NewAccounts across MOB would multiply the cohort if the extract
    repeats the booking count on every month, so it is read at the first MOB
    and the other months are checked rather than added.
    """
    boards_m = _col(out, spec.BOARDS_COLUMN, missing=missing)
    mob = _col(out, MOB_KEY, missing=missing)
    grouper = [out[k] for k in keys]
    first_mob = mob.groupby(grouper).transform("min")
    at_first = boards_m.where(mob == first_mob, 0.0)
    boards = at_first.groupby(grouper).transform("sum")

    later = boards_m.where(mob > first_mob, 0.0)
    if (later != 0).any():
        n = int((later != 0).sum())
        notes.append(f"NOTE - {spec.BOARDS_COLUMN} is non-zero after the first "
                     f"MOB on {n:,} rows, so booked accounts are read at the "
                     f"first MOB rather than summed across MOB.")
    if (boards == 0).any():
        n = int((boards == 0).sum())
        notes.append(f"WARNING - {spec.BOARDS_COLUMN} is zero at the first MOB "
                     f"for {n:,} rows, so those cohorts have no booked count.")
    return boards


def _div(num, den):
    den = den.where(den.notna() & (den != 0))
    return num / den


# ------------------------------------------------------------------ check ----
def reconcile(df, *, tolerance=0.01):
    """The revenue block must add back to GrossRevenue, and pretax income must
    equal net revenues less operating expenses. Returns the worst breaks."""
    checks = {}
    if spec.GROSS_REVENUE in df.columns:
        checks["Total Gross Revenues vs GrossRevenue"] = \
            (df[L_TGR] - pd.to_numeric(df[spec.GROSS_REVENUE],
                                       errors="coerce").fillna(0.0)).abs().max()
    checks["Pretax Income vs net revenues - operating expenses"] = \
        (df[L_PTI] - (df[L_TNR] - df[L_TOE])).abs().max()
    bad = {k: v for k, v in checks.items() if pd.notna(v) and v > tolerance}
    return checks, bad


PNL_COLUMNS = (
    [label for label, _c, _s in spec.REVENUE_LINES]
    + [L_MISC, L_TGR, L_PROV, L_TNR]
    + [label for label, _c in spec.SERVICING_EXPENSE_LINES]
    + [L_TSE]
    + [label for label, _c in spec.OTHER_EXPENSE_LINES]
    + [L_FRAUD, L_CPA, L_AMEX, L_TOE, L_PTI]
)
CUMULATIVE_COLUMNS = [L_CUM_PTI, L_AVG_REC, L_CUM_NCO, L_CUM_ROA,
                      L_BOARDS, "Cumul. Charge-Off Accounts",
                      L_UNIT_DEN, L_CUM_UNIT]
CUM_UNIT_NUMERATOR = "Cumul. Charge-Off Accounts"


def build(csv_path, *, cpa=None, amex_share=None,
          unit_co_denominator=None, report=None):
    """Read the VCR CSV and add every column above."""
    notes = report if report is not None else []
    df = pd.read_csv(csv_path, low_memory=False)
    notes.append(f"{len(df):,} rows, {len(df.columns)} columns read from {csv_path}")
    audit_columns(df, report=notes)
    df = aggregate_to_cohort(df, report=notes)
    df = add_pnl_lines(df, cpa=cpa, amex_share=amex_share, report=notes)
    df = add_cumulative(df, unit_co_denominator=unit_co_denominator, report=notes)
    _checks, bad = reconcile(df)
    for name, worst in bad.items():
        notes.append(f"CHECK FAILED - {name}: worst break {worst:,.2f}")
    return df


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csv")
    ap.add_argument("-o", "--out", default="vcr_with_pnl.csv")
    ap.add_argument("--cpa", default=None)
    ap.add_argument("--amex-share", type=float, default=None)
    ap.add_argument("--unit-co-denominator", default=None,
                    choices=["boards_net_unwind", "active"])
    a = ap.parse_args()
    cpa = a.cpa
    if cpa is not None:
        try:
            cpa = float(cpa)
        except ValueError:
            pass
    log = []
    frame = build(a.csv, cpa=cpa, amex_share=a.amex_share,
                  unit_co_denominator=a.unit_co_denominator, report=log)
    frame.to_csv(a.out, index=False)
    for line in log:
        print(" -", line)
    print(f"wrote {a.out}: {len(frame):,} rows, {len(frame.columns)} columns")
