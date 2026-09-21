"""
Build the Finance Impact notes workbook by diffing the current month's P&L
forecast against the prior month's, sheet by sheet.

For every product tab between START_SHEET and END_SHEET the script pulls the
metrics listed in METRICS for Yr 1 / Yr 2 / Yr 3 (columns H / I / J) out of both
workbooks and writes the signed change (current - prior) to the output.
"""

import re
import os
from openpyxl import load_workbook, Workbook
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
from openpyxl.utils import get_column_letter

# ========== CONFIGURATION ==========
curr = r"\\fnbm.corp\share\Risk\Portfolio Growth\Personal Folders\Lucas Lin\Digital\PAF\2026\10'26\10'26 P&L Forecast - All.xlsm"
prev = r"\\fnbm.corp\share\Risk\Portfolio Growth\Personal Folders\Lucas Lin\Digital\PAF\2026\09'26\09'26 P&L Forecast - All.xlsm"
OUTPUT_PATH = r"\\fnbm.corp\share\Risk\Portfolio Growth\Personal Folders\Lucas Lin\Digital\PAF\2026\10'26\ROA Decomp & Finance Impact Notes\finance_impact.xlsx"

START_SHEET = "MoneyLion $75 601-6"
END_SHEET = "Organic $95 <=600"
SUMMARY_SHEET = "summary"

DELTA_FORMAT = '+0.00;-0.00;0.00'   # shows + for positive, - for negative, 0.00 for zero

# Metrics pulled from each product tab.
#   row            -> the worksheet row the metric lives on
#   scale          -> multiplier applied to the delta. Leave at 1 to keep the raw
#                     cell units. Set to 100 if the source cells are stored as
#                     true percentages (0.0525) and you want percentage-point
#                     deltas (5.25) in the output.
#   number_format  -> Excel format applied to that metric's delta columns
METRICS = [
    {"label": "Unit C/O",            "row": 11, "scale": 1, "number_format": DELTA_FORMAT},
    {"label": "$ C/O",               "row": 12, "scale": 1, "number_format": DELTA_FORMAT},
    {"label": "Gross Revenue",       "row": 15, "scale": 1, "number_format": DELTA_FORMAT},
    {"label": "Provision",           "row": 16, "scale": 1, "number_format": DELTA_FORMAT},
    {"label": "Total Expenses",      "row": 18, "scale": 1, "number_format": DELTA_FORMAT},
    {"label": "Cuml ROA Annualized", "row": 22, "scale": 1, "number_format": DELTA_FORMAT},
]

YEAR_COLUMNS = ["H", "I", "J"]                      # Yr 1, Yr 2, Yr 3 on the source tabs
YEAR_LABELS = ["Yr 1", "2Yr Cuml", "3Yr Cuml"]      # sub-header shown under each metric

ID_HEADERS = ["Product", "First Word", "Vantage", "Credit Line"]
NOTE_HEADERS = ["Credit Line Notes", "Product Notes"]

FIRST_DELTA_COL = len(ID_HEADERS) + 1
DELTA_COL_COUNT = len(METRICS) * len(YEAR_COLUMNS)
LAST_DELTA_COL = FIRST_DELTA_COL + DELTA_COL_COUNT - 1
FIRST_NOTE_COL = LAST_DELTA_COL + 1
TOTAL_COLS = LAST_DELTA_COL + len(NOTE_HEADERS)

HEADER_ROWS = 2          # row 1 = metric group, row 2 = year
DATA_START_ROW = HEADER_ROWS + 1
# ===================================

# ---------- Custom styles ----------
header_font = Font(bold=True, color="FFFFFF")
header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
group_fill = PatternFill(start_color="2F5597", end_color="2F5597", fill_type="solid")
header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
data_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
notes_alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)

