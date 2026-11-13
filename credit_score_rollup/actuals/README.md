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
- `Cumul. Unit Charge-Off Rate` - cumulative `ChargeOffIndicator` / active accounts (`ActiveAccountIndicator`). The denominator moves with MOB, so the rate rises on both a bigger numerator and a shrinking book. Pass `--unit-co-denominator boards_net_unwind` for the other reading: booked accounts less unwinds through MOB 4, held constant across MOB.

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
