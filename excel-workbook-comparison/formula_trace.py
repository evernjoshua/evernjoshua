"""Parse an Excel formula, walk what it depends on, and re-evaluate it under scenarios.

The value comparison answers "this cell changed". To answer "and here is why, and what it did
to ROA", you have to read the *formula* and follow it down to the inputs that moved.

Three things live here:

  parse(text)                -> an AST for an Excel formula
  trace(book, sheet, cell)   -> the precedent tree, and the changed inputs inside it
  compile_scenario(...)      -> that tree flattened to "ROA as a function of the changed inputs",
                                so any subset of them can be switched old -> new and re-evaluated

That last part is the point. ROA is a ratio, so its drivers are *not* additive: the effect of two
changes together is not the sum of their separate effects. Re-evaluating the real formula under a
chosen subset is the only way to get that right.

Formulas are only available from .xlsx/.xlsm. pyxlsb and xlrd cannot see formula text, so a .xlsb
has to be saved as .xlsx before it can be traced.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string, get_column_letter

__all__ = [
    "FormulaError", "UnsupportedFormula", "parse", "evaluate", "Node",
    "Book", "load_book", "Cell", "Component", "Trace", "trace", "compile_scenario",
]


class FormulaError(ValueError):
    """The formula could not be parsed or evaluated."""


class UnsupportedFormula(FormulaError):
    """The formula uses something this evaluator deliberately does not implement."""


# ---------------------------------------------------------------------------
#  Tokenizer
# ---------------------------------------------------------------------------

_SHEET = r"(?:'(?:[^']|'')+'|[A-Za-z_][\w.]*)!"
_A1 = r"\$?[A-Za-z]{1,3}\$?\d{1,7}"
_ERRORS = ("#NULL!", "#DIV/0!", "#VALUE!", "#REF!", "#NAME?", "#NUM!", "#N/A",
           "#SPILL!", "#CALC!", "#GETTING_DATA")

_TOKEN_RE = re.compile(
    r"""(?P<ws>\s+)
      | (?P<error>\#(?:NULL!|DIV/0!|VALUE!|REF!|NAME\?|NUM!|N/A|SPILL!|CALC!|GETTING_DATA))
      | (?P<string>"(?:[^"]|"")*")
      | (?P<range>(?:""" + _SHEET + r""")?""" + _A1 + r"""\s*:\s*(?:""" + _SHEET + r""")?""" + _A1 + r""")
      | (?P<wholecol>(?:""" + _SHEET + r""")?\$?[A-Za-z]{1,3}\s*:\s*(?:""" + _SHEET + r""")?\$?[A-Za-z]{1,3}\b)
      | (?P<wholerow>(?:""" + _SHEET + r""")?\$?\d{1,7}\s*:\s*(?:""" + _SHEET + r""")?\$?\d{1,7}\b)
      | (?P<func>[A-Za-z_][\w.]*\s*(?=\())
      | (?P<ref>(?:""" + _SHEET + r""")?""" + _A1 + r""")
      | (?P<bool>\b(?:TRUE|FALSE)\b)
      | (?P<number>(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)
      | (?P<op><=|>=|<>|[-+*/^&=<>%])
      | (?P<lparen>\()
      | (?P<rparen>\))
      | (?P<comma>[,;])
    """, re.VERBOSE)


@dataclass
class Token:
    kind: str
    text: str
    pos: int


def tokenize(src: str) -> List[Token]:
    out, i, n = [], 0, len(src)
    while i < n:
        m = _TOKEN_RE.match(src, i)
        if not m or m.end() == i:
            raise FormulaError(f"cannot read formula at position {i}: {src[i:i + 24]!r}")
        kind = m.lastgroup
        if kind != "ws":
            out.append(Token(kind, m.group().strip(), i))
        i = m.end()
    return out


# ---------------------------------------------------------------------------
#  AST
# ---------------------------------------------------------------------------

@dataclass
class Node:
    kind: str                       # num | str | bool | err | ref | range | binop | unary | func
    value: Any = None               # literal value, operator symbol, or function name
    args: List["Node"] = field(default_factory=list)
    sheet: Optional[str] = None     # ref / range only
    coord: Any = None               # ref: (row, col); range: ((r1,c1),(r2,c2))


def _split_ref(text: str) -> Tuple[Optional[str], str]:
    if "!" in text:
        sheet, rest = text.rsplit("!", 1)
        sheet = sheet.strip()
        if sheet.startswith("'") and sheet.endswith("'"):
            sheet = sheet[1:-1].replace("''", "'")
        return sheet, rest
    return None, text


def _a1(text: str) -> Tuple[int, int]:
    m = re.fullmatch(r"\$?([A-Za-z]{1,3})\$?(\d{1,7})", text.strip())
    if not m:
        raise FormulaError(f"not a cell reference: {text!r}")
    return int(m.group(2)), column_index_from_string(m.group(1).upper())


# ---------------------------------------------------------------------------
#  Parser - precedence climbing
# ---------------------------------------------------------------------------

_BINARY = [
    {"=", "<>", "<", ">", "<=", ">="},
    {"&"},
    {"+", "-"},
    {"*", "/"},
    {"^"},
]


class _Parser:
    def __init__(self, tokens: List[Token], src: str):
        self.t, self.i, self.src = tokens, 0, src

    def peek(self) -> Optional[Token]:
        return self.t[self.i] if self.i < len(self.t) else None

    def take(self) -> Token:
        tok = self.peek()
        if tok is None:
            raise FormulaError(f"formula ends unexpectedly: {self.src!r}")
        self.i += 1
        return tok

    def expect(self, kind: str) -> Token:
        tok = self.take()
        if tok.kind != kind:
            raise FormulaError(f"expected {kind}, found {tok.text!r} in {self.src!r}")
        return tok

    def parse(self) -> Node:
        node = self.expr(0)
        if self.peek() is not None:
            raise FormulaError(f"unexpected {self.peek().text!r} in {self.src!r}")
        return node

    def expr(self, level: int) -> Node:
        if level >= len(_BINARY):
            return self.unary()
        node = self.expr(level + 1)
        while True:
            tok = self.peek()
            if tok is None or tok.kind != "op" or tok.text not in _BINARY[level]:
                return node
            self.take()
            rhs = self.expr(level + 1)
            node = Node("binop", tok.text, [node, rhs])

    def unary(self) -> Node:
        tok = self.peek()
        if tok is not None and tok.kind == "op" and tok.text in {"-", "+"}:
            self.take()
            return Node("unary", tok.text, [self.unary()])
        return self.postfix()

    def postfix(self) -> Node:
        node = self.primary()
        while True:
            tok = self.peek()
            if tok is not None and tok.kind == "op" and tok.text == "%":
                self.take()
                node = Node("unary", "%", [node])
            else:
                return node

    def primary(self) -> Node:
        tok = self.take()
        if tok.kind == "number":
            return Node("num", float(tok.text))
        if tok.kind == "string":
            return Node("str", tok.text[1:-1].replace('""', '"'))
        if tok.kind == "bool":
            return Node("bool", tok.text.upper() == "TRUE")
        if tok.kind == "error":
            return Node("err", tok.text)
        if tok.kind == "ref":
            sheet, a1 = _split_ref(tok.text)
            return Node("ref", tok.text, sheet=sheet, coord=_a1(a1))
        if tok.kind == "range":
            left, right = tok.text.split(":")
            s1, a1 = _split_ref(left)
            s2, a2 = _split_ref(right)
            return Node("range", tok.text, sheet=s1 or s2, coord=(_a1(a1), _a1(a2)))
        if tok.kind in ("wholecol", "wholerow"):
            return Node("wholeref", tok.text)
        if tok.kind == "func":
            name = tok.text.upper()
            self.expect("lparen")
            args: List[Node] = []
            if self.peek() is not None and self.peek().kind == "rparen":
                self.take()
                return Node("func", name, args)
            while True:
                args.append(self.expr(0))
                nxt = self.take()
                if nxt.kind == "rparen":
                    break
                if nxt.kind != "comma":
                    raise FormulaError(f"expected , or ) in {name}(...), found {nxt.text!r}")
            return Node("func", name, args)
        if tok.kind == "lparen":
            node = self.expr(0)
            self.expect("rparen")
            return node
        raise FormulaError(f"unexpected {tok.text!r} in {self.src!r}")


def parse(text: str) -> Node:
    """Parse an Excel formula. The leading '=' is optional."""
    src = text.strip()
    if src.startswith("="):
        src = src[1:]
    if not src:
        raise FormulaError("empty formula")
    return _Parser(tokenize(src), src).parse()


# ---------------------------------------------------------------------------
#  Evaluation
# ---------------------------------------------------------------------------

def _num(v: Any) -> float:
    if v is None or v == "":
        return 0.0
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        if v.strip().upper() in _ERRORS:
            raise FormulaError(f"formula reaches an error value: {v}")
        try:
            return float(v.replace(",", "").strip())
        except ValueError as exc:
            raise FormulaError(f"cannot use {v!r} as a number") from exc
    raise FormulaError(f"cannot use {type(v).__name__} as a number")


def _flat(values: Iterable[Any]) -> List[Any]:
    out: List[Any] = []
    for v in values:
        out.extend(v) if isinstance(v, list) else out.append(v)
    return out


def _numbers(args: Sequence[Any]) -> List[float]:
    return [_num(v) for v in _flat(args)
            if v is not None and v != "" and not isinstance(v, str)]


def _div(a: float, b: float) -> float:
    if b == 0:
        raise FormulaError("division by zero")
    return a / b


FUNCTIONS: Dict[str, Callable[[List[Any]], Any]] = {
    "SUM":      lambda a: math.fsum(_numbers(a)),
    "AVERAGE":  lambda a: (math.fsum(_numbers(a)) / len(_numbers(a))) if _numbers(a) else 0.0,
    "MIN":      lambda a: min(_numbers(a)) if _numbers(a) else 0.0,
    "MAX":      lambda a: max(_numbers(a)) if _numbers(a) else 0.0,
    "COUNT":    lambda a: float(len(_numbers(a))),
    "ABS":      lambda a: abs(_num(a[0])),
    "SQRT":     lambda a: math.sqrt(_num(a[0])),
    "POWER":    lambda a: _num(a[0]) ** _num(a[1]),
    "ROUND":    lambda a: round(_num(a[0]), int(_num(a[1]))),
    "ROUNDUP":  lambda a: math.ceil(_num(a[0]) * 10 ** int(_num(a[1]))) / 10 ** int(_num(a[1])),
    "ROUNDDOWN": lambda a: math.floor(_num(a[0]) * 10 ** int(_num(a[1]))) / 10 ** int(_num(a[1])),
    "PRODUCT":  lambda a: math.prod(_numbers(a)) if _numbers(a) else 0.0,
    "SIGN":     lambda a: float((_num(a[0]) > 0) - (_num(a[0]) < 0)),
}
LAZY_FUNCTIONS = {"IF", "IFERROR", "IFNA"}          # evaluated by the walker, not the table above

_COMPARE = {
    "=":  lambda a, b: a == b,
    "<>": lambda a, b: a != b,
    "<":  lambda a, b: a < b,
    ">":  lambda a, b: a > b,
    "<=": lambda a, b: a <= b,
    ">=": lambda a, b: a >= b,
}


def evaluate(node: Node, resolve: Callable[[Optional[str], int, int], Any],
             sheet: Optional[str] = None) -> Any:
    """Evaluate an AST. `resolve(sheet, row, col)` returns one cell's value."""
    k = node.kind

    if k in ("num", "str", "bool"):
        return node.value
    if k == "err":
        raise FormulaError(f"formula contains {node.value}")
    if k == "wholeref":
        raise UnsupportedFormula(
            f"whole-column/row reference {node.value!r} is not supported - "
            "the trace needs a bounded range like B10:B248")
    if k == "ref":
        r, c = node.coord
        return resolve(node.sheet or sheet, r, c)
    if k == "range":
        (r1, c1), (r2, c2) = node.coord
        sh = node.sheet or sheet
        return [resolve(sh, r, c)
                for r in range(min(r1, r2), max(r1, r2) + 1)
                for c in range(min(c1, c2), max(c1, c2) + 1)]
    if k == "list":
        return [evaluate(a, resolve, sheet) for a in node.args]

    if k == "unary":
        if node.value == "%":
            return _num(evaluate(node.args[0], resolve, sheet)) / 100.0
        v = _num(evaluate(node.args[0], resolve, sheet))
        return -v if node.value == "-" else v

    if k == "binop":
        op = node.value
        if op == "&":
            def txt(v):
                if v is None:
                    return ""
                if isinstance(v, float) and v.is_integer():
                    return str(int(v))
                return str(v)
            return txt(evaluate(node.args[0], resolve, sheet)) + \
                   txt(evaluate(node.args[1], resolve, sheet))
        a = evaluate(node.args[0], resolve, sheet)
        b = evaluate(node.args[1], resolve, sheet)
        if op in _COMPARE:
            if isinstance(a, str) or isinstance(b, str):
                return _COMPARE[op](str(a).casefold(), str(b).casefold())
            return _COMPARE[op](_num(a), _num(b))
        x, y = _num(a), _num(b)
        if op == "+": return x + y
        if op == "-": return x - y
        if op == "*": return x * y
        if op == "/": return _div(x, y)
        if op == "^": return x ** y
        raise UnsupportedFormula(f"operator {op!r}")

    if k == "func":
        name = node.value
        if name == "IF":
            cond = evaluate(node.args[0], resolve, sheet)
            truthy = bool(cond) if isinstance(cond, bool) else _num(cond) != 0
            if truthy:
                return evaluate(node.args[1], resolve, sheet)
            return evaluate(node.args[2], resolve, sheet) if len(node.args) > 2 else False
        if name in ("IFERROR", "IFNA"):
            try:
                return evaluate(node.args[0], resolve, sheet)
            except UnsupportedFormula:
                raise                       # never let IFERROR hide a gap in this evaluator
            except FormulaError:
                return evaluate(node.args[1], resolve, sheet)
        fn = FUNCTIONS.get(name)
        if fn is None:
            raise UnsupportedFormula(
                f"{name}() is not implemented. Supported: "
                f"{', '.join(sorted(set(FUNCTIONS) | LAZY_FUNCTIONS))}.")
        return fn([evaluate(a, resolve, sheet) for a in node.args])

    raise UnsupportedFormula(f"node kind {k!r}")


def refs_in(node: Node, sheet: Optional[str] = None) -> List[Tuple[Optional[str], int, int]]:
    """Every single cell the formula touches, ranges expanded."""
    out: List[Tuple[Optional[str], int, int]] = []
    if node.kind == "ref":
        out.append((node.sheet or sheet, *node.coord))
    elif node.kind == "range":
        (r1, c1), (r2, c2) = node.coord
        sh = node.sheet or sheet
        out += [(sh, r, c)
                for r in range(min(r1, r2), max(r1, r2) + 1)
                for c in range(min(c1, c2), max(c1, c2) + 1)]
    for a in node.args:
        out += refs_in(a, sheet)
    return out


# ---------------------------------------------------------------------------
#  Workbooks: cached values and formula text, side by side
# ---------------------------------------------------------------------------

@dataclass
class Book:
    path: Path
    values: Dict[str, Dict[Tuple[int, int], Any]]
    formulas: Dict[str, Dict[Tuple[int, int], str]]

    def value(self, sheet: str, row: int, col: int) -> Any:
        return self.values.get(sheet, {}).get((row, col))

    def formula(self, sheet: str, row: int, col: int) -> Optional[str]:
        return self.formulas.get(sheet, {}).get((row, col))

    @property
    def sheets(self) -> List[str]:
        return list(self.values)


def load_book(path: str | Path, sheets: Optional[Iterable[str]] = None) -> Book:
    """Read cached values and formula text from an .xlsx/.xlsm."""
    p = Path(path)
    if p.suffix.lower() in {".xlsb", ".xls"}:
        raise UnsupportedFormula(
            f"{p.name}: formulas cannot be read from '{p.suffix}' - pyxlsb and xlrd only expose "
            "cached values. Save the workbook as .xlsx (File > Save As > Excel Workbook) to trace it. "
            "The value comparison works on the original file either way.")
    wanted = set(sheets) if sheets is not None else None
    values: Dict[str, Dict[Tuple[int, int], Any]] = {}
    formulas: Dict[str, Dict[Tuple[int, int], str]] = {}

    for data_only, sink in ((True, values), (False, formulas)):
        wb = load_workbook(p, data_only=data_only, read_only=True, keep_links=False)
        try:
            for name in wb.sheetnames:
                if wanted is not None and name not in wanted:
                    continue
                ws = wb[name]
                if not hasattr(ws, "iter_rows"):
                    continue
                grid: Dict[Tuple[int, int], Any] = {}
                for row in ws.iter_rows():
                    for cell in row:
                        v = cell.value
                        if v is None:
                            continue
                        if data_only:
                            grid[(cell.row, cell.column)] = v
                        elif isinstance(v, str) and v.startswith("="):
                            grid[(cell.row, cell.column)] = v
                        elif type(v).__name__ in ("ArrayFormula", "DataTableFormula"):
                            grid[(cell.row, cell.column)] = getattr(v, "text", "=?")
                sink[name] = grid
        finally:
            wb.close()
    return Book(path=p.resolve(), values=values, formulas=formulas)


# ---------------------------------------------------------------------------
#  Tracing
# ---------------------------------------------------------------------------

@dataclass
class Component:
    key: str                    # stable id, e.g. "Vintage 1!C168"
    sheet: str
    row_old: int
    row_new: int
    col: int
    label: str                  # from the label column, or the cell ref when there isn't one
    old: float
    new: float
    depth: int
    labelled: bool
    formula: Optional[str] = None

    @property
    def ref_old(self) -> str:
        return f"{get_column_letter(self.col)}{self.row_old}"

    @property
    def ref_new(self) -> str:
        return f"{get_column_letter(self.col)}{self.row_new}"

    @property
    def delta(self) -> float:
        return self.new - self.old


@dataclass
class Trace:
    sheet: str
    col: int
    row_old: int
    row_new: int
    formula_old: Optional[str]
    formula_new: Optional[str]
    value_old: float
    value_new: float
    components: List[Component]
    tree: Node                  # the formula, rebuilt with components as parameters
    notes: List[str] = field(default_factory=list)

    @property
    def ref_old(self) -> str:
        return f"{get_column_letter(self.col)}{self.row_old}"

    @property
    def ref_new(self) -> str:
        return f"{get_column_letter(self.col)}{self.row_new}"

    @property
    def formula_changed(self) -> bool:
        return (self.formula_old or "").replace(" ", "") != (self.formula_new or "").replace(" ", "")

    def evaluate_with(self, selected: Set[str]) -> float:
        """Re-evaluate with the named components switched to their new values."""
        picked = {c.key: (c.new if c.key in selected else c.old) for c in self.components}
        return float(_eval_scenario(self.tree, picked))

    def check(self, tol: float = 1e-6) -> None:
        """All-old must reproduce the old cached value; all-new the new one."""
        got_old = self.evaluate_with(set())
        got_new = self.evaluate_with({c.key for c in self.components})
        for got, want, which in ((got_old, self.value_old, "old"), (got_new, self.value_new, "new")):
            if want is None:
                continue
            scale = max(abs(want), 1.0)
            if abs(got - want) / scale > tol:
                raise AssertionError(
                    f"trace does not reproduce the {which} value at {self.sheet}!"
                    f"{self.ref_old if which == 'old' else self.ref_new}: re-evaluated {got!r}, "
                    f"workbook says {want!r}. The formula was followed incorrectly - do not trust "
                    "the component impacts.")


def _eval_scenario(node: Node, picked: Dict[str, float]) -> Any:
    def unreachable(sheet, row, col):
        raise UnsupportedFormula(
            f"the scenario tree still references {sheet}!{row}:{col}; it should have been "
            "resolved to a constant or a parameter when the trace was built")
    return evaluate(_eval_scenario_node(node, picked), unreachable)


def _eval_scenario_node(node: Node, picked: Dict[str, float]) -> Node:
    if node.kind == "param":
        return Node("num", float(picked[node.value]))
    if node.kind == "list":
        return Node("list", None, [_eval_scenario_node(a, picked) for a in node.args])
    if node.kind in ("num", "str", "bool", "err"):
        return node
    return Node(node.kind, node.value, [_eval_scenario_node(a, picked) for a in node.args],
                node.sheet, node.coord)


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _same(a: Any, b: Any, tol: float) -> bool:
    if _is_num(a) and _is_num(b):
        return abs(float(a) - float(b)) <= tol
    if a is None and b is None:
        return True
    if (a is None) != (b is None):
        return False
    return str(a).strip().casefold() == str(b).strip().casefold()


def trace(old: Book, new: Book, sheet: str, row: int, col: int,
          row_map: Optional[Callable[[int], int]] = None,
          label_col: int = 2, max_depth: int = 8, tol: float = 1e-9,
          sheet_new: Optional[str] = None) -> Trace:
    """Follow the formula at (sheet, row, col) down to the inputs that changed.

    `row_map` maps a row in the old workbook to the same logical row in the new one - this is
    what carries the inserted-row offset, so old row 209 can be compared against new row 210.

    A cell becomes a *component* when it changed and nothing labelled below it changed: that is
    the individual revenue or expense line that moved, however many subtotal layers sit above it.
    """
    rmap = row_map or (lambda r: r)
    sheet_b = sheet_new or sheet
    notes: List[str] = []
    components: Dict[str, Component] = {}
    memo: Dict[Tuple[str, int, int], Tuple[Node, bool]] = {}
    visiting: Set[Tuple[str, int, int]] = set()

    def label_of(sh: str, r: int) -> str:
        v = old.value(sh, r, label_col)
        return str(v).strip() if v is not None and str(v).strip() else ""

    def add_component(sh: str, r: int, c: int, ov: Any, nv: Any, depth: int, lab: str) -> Node:
        key = f"{sh}!{get_column_letter(c)}{r}"
        if key not in components:
            components[key] = Component(
                key=key, sheet=sh, row_old=r, row_new=rmap(r), col=c,
                label=lab or f"{get_column_letter(c)}{r}",
                old=float(ov or 0), new=float(nv or 0), depth=depth, labelled=bool(lab),
                formula=old.formula(sh, r, c))
        return Node("param", key)

    def rebuild(node: Node, sh: str, depth: int) -> Tuple[Node, bool]:
        if node.kind == "ref":
            r, c = node.coord
            return visit(node.sheet or sh, r, c, depth + 1)
        if node.kind == "range":
            (r1, c1), (r2, c2) = node.coord
            target = node.sheet or sh
            kids, found = [], False
            for r in range(min(r1, r2), max(r1, r2) + 1):
                for c in range(min(c1, c2), max(c1, c2) + 1):
                    kid, f = visit(target, r, c, depth + 1)
                    kids.append(kid)
                    found = found or f
            return Node("list", None, kids), found
        kids, found = [], False
        for a in node.args:
            kid, f = rebuild(a, sh, depth)
            kids.append(kid)
            found = found or f
        return Node(node.kind, node.value, kids, node.sheet, node.coord), found

    def visit(sh: str, r: int, c: int, depth: int) -> Tuple[Node, bool]:
        key = (sh, r, c)
        if key in memo:
            return memo[key]
        if key in visiting:
            raise FormulaError(f"circular reference at {sh}!{get_column_letter(c)}{r}")

        ov = old.value(sh, r, c)
        nv = new.value(sheet_b if sh == sheet else sh, rmap(r), c)
        lab = label_of(sh, r)

        if _same(ov, nv, tol):
            # Unchanged: freeze it. Prefer the cached value; if the workbook carries none
            # (it was written by a script and never recalculated), compute it from the
            # formula instead of silently freezing the cell at zero.
            if _is_num(ov):
                result = (Node("num", float(ov)), False)
            else:
                f_same = old.formula(sh, r, c)
                if f_same is not None and depth < max_depth:
                    visiting.add(key)
                    try:
                        sub, _ = rebuild(parse(f_same), sh, depth)
                        result = (sub, False)
                    except FormulaError as exc:
                        notes.append(f"{sh}!{get_column_letter(c)}{r}: {exc} - held at zero")
                        result = (Node("num", 0.0), False)
                    finally:
                        visiting.discard(key)
                else:
                    if ov is not None and not _is_num(ov):
                        notes.append(f"{sh}!{get_column_letter(c)}{r} holds {ov!r}, "
                                     "not a number - held at zero")
                    result = (Node("num", 0.0), False)
            memo[key] = result
            return result

        if not (_is_num(ov) or ov is None) or not (_is_num(nv) or nv is None):
            notes.append(f"{sh}!{get_column_letter(c)}{r} changed from {ov!r} to {nv!r} - "
                         "not a number, so it is held at its old value in the model")
            result = (Node("num", 0.0), False)
            memo[key] = result
            return result

        f = old.formula(sh, r, c)
        if f is None or depth >= max_depth:
            if f is not None:
                notes.append(f"stopped at {sh}!{get_column_letter(c)}{r} (depth limit {max_depth}) - "
                             "anything below it is folded into this component")
            result = (add_component(sh, r, c, ov, nv, depth, lab), bool(lab))
            memo[key] = result
            return result

        visiting.add(key)
        try:
            sub, found_below = rebuild(parse(f), sh, depth)
        except FormulaError as exc:
            notes.append(f"{sh}!{get_column_letter(c)}{r}: {exc} - treated as a single component")
            visiting.discard(key)
            result = (add_component(sh, r, c, ov, nv, depth, lab), bool(lab))
            memo[key] = result
            return result
        visiting.discard(key)

        # A labelled cell with nothing labelled below it IS the line that moved: stop here.
        if lab and not found_below:
            result = (add_component(sh, r, c, ov, nv, depth, lab), True)
            memo[key] = result
            return result

        result = (sub, found_below or bool(lab))
        memo[key] = result
        return result

    f_old = old.formula(sheet, row, col)
    f_new = new.formula(sheet_b, rmap(row), col)
    if f_old is None:
        raise FormulaError(
            f"{sheet}!{get_column_letter(col)}{row} holds no formula - it is a plain value, so "
            "there is nothing to decompose. Check the row and column.")

    tree, _ = rebuild(parse(f_old), sheet, 0)

    v_old = old.value(sheet, row, col)
    v_new = new.value(sheet_b, rmap(row), col)
    result = Trace(
        sheet=sheet, col=col, row_old=row, row_new=rmap(row),
        formula_old=f_old, formula_new=f_new,
        value_old=float(v_old) if _is_num(v_old) else None,
        value_new=float(v_new) if _is_num(v_new) else None,
        components=sorted(components.values(), key=lambda c: -abs(c.delta)),
        tree=tree, notes=notes)

    if result.value_old is None or result.value_new is None:
        notes.append(
            f"{sheet} carries no cached value at the ROA cell, so both figures below are "
            "computed from the formula rather than read from the workbook. Open the file in "
            "Excel and re-save it to store calculated values and cross-check them.")
        if result.value_old is None:
            result.value_old = result.evaluate_with(set())
        if result.value_new is None:
            result.value_new = result.evaluate_with({c.key for c in result.components})
    if result.formula_changed:
        result.notes.insert(0, "The ROA formula itself differs between the two workbooks. The "
                               "decomposition below uses the old formula; compare them directly "
                               "before reading the impacts.")
    return result


def compile_scenario(tr: Trace) -> Dict[str, Any]:
    """Serialise the scenario tree so a browser can re-evaluate it."""
    def pack(n: Node) -> Dict[str, Any]:
        if n.kind == "param":
            return {"k": "p", "id": n.value}
        if n.kind in ("num", "bool"):
            return {"k": "n", "v": n.value}
        if n.kind == "str":
            return {"k": "s", "v": n.value}
        if n.kind == "list":
            return {"k": "l", "a": [pack(a) for a in n.args]}
        if n.kind == "binop":
            return {"k": "b", "o": n.value, "a": [pack(a) for a in n.args]}
        if n.kind == "unary":
            return {"k": "u", "o": n.value, "a": [pack(a) for a in n.args]}
        if n.kind == "func":
            return {"k": "f", "o": n.value, "a": [pack(a) for a in n.args]}
        raise UnsupportedFormula(f"cannot serialise node {n.kind!r}")
    return pack(tr.tree)
