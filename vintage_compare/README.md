# Vintage workbook compare

Cell-by-cell **value** comparison of `Digital Vantage.xlsb` (original) vs `Digital by Vantage WIP.xlsb` (WIP).

- Only sheets `Vintage1` … `Vintage24` are read; all other sheets, charts and formulas are ignored (cached values only).
- Sheet layout: column A = section notes, column B = attribute name, columns C:Z (Vintage1) / C:Y (Vintage2–24) = values.
- **Row alignment:** rows match one-to-one up to row 200. WIP row 201 is a new row and is skipped, so original row 201 is compared with WIP row 202, 202 with 203, and so on to the end. Change it with `--inserted-wip-rows` (e.g. `--inserted-wip-rows 201`, or several: `--inserted-wip-rows 9 201`).

Each sheet's report tab uses the original's row numbers and column letters:

| Part | Content |
|---|---|
| Rows 1–8 | copied as is from the original (not compared) |
| Column A | section notes, copied as is |
| Column B | attribute; red if the WIP attribute on the paired row differs |
| Rows 9–13 | values copied as is; red if WIP differs |
| Rows 14+ | `WIP - Original` rounded to 3 decimals (rounds to 0.000 = match); text shows `Original -> WIP` |
| After the data | `WIP row` number and `WIP attribute (if different)` |

```bash
pip install pyxlsb openpyxl
python compare_vintage.py "Digital Vantage.xlsb" "Digital by Vantage WIP.xlsb" -o vintage_comparison.xlsx
```

Optional: `--start-row 9 --inserted-wip-rows 201 --header-last-row 13 --decimals 3`.

Also in the report: `Summary` (differences per sheet) and `Differences` (every differing cell with original and WIP cell addresses, attribute, both values and the delta).
