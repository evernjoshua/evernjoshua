# Segment heat map

`02_heatmap_19.ipynb` is the current notebook. Only the settings cell is meant to be edited.

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

## Which tabs come in

The sweep runs from the tab after `Secured Card<=600` through `CSOX $75640+`, the last
segment tab. The families that sit before that range are named one by one in
`EXTRA_SEGMENTS` and read exactly as spelled; nothing else from before `Secured Card<=600`
is picked up. `NameManager` and `Sheet1`, which follow the last segment tab, are in
`SKIP_SHEETS`.

## Metrics

The volume line, B6, is labelled **Booked Accts**, and the tile above the table is
**Booked accounts**. Right after its variance sits **Share of Booked**: the row's booked
accounts over its roll-up's, so a family's segments add to 100% and the roll-up row reads
100%. A family with no roll-up tab is divided by the sum of its own segments; the
campaign-total rows are divided by the last of them, the Campaign Total row.

## Column names

Every heading is a constant at the top of the settings cell, so renaming one is a single
edit: `VOLUME`, `SHARE`, `CPA`, `ACL`, `U1`-`U3` (unit C/O), `D1`-`D3` (dollar C/O),
`R1`-`R3` (ROA). Nothing downstream repeats a heading as a literal.

## Actuals

Point `ACTUALS_FILE` at the actuals table (.csv, .xlsx or .xlsm) and a **second pair of
outputs** is written beside the forecast-only ones:

| | forecast only | with actuals |
| --- | --- | --- |
| page | `segment_heatmap.html` | `segment_heatmap_actuals.html` |
| to publish | `segment_heatmap_artifact.html` | `segment_heatmap_actuals_artifact.html` |
| workbook | `segment_heatmap.xlsx` | `segment_heatmap_actuals.xlsx` |

Every metric group gains an **Actual** column after its variance. Actuals join at
**roll-up level only** - a row of the actuals counts when `Branding` is `all` and `Fee` is
not, and its name is segment, fee, then branding with a `_` before the branding, which is
the roll-up tab exactly: `Credit Karma` + `$95` + `_` + `ALL`. Tabs with no fee in the
name, like `Google PQ Paid Search_ALL`, match the no-fee pattern. `ACTUALS_ALIASES` fixes
any that still disagree.

`ACTUALS_MAP` says which actuals column and which MOB stands behind each metric - Yr 1 is
MOB 12, Yr 2 MOB 24, Yr 3 MOB 36. `CumUnitRate` feeds the unit losses, `CumNetDollar` the
dollar losses, `CumulativeROA` the ROA, `Boards` the booked accounts and
`Avg_InitialLinePerBooked` the credit line. CPA has no actual.

**Which vintage.** `ACTUALS_VINTAGE = "latest"` takes the newest vintage that has actually
*reached* that MOB, so Yr 3 comes from a three-year-old vintage rather than the newest one,
which cannot have a Yr 3 number yet. `ACTUALS_REQUIRE_SEASONED` throws out any vintage that
cannot have got there, whatever the file claims. `median`, `mean` and `max` are the other
choices.

**The spread.** The hover summarises **every seasoned vintage carrying data at that MOB** -
all the MOB 12 vintages behind a Yr 1 figure, all the MOB 24 ones behind Yr 2. That is the
population the forecast is being judged against, so nothing is left out of it.
`ACTUALS_SPREAD_N = 0` means all; set a number to look at only that many of the most recent.

**Reading it.** The Actual cell is shaded by the forecast against it, the opposite way
round to the metric itself: **red where the forecast is optimistic** - a loss below the
actual, a return above it - and green where it is conservative. A column of red in the loss
groups means the losses are being understated. Hover a cell (or read the cell note in
Excel) for the vintage it came from, and the median, mean and range across the last
`ACTUALS_SPREAD_N` seasoned vintages.

## The boxes

`TILES` names the boxes above the table and the metric each one reads:
Booked accounts, Yr. 1 Unit C/O, 3 Yr. Cuml. ROA Annualized, CPA, Avg. Credit Line.
`SUMMARY_EXTRA_TILES` holds boxes that are **not** columns in the heat map - give one the
cell it sits in on `SUMMARY_SHEET` and it appears. `3 Yr. Cuml. PTI per Board` is there
waiting for its cell. No box prints where its number came from.

A box only renders when its current-month value reads as a number. A box that never shows
up means that cell came back empty on the summary tab.

## Row order

Families are grouped by annual fee, in `FEE_ORDER`: **$75, then $39, then $0, then $95**,
then the campaign totals, then any rows the volume floor excluded. The $0 slot is where the
roll-up-only rows land.

Inside a fee, `BRAND_ORDER` sets the sequence:

> Credit Karma, Experian, MoneyLion, Credit Sesame, Google, AMEX DCO, MoneyLion DCO,
> Creditcards.com, Organic

A brand with no sheet at that fee is skipped. `BRAND_ALIASES` maps how the tabs spell each
one - `CK` is Credit Karma, `EXPX` is Experian, `CSOX` is Credit Sesame - and the longest
match wins, so `MoneyLion DCO` is never mistaken for `MoneyLion`. Two families of the same
brand and fee keep tab order, and each roll-up row stays with its own family.

## Campaign totals

