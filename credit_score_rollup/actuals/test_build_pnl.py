"""Exercise build_pnl against a CSV carrying the spec document's column list."""
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
MiscFeeamount RecoveryExpense GrossRevenue FraudAmount RequiredReserves
CostofFundsExpense CashInflow CashOutflow NetCashFlow fpdcount fpdeval
VantageRange""".split()

REV = [c for _l, c, _s in spec.REVENUE_LINES]


def fixture(seed=7, mobs=36):
    rng = np.random.default_rng(seed)
    rows = []
    cohorts = [("2024-01-01", "Credit Karma", "39", "All", "All"),
               ("2024-03-01", "Credit Karma", "39", "All", "All"),
               ("2024-03-01", "Experian",     "75", "500", "601-639")]
    for vdate, brand, fee, line, band in cohorts:
        boards = float(rng.integers(800, 3000))
        for mob in range(1, mobs + 1):
            r = {c: 0.0 for c in COLUMNS}
            r.update(vintage=vdate[:7], VintageDate=vdate, MonthsOnBooks=mob,
                     AccountNumber=boards, Branding=brand, Acquisitions="All",
                     Association="All", source="All", Subchannel="All",
                     AnnualFeeGroup=fee, Fee=fee, OriginalCreditLine=line,
                     VantageRange=band)
            r["NewAccounts"] = boards if mob == 1 else 0.0
            r["UnwindCount"] = float(rng.integers(0, 30)) if mob <= 4 else 0.0
            r["EndingReceivable"] = boards * 400 * (1 - 0.01 * mob)
            r["ActiveAccountIndicator"] = boards * (1 - 0.012 * mob)
            # revenue lines
            for c in REV:
                r[c] = boards * float(rng.uniform(0.2, 2.0))
            # gross revenue carries the named lines plus a miscellaneous bit
            named = sum(s * r[c] for _l, c, s in spec.REVENUE_LINES)
            r["GrossRevenue"] = named + boards * 0.35
            r["ProvisionExpense"] = boards * float(rng.uniform(1.0, 4.0))
            for _l, c in spec.SERVICING_EXPENSE_LINES:
                r[c] = boards * float(rng.uniform(0.1, 0.9))
            for _l, c in spec.OTHER_EXPENSE_LINES:
                r[c] = boards * float(rng.uniform(0.1, 1.2))
            for c in spec.FRAUD_LOSS_PARTS:
                r[c] = boards * float(rng.uniform(0.01, 0.2))
            r["ChargeOffIndicator"] = float(rng.integers(0, 25))
            r["ChargeOffPrincipalAmount"] = r["ChargeOffIndicator"] * 900.0
            rows.append(r)
    return pd.DataFrame(rows, columns=COLUMNS)


def main():
    raw = fixture()
    assert list(raw.columns) == COLUMNS
    log = []
    df = bp.add_pnl_lines(raw, report=log)
    df = bp.add_cumulative(df, report=log)
    checks, bad = bp.reconcile(df)

    print(f"fixture: {len(df)} rows x {len(COLUMNS)} spec columns "
          f"-> {len(df.columns)} columns\n")
    print("reconciliation")
    for name, worst in checks.items():
        print(f"  {name}: worst break {worst:.6f}")
    assert not bad, bad

    print("\nnotes")
    for line in log:
        print("  -", line)

    print("\nP&L at one cohort, MOB 12")
    row = df[(df.Branding == "Credit Karma") & (df.vintage == "2024-01")
             & (df.MonthsOnBooks == 12)].iloc[0]
    for label in bp.PNL_COLUMNS:
        print(f"  {label:<34} {row[label]:>14,.2f}")

    print("\ncumulative measures, 2024-01 Credit Karma")
    sl = df[(df.Branding == "Credit Karma") & (df.vintage == "2024-01")]
    sl = sl[sl.MonthsOnBooks.isin([1, 12, 24, 36])]
    for _i, r in sl.iterrows():
        print(f"  MOB {int(r.MonthsOnBooks):>2}  cumPTI {r[bp.L_CUM_PTI]:>14,.0f}"
              f"  avgRec {r[bp.L_AVG_REC]:>14,.0f}"
              f"  cumNCO {r[bp.L_CUM_NCO]:>8.2%}"
              f"  ROA {r[bp.L_CUM_ROA]:>8.2%}"
              f"  unitC/O {r[bp.L_CUM_UNIT]:>7.2%}")

    # the default denominator is active accounts, which falls as MOB rises
    assert spec.UNIT_CO_DENOMINATOR == "active"
    one = df[(df.Branding == "Credit Karma") & (df.vintage == "2024-01")] \
            .sort_values("MonthsOnBooks")
    assert one[bp.L_UNIT_DEN].nunique() > 1, "active accounts move with MOB"
    assert one[bp.L_UNIT_DEN].is_monotonic_decreasing
    assert (one[bp.L_UNIT_DEN] <= one[bp.L_BOARDS]).all()
    assert one[bp.L_CUM_UNIT].is_monotonic_increasing
    assert (one[bp.L_UNIT_DEN] == one["ActiveAccountIndicator"]).all()

    # CPA and the Amex line, switched on
    log2 = []
    df2 = bp.add_pnl_lines(raw, cpa=185.0, amex_share=0.62, report=log2)
    print("\nwith cpa=185.00 and amex_share=0.62")
    for line in log2:
        print("  -", line)
    def pick(v, mob):
        return df2[(df2.vintage == v) & (df2.MonthsOnBooks == mob)
                   & (df2.Branding == "Credit Karma")].iloc[0]
    for v, mob in [("2024-01", 1), ("2024-01", 30),
                   ("2024-03", 1), ("2024-03", 24), ("2024-03", 25)]:
        r = pick(v, mob)
        print(f"  {v} MOB {mob:>2}: CPA {r[bp.L_CPA]:>12,.2f}"
              f"   amex {r[bp.L_AMEX]:>10,.2f}")
    # CPA lands in the booking month only, on that month's boards
    assert pick("2024-01", 1)[bp.L_CPA] == 185.0 * pick("2024-01", 1)["NewAccounts"]
    assert pick("2024-01", 30)[bp.L_CPA] == 0.0
    # the incentive runs for vintages from Feb 2024, MOB 1-24, and is negative
    assert pick("2024-03", 1)[bp.L_AMEX] < 0
    assert pick("2024-03", 24)[bp.L_AMEX] < 0
    assert pick("2024-03", 25)[bp.L_AMEX] == 0.0, "stops after MOB 24"
    assert pick("2024-01", 1)[bp.L_AMEX] == 0.0, "nothing before Feb 2024"
    # 24 monthly instalments add back to rate x share x boards
    ck3 = df2[(df2.vintage == "2024-03") & (df2.Branding == "Credit Karma")]
    boards = ck3["NewAccounts"].sum()
    assert abs(ck3[bp.L_AMEX].sum() + 2.03 * 0.62 * boards) < 0.01
    print(f"  24 instalments total {ck3[bp.L_AMEX].sum():,.2f}"
          f" = -(2.03 x 0.62 x {boards:,.0f} boards)")

    # the other reading of the unit rate, still available
    alt = bp.add_cumulative(bp.add_pnl_lines(raw),
                            unit_co_denominator="boards_net_unwind")
    alt = alt[(alt.Branding == "Credit Karma") & (alt.vintage == "2024-01")]
    assert alt[bp.L_UNIT_DEN].nunique() == 1, "boards net unwind is constant"
    print("\nunit C/O rate, 2024-01 Credit Karma")
    for mob in (12, 24, 36):
        a = one[one.MonthsOnBooks == mob].iloc[0]
        b = alt[alt.MonthsOnBooks == mob].iloc[0]
        print(f"  MOB {mob:>2}  active accounts {a[bp.L_CUM_UNIT]:>7.2%}"
              f"  (denom {a[bp.L_UNIT_DEN]:>8,.0f})"
              f"   vs boards less unwinds {b[bp.L_CUM_UNIT]:>7.2%}"
              f"  (denom {b[bp.L_UNIT_DEN]:>8,.0f})")

    print("\nall assertions passed")


if __name__ == "__main__":
    main()
