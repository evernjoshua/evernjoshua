# Segment heat map

`02_heatmap_8.ipynb` is the current notebook. Only the settings cell is meant to be edited.

## Roll-up tabs

| segment tabs | roll-up tab |
| --- | --- |
| `CSOX $39` | `Credit Sesame $39_ALL` |
| `AMEX DCO $39` | `AMEX DCO $39_ALL` |
| `BrightMoney $39` | `BrightMoney $39_ALL` |
| `Organic $39` | `ORGANIC $39_ALL` |
| `MoneyLion DCO $39` | `MoneyLion DCO $39_ALL` |
| `Creditcards.com $75` | `CREDITCARDS.COM_ALL` |
| `MoneyLion DCO $75` | `MoneyLion DCO $75_ALL` |
| `Google $75` | `Google PQ Paid Search_ALL` |
| `CSOX $75` | `Credit Sesame $75_ALL` |
| `Credit Karma $95` | `Credit Karma $95_ALL` |
| `CK Wander $95` | `Credit Karma WANDER_ALL` |
| `EXPX Wander $95` | `EXPERIAN WANDER_ALL` |
| `Organic $95` + `Organic Wander $95` | `ORGANIC X5 and Wander_ALL` |
| `CSOX $95` + `CSOX Wander $95` | `Credit Sesame X5 and Wander_ALL` |

Two families can name the same roll-up tab, and then one roll-up row is written after
the last tab of either family.

`Credit Karma $0_ALL`, `Experian $0_ALL`, `AMEX DCO $0_ALL`, `ORGANIC $0_ALL` and
`Organic Omni $0_ALL` have no segments behind them. They are listed in `ROLLUP_ONLY` and
written one after the other at the bottom, in that order.

## Version history

### v8

- **Whole workbook in range.** `START_SHEET` / `START_AFTER_SHEET` / `END_SHEET` all
  default to blank, which means first tab to last. The old range began after
  `Secured Card <=600`, which silently dropped every $39 product, Creditcards.com,
  MoneyLion DCO, and the Organic and Wander families - all of which sit before it.
- **The two months move on their own.** Sign-offs run a month ahead, so current is the
  month after today: run it in August 2026 and the columns read `Sep-2026` and
  `Aug-2026`, and the four workbook names are built from those months. Pin
  `CURRENT_MONTH` to override.
- **Column order and headings.** Each metric now reads current, prior, then `Variance`,
  and the two month columns are headed with the months themselves.
- **Empty rows drop out.** No volume in either month, no row. This runs before the
  roll-up lookup, so a cover sheet never asks for a roll-up tab that was never going
  to exist.
- **No direction triangles** in the HTML page. The signed number carries the direction;
  the sort arrows in the column headings are untouched.
- **Roll-up placement defaults to `bottom`.** Several families run 640+, 601-6, <=600 in
  tab order, and the old `band` setting would have put their roll-up row in the middle
  of the family.

### v7

- `ROLLUP_SHEETS` map, so a roll-up tab named nothing like its segments is still found.
- `601-639` added to `BANDS`; the space before a band is optional.
