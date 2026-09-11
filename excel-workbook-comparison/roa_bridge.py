"""ROA bridge: turn a pile of cell differences into "here is what moved return on assets".

ROA = net income / total assets, so a change in ROA has exactly two sources: the income
line items moved, or the asset base moved. This decomposes one into the other:

    dROA  =  SUM_i (d contribution_i / A0)   +   NI1 * (1/A1 - 1/A0)
             ^-- what each P&L line did       ^-- what the asset base did

The two halves sum to the total change exactly, with no residual, provided the named
line items sum to net income. They often don't -- a sheet has subtotals, or a line nobody
mapped -- so the unexplained remainder is computed and shown as its own step rather than
quietly spread across the others.

Renders to a standalone HTML page, so the person reading it never opens the workbook.
"""

from __future__ import annotations

import datetime as dt
import html
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

__all__ = ["Line", "BridgeStep", "BridgeResult", "build_bridge", "render_html", "write_html"]

BPS = 10_000.0


# ---------------------------------------------------------------------------
#  Inputs
# ---------------------------------------------------------------------------

@dataclass
class Line:
    """One income-statement line, on both sides of the comparison.

    `base` and `other` are the line's *signed contribution to net income*: revenue
    positive, costs negative. If the workbook stores costs as positive numbers, pass
    sign=-1 and the values are flipped for you.
    """
    label: str
    base: float
    other: float
    sign: int = 1
    source: str = ""            # where it came from, e.g. "Vintage Summary!B412"

    @property
    def base_contrib(self) -> float:
        return self.sign * float(self.base)

    @property
    def other_contrib(self) -> float:
        return self.sign * float(self.other)

    @property
    def delta(self) -> float:
        return self.other_contrib - self.base_contrib


@dataclass
class BridgeStep:
    label: str
    bps: float                  # effect on ROA, in basis points
    kind: str                   # "open" | "close" | "driver" | "assets" | "residual"
    amount: Optional[float] = None      # the money behind it, where there is one
    source: str = ""
    start: float = 0.0          # cumulative ROA (bps) the bar starts at
    end: float = 0.0            # ... and ends at


@dataclass
class BridgeResult:
    title: str
    base_label: str
    other_label: str
    base_assets: float
    other_assets: float
    base_income: float
    other_income: float
    steps: List[BridgeStep]
    lines: List[Line]
    currency: str = "$"
    units: float = 1_000_000.0
    units_label: str = "m"
    caveats: List[str] = field(default_factory=list)
    generated: dt.datetime = field(default_factory=dt.datetime.now)
    sample: bool = False

    @property
    def base_roa(self) -> float:
        return self.base_income / self.base_assets * BPS

    @property
    def other_roa(self) -> float:
        return self.other_income / self.other_assets * BPS

    @property
    def delta_roa(self) -> float:
        return self.other_roa - self.base_roa

    def check(self, tol: float = 1e-6) -> None:
        """The steps must reconstruct the closing ROA exactly. Fail loudly if they don't."""
        walked = self.base_roa + sum(s.bps for s in self.steps if s.kind != "open" and s.kind != "close")
        if abs(walked - self.other_roa) > tol:
            raise AssertionError(
                f"bridge does not tie: walked to {walked:.6f} bps, closing ROA is "
                f"{self.other_roa:.6f} bps (gap {walked - self.other_roa:.6e})")


