# Actuals for the segment heat map

`../05_actuals.ipynb` is self-contained - open it where the CSV is and run the
cells in order. `read_actuals.py` is the same code as a module, with
`test_read_actuals.py` exercising it against a synthetic file.

## The measures

| measure | how |
| --- | --- |
| Unit Charge-Off Rate | `net unit charge off / (new accounts - unwinds count)` |
| Dollar Charge-Off Rate | `net dollar / average gross receivables` |
| ROA | `(cf pretax minus cost of funds / average gross receivables) / MOB x 12` |

Only months on book 12, 24 and 36 are kept, as Yr 1, Yr 2 and Yr 3.

## The columns

`acquisition segment` carries Credit Karma, Experian and so on - it is what
matches a row to a workbook tab. `account`, `account number` and
`annual fee group` are ignored as instructed. Names are matched ignoring case,
spaces and punctuation, so `Net Unit Charge Off`, `net_unit_chargeoff` and
`NetUnitChargeOff` all resolve to the same column. Anything unrecognised goes
in `EXTRA_ALIASES` in the notebook's settings cell.

## Average gross receivables

An average **to date**, so it needs months 1-11 to produce the Yr 1 figure.
The notebook computes it before selecting the 12 / 24 / 36 rows for exactly
that reason - on the test data the difference is 147,319 against a month-12
balance of 140,482, and it lands in both the dollar rate and the ROA. If the
file already carries the average, set `RECEIVABLES_IS_AVERAGE = True`.

## Checking a file without sending it anywhere

`column_map(raw)` lists every column beside the name the code gave it, with a
`- MISSING -` row for anything the measures need and cannot find.
`dimension_values(df)` lists the distinct values of each cohort column, which
is how to check the acquisition segment and vantage range values against the
workbook's tab names. Both are cells 1 and 2 of the notebook.