thin_border = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)
group_border = Border(
    left=Side(style="medium"),
    right=Side(style="medium"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)

alternating_fills = [
    PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid"),   # white
    PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid"),   # light grey
]
# -----------------------------------


def parse_sheet_name(name):
    """
    Parse sheet name like:
      'MoneyLion $75 601-6'
      'Some Product $95_$400 <=600'
    Returns (first_word, product, vantage, credit_line)
    - first_word = everything before the first '$' (trimmed)
    - product = first dollar amount (including '$')
    - credit_line = second dollar amount (including '$')
    - vantage = last word (text after last space)
    """
    name = name.strip()
    if '$' in name:
        first_word = name.split('$')[0].strip()
    else:
        first_word = name   # fallback: whole name if no dollar sign

    dollar_matches = re.findall(r"\$\d[\d,]*(?:\.\d+)?", name)
    product = dollar_matches[0] if len(dollar_matches) >= 1 else ""
    credit_line = dollar_matches[1] if len(dollar_matches) >= 2 else ""
    vantage = name.rsplit(" ", 1)[-1] if " " in name else ""
    return first_word, product, vantage, credit_line


def to_number(value):
    """Convert a cell value to float if possible."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).replace("$", "").replace(",", "").strip()
    if s.endswith("%"):
        s = s[:-1].strip()
    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1]
    try:
        return -float(s) if negative else float(s)
    except ValueError:
        return None


def compare_values(curr_val, prev_val, scale=1):
    """
    Return signed difference (curr - prev) * scale, rounded to 4 decimals.
    Returns None if either value is missing.
    """
    a = to_number(curr_val)
    b = to_number(prev_val)
    if a is None or b is None:
        return None
    return round((a - b) * scale, 4)


def collect_deltas(curr_sheet, prev_sheet):
    """Return the flat list of deltas for one product tab, metric by metric."""
    deltas = []
    for metric in METRICS:
        for col in YEAR_COLUMNS:
            cell_ref = f"{col}{metric['row']}"
            if prev_sheet is None:
                deltas.append(None)
                continue
            deltas.append(
                compare_values(
                    curr_sheet[cell_ref].value,
                    prev_sheet[cell_ref].value,
                    metric.get("scale", 1),
                )
            )
    return deltas


def write_headers(ws):
    """Two-row header: metric group on row 1, Yr 1 / 2Yr / 3Yr on row 2."""
    for idx, title in enumerate(ID_HEADERS, start=1):
        ws.cell(row=1, column=idx, value=title)
        ws.merge_cells(start_row=1, start_column=idx, end_row=HEADER_ROWS, end_column=idx)

    col = FIRST_DELTA_COL
    for metric in METRICS:
        ws.cell(row=1, column=col, value=metric["label"])
        ws.merge_cells(start_row=1, start_column=col,
                       end_row=1, end_column=col + len(YEAR_COLUMNS) - 1)
        for offset, year_label in enumerate(YEAR_LABELS):
            ws.cell(row=2, column=col + offset, value=year_label)
        col += len(YEAR_COLUMNS)

    for offset, title in enumerate(NOTE_HEADERS):
        idx = FIRST_NOTE_COL + offset
        ws.cell(row=1, column=idx, value=title)
        ws.merge_cells(start_row=1, start_column=idx, end_row=HEADER_ROWS, end_column=idx)

    for row_idx in range(1, HEADER_ROWS + 1):
        for col_idx in range(1, TOTAL_COLS + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.font = header_font
            cell.fill = group_fill if row_idx == 1 else header_fill
            cell.alignment = header_alignment
            cell.border = thin_border


def metric_boundary_columns():
    """Columns that start a new metric block, so they can get a heavier left edge."""
    boundaries = set()
    col = FIRST_DELTA_COL
    for _ in METRICS:
        boundaries.add(col)
        col += len(YEAR_COLUMNS)
    boundaries.add(FIRST_NOTE_COL)
    return boundaries


def apply_data_styles(ws, last_row):
    """Borders, alignment and per-metric number formats for every data row."""
    boundaries = metric_boundary_columns()
    metric_by_col = {}
    col = FIRST_DELTA_COL
    for metric in METRICS:
        for offset in range(len(YEAR_COLUMNS)):
            metric_by_col[col + offset] = metric
        col += len(YEAR_COLUMNS)

    for row_idx in range(DATA_START_ROW, last_row + 1):
        for col_idx in range(1, TOTAL_COLS + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.border = group_border if col_idx in boundaries else thin_border
            if col_idx >= FIRST_NOTE_COL:
                cell.alignment = notes_alignment
            else:
                cell.alignment = data_alignment
            if col_idx in metric_by_col:
                cell.number_format = metric_by_col[col_idx]["number_format"]


def set_column_widths(ws):
    widths = {1: 15, 2: 20, 3: 12, 4: 12}
    for col_idx in range(FIRST_DELTA_COL, LAST_DELTA_COL + 1):
        widths[col_idx] = 12
    for col_idx in range(FIRST_NOTE_COL, TOTAL_COLS + 1):
        widths[col_idx] = 28
    for col_idx, width in widths.items():
        ws.column_dimensions[get_column_letter(col_idx)].width = width
    ws.row_dimensions[1].height = 28
    ws.row_dimensions[2].height = 22


def main():
    # Check files exist
    if not os.path.exists(curr):
        raise FileNotFoundError(f"Could not find {curr}")
    if not os.path.exists(prev):
        raise FileNotFoundError(f"Could not find {prev}")

    print("Loading workbooks...")
    curr_wb = load_workbook(curr, data_only=True)
    prev_wb = load_workbook(prev, data_only=True)

    # Select sheet names between START_SHEET and END_SHEET inclusive
    all_sheet_names = curr_wb.sheetnames
    if START_SHEET in all_sheet_names and END_SHEET in all_sheet_names:
        start_idx = all_sheet_names.index(START_SHEET)
        end_idx = all_sheet_names.index(END_SHEET)
        if start_idx > end_idx:
            start_idx, end_idx = end_idx, start_idx
        selected_sheet_names = all_sheet_names[start_idx:end_idx + 1]
    else:
        print("Warning: Start or end sheet not found. Processing all sheet names except summary.")
        selected_sheet_names = [n for n in all_sheet_names if n != SUMMARY_SHEET]

    rows_with_second_dollar = []
    rows_without_second_dollar = []

    for sheet_name in selected_sheet_names:
        first_word, product, vantage, credit_line = parse_sheet_name(sheet_name)
        curr_sheet = curr_wb[sheet_name]
        prev_sheet = prev_wb[sheet_name] if sheet_name in prev_wb.sheetnames else None
        if prev_sheet is None:
            print(f"  Note: '{sheet_name}' is missing from the prior workbook - deltas left blank.")

        comparisons = collect_deltas(curr_sheet, prev_sheet)

        row = [product, first_word, vantage, credit_line] + comparisons + [None] * len(NOTE_HEADERS)
        if credit_line:
            rows_with_second_dollar.append(row)
        else:
            rows_without_second_dollar.append(row)

    # Create output workbook
    output_wb = Workbook()
    ws_main = output_wb.active
    ws_main.title = "With Second Dollar"
    ws_no_second = output_wb.create_sheet("No Second Dollar")

    write_headers(ws_main)
    write_headers(ws_no_second)

    # ---- "No Second Dollar" sheet (flat, no merging) ----
    for offset, row_data in enumerate(rows_without_second_dollar):
        for col_idx, value in enumerate(row_data, start=1):
            ws_no_second.cell(row=DATA_START_ROW + offset, column=col_idx, value=value)

    # ---- "With Second Dollar" sheet with grouping/merging ----
    # Group rows by (Product, Vantage) preserving order of first appearance
    grouped = {}
    order = []
    for row in rows_with_second_dollar:
        key = (row[0], row[2])   # (Product, Vantage)
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(row)

    current_row = DATA_START_ROW
    group_index = 0
    for key in order:
        rows_in_group = grouped[key]
        num_rows = len(rows_in_group)

        for i, row_data in enumerate(rows_in_group):
            for col_idx, value in enumerate(row_data, start=1):
                ws_main.cell(row=current_row + i, column=col_idx, value=value)

        # Merge Product (column 1) and Vantage (column 3) across group rows
        if num_rows > 1:
            ws_main.merge_cells(start_row=current_row, start_column=1,
                                end_row=current_row + num_rows - 1, end_column=1)
            ws_main.merge_cells(start_row=current_row, start_column=3,
                                end_row=current_row + num_rows - 1, end_column=3)

        fill = alternating_fills[group_index % 2]
        for r in range(current_row, current_row + num_rows):
            for c in range(1, TOTAL_COLS + 1):
                ws_main.cell(row=r, column=c).fill = fill

        current_row += num_rows
        group_index += 1

    apply_data_styles(ws_main, current_row - 1)
    apply_data_styles(ws_no_second, DATA_START_ROW + len(rows_without_second_dollar) - 1)

    for ws in (ws_main, ws_no_second):
        set_column_widths(ws)
        ws.freeze_panes = f"{get_column_letter(FIRST_DELTA_COL)}{DATA_START_ROW}"

    output_wb.save(OUTPUT_PATH)

    print("Done!")
    print(f"  Metrics compared: {', '.join(m['label'] for m in METRICS)}")
    print(f"  Rows with second dollar amount: {len(rows_with_second_dollar)}")
    print(f"  Rows without second dollar amount: {len(rows_without_second_dollar)}")
    print(f"  Output saved to: {OUTPUT_PATH}")

    curr_wb.close()
    prev_wb.close()


if __name__ == "__main__":
    main()
