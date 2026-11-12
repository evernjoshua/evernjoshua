# Getting the actuals out of Snowflake

Three files. The query shapes the data the way the heat map reads it, the runner
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
