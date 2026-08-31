# Credit-band roll-ups

Stacks the three credit-band tabs of each campaign (`<=600`, `601-639`, `640+`)
into one combined `_ALL` tab in the same workbook.

| Source tabs | Roll-up tab |
| --- | --- |
| `Credit Karma $95<=600`, `Credit Karma $95601-639`, `Credit Karma $95640+` | `Credit Karma $95_ALL` |
| `CK Wander $95<=600`, `CK Wander $95601-639`, `CK Wander $95640+` | `Credit Karma WANDER_ALL` |
| `EXPX Wander $95<=600`, `EXPX Wander $95601-639`, `EXPX Wander $95640+` | `EXPERIAN WANDER_ALL` |
| `Google $75<=600`, `Google $75601-639`, `Google $75640+` | `Google PQ Paid Search_ALL` |
| `CSOX $75<=600`, `CSOX $75601-639`, `CSOX $75640+` | `Credit Sesame $75_ALL` |

## Use

```
pip install openpyxl
python rollup.py workbook.xlsx              # writes workbook.rollup.xlsx
python rollup.py workbook.xlsx -o out.xlsx
python rollup.py workbook.xlsx --in-place
python rollup.py workbook.xlsx --no-band-column
```

## Behaviour

- Sheet names match loosely — case, spaces, underscores, and hyphens are
  ignored, so `Credit Karma $95 <= 600` matches `Credit Karma $95<=600`.
- The header row is taken from the first band tab found; the other tabs
  contribute data rows only. A differing header is reported as a warning
  rather than dropped silently.
- Each row gets a `Credit Band` column naming the tab it came from
  (`--no-band-column` turns this off).
- Formula cells are stacked as their last-calculated values, since formulas
  would point at the wrong cells once the rows are restacked. Open and save
  the source workbook in Excel first if any cached values are stale.
- A missing band tab is reported and the remaining tabs still roll up. A group
  with no tabs present is skipped.
- Re-running replaces an existing `_ALL` tab, so it is safe to run repeatedly.

Sheet names live in `rollup_config.py`; edit `ROLLUPS` there to add a campaign.