def build_bridge(lines: Sequence[Line],
                 base_assets: float, other_assets: float,
                 base_income: Optional[float] = None, other_income: Optional[float] = None,
                 title: str = "ROA bridge",
                 base_label: str = "Baseline", other_label: str = "Candidate",
                 currency: str = "$", units: float = 1_000_000.0, units_label: str = "m",
                 caveats: Optional[Sequence[str]] = None,
                 sample: bool = False) -> BridgeResult:
    """Decompose the ROA change into one step per line item plus the asset-base effect.

    base_income / other_income default to the sum of the lines. Pass the workbook's own
    net income figures instead to surface any gap between them as a residual step.
    """
    lines = list(lines)
    summed_base = sum(l.base_contrib for l in lines)
    summed_other = sum(l.other_contrib for l in lines)
    ni0 = summed_base if base_income is None else float(base_income)
    ni1 = summed_other if other_income is None else float(other_income)

    steps: List[BridgeStep] = [BridgeStep("Opening ROA", 0.0, "open")]

    for line in lines:
        steps.append(BridgeStep(
            label=line.label,
            bps=line.delta / base_assets * BPS,     # income effect, held at the opening asset base
            kind="driver",
            amount=line.delta,
            source=line.source,
        ))

    residual = (ni1 - summed_other) - (ni0 - summed_base)
    if abs(residual) > 1e-9:
        steps.append(BridgeStep(
            label="Other income not itemised",
            bps=residual / base_assets * BPS,
            kind="residual",
            amount=residual,
            source="net income less the lines above",
        ))

    asset_effect = ni1 * (1.0 / other_assets - 1.0 / base_assets) * BPS
    steps.append(BridgeStep(
        label="Asset base",
        bps=asset_effect,
        kind="assets",
        amount=other_assets - base_assets,
        source="denominator effect",
    ))
    steps.append(BridgeStep("Closing ROA", 0.0, "close"))

    result = BridgeResult(
        title=title, base_label=base_label, other_label=other_label,
        base_assets=base_assets, other_assets=other_assets,
        base_income=ni0, other_income=ni1,
        steps=steps, lines=lines, currency=currency, units=units, units_label=units_label,
        caveats=list(caveats or []), sample=sample,
    )

    cum = result.base_roa
    for step in steps:
        if step.kind == "open":
            step.start, step.end = 0.0, result.base_roa
        elif step.kind == "close":
            step.start, step.end = 0.0, result.other_roa
        else:
            step.start, step.end = cum, cum + step.bps
            cum = step.end

    result.check()
    return result


# ---------------------------------------------------------------------------
#  Rendering
# ---------------------------------------------------------------------------

def _bps(v: float, sign: bool = True) -> str:
    s = f"{v:+,.1f}" if sign else f"{v:,.1f}"
    return f"{s} bps"


def _money(v: float, res: BridgeResult, sign: bool = True) -> str:
    scaled = v / res.units
    lead = ("+" if scaled >= 0 else "-") if sign else ("-" if scaled < 0 else "")
    return f"{lead}{res.currency}{abs(scaled):,.1f}{res.units_label}"


def _esc(s: Any) -> str:
    return html.escape(str(s), quote=True)


