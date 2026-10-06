# Vintage workbook compare

Cell-by-cell **value** comparison of `Digital Vantage.xlsb` (base) vs `Digital by Vantage WIP.xlsb` (WIP).

- Only sheets `VintageSummary`, `Vintage1` … `Vintage24` are read; all other sheets, charts and formulas are ignored (cached values only).
- Columns compared: `B:Z` on VintageSummary and Vintage1, `B:Y` on Vintage2–Vintage24.
- Column A and rows 1–13 are copied as is; rows 14+ show `WIP - Base` (text cells show `Base -> WIP` when they differ).

```bash
pip install pyxlsb openpyxl
python compare_vintage.py "Digital Vantage.xlsb" "Digital by Vantage WIP.xlsb" -o vintage_comparison.xlsx
```

Output workbook: `Summary`, `Differences` (every differing cell), and one tab per sheet with deltas (differences highlighted red).
