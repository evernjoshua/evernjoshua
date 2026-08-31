# Segment heat map - roll-up mapping

`02_heatmap_7.ipynb` is `02_heatmap_6.ipynb` with the roll-up tab names wired in.

| segment tabs (`<=600`, `601-639`, `640+`) | roll-up tab |
| --- | --- |
| `Credit Karma $95` | `Credit Karma $95_ALL` |
| `CK Wander $95` | `Credit Karma WANDER_ALL` |
| `EXPX Wander $95` | `EXPERIAN WANDER_ALL` |
| `Google $75` | `Google PQ Paid Search_ALL` |
| `CSOX $75` | `Credit Sesame $75_ALL` |

Four of the five roll-up tabs are named nothing like their segments, so the old
rule of family + `_ALL` could not find them. They now live in `ROLLUP_SHEETS` in
the settings cell; add a line there for any future family that does not follow
the plain `_ALL` rule.

Also changed:

- `601-639` added to `BANDS`.
- The space before a band is now optional, so `Credit Karma $95640+` splits into
  family and band exactly like `Credit Karma $95 640+` does.
- `ROLLUP_SHEETS` reads in reverse too: an `_ALL` tab found in the main workbook
  is matched back to its family, so `Credit Karma WANDER_ALL` sits under the
  `CK Wander $95` segments instead of drifting off as its own family, and is
  never pulled a second time from the roll-up workbook.
- The placement report names the tab it looked for, so a miss says which
  spelling to fix.