CSS = """
.roa { --ink: #0b0b0b; --ink-2: #52514e; --ink-3: #898781;
  --surface: #fcfcfb; --plane: #f9f9f7; --rule: #e1e0d9; --axis: #c3c2b7;
  --up: #2a78d6; --down: #e34948; --flat: #898781;
  --band: #fdf6e3; --band-ink: #6b5310; --band-rule: #e8d9a8;
  color-scheme: light; background: var(--plane); color: var(--ink);
  font-family: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
  font-size: 15px; line-height: 1.55; }
@media (prefers-color-scheme: dark) { :root:where(:not([data-theme="light"])) .roa {
  --ink: #ffffff; --ink-2: #c3c2b7; --ink-3: #898781;
  --surface: #1a1a19; --plane: #0d0d0d; --rule: #2c2c2a; --axis: #383835;
  --up: #3987e5; --down: #e66767; --flat: #898781;
  --band: #2a2313; --band-ink: #e8cf8a; --band-rule: #4a3f20; color-scheme: dark; } }
:root[data-theme="dark"] .roa {
  --ink: #ffffff; --ink-2: #c3c2b7; --ink-3: #898781;
  --surface: #1a1a19; --plane: #0d0d0d; --rule: #2c2c2a; --axis: #383835;
  --up: #3987e5; --down: #e66767; --flat: #898781;
  --band: #2a2313; --band-ink: #e8cf8a; --band-rule: #4a3f20; color-scheme: dark; }

.roa * { box-sizing: border-box; }
.roa-wrap { max-width: 860px; margin: 0 auto; padding-block: 40px 56px; padding-left: 20px; padding-right: 20px;
  display: flex; flex-direction: column; gap: 34px; }
.roa-mono { font-family: "IBM Plex Mono", ui-monospace, "SF Mono", Menlo, monospace; }
.roa-num { font-variant-numeric: tabular-nums; }

.roa-sample { background: var(--band); color: var(--band-ink); border: 1px solid var(--band-rule);
  border-radius: 3px; padding: 11px 15px; font-size: 13.5px; }
.roa-sample strong { font-weight: 600; }

.roa-head { display: flex; flex-direction: column; gap: 7px; }
.roa-eyebrow { font-size: 11.5px; letter-spacing: .1em; text-transform: uppercase;
  color: var(--ink-3); font-weight: 500; }
.roa-title { font-size: 28px; line-height: 1.2; font-weight: 600; margin: 0; text-wrap: balance; }
.roa-sub { color: var(--ink-2); font-size: 14px; margin: 0; }

.roa-verdict { background: var(--surface); border: 1px solid var(--rule); border-radius: 4px;
  padding: 26px 28px; display: flex; flex-wrap: wrap; align-items: baseline; gap: 10px 34px; }
.roa-hero { font-size: 54px; line-height: 1; font-weight: 600; letter-spacing: -.02em; }
.roa-hero.up { color: var(--up); } .roa-hero.down { color: var(--down); }
.roa-fromto { display: flex; align-items: baseline; gap: 10px; font-size: 19px; color: var(--ink-2); }
.roa-fromto b { color: var(--ink); font-weight: 600; }
.roa-read { flex-basis: 100%; color: var(--ink-2); font-size: 14.5px; margin: 0;
  padding-top: 4px; max-width: 62ch; }

.roa-sec-h { font-size: 12px; letter-spacing: .09em; text-transform: uppercase;
  color: var(--ink-3); font-weight: 600; margin: 0 0 3px; }
.roa-sec-n { color: var(--ink-2); font-size: 13.5px; margin: 0 0 16px; max-width: 66ch; }

.roa-chart { background: var(--surface); border: 1px solid var(--rule); border-radius: 4px;
  padding: 22px 24px 16px; }
.roa-row { display: grid; grid-template-columns: 190px 1fr 96px; align-items: center;
  gap: 14px; min-height: 30px; }
.roa-row.rule { border-top: 1px solid var(--rule); margin-top: 6px; padding-top: 10px; }
.roa-row.rule + .roa-row { margin-top: 0; }
.roa-lab { font-size: 13.5px; color: var(--ink-2); text-align: right; }
.roa-row.total .roa-lab { color: var(--ink); font-weight: 600; }
.roa-track { position: relative; height: 20px; }
.roa-grid { position: absolute; inset: 0; }
.roa-gl { position: absolute; top: -4px; bottom: -4px; width: 1px; background: var(--rule); }
.roa-bar { position: absolute; top: 4px; height: 12px; border-radius: 2px; }
.roa-bar.up { background: var(--up); } .roa-bar.down { background: var(--down); }
.roa-level { position: absolute; top: 0; height: 20px; width: 3px; border-radius: 1px;
  background: var(--ink); transform: translateX(-1.5px); }
.roa-levelrule { position: absolute; top: 9.5px; left: 0; right: 0; height: 1px; background: var(--axis); }
.roa-val { font-size: 13px; text-align: right; color: var(--ink-2); }
.roa-val.up { color: var(--up); } .roa-val.down { color: var(--down); }
.roa-row.total .roa-val { color: var(--ink); font-weight: 600; }
.roa-axis { display: grid; grid-template-columns: 190px 1fr 96px; gap: 14px;
  margin-top: 8px; border-top: 1px solid var(--axis); padding-top: 6px; }
.roa-ticks { position: relative; height: 14px; }
.roa-tick { position: absolute; transform: translateX(-50%); font-size: 11px; color: var(--ink-3); }
.roa-cap { font-size: 12.5px; color: var(--ink-3); margin: 10px 0 0; max-width: 68ch; }

.roa-cell { position: relative; }
.roa-tip { position: absolute; left: 50%; bottom: calc(100% + 8px); transform: translateX(-50%);
  background: var(--ink); color: var(--surface); padding: 7px 10px; border-radius: 3px;
  font-size: 12px; white-space: nowrap; opacity: 0; pointer-events: none;
  transition: opacity .12s ease; z-index: 5; }
.roa-row:hover .roa-tip, .roa-row:focus-within .roa-tip { opacity: 1; }
@media (prefers-reduced-motion: reduce) { .roa-tip { transition: none; } }

.roa-tablewrap { overflow-x: auto; background: var(--surface);
  border: 1px solid var(--rule); border-radius: 4px; }
.roa table { border-collapse: collapse; width: 100%; font-size: 13.5px; }
.roa th { text-align: left; font-weight: 600; font-size: 11.5px; letter-spacing: .07em;
  text-transform: uppercase; color: var(--ink-3); padding: 11px 16px;
  border-bottom: 1px solid var(--rule); white-space: nowrap; }
.roa td { padding: 10px 16px; border-bottom: 1px solid var(--rule); color: var(--ink-2); }
.roa tr:last-child td { border-bottom: 0; }
.roa td.name { color: var(--ink); }
.roa td.n { text-align: right; white-space: nowrap; }
.roa td.n.up { color: var(--up); } .roa td.n.down { color: var(--down); }
.roa td.src { font-size: 12px; color: var(--ink-3); }

.roa-notes { display: flex; flex-direction: column; gap: 9px; }
.roa-note { display: flex; gap: 10px; font-size: 13.5px; color: var(--ink-2);
  padding-left: 12px; border-left: 2px solid var(--rule); max-width: 70ch; }
.roa-foot { color: var(--ink-3); font-size: 12.5px; border-top: 1px solid var(--rule);
  padding-top: 14px; display: flex; flex-direction: column; gap: 4px; }

@media (max-width: 620px) {
  .roa-row, .roa-axis { grid-template-columns: 116px 1fr 78px; gap: 9px; }
  .roa-lab { font-size: 12px; } .roa-hero { font-size: 42px; }
  .roa-wrap { padding-block: 28px 40px; }
}
"""


