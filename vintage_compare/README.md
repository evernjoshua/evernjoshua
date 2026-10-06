# Vintage workbook compare

Cell-by-cell **value** comparison of `Digital Vantage.xlsb` (original) vs `Digital by Vantage WIP.xlsb` (WIP).

- Only sheets `Vintage1` … `Vintage24` are read; all other sheets, charts and formulas are ignored (cached values only).
- Columns compared: `B:Z` on Vintage1, `B:Y` on Vintage2–Vintage24.
- **Row offset:** WIP has an extra row inserted, so original row 9 is compared with WIP row 10, 10 with 11, and so on. Rows 1–8 are skipped; WIP row 9 (the new row) is not compared.
- Report column A = attribute from the original row, column B = attribute from the paired WIP row (side by side); a mismatch is flagged to catch misaligned rows. Source columns B..Z appear one column to the right in the report (row 8 shows the source column letter).
- Original rows 9–13 are copied as is; rows 14+ show `WIP - Original` rounded to 3 decimals (rounds to 0.000 = match) (text cells show `Original -> WIP` when they differ).

```bash
pip install pyxlsb openpyxl
python compare_vintage.py "Digital Vantage.xlsb" "Digital by Vantage WIP.xlsb" -o vintage_comparison.xlsx
```

Optional: `--start-row 9 --offset 1 --header-last-row 13 --decimals 3`.

Output workbook: `Summary`, `Differences` (every differing cell with original and WIP cell addresses), and one tab per sheet laid out on the original row numbers with a `WIP row` column; differences highlighted red.
