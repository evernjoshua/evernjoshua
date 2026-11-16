# Actuals for the segment heat map, built from the VCR CSV

No new SQL. These read the VCR extract you already have and add the columns the
spec document defines.

| file | what it is |
| --- | --- |
| `pnl_spec.py` | the spec document transcribed: every P&L line and the CSV column it reads |
| `build_pnl.py` | the two build stages, plus a CLI |
| `test_build_pnl.py` | runs every stage against a CSV shaped like the real extract |
| `../04_actuals_pnl.ipynb` | the same code as a self-contained notebook |

```
python3 build_pnl.py vcr_actuals.csv -o vcr_with_pnl.csv --cpa 185 --amex-share 0.62
python3 build_pnl.py vcr_actuals.csv --unit-co-denominator boards_net_unwind
python3 test_build_pnl.py
```

## What the extract looks like

`VCRData` already arrives aggregated - `NewAccounts` runs 1, 5, 219, 139, and
`ChargeOffIndicator` / `ActiveAccountIndicator` are counts of accounts. Three
things about it are easy to get wrong:

- `AccountNumber` holds text (*"First Account"*). It is a dimension, not an
  account id, so it is grouped on rather than counted.
- The score columns are **sums**: `ACE2Score` 190,594 sits beside
  `ACE2ScoreIndicator` 207, an average of 920.7. They are summed like any other
  measure and `Avg ACE2 Score` is derived from the pair.
- `NewAccounts` is read at the cohort's **first MOB**, not summed across MOB,
  so a repeated booking count cannot multiply the cohort.

Dates come as `31-Jan-23` and `Jan-23`, parsed by explicit format.

## Stage 0 - sum to cohort level

`aggregate_to_cohort` sums to one row per cohort x MOB. That is a no-op at the
grain the extract already has, and it collapses repeats if it is ever cut
differently. `audit_columns` reports what the spec reads, what it wants but the
file lacks, and what the file carries that nothing reads.

## What gets written

Only the columns the solution needs, in this order: the dimensions, then the
source columns the formulas read, then everything computed from them. The
extract carries ~59 columns no formula touches, some with numeric or date
headers, and writing them whole makes the header row unreadable in Excel.
`--derived-only` (or `keep_inputs=False`) drops the source columns too.

## Stage 1 - the monthly P&L

The thirteen revenue lines, then `Miscellaneous Fees/Income` as
`GrossRevenue` less those thirteen, which makes `Total Gross Revenues`
reconcile to `GrossRevenue` exactly. Then the provision, `Total Net Revenues`,
the six servicing lines, the other expenses, `Total Operating Expenses` and
`Pretax Income` = net revenues less operating expenses.

## Stage 2 - the cumulative measures

Each runs across MOB inside one vintage cohort:

- `Cumul. Pre-Tax Income` - running sum
- `Avg Total Gross Receivables - End of Period` - running mean of `EndingReceivable`
- `Cumul. Net Charge-Off Before Recoveries` - cumulative `ChargeOffPrincipalAmount` / that average
- `Cumul. ROA - Annualized` - (cumulative pretax income / that average) / MOB x 12
- `Cumul. Unit Charge-Off Rate` - the running count of accounts that have charged off (cumulative `ChargeOffIndicator`) over the count still active that month (`ActiveAccountIndicator`). Both are account counts after stage 0. The denominator shrinks as the book attrits, so the rate rises on both a bigger numerator and a smaller book. `Cumul. Charge-Off Accounts` and `Unit C/O Denominator` are written out alongside it so the division is visible. Pass `--unit-co-denominator boards_net_unwind` for the other reading: booked accounts less unwinds through MOB 4, constant across MOB.

MOB 12 / 24 / 36 are the heat map's Yr 1 / Yr 2 / Yr 3.

## Two gaps in the extract

The spec asks for both; the column list does not carry either, so both lines
read zero until you set them.

- **CPA** - `One Time - Marketing Expense (CPA)`. Pass `cpa=<column name>` or
  `cpa=<dollars per board>` (charged in the booking month).
- **amex_share** - the share in `2.03 x amex_share x booked accounts / 24`.
  Pass `amex_share=<fraction>`.

The extract also has no `NetRevenue` column, which is why net revenue is
computed as gross less provision rather than read.
