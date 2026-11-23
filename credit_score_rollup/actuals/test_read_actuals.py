"""Exercise read_actuals against a CSV in the described shape."""
import numpy as np, pandas as pd, read_actuals as ra

# Headers spelled the way a hand-built export tends to spell them.
HEADERS = ["Vintage", "Vintage Date", "Account", "Account Number",
           "Subchannel", "Application Credit Score", "Vantage Range",
           "Annual Fee Group", "Annual Fee", "Original Credit Line",
           "Month on Book", "New Accounts", "Net Unit Charge Off",
           "Unwinds Count", "Net Dollar", "CF Pretax minus Cost of Funds"]


def fixture(seed=3):
    rng = np.random.default_rng(seed)
    rows = []
    for vintage, vdate in [("Jan-23", "31-Jan-23"), ("Aug-24", "31-Aug-24")]:
        for band in ("<=600", "601-639", "640+"):
            for fee in ("$75", "$99"):
                for line in (300, 500):
                    boards = int(rng.integers(80, 400))
                    unwinds = int(rng.integers(0, 12))
                    for mob in (1, 6, 12, 24, 36, 48):
                        live = max(boards - unwinds, 1)
                        co = int(live * 0.004 * mob)
                        rows.append({
                            "Vintage": vintage, "Vintage Date": vdate,
                            "Account": "First Account",
                            "Account Number": None,
                            "Subchannel": "Digital",
                            "Application Credit Score": int(rng.integers(560, 720)),
                            "Vantage Range": band,
                            "Annual Fee Group": f"{fee} / $99",
                            "Annual Fee": fee, "Original Credit Line": line,
                            "Month on Book": mob, "New Accounts": boards,
                            "Net Unit Charge Off": co,
                            "Unwinds Count": unwinds,
                            "Net Dollar": co * 920.0,
                            "CF Pretax minus Cost of Funds":
                                boards * 40.0 - co * 900.0,
                        })
    return pd.DataFrame(rows, columns=HEADERS)


def main():
    raw = fixture()
    log = []
    df = ra.resolve_columns(raw, report=log)

    # the two account columns are gone, annual fee group with them
    for gone in ("Account", "Account Number", "Annual Fee Group"):
        assert gone not in df.columns, gone
    assert "AnnualFee" in df.columns and "VantageRange" in df.columns
    assert not [c for c in ra.ALIASES if c not in df.columns], \
        [c for c in ra.ALIASES if c not in df.columns]

    df = ra.keep_year_mobs(df, report=log)
    assert set(df["MOB"]) == {12, 24, 36}
    assert set(df[ra.YEAR]) == {"Yr 1", "Yr 2", "Yr 3"}

    df = ra.aggregate(df, report=log)
    df = ra.add_rates(df, report=log)

    print(f"{len(raw)} rows in -> {len(df)} cohort-years, "
          f"{len(df.columns)} columns\n")
    for line in log:
        print("  -", line)

    # the unit rate is net unit charge-off over new accounts less unwinds
    r = df.iloc[0]
    assert np.isclose(r[ra.UNIT_DEN], r["NewAccounts"] - r["UnwindCount"])
    assert np.isclose(r[ra.UNIT_RATE],
                      r["NetUnitChargeOff"] / r[ra.UNIT_DEN])
    assert (df[ra.UNIT_RATE] > 0).all()
    # the two undetermined rates stay blank rather than guessing
    assert df[ra.DOLLAR_RATE].isna().all()
    assert df[ra.ROA].isna().all()

    print("\nunit charge-off rate by year, $75 / 601-639 / line 300")
    sl = df[(df.AnnualFee == "$75") & (df.VantageRange == "601-639")
            & (df.OriginalCreditLine == 300) & (df.Vintage == "Jan-23")]
    for _i, r in sl.sort_values("MOB").iterrows():
        print(f"  {r[ra.YEAR]} (MOB {r['MOB']:>2})  "
              f"{r['NetUnitChargeOff']:>5,.0f} / {r[ra.UNIT_DEN]:>5,.0f}"
              f" = {r[ra.UNIT_RATE]:>7.2%}   boards {r[ra.BOARDS]:>5,.0f}")

    # a denominator, once named, is used
    with_den = ra.add_rates(df, dollar_denominator="NewAccounts",
                            roa_denominator=lambda d: d["NewAccounts"] * 400)
    assert with_den[ra.DOLLAR_RATE].notna().all()
    assert np.isclose(with_den[ra.ROA].iloc[0],
                      df["PretaxLessCoF"].iloc[0] / (df["NewAccounts"].iloc[0] * 400))
    print("\ndenominators, once named, are applied:"
          f"  $ C/O {with_den[ra.DOLLAR_RATE].iloc[0]:,.2f} per account,"
          f"  ROA {with_den[ra.ROA].iloc[0]:.2%}")

    print("\nall assertions passed")


if __name__ == "__main__":
    main()