def _pos(v: float, lo: float, hi: float) -> float:
    return (v - lo) / ((hi - lo) or 1.0) * 100


def _bar_geom(step: BridgeStep, lo: float, hi: float) -> Tuple[float, float]:
    left = _pos(min(step.start, step.end), lo, hi)
    width = abs(step.end - step.start) / ((hi - lo) or 1.0) * 100
    return left, max(width, 0.5)       # keep a hairline visible for a near-zero step


def _domain(res: "BridgeResult") -> Tuple[float, float]:
    """Bracket the cumulative path, not zero.

    The steps are a few bps on a level of a few hundred, so a zero-anchored axis makes every
    step invisible. The axis is truncated instead, and says so under the chart.
    """
    moves = [s for s in res.steps if s.kind not in ("open", "close")]
    cums = [s.start for s in moves] + [s.end for s in moves] + [res.base_roa, res.other_roa]
    lo_raw, hi_raw = min(cums), max(cums)
    span = (hi_raw - lo_raw) or (abs(hi_raw) * 0.1) or 1.0
    return lo_raw - span * 0.18, hi_raw + span * 0.18


def _ticks(lo: float, hi: float, target: int = 5) -> List[float]:
    span = hi - lo
    raw = span / target
    mag = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1
    step = min([m * mag for m in (1, 2, 2.5, 5, 10)], key=lambda s: abs(s - raw))
    first = math.ceil(lo / step) * step
    out, v = [], first
    while v <= hi + 1e-9:
        out.append(round(v, 6))
        v += step
    return out


