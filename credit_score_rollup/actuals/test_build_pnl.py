"""Exercise build_pnl against a CSV shaped like the real VCRData extract.

The fixture copies what the extract actually looks like: already aggregated,
AccountNumber a text dimension, ChargeOffIndicator and ActiveAccountIndicator
as counts of accounts, score columns as sums with a matching *ScoreIndicator
count, and fees carrying a dollar sign.
"""
import re
import numpy as np, pandas as pd, build_pnl as bp, pnl_spec as spec

# The column list from the spec document's last page, verbatim and in order.
COLUMNS = """vintage VintageDate MonthsOnBooks AccountNumber Branding Acquisitions
Association source Subchannel AnnualFeeGroup Fee OriginalCreditLine NewAccounts
TotalFinanceCharges EndingReceivable RewardsAmount TotalNetSales
FeeAnnualChargeAmount Bucket0Count Bucket5Count Bucket30Count Bucket60Count
Bucket90Count Bucket120Count Bucket150Count Bucket90PrincipalAmount
Bucket120PrincipalAmount Bucket150PrincipalAmount Bucket0Amount Bucket5Amount
Bucket30Amount Bucket60Amount Bucket90Amount Bucket120Amount Bucket150Amount
ChargeOffIndicator FraudCount UnwindCount ACE2Score ACE4Score Vantage3score
ACE2ScoreIndicator ACE4ScoreIndicator ActiveAccountIndicator
InactiveAccountIndicator PrincipalReceivable FraudLossAmount FraudNetAmount52
FraudGrossAmount88 ChargeOffPrincipalAmount ChargeOffAmount RecoveriesAmount
CreditProtectionAmount FeeLateAccruedAmount InterchangeRevenue
FeeDirectCheckAmount FeeCashAdvanceAmount FeeCrLineIncreaseMiscAmt
TotalFeeAdjustments ActiveCreditLine FeeMiscAccruedTtlAmt FeeEnrollmentAmount
FeeOverlimitAmount ReserveBalGrossAmount2 ReserveBalGrossAmount4
ProvisionExpense CollectionsExpense60Plus CollectionsExpensePreCalland530
CreditProtectionExpense CustomerServiceExpense OneTimeBookingExpense
OtherOverheadExpense SystemsExpense TotalNetPayments Vantage3ScoreIndicator
TotalCashAdvances FeeCreditProtectionCount CreditLineIncreaseIndicator
FeeCrLineIncreaseMiscCnt FreeCLI FeeDirectCheckCount FeeLateAccruedCount
CurrentAccountLateFee Attrition RetainedFlag FeeAnnualDueMonthlyAmount
FeeAnnualMembershipAmount FeeDuplicateStatementAmount FeeFedExAmount
FeeFinanceChargeAmount FeeLateAmount FeeReplacementAmount
FeeReplacementManualAmount FeeSalesSlipAmount FeeOverlimitAdjustmentAmount
MiscFeeamount RecoveryExpense 2-Apr GrossRevenue FraudAmount RequiredReserves
CostofFundsExpense CashInflow CashOutflow NetCashFlow fpdcount fpdeval
VantageRange""".split()

REV = [c for _l, c, _s in spec.REVENUE_LINES]

# Cohorts in the extract's own vocabulary, from the workbook screenshots.
COHORTS = [
    # vintage, boards, AccountNumber, Branding, Acquisitions, Association,
    # source, Subchannel, AnnualFeeGroup, Fee, OriginalCreditLine, VantageRange
    ("2023-01-31", 219, "First Account", "C1B American Express",
     "Prequal - Credit-Targeted", "AMEX", "EXPX", "Prequal",
     "$75 / $75", "$75", 300, "601-639"),
    ("2023-01-31", 139, "First Account", "C1B American Express",
     "Prequal - Credit-Targeted", "AMEX", "EXPX", "Prequal",
     "$75 / $99", "$75", 300, "640+"),
    ("2024-03-31", 150, "First Account", "C1B American Express",
     "Prequal - Non-Targeted", "AMEX", "AMEX DCO", "Prequal",
     "$75 / $75", "$75", 500, "<=600"),
]


