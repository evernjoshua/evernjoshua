# Getting the actuals out of Snowflake

Built on the BAU VCR query, kept verbatim in `vcr_base.sql`.

| file | |
| --- | --- |
| `discover_dimensions.sql` | run first - the AcqSource / Branding / Fee values that actually exist |
| `vcr_base.sql` | the BAU VCR query, untouched, for reference |
| `vcr_actuals.sql` | the BAU query extended into the actuals the heat map reads |
| `export_actuals.py` | runs it, writes `actuals.csv` |
| `check_actuals.py` | says what the heat map will and will not find in that CSV |
| `actuals.sql` | the generic version, if you ever source actuals from somewhere else |

## What vcr_actuals.sql changes, and why

**It widens the reporting window** to 2023-01-01 .. 2026-10-31. The heat map wants
figures *cumulative* to MOB 12, 24 and 36, and a cumulative figure needs every month from
the account's first through its twelfth. The BAU window of 2026-01-01 .. 2026-09-30 is
nine months, so it would only catch whichever MOBs happened to land inside it - most
vintages would come out short or empty. This is not optional for cumulative figures.

**It cumulates the flows and not the stocks.** Charge-offs, revenue, expenses, fees and
cash flow happen *in* a month, so they are summed from MOB 1 to the MOB in question.
Receivables, active and inactive counts, buckets, reserves and credit line are balances,
so they are taken as at that MOB. Summing a balance across months would be meaningless.
64 columns are treated as flows and 35 as stocks; the split is at the top of the
generator that wrote the file.

**It collapses to roll-up grain** - `Branding` and `OriginalCreditLine` both `'All'` -
because that is the only grain the heat map joins on, and a single credit-line slice can
read 0% or 100% charge-off.

**Every VCR attribute and measure is carried through**, so the CSV is a superset of what
the heat map needs.

## Two things to do before it runs

1. **`name_map`** in `vcr_actuals.sql` - your `AcqSource` / `Branding` / `Fee` against
   the names the heat map expects. The right-hand side is pre-filled with all of them,
   generated from the notebook's own `ROLLUP_SHEETS`, `ROLLUP_ONLY` and
   `CAMPAIGN_TOTALS`. Run `discover_dimensions.sql` to see what to put on the left.
2. **The three rate definitions**, in the `rates` block near the end. Everything else is
   arithmetic on the BAU query's own columns, but the BAU query leaves pre-tax income to
   "existing calculation upstream in VCR", so `CumulativeROA`, `CumPTI` and `CumNetDollar`
   rest on a definition I had to write. Check it against the VCR's own. The components
   are all in the output, so a correction changes one expression and nothing else.

## The Vantage band rows

The query also emits a row per `VantageRange`, which is what the heat map's
`Vantage <=600`, `Vantage 601-639` and `Vantage 640+` rows need. Their tab names carry no
`_ALL`, so the key cannot be rebuilt from segment and fee - add this to the notebook:

```python
ACTUALS_ALIASES = {
    "<=600":   "<=600_All",
    "601-639": "601-639_All",
    "640+":    "640+_All",
}
```

## Three files. The query shapes the data the way the heat map reads it, the runner
writes the CSV, and the checker tells you whether the heat map will actually find
anything in it before you run the notebook.

```
# 1. fill in the two EDIT blocks in actuals.sql
# 2. export
export SNOWFLAKE_ACCOUNT=... SNOWFLAKE_USER=... SNOWFLAKE_WAREHOUSE=...
export SNOWFLAKE_PASSWORD=...            # or a key pair, or SSO - see the runner
python export_actuals.py                 # -> actuals.csv

# 3. check it before the notebook sees it
python check_actuals.py actuals.csv
```

## What the heat map needs

Actuals join at **roll-up level only**. A row counts when:

| | |
| --- | --- |
| `Branding` | `All` |
| `OriginalCreditLine` | `All` |
| `segment` + ` ` + `Fee` + `_` + `Branding` | rebuilds the roll-up tab name |
| `mob` | 12, 24 or 36 - years 1, 2 and 3 |

`Credit Karma` + `95` + `_` + `All` becomes `Credit Karma $95_ALL`. Matching ignores
case, spaces **and the dollar sign**, so write the fee as `95`, not `$95`. Where the tab
has no fee in its name, put `All` in `Fee` and the name becomes segment + `_All`, which is
how `Google PQ Paid Search_ALL` and `Digital_ALL` match.

The credit-line filter is not optional. Without it the per-line slices come along, and a
slice with a handful of accounts reads 0% or 100% charge-off - that is where a spread of
0 to 100 came from before.

## actuals.sql

Two blocks marked `EDIT`:

1. **SOURCE** - the vintage/MOB performance table the figures come from, and its column
   names. The metric columns keep their output names because the heat map reads them by
   name.
2. **name_map** - your campaign identifiers against the segment and fee the heat map
   expects. The right-hand side is pre-filled with all 29 names, generated from the
   notebook's `ROLLUP_SHEETS`, `ROLLUP_ONLY` and `CAMPAIGN_TOTALS`.

If your table is finer than roll-up grain you have to aggregate, and the footer of the
query spells out the one trap: **do not average the rates.** `CumUnitRate`,
`CumNetDollar` and `CumulativeROA` are ratios, so averaging across slices weights a
200-account slice like a 40,000-account one. Re-derive each from its own numerator and
denominator.

## check_actuals.py

Applies the notebook's own rules to the CSV and reports:

- how many rows survive the roll-up filter, and how many were dropped;
- which roll-up rows will find actuals, and which will not - separating the ones your
  query can fix from the ones that need an `ACTUALS_ALIASES` entry because their tab name
  cannot be rebuilt from segment and fee at all (`<=600`, `601-639`, `640+`);
- names in the file that the notebook does not list, which are usually the families swept
  out of the workbook and perfectly fine;
- MOB cover per roll-up, so a year that would come back blank says so;
- a scale check on the rates - if `CumUnitRate` arrives as `5.2` rather than `0.052` it
  tells you to set `ACTUALS_SCALE["CumUnitRate"] = 0.01`;
- the vintage range, and whether the vintages parse as dates, which the seasoning guard
  depends on.

## Credentials

Never in the files. The runner reads `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER` and the rest
from the environment, and takes a password, a key pair
(`SNOWFLAKE_PRIVATE_KEY_PATH`) or SSO (`SNOWFLAKE_AUTHENTICATOR=externalbrowser`).
