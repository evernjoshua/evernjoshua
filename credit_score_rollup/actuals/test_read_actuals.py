"""Exercise read_actuals against a CSV in the described shape."""
import numpy as np, pandas as pd, read_actuals as ra

# Headers spelled the way a hand-built export tends to spell them.
HEADERS = ["Acquisition Segment", "Vintage", "Vintage Date", "Account", "Account Number",
           "Subchannel", "Application Credit Score", "Vantage Range",
           "Annual Fee Group", "Annual Fee", "Original Credit Line",
           "Month on Book", "New Accounts", "Net Unit Charge Off",
           "Unwinds Count", "Net Dollar", "Ending Receivable",
           "CF Pretax minus Cost of Funds"]


def fixture(seed=3):
    rng = np.random.default_rng(seed)
    rows = []
    for campaign in ("Credit Karma", "Experian"):
      for vintage, vdate in [("Jan-23", "31-Jan-23"), ("Aug-24", "31-Aug-24")]:
        for band in ("<=600", "601-639", "640+"):
            for fee in ("$75", "$99"):
                for line in (300, 500):
                    boards = int(rng.integers(80, 400))
                    unwinds = int(rng.integers(0, 12))
                    for mob in range(1, 49):
                        live = max(boards - unwinds, 1)
                        co = int(live * 0.004 * mob)
                        rows.append({
                            "Acquisition Segment": campaign,
                            "Ending Receivable":
                                live * 420.0 * (1 - 0.008 * mob),
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

    assert "Campaign" in df.columns and "Receivables" in df.columns
    # the mapping report names every column and what it became
    cmap = ra.column_map(fixture())
    assert cmap.loc[cmap["column in your file"] == "Acquisition Segment",
                    "used as"].iloc[0] == "Campaign"
    assert not (cmap["column in your file"] == "- MISSING -").any(), \
        cmap[cmap["column in your file"] == "- MISSING -"]
    print("\ncolumn map")
    print(cmap.to_string(index=False))
    print("\nvalues found")
    print(ra.dimension_values(df).to_string(index=False))
    df = ra.add_avg_receivables(df, report=log)
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
    # the dollar rate and the ROA are over average gross receivables
    assert np.isclose(r[ra.DOLLAR_RATE], r["NetDollar"] / r[ra.AVG_REC])
    assert np.isclose(r[ra.ROA],
                      r["PretaxLessCoF"] / r[ra.AVG_REC] / r["MOB"] * 12)
    assert df[ra.DOLLAR_RATE].notna().all() and df[ra.ROA].notna().all()

    # the average is taken across every month, so it is not the MOB 12 balance
    raw2 = ra.resolve_columns(fixture(), report=[])
    cohort = ((raw2.Campaign == "Credit Karma") & (raw2.Vintage == "Jan-23")
              & (raw2.VantageRange == "601-639") & (raw2.AnnualFee == "$75")
              & (raw2.OriginalCreditLine == 300))
    months = raw2[cohort].sort_values("MOB")
    want = months[months.MOB <= 12]["Receivables"].mean()
    got_all = ra.add_avg_receivables(raw2, report=[])
    mask = ((got_all.Campaign == "Credit Karma") & (got_all.Vintage == "Jan-23")
            & (got_all.VantageRange == "601-639")
            & (got_all.AnnualFee == "$75")
            & (got_all.OriginalCreditLine == 300) & (got_all.MOB == 12))
    got = got_all[mask][ra.AVG_REC].iloc[0]
    assert np.isclose(got, want), (got, want)
    assert not np.isclose(got, months[months.MOB == 12]["Receivables"].iloc[0])
    print(f"\n  avg receivables at MOB 12 = mean of months 1-12 "
          f"({want:,.0f}), not the month-12 balance "
          f"({months[months.MOB == 12]['Receivables'].iloc[0]:,.0f})")

    print("\nCredit Karma / Jan-23 / $75 / 601-639 / line 300")
    sl = df[(df.Campaign == "Credit Karma") & (df.AnnualFee == "$75")
            & (df.VantageRange == "601-639") & (df.OriginalCreditLine == 300)
            & (df.Vintage == "Jan-23")]
    for _i, r in sl.sort_values("MOB").iterrows():
        print(f"  {r[ra.YEAR]} (MOB {r['MOB']:>2})  boards {r[ra.BOARDS]:>4,.0f}"
              f"   unit C/O {r[ra.UNIT_RATE]:>7.2%}"
              f"   $ C/O {r[ra.DOLLAR_RATE]:>7.2%}"
              f"   ROA {r[ra.ROA]:>8.2%}")

    # a file that already carries the average is taken at face value
    pre = ra.add_avg_receivables(raw2, already_average=True, report=[])
    assert (pre[ra.AVG_REC] == pd.to_numeric(pre["Receivables"])).all()

    print("\nall assertions passed")


if __name__ == "__main__":
    main()