Written underneath the heat map, on their own colour scale (`CAMPAIGN_TOTALS`):

| row | tab |
| --- | --- |
| `Vantage <=600` | `<=600` |
| `Vantage 601-639` | `601-639` |
| `Vantage 640+` | `640+` |
| `Omni` | `Omni_ALL` |
| `Campaign Total` | `Digital_ALL` |

## Version history

### v19

- The spread in the hover now covers **every** seasoned vintage with data at that MOB,
  not the last eight. `ACTUALS_SPREAD_N = 0` is the new default and means all of them.

### v18

- The three ROA metrics read `H22`, `I22`, `J22`. They were on `H22`, `I23`, `J23`,
  so the 2 Yr. and 3 Yr. ROA columns were reading an empty row - which is also why the
  3 Yr. ROA box never appeared. Each group now sits on one row: unit C/O on 11, dollar
  C/O on 12, ROA on 22.

### v17

- Column headings moved into constants and renamed: Yr. 1 Unit C/O, 2 Yr. Cuml. Unit
  C/O, 3 Yr. Cuml. Unit C/O, Yr. 1-3 $ C/O, Yr. 1 Expected ROA, 2 and 3 Yr. Expected
  Cuml. ROA Annl.
- **Fixed** the hover behind each Actual: the vintage span it printed came from every
  seasoned vintage, while the median, mean and range came from the last
  `ACTUALS_SPREAD_N` - so the span was wider than the figures it claimed to describe.
  Both now come from the same window, and it says how many older vintages were left out.
- **Fixed** the same hover printing raw values (`0.1195`) against a cell showing `11.95%`.
  The stats now use the column's own format.

### v16

- Actuals. `ACTUALS_FILE` and the settings around it add an Actual column to every
  metric group and write a second pair of outputs; without the file nothing changes.
- The Actual column is shaded by forecast-minus-actual, so optimistic reads red, and
  the vintage and its spread sit in the hover and in the Excel cell note.
- Vintage choice is by maturity, not recency, and unseasoned vintages are ignored.

### v15

- `TILES` and `SUMMARY_EXTRA_TILES` make the boxes configurable. Yr. 1 Unit C/O and
  3 Yr. Cuml. ROA Annualized carry those names, and 3 Yr. Cuml. PTI per Board is
  wired up pending its cell address.
- The boxes no longer print "from Digital_ALL" underneath.
- Share of Booked is blank on the row that IS the denominator - every roll-up row and
  the Campaign Total row - instead of printing 100%.

### v14

- `BRAND_ORDER` sequences the families inside each fee, with `BRAND_ALIASES` translating
  the tab spellings. Missing brands are skipped rather than leaving a gap.

### v13

- "Volume" is now `VOLUME = "Booked Accts"`, and the first summary tile reads
  "Booked accounts".
- New `Share of Booked` metric straight after it - current, prior and the variance in
  percentage points. It has no cell of its own; it is computed once the roll-up rows
  are known.
- The HTML page drops the Comments column. Anything a row has to say - so far, only the
  excluded rows - is printed beside its name instead. Excel and the notebook preview
  keep the column.

### v12

- Rows are grouped by annual fee - `FEE_ORDER = ["$75", "$39", "$0", "$95"]` - with the
  campaign totals after them.
- A tab under `MIN_VOLUME` (1) in BOTH months is kept out of the heat map, and listed
  below everything else with no figures and a Comments note saying it had zero in both
  months. `SHOW_EXCLUDED = False` drops the listing too.
- The Comments column is now written from the row itself, so any row can carry a note.
- The HTML page loses its explanatory prose: the summary line under the title and the
  whole "Reading the shading" / "Where each number comes from" footer.

### v11

- Range names corrected against the real workbook: the tab is `Secured Card<=600` with
  no space, and there is no `Organic Omni $0_ALL` in the main workbook - the last
  segment tab is `CSOX $75640+`, with `NameManager` and `Sheet1` after it.
- `MoneyLion DCO $75 <=600` added to `EXTRA_SEGMENTS`; it does sit before the range.
- `EXTRA_SEGMENTS` reordered to match the workbook's own tab order.
- No `BrightMoney` tab exists in the workbook, so that entry is commented out.
- `sheet_span` now matches tab names ignoring spacing as well as case, so
  `Secured Card <=600` finds `Secured Card<=600`.

### v10

- The sweep is back to starting after `Secured Card <=600`. v8 had widened it to the
  whole workbook, which dragged in tabs that are not wanted.
- `EXTRA_SEGMENTS` names the tabs from before that range that ARE wanted - the $39
  products, Creditcards.com, and the Organic and CSOX $95/Wander families - read tab by
  tab and written above the swept rows, with their roll-up rows placed as usual.

### v9

- File names follow the house convention - `09'26 P&L Forecast - All.xlsm` and
  `09'26 P&L Forecast - Rollup.xlsx` - built from the two months. `FOLDER_PATTERN`
  puts each month in its own folder, and four commented lines in the settings cell
  name the files outright when a month is spelled some other way.
- The campaign-total block above, underneath the table in the notebook preview, the
  Excel file and the HTML page.
- Segments, roll-ups and campaign totals now get three separate colour scales instead
  of two, since a campaign total restates the whole book.

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