def render_html(res: BridgeResult, fragment: bool = True) -> str:
    """The page body. fragment=False wraps it in a full standalone document."""
    up_down = "up" if res.delta_roa >= 0 else "down"
    drivers = [s for s in res.steps if s.kind in ("driver", "residual", "assets")]
    ranked = sorted(drivers, key=lambda s: -abs(s.bps))

    lo, hi = _domain(res)
    ticks = _ticks(lo, hi)

    gridlines = "".join(
        f'<span class="roa-gl" style="left:{_pos(t, lo, hi):.3f}%"></span>' for t in ticks)

    def row(step: BridgeStep) -> str:
        total = step.kind in ("open", "close")
        if total:
            val, valcls = _bps(step.end, sign=False), ""
            mark = (f'<div class="roa-levelrule"></div>'
                    f'<div class="roa-level" style="left:{_pos(step.end, lo, hi):.3f}%"></div>')
        else:
            left, width = _bar_geom(step, lo, hi)
            cls = "up" if step.bps >= 0 else "down"
            val, valcls = _bps(step.bps), cls
            mark = f'<div class="roa-bar {cls}" style="left:{left:.3f}%;width:{width:.3f}%"></div>'
        tip = f"{_esc(step.label)} &middot; {_esc(val)}"
        if step.amount is not None:
            tip += f" &middot; {_esc(_money(step.amount, res))}"
        if step.source:
            tip += f" &middot; {_esc(step.source)}"
        return (
            f'<div class="roa-row{" total" if total else ""}{" rule" if step.kind == "close" else ""}">'
            f'<div class="roa-lab">{_esc(step.label)}</div>'
            f'<div class="roa-track roa-cell"><div class="roa-grid">{gridlines}</div>{mark}'
            f'<span class="roa-tip">{tip}</span></div>'
            f'<div class="roa-val roa-num {valcls}">{_esc(val)}</div></div>')

    rows = "".join(row(s) for s in res.steps)
    tickmarks = "".join(
        f'<span class="roa-tick roa-num" style="left:{_pos(t, lo, hi):.3f}%">{t:,.0f}</span>'
        for t in ticks)

    table_rows = "".join(
        f'<tr><td class="name">{_esc(s.label)}</td>'
        f'<td class="n roa-num roa-mono">{_esc(_money(s.amount, res)) if s.amount is not None else "&mdash;"}</td>'
        f'<td class="n roa-num roa-mono {"up" if s.bps >= 0 else "down"}">{_esc(_bps(s.bps))}</td>'
        f'<td class="src roa-mono">{_esc(s.source) or "&mdash;"}</td></tr>'
        for s in ranked)

    biggest = ranked[0] if ranked else None
    read = (f"ROA {'rose' if res.delta_roa >= 0 else 'fell'} {abs(res.delta_roa):,.1f} bps. "
            f"The largest single driver is {biggest.label.lower()} at {_bps(biggest.bps)}, "
            f"{abs(biggest.bps / res.delta_roa) * 100:,.0f}% of the total move."
            if biggest and res.delta_roa else "ROA is unchanged between the two workbooks.")

    sample_band = (
        '<div class="roa-sample"><strong>Sample data.</strong> These figures are invented to show '
        'the format. They are not from any real workbook, and nothing on this page should be '
        'read as a financial result.</div>' if res.sample else "")

    notes = "".join(f'<div class="roa-note">{_esc(c)}</div>' for c in res.caveats)
    notes_block = (f'<section><h2 class="roa-sec-h">Before you rely on this</h2>'
                   f'<div class="roa-notes">{notes}</div></section>') if notes else ""

    body = f"""<div class="roa"><div class="roa-wrap">
{sample_band}
<header class="roa-head">
  <div class="roa-eyebrow">Return on assets &middot; bridge</div>
  <h1 class="roa-title">{_esc(res.title)}</h1>
  <p class="roa-sub">{_esc(res.base_label)} &rarr; {_esc(res.other_label)}</p>
</header>

<section class="roa-verdict">
  <div class="roa-hero roa-num {up_down}">{_bps(res.delta_roa)}</div>
  <div class="roa-fromto roa-num roa-mono">
    <span>{res.base_roa / 100:,.2f}%</span><span>&rarr;</span><b>{res.other_roa / 100:,.2f}%</b>
  </div>
  <p class="roa-read">{_esc(read)}</p>
</section>

<section>
  <h2 class="roa-sec-h">What moved it</h2>
  <p class="roa-sec-n">Each line's effect on ROA, held at the opening asset base, plus the effect of
     the asset base itself. The steps sum to the total change exactly.</p>
  <div class="roa-chart">
    {rows}
    <div class="roa-axis"><div></div><div class="roa-ticks">{tickmarks}</div><div></div></div>
  </div>
  <p class="roa-cap">Basis points. The axis spans {lo:,.0f}&ndash;{hi:,.0f} bps and does not start at
     zero &mdash; the steps are single digits on a level of {res.base_roa:,.0f}. Opening and closing
     ROA are marked as levels on that scale; the coloured bars are the changes between them.</p>
</section>

<section>
  <h2 class="roa-sec-h">The same thing, in money</h2>
  <p class="roa-sec-n">Ranked by size of effect.</p>
  <div class="roa-tablewrap"><table>
    <thead><tr><th>Line</th><th class="n">Change</th><th class="n">Effect on ROA</th><th>Source</th></tr></thead>
    <tbody>{table_rows}</tbody>
  </table></div>
</section>

{notes_block}

<footer class="roa-foot">
  <div>ROA = net income &divide; total assets. Opening {_money(res.base_income, res, sign=False)} on
       {_money(res.base_assets, res, sign=False)}; closing {_money(res.other_income, res, sign=False)} on
       {_money(res.other_assets, res, sign=False)}.</div>
  <div>Values only &mdash; formulas compared on their cached results, charts ignored.
       Generated {res.generated:%Y-%m-%d %H:%M}.</div>
  {'<div><strong>Sample data, not a real result.</strong></div>' if res.sample else ''}
</footer>
</div></div>"""

    fonts = ('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
             'family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">')
    style = f"<style>{CSS}</style>"

    if fragment:
        return f"<title>{_esc(res.title)}</title>\n{fonts}\n{style}\n{body}"
    return (f"<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
            f"<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            f"<title>{_esc(res.title)}</title>{fonts}"
            f"<style>html,body{{margin:0;padding:0}}</style>{style}</head><body>{body}</body></html>")


def write_html(res: BridgeResult, path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_html(res, fragment=False), encoding="utf-8")
    return out.resolve()