def fixture(seed=7, mobs=36):
    """One row per cohort per MOB, already aggregated, as the extract comes."""
    rng = np.random.default_rng(seed)
    rows = []
    for (vdate, boards, acct, brand, acq, assoc, src, sub,
         feegroup, fee, line, band) in COHORTS:
        stamp = pd.Timestamp(vdate)
        active = boards
        charged_off_to_date = 0
        for mob in range(1, mobs + 1):
            # accounts charging off this month, out of those still active
            co = int(rng.binomial(active, 0.006 * (1 + mob / 12)))
            r = {c: 0.0 for c in COLUMNS}
            r.update(vintage=stamp.strftime("%b-%y"),
                     VintageDate=stamp.strftime("%d-%b-%y"),
                     MonthsOnBooks=mob, AccountNumber=acct, Branding=brand,
                     Acquisitions=acq, Association=assoc, source=src,
                     Subchannel=sub, AnnualFeeGroup=feegroup, Fee=fee,
                     OriginalCreditLine=line, VantageRange=band)
            # NewAccounts lands on the booking month only
            r["NewAccounts"] = float(boards) if mob == 1 else 0.0
            r["UnwindCount"] = float(rng.integers(0, 3)) if mob <= 4 else 0.0
            r["ChargeOffIndicator"] = float(co)
            active -= co
            charged_off_to_date += co
            r["ActiveAccountIndicator"] = float(active)
            r["InactiveAccountIndicator"] = float(boards - active)
            # score columns are SUMS, with the count of accounts scored beside
            r["ACE2ScoreIndicator"] = float(active)
            r["ACE4ScoreIndicator"] = float(active)
            r["ACE2Score"] = float(active) * float(rng.uniform(900, 940))
            r["ACE4Score"] = float(active) * float(rng.uniform(820, 870))
            r["Vantage3ScoreIndicator"] = 0.0
            r["Vantage3score"] = 0.0
            r["EndingReceivable"] = active * 400.0 * (1 - 0.01 * mob)
            r["ChargeOffPrincipalAmount"] = co * 900.0 * float(
                rng.uniform(0.7, 1.3))
            for c in REV:
                r[c] = active * float(rng.uniform(0.2, 2.0))
            named = sum(sg * r[c] for _l, c, sg in spec.REVENUE_LINES)
            r["GrossRevenue"] = named + active * 0.35
            r["ProvisionExpense"] = active * float(rng.uniform(1.0, 4.0))
            for _l, c in spec.SERVICING_EXPENSE_LINES:
                r[c] = active * float(rng.uniform(0.1, 0.9))
            for _l, c in spec.OTHER_EXPENSE_LINES:
                r[c] = active * float(rng.uniform(0.1, 1.2))
            for c in spec.FRAUD_LOSS_PARTS:
                r[c] = active * float(rng.uniform(0.01, 0.2))
            rows.append(r)
    return pd.DataFrame(rows, columns=COLUMNS)


