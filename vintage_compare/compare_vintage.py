"""
Cell-by-cell value comparison of two .xlsb workbooks.

Compares ONLY these sheets (every other sheet is never opened):
    VintageSummary, Vintage1, Vintage2, ... Vintage24

Rules
-----
* Values only: .xlsb stores the last calculated value of every cell, and
  that is what is read. Formulas and charts are ignored.
* Column A is copied as is (it is the row's attribute label).
* Rows 1-13 are copied as is (header block).
* Rows 14+ in the compared columns show the delta:
      numbers      -> WIP - Base
      text/blank   -> blank if equal, otherwise "Base -> WIP"
* Compared columns: B..Z on VintageSummary and Vintage1,
                    B..Y on Vintage2..Vintage24 (one less column).

Output: an .xlsx report with
    * "Summary"      - one row per sheet with the number of differences
    * "Differences"  - every differing cell (sheet, cell, attribute, base, wip, delta)
    * one tab per compared sheet, laid out like the source with deltas

Usage
-----
    pip install pyxlsb openpyxl
    python compare_vintage.py "Digital Vantage.xlsb" "Digital by Vantage WIP.xlsb"
    python compare_vintage.py base.xlsb wip.xlsb -o my_report.xlsx --tolerance 0.0001
"""

import argparse
import sys
from numbers import Number

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from pyxlsb import open_workbook

HEADER_ROWS = 13          # rows 1..13 are printed as is
FIRST_COL = 2             # column B
FULL_LAST_COL = 26        # column Z
SHORT_LAST_COL = 25       # column Y (Vintage2..Vintage24)

SHEETS = ["VintageSummary"] + [f"Vintage{i}" for i in range(1, 25)]

DIFF_FILL = PatternFill("solid", fgColor="FFC7CE")
MISSING_FILL = PatternFill("solid", fgColor="FFEB9C")
BOLD = Font(bold=True)


def last_col_for(sheet_name):
    if sheet_name in ("VintageSummary", "Vintage1"):
        return FULL_LAST_COL
    return SHORT_LAST_COL


def read_sheet(path, sheet_name, last_col):
    """Return {(row, col): value} (1-based) for columns A..last_col, or None
    if the sheet does not exist. Only the requested sheet is read."""
    with open_workbook(path) as wb:
        if sheet_name not in wb.sheets:
            return None
        cells = {}
        with wb.get_sheet(sheet_name) as sh:
            for row in sh.rows(sparse=True):
                for c in row:
                    col = c.c + 1
                    if col > last_col or c.v is None:
                        continue
                    v = c.v
                    if isinstance(v, str) and v.strip() == "":
                        continue
                    cells[(c.r + 1, col)] = v
        return cells


def is_num(v):
    return isinstance(v, Number) and not isinstance(v, bool)


def compare_values(base, wip, tolerance):
    """Return (is_different, delta_to_display)."""
    if is_num(base) or is_num(wip):
        if (is_num(base) or base is None) and (is_num(wip) or wip is None):
            delta = (wip or 0) - (base or 0)
            if abs(delta) <= tolerance:
                return False, 0
            return True, delta
        # number vs text
        return True, f"{base!r} -> {wip!r}"
    if base == wip:
        return False, None
    return True, f"{'' if base is None else base} -> {'' if wip is None else wip}"


def compare_sheet(sheet_name, base_cells, wip_cells, tolerance):
    last_col = last_col_for(sheet_name)
    max_row = max([r for r, _ in base_cells] + [r for r, _ in wip_cells] + [HEADER_ROWS])

    grid = {}          # (row, col) -> value to write in the report tab
    flagged = set()    # cells to highlight
    diffs = []

    for r in range(1, max_row + 1):
        label = base_cells.get((r, 1), wip_cells.get((r, 1)))
        grid[(r, 1)] = label
        if base_cells.get((r, 1)) != wip_cells.get((r, 1)):
            flagged.add((r, 1))
            diffs.append((sheet_name, f"A{r}", label, base_cells.get((r, 1)),
                          wip_cells.get((r, 1)), "label differs"))

        for c in range(FIRST_COL, last_col + 1):
            b = base_cells.get((r, c))
            w = wip_cells.get((r, c))
            if r <= HEADER_ROWS:
                grid[(r, c)] = b if b is not None else w
                if b != w:
                    flagged.add((r, c))
                    diffs.append((sheet_name, f"{get_column_letter(c)}{r}", label,
                                  b, w, "header differs"))
                continue
            different, delta = compare_values(b, w, tolerance)
            grid[(r, c)] = delta
            if different:
                flagged.add((r, c))
                diffs.append((sheet_name, f"{get_column_letter(c)}{r}", label, b, w, delta))

    return grid, flagged, diffs, max_row, last_col


def write_sheet_tab(ws, grid, flagged, max_row, last_col):
    for (r, c), v in grid.items():
        if v is None:
            continue
        cell = ws.cell(row=r, column=c, value=v)
        if r <= HEADER_ROWS or c == 1:
            cell.font = BOLD
        if (r, c) in flagged:
            cell.fill = DIFF_FILL
    ws.freeze_panes = ws.cell(row=HEADER_ROWS + 1, column=2)
    ws.column_dimensions["A"].width = 40
    for c in range(FIRST_COL, last_col + 1):
        ws.column_dimensions[get_column_letter(c)].width = 14


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("base", nargs="?", default="Digital Vantage.xlsb")
    p.add_argument("wip", nargs="?", default="Digital by Vantage WIP.xlsb")
    p.add_argument("-o", "--output", default="vintage_comparison.xlsx")
    p.add_argument("--tolerance", type=float, default=1e-9,
                   help="numeric differences with abs value <= this are treated as equal")
    args = p.parse_args()

    out = Workbook()
    summary = out.active
    summary.title = "Summary"
    summary.append(["Sheet", "Columns compared", "Status", "Differences"])
    details = out.create_sheet("Differences")
    details.append(["Sheet", "Cell", "Attribute (col A)", "Base", "WIP", "Delta (WIP - Base)"])
    for ws in (summary, details):
        for cell in ws[1]:
            cell.font = BOLD

    total = 0
    print(f"Base: {args.base}\nWIP : {args.wip}\n")
    for name in SHEETS:
        last_col = last_col_for(name)
        cols = f"B:{get_column_letter(last_col)}"
        base_cells = read_sheet(args.base, name, last_col)
        wip_cells = read_sheet(args.wip, name, last_col)

        if base_cells is None or wip_cells is None:
            where = " and ".join(n for n, d in (("Base", base_cells), ("WIP", wip_cells)) if d is None)
            status = f"missing in {where}"
            summary.append([name, cols, status, None])
            for cell in summary[summary.max_row]:
                cell.fill = MISSING_FILL
            print(f"{name:<16} {status}")
            continue

        grid, flagged, diffs, max_row, last_col = compare_sheet(
            name, base_cells, wip_cells, args.tolerance)
        write_sheet_tab(out.create_sheet(name), grid, flagged, max_row, last_col)
        for d in diffs:
            details.append(list(d))
        total += len(diffs)
        status = "MATCH" if not diffs else "DIFFERENT"
        summary.append([name, cols, status, len(diffs)])
        if diffs:
            for cell in summary[summary.max_row]:
                cell.fill = DIFF_FILL
        print(f"{name:<16} {status:<10} {len(diffs)} difference(s)")

    for ws, widths in ((summary, [18, 18, 22, 14]), (details, [16, 8, 40, 18, 18, 22])):
        for i, w in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = w
    details.freeze_panes = "A2"

    out.save(args.output)
    print(f"\nTotal differences: {total}\nReport written to {args.output}")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
