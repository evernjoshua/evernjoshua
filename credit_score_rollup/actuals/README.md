# Actuals for the segment heat map, built from the VCR CSV

No new SQL. These read the VCR extract you already have and add the columns the
spec document defines.

| file | what it is |
| --- | --- |
| `pnl_spec.py` | the spec document transcribed: every P&L line and the CSV column it reads |
| `build_pnl.py` | the two build stages, plus a CLI |
| `test_build_pnl.py` | runs both stages against a CSV carrying the spec's exact column list |
| `../04_actuals_pnl.ipynb` | the same code as a self-contained notebook |

```
python3 build_pnl.py vcr_actuals.csv -o vcr_with_pnl.csv --cpa 185 --amex-share 0.62
python3 build_pnl.py vcr_actuals.csv --unit-co-denominator boards_net_unwind
python3 test_build_pnl.py
```

## Stage 0 - sum to cohort level

The extract is one row per **account** per month: it carries `AccountNumber`,
and `ChargeOffIndicator` / `ActiveAccountIndicator` are 0/1 flags on a single
account. `aggregate_to_cohort` sums the rows to one per cohort x MOB, which
turns each flag into a count of accounts. Scores are averaged rather than
summed; an extract already at cohort grain passes through unchanged.

Skipping this is what makes the unit charge-off rate come out as 0% or 100% -
the denominator is 1.

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