def main():
    raw = fixture()
    assert list(raw.columns) == COLUMNS
    # the extract arrives aggregated: these are counts, not 0/1 flags
    assert raw["ActiveAccountIndicator"].max() > 1
    assert raw["NewAccounts"].max() > 1
    assert not pd.api.types.is_numeric_dtype(raw["AccountNumber"]), \
        "AccountNumber is a text dimension, not an account id"

    log = []
    bp.audit_columns(raw, report=log)
    agg = bp.aggregate_to_cohort(raw, report=log)
    df = bp.add_pnl_lines(agg, report=log)
    df = bp.add_cumulative(df, report=log)
    checks, bad = bp.reconcile(df)

    keys = bp.grain_keys(agg)
    assert "AccountNumber" in keys, "AccountNumber is a dimension"
    # dimensions keep the order the extract has them in, MonthsOnBooks third
    extract_order = [c for c in COLUMNS if c in bp.DIMENSIONS]
    assert bp.dimension_columns(agg) == extract_order, bp.dimension_columns(agg)
    assert extract_order[:4] == ["vintage", "VintageDate", "MonthsOnBooks",
                                 "AccountNumber"], extract_order[:4]
    assert len(agg) == len(raw), "already at cohort grain, nothing to collapse"
    print(f"fixture: {len(raw)} rows x {len(COLUMNS)} spec columns "
          f"-> {len(df.columns)} columns\n")

    print("reconciliation")
    for name, worst in checks.items():
        print(f"  [{'FAILED' if name in bad else 'ok'}] {name}: "
              f"worst break {worst:,.6f}")
    assert not bad, bad

    print("\nnotes")
    for line in log:
        print("  -", line)

    # average scores come from the sum over the count, not a mean of sums
    one = df[(df.VantageRange == "601-639")].sort_values("MonthsOnBooks")
    r = one[one.MonthsOnBooks == 12].iloc[0]
    assert np.isclose(r["Avg ACE2 Score"], r["ACE2Score"] / r["ACE2ScoreIndicator"])
    assert 900 < r["Avg ACE2 Score"] < 940, r["Avg ACE2 Score"]
    print(f"\navg ACE2 score at MOB 12: {r['ACE2Score']:,.0f} / "
          f"{r['ACE2ScoreIndicator']:,.0f} = {r['Avg ACE2 Score']:,.1f}")

    # boards read at the first MOB, not summed across MOB
    assert (one[bp.L_BOARDS] == 219).all(), one[bp.L_BOARDS].unique()

    # unit charge-off rate = running count charged off / count still active
    CUMCO = "Cumul. Charge-Off Accounts"
    assert (one[bp.L_UNIT_DEN] == one["ActiveAccountIndicator"]).all()
    assert one[CUMCO].is_monotonic_increasing
    assert np.allclose(one[bp.L_CUM_UNIT], one[CUMCO] / one[bp.L_UNIT_DEN])
    assert 0.01 < one[bp.L_CUM_UNIT].iloc[-1] < 0.9

    print("\nunit charge-off rate, Jan-23 / $75 / 601-639")
    for mob in (1, 6, 12, 24, 36):
        r = one[one.MonthsOnBooks == mob].iloc[0]
        print(f"  MOB {mob:>2}  {r[CUMCO]:>4,.0f} charged off /"
              f" {r[bp.L_UNIT_DEN]:>4,.0f} active  (of {r[bp.L_BOARDS]:,.0f}"
              f" booked) = {r[bp.L_CUM_UNIT]:>6.2%}")

    # CPA and the Amex line
    log2 = []
    df2 = bp.add_pnl_lines(agg, cpa=185.0, amex_share=0.62, report=log2)
    def pick(band, mob):
        return df2[(df2.VantageRange == band)
                   & (df2.MonthsOnBooks == mob)].iloc[0]
    assert pick("601-639", 1)[bp.L_CPA] == 185.0 * 219
    assert pick("601-639", 30)[bp.L_CPA] == 0.0
    assert pick("601-639", 1)[bp.L_AMEX] == 0.0, "Jan-23 is before Feb 2024"
    assert pick("<=600", 1)[bp.L_AMEX] < 0 and pick("<=600", 25)[bp.L_AMEX] == 0
    mar = df2[df2.VantageRange == "<=600"]
    assert abs(mar[bp.L_AMEX].sum() + 2.03 * 0.62 * 150) < 0.01
    print(f"\nwith cpa=185 and amex_share=0.62:"
          f"  CPA at MOB 1 = {pick('601-639', 1)[bp.L_CPA]:,.2f}"
          f"   24 Amex instalments = {mar[bp.L_AMEX].sum():,.2f}")

    # the other reading of the unit rate
    alt = bp.add_cumulative(bp.add_pnl_lines(agg),
                            unit_co_denominator="boards_net_unwind")
    alt = alt[alt.VantageRange == "601-639"]
    assert alt[bp.L_UNIT_DEN].nunique() == 1
    print("\nunit C/O rate, Jan-23 / $75 / 601-639")
    for mob in (12, 24, 36):
        a = one[one.MonthsOnBooks == mob].iloc[0]
        b = alt[alt.MonthsOnBooks == mob].iloc[0]
        print(f"  MOB {mob:>2}  active accounts {a[bp.L_CUM_UNIT]:>7.2%}"
              f"  (denom {a[bp.L_UNIT_DEN]:>5,.0f})"
              f"   vs boards less unwinds {b[bp.L_CUM_UNIT]:>7.2%}"
              f"  (denom {b[bp.L_UNIT_DEN]:>5,.0f})")

    # ---- the output carries only what the solution needs -----------------
    # the real extract has columns nothing reads, some with numeric or date
    # headers; none of them may reach the output
    import tempfile, os
    noisy = raw.copy()
    noisy["Unnamed: 97"] = 2.0         # a blank header
    noisy["SomeOtherMeasure"] = 3.0
    tmp = os.path.join(tempfile.mkdtemp(), "noisy.csv")
    noisy.to_csv(tmp, index=False)

    log3 = []
    out = bp.build(tmp, report=log3)
    print("\nbuild() from a CSV with junk columns")
    for line in log3:
        print("  -", line)

    junk = {"2-Apr", "Unnamed: 97", "SomeOtherMeasure"}
    assert not (junk & set(out.columns)), junk & set(out.columns)
    # every output column is named, and no name is a bare number or a date
    for c in out.columns:
        assert isinstance(c, str) and c.strip(), repr(c)
        assert not c.replace(".", "").replace("-", "").isdigit(), c
        # not a date sitting where a column name should be
        assert not re.fullmatch(r"[\d/.\-]+", c), c
    # nothing the extract carries but the formulas never read survives
    unread = set(raw.columns) - bp.spec_columns() - set(bp.GRAIN_KEYS)
    assert not (unread & set(out.columns)), sorted(unread & set(out.columns))
    # and everything the formulas produce does
    for c in bp.PNL_COLUMNS + bp.CUMULATIVE_COLUMNS:
        assert c in out.columns, c
    print(f"\n  {len(noisy.columns)} columns in -> {len(out.columns)} out")
    print("  " + ", ".join(list(out.columns)[:14]) + ", ...")

    slim = bp.build(tmp, keep_inputs=False)
    assert len(slim.columns) < len(out.columns)
    assert "GrossRevenue" not in slim.columns
    assert "Pretax Income" in slim.columns
    print(f"  derived-only: {len(slim.columns)} columns")

    # ---- the written file must read back with every header in place ------
    out_path = os.path.join(os.path.dirname(tmp), "out.csv")
    log4 = []
    back = bp.write_output(out, out_path, report=log4)
    print()
    for line in log4:
        print("  -", line)
    assert list(back.columns) == list(out.columns)
    # every header field present on the data rows too
    with open(out_path) as fh:
        head = next(fh).rstrip("\n")
        first = next(fh).rstrip("\n")
    import csv as _csv
    n_head = len(next(_csv.reader([head])))
    n_row = len(next(_csv.reader([first])))
    assert n_head == n_row == len(out.columns), (n_head, n_row, len(out.columns))
    print(f"  header {n_head} fields, first data row {n_row} fields")

    print("\nfirst row, each column beside its value")
    hm = bp.header_map(out)
    for _i, r in hm.head(16).iterrows():
        v = r["value"]
        v = f"{v:,.4f}" if isinstance(v, float) else str(v)
        print(f"  {r['#']:>3}  {r['column']:<34} {v}")
    print(f"  ... {len(hm) - 16} more")

    print("\nall assertions passed")


if __name__ == "__main__":
    main()
