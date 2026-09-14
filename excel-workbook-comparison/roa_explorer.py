"""Interactive ROA explorer: tick the components that changed, watch ROA move.

Static bridges assume the drivers add up. ROA is net income over assets -- a ratio -- so they
don't: the effect of two changes together is not the sum of their separate effects. This page
carries the actual formula and re-evaluates it in the browser for whatever subset you select,
so every figure on it is the real thing rather than an approximation.
"""

from __future__ import annotations

import datetime as dt
import html
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from formula_trace import Trace, compile_scenario

__all__ = ["build_payload", "render_html", "write_html"]

BPS = 10_000.0


def _esc(s: Any) -> str:
    return html.escape(str(s), quote=True)


def _dedupe_structural(changes) -> List[Dict[str, Any]]:
    """One entry per distinct finding. The same widened range shows up in all 24 month columns."""
    out, seen = [], set()
    for sc in changes:
        key = (sc.label, sc.kind, sc.describe())
        if key in seen:
            continue
        seen.add(key)
        out.append({"label": sc.label or sc.ref_old, "refOld": sc.ref_old, "refNew": sc.ref_new,
                    "kind": sc.kind, "old": sc.formula_old, "new": sc.formula_new,
                    "detail": sc.describe()})
    return out


def build_payload(traces: Sequence[Trace],
                  names: Optional[Sequence[str]] = None,
                  groups: Optional[Sequence[str]] = None,
                  items: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """Turn traces into the JSON the page evaluates against.

    `groups` and `items` give the page its two selectors - vintage sheet and month.
    """
    out = []
    for i, tr in enumerate(traces):
        base = tr.evaluate_with(set())
        comps = []
        for c in tr.components:
            solo = tr.evaluate_with({c.key}) - base
            comps.append({
                "id": c.key, "label": c.label,
                "refOld": c.ref_old, "refNew": c.ref_new,
                "old": c.old, "new": c.new, "delta": c.delta,
                "solo": solo * BPS, "labelled": c.labelled,
                "formula": c.formula or "",
            })
        comps.sort(key=lambda d: -abs(d["solo"]))
        out.append({
            "name": (names[i] if names and i < len(names) else tr.sheet),
            "group": (groups[i] if groups and i < len(groups) else tr.sheet),
            "item": (items[i] if items and i < len(items) else tr.ref_old),
            "sheet": tr.sheet,
            "refOld": tr.ref_old, "refNew": tr.ref_new,
            "formulaOld": tr.formula_old or "", "formulaNew": tr.formula_new or "",
            "formulaChanged": tr.formula_changed,
            "roaOld": tr.value_old, "roaNew": tr.value_new,
            "tree": compile_scenario(tr),
            "components": comps,
            "notes": tr.notes,
            "modelled": tr.modelled_new,
            "gap": (tr.structural_gap * BPS) if tr.structural_gap is not None else None,
            "structural": _dedupe_structural(tr.structural),
        })
    return {"vintages": out, "generated": dt.datetime.now().strftime("%Y-%m-%d %H:%M")}


CSS = """
.rx { --ink:#0b0b0b; --ink-2:#52514e; --ink-3:#898781;
  --surface:#fcfcfb; --plane:#f9f9f7; --rule:#e1e0d9; --axis:#c3c2b7; --hover:#f2f1ec;
  --up:#2a78d6; --down:#e34948; --flat:#898781;
  --band:#fdf6e3; --band-ink:#6b5310; --band-rule:#e8d9a8;
  color-scheme:light; background:var(--plane); color:var(--ink);
  font-family:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;
  font-size:15px; line-height:1.55; }
@media (prefers-color-scheme:dark){ :root:where(:not([data-theme="light"])) .rx{
  --ink:#fff; --ink-2:#c3c2b7; --ink-3:#898781;
  --surface:#1a1a19; --plane:#0d0d0d; --rule:#2c2c2a; --axis:#383835; --hover:#242422;
  --up:#3987e5; --down:#e66767;
  --band:#2a2313; --band-ink:#e8cf8a; --band-rule:#4a3f20; color-scheme:dark; } }
:root[data-theme="dark"] .rx{
  --ink:#fff; --ink-2:#c3c2b7; --ink-3:#898781;
  --surface:#1a1a19; --plane:#0d0d0d; --rule:#2c2c2a; --axis:#383835; --hover:#242422;
  --up:#3987e5; --down:#e66767;
  --band:#2a2313; --band-ink:#e8cf8a; --band-rule:#4a3f20; color-scheme:dark; }

.rx *{box-sizing:border-box}
.rx-wrap{max-width:900px;margin:0 auto;padding-block:38px 56px;padding-left:20px;padding-right:20px;
  display:flex;flex-direction:column;gap:30px}
.rx-mono{font-family:"IBM Plex Mono",ui-monospace,"SF Mono",Menlo,monospace}
.rx-num{font-variant-numeric:tabular-nums}

.rx-sample{background:var(--band);color:var(--band-ink);border:1px solid var(--band-rule);
  border-radius:3px;padding:11px 15px;font-size:13.5px}
.rx-head{display:flex;flex-direction:column;gap:7px}
.rx-eyebrow{font-size:11.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--ink-3);font-weight:500}
.rx-title{font-size:28px;line-height:1.2;font-weight:600;margin:0;text-wrap:balance}
.rx-sub{color:var(--ink-2);font-size:14px;margin:0}

.rx-tabs{display:flex;flex-wrap:wrap;gap:14px;align-items:flex-end}
.rx-pick{display:flex;flex-direction:column;gap:4px}
.rx-pick label{font-size:11.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-3);font-weight:600}
.rx-pick select{font:inherit;font-size:14px;padding:6px 10px;border:1px solid var(--rule);
  border-radius:3px;background:var(--surface);color:var(--ink);min-width:170px}
.rx-pick select:focus-visible{outline:2px solid var(--up);outline-offset:2px}
.rx-tab{font:inherit;font-size:13px;padding:5px 13px;border:1px solid var(--rule);
  background:var(--surface);color:var(--ink-2);border-radius:3px;cursor:pointer}
.rx-tab:hover{background:var(--hover)}
.rx-tab[aria-selected="true"]{background:var(--ink);color:var(--surface);border-color:var(--ink);font-weight:500}
.rx-tab:focus-visible{outline:2px solid var(--up);outline-offset:2px}

.rx-panel{background:var(--surface);border:1px solid var(--rule);border-radius:4px;padding:24px 26px;
  display:flex;flex-direction:column;gap:20px}
.rx-stats{display:flex;flex-wrap:wrap;gap:12px 40px;align-items:flex-end}
.rx-stat{display:flex;flex-direction:column;gap:2px}
.rx-stat .k{font-size:11.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-3);font-weight:600}
.rx-stat .v{font-size:24px;font-weight:600;line-height:1.1}
.rx-stat.lead .v{font-size:42px;letter-spacing:-.02em}
.rx-stat .v.up{color:var(--up)} .rx-stat .v.down{color:var(--down)}
.rx-stat .n{font-size:12.5px;color:var(--ink-3)}

.rx-meter{display:flex;flex-direction:column;gap:7px}
.rx-track{position:relative;height:8px;background:var(--rule);border-radius:4px}
.rx-fill{position:absolute;top:0;bottom:0;border-radius:4px;background:var(--up)}
.rx-fill.down{background:var(--down)}
.rx-pin{position:absolute;top:-5px;width:3px;height:18px;border-radius:1px;background:var(--ink);
  transform:translateX(-1.5px)}
.rx-ends{display:flex;justify-content:space-between;font-size:12px;color:var(--ink-3)}

.rx-formula{background:var(--plane);border:1px solid var(--rule);border-radius:3px;
  padding:11px 14px;font-size:13px;overflow-x:auto;white-space:nowrap}
.rx-formula .k{color:var(--ink-3);margin-right:9px}

.rx-actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.rx-btn{font:inherit;font-size:12.5px;padding:5px 12px;border:1px solid var(--rule);
  background:var(--surface);color:var(--ink-2);border-radius:3px;cursor:pointer}
.rx-btn:hover{background:var(--hover)} .rx-btn:focus-visible{outline:2px solid var(--up);outline-offset:2px}
.rx-count{font-size:12.5px;color:var(--ink-3);margin-left:auto}

.rx-tablewrap{overflow-x:auto;border:1px solid var(--rule);border-radius:4px}
.rx table{border-collapse:collapse;width:100%;font-size:13.5px}
.rx th{text-align:left;font-weight:600;font-size:11.5px;letter-spacing:.07em;text-transform:uppercase;
  color:var(--ink-3);padding:10px 14px;border-bottom:1px solid var(--rule);white-space:nowrap;background:var(--surface)}
.rx td{padding:9px 14px;border-bottom:1px solid var(--rule);color:var(--ink-2)}
.rx tr:last-child td{border-bottom:0}
.rx tbody tr{cursor:pointer}
.rx tbody tr:hover{background:var(--hover)}
.rx tbody tr.on{background:color-mix(in srgb, var(--up) 7%, transparent)}
.rx td.name{color:var(--ink)}
.rx td.n{text-align:right;white-space:nowrap}
.rx td.n.up{color:var(--up)} .rx td.n.down{color:var(--down)}
.rx td.chk{width:34px;padding-right:0}
.rx input[type=checkbox]{width:15px;height:15px;accent-color:var(--up);cursor:pointer;margin:0;display:block}
.rx td.ref{font-size:12px;color:var(--ink-3)}

.rx-sec-h{font-size:12px;letter-spacing:.09em;text-transform:uppercase;color:var(--ink-3);
  font-weight:600;margin:0 0 3px}
.rx-sec-n{color:var(--ink-2);font-size:13.5px;margin:0 0 14px;max-width:68ch}
.rx-struct-list{display:flex;flex-direction:column;gap:14px}
.rx-struct-row{display:flex;flex-direction:column;gap:5px;border-left:2px solid var(--down);padding-left:12px}
.rx-struct-head{font-size:13.5px;color:var(--ink)}
.rx-note{display:flex;gap:10px;font-size:13.5px;color:var(--ink-2);padding-left:12px;
  border-left:2px solid var(--rule);max-width:72ch}
.rx-notes{display:flex;flex-direction:column;gap:9px}
.rx-foot{color:var(--ink-3);font-size:12.5px;border-top:1px solid var(--rule);padding-top:14px;
  display:flex;flex-direction:column;gap:4px}
@media (max-width:620px){
  .rx-stat.lead .v{font-size:32px} .rx-stat .v{font-size:19px}
  .rx-wrap{padding-block:26px 40px} .rx-panel{padding:18px}
}
"""

JS = r"""
(function () {
  var DATA = window.__ROA__, cur = 0, on = {};

  function flat(a){var o=[];a.forEach(function(v){Array.isArray(v)?o.push.apply(o,flat(v)):o.push(v)});return o;}
  function num(v){
    if (v===null||v===undefined||v==="") return 0;
    if (typeof v==="boolean") return v?1:0;
    if (typeof v==="number") return v;
    var n=parseFloat(String(v).replace(/,/g,""));
    if (isNaN(n)) throw new Error("not a number: "+v);
    return n;
  }
  function txt(v){
    if (v===null||v===undefined) return "";
    if (typeof v==="boolean") return v?"TRUE":"FALSE";
    if (typeof v==="number" && Number.isInteger(v)) return String(v);
    return String(v);
  }
  function nums(a){return flat(a).filter(function(v){return typeof v==="number"||typeof v==="boolean"}).map(num);}
  // Excel's comparison rules: a blank equals both "" and 0; text never equals a number.
  function cmp(o,a,b){
    if (a===null&&b===null){a=0;b=0;}
    else {
      if (a===null) a = (typeof b==="string")?"":((typeof b==="boolean")?false:0);
      if (b===null) b = (typeof a==="string")?"":((typeof a==="boolean")?false:0);
    }
    var at=typeof a==="string", bt=typeof b==="string";
    if (at&&bt){ a=a.toLowerCase(); b=b.toLowerCase(); }
    else if (at!==bt){
      if (o==="=") return false;
      if (o==="<>") return true;
      a=at?1:0; b=bt?1:0;
    } else { a=num(a); b=num(b); }
    switch(o){case "=":return a===b;case "<>":return a!==b;case "<":return a<b;
              case ">":return a>b;case "<=":return a<=b;default:return a>=b;}
  }

  var FN = {
    SUM:function(a){return nums(a).reduce(function(s,v){return s+v},0)},
    AVERAGE:function(a){var n=nums(a);return n.length?n.reduce(function(s,v){return s+v},0)/n.length:0},
    MIN:function(a){var n=nums(a);return n.length?Math.min.apply(null,n):0},
    MAX:function(a){var n=nums(a);return n.length?Math.max.apply(null,n):0},
    COUNT:function(a){return nums(a).length},
    ABS:function(a){return Math.abs(num(a[0]))},
    SQRT:function(a){return Math.sqrt(num(a[0]))},
    POWER:function(a){return Math.pow(num(a[0]),num(a[1]))},
    PRODUCT:function(a){var n=nums(a);return n.length?n.reduce(function(s,v){return s*v},1):0},
    SIGN:function(a){var v=num(a[0]);return v>0?1:(v<0?-1:0)},
    ROUND:function(a){var d=Math.pow(10,num(a[1]));return Math.round(num(a[0])*d)/d},
    ROUNDUP:function(a){var d=Math.pow(10,num(a[1]));return Math.ceil(num(a[0])*d)/d},
    ROUNDDOWN:function(a){var d=Math.pow(10,num(a[1]));return Math.floor(num(a[0])*d)/d},
    MID:function(a){var st=Math.trunc(num(a[1]));
      if (st<1) throw new Error("MID: start position must be 1 or more");
      return txt(a[0]).substr(st-1, Math.max(Math.trunc(num(a[2])),0));},
    LEFT:function(a){return txt(a[0]).slice(0, a.length>1?Math.trunc(num(a[1])):1)},
    RIGHT:function(a){var n=a.length>1?Math.trunc(num(a[1])):1; return n<=0?"":txt(a[0]).slice(-n)},
    LEN:function(a){return txt(a[0]).length},
    TRIM:function(a){return txt(a[0]).split(/\s+/).filter(Boolean).join(" ")},
    UPPER:function(a){return txt(a[0]).toUpperCase()},
    LOWER:function(a){return txt(a[0]).toLowerCase()},
    VALUE:function(a){return num(txt(a[0]))},
    CONCATENATE:function(a){return flat(a).map(txt).join("")},
    CONCAT:function(a){return flat(a).map(txt).join("")},
    N:function(a){return num(a[0])},
    T:function(a){return (typeof a[0]==="string")?a[0]:""}
  };

  function ev(n, vals, defs, memo) {
    if (n.k === "r") {
      if (memo[n.i] !== undefined) return memo[n.i];
      return (memo[n.i] = ev(defs[n.i], vals, defs, memo));
    }
    switch (n.k) {
      case "z": return null;                       // a blank cell, which is not the number zero
      case "n": case "s": return n.v;
      case "p": { var v = vals[n.id]; return (v===null||v===undefined) ? null : v; }
      case "l": return n.a.map(function(x){return ev(x,vals,defs,memo)});
      case "u":
        if (n.o==="%") return num(ev(n.a[0],vals,defs,memo))/100;
        return n.o==="-" ? -num(ev(n.a[0],vals,defs,memo)) : num(ev(n.a[0],vals,defs,memo));
      case "b": {
        var o=n.o;
        if (o==="&") return txt(ev(n.a[0],vals,defs,memo))+txt(ev(n.a[1],vals,defs,memo));
        var x=ev(n.a[0],vals,defs,memo), y=ev(n.a[1],vals,defs,memo);
        if (o==="="||o==="<>"||o==="<"||o===">"||o==="<="||o===">=") return cmp(o,x,y);
        var a=num(x), b=num(y);
        if (o==="+") return a+b;
        if (o==="-") return a-b;
        if (o==="*") return a*b;
        if (o==="/") { if (b===0) throw new Error("division by zero"); return a/b; }
        if (o==="^") return Math.pow(a,b);
        throw new Error("operator "+o);
      }
      case "f": {
        if (n.o==="IF") {
          var c=ev(n.a[0],vals,defs,memo);
          var t=(typeof c==="boolean")?c:(c===null?false:num(c)!==0);
          return t?ev(n.a[1],vals,defs,memo):(n.a.length>2?ev(n.a[2],vals,defs,memo):false);
        }
        if (n.o==="IFERROR"||n.o==="IFNA") {
          try { return ev(n.a[0],vals,defs,memo); }
          catch(e){ if (e && e.unsupported) throw e; return ev(n.a[1],vals,defs,memo); }
        }
        var f=FN[n.o];
        if (!f) { var err=new Error(n.o+"() not implemented"); err.unsupported=true; throw err; }
        return f(n.a.map(function(x){return ev(x,vals,defs,memo)}));
      }
    }
    throw new Error("node "+n.k);
  }

  function roaFor(v, picked) {
    var vals={};
    v.components.forEach(function(c){ vals[c.id] = picked[c.id] ? c.new : c.old; });
    var t = v.tree;
    return ev(t.root, vals, t.defs, {});
  }

  var bps = function(x){
    if (Math.abs(x) < 0.05) return "0.0 bps";
    return (x > 0 ? "+" : "−") + Math.abs(x).toFixed(1) + " bps";
  };
  var pct = function(x){ return (x*100).toFixed(4) + "%"; };
  var money = function(x){ return (x>=0?"+":"−") + Math.abs(x).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2}); };

  function el(id){ return document.getElementById(id); }

  function render() {
    var v = DATA.vintages[cur];
    var picked = on[v.name] || (on[v.name] = {});
    var scenario = roaFor(v, picked);
    var moved = (scenario - v.roaOld) * 10000;
    var total = (v.roaNew - v.roaOld) * 10000;
    var nsel = v.components.filter(function(c){return picked[c.id]}).length;

    el("rx-old").textContent = pct(v.roaOld);
    el("rx-new").textContent = pct(v.roaNew);
    el("rx-scn").textContent = pct(scenario);
    var lead = el("rx-lead");
    lead.textContent = bps(moved);
    lead.className = "v roa-num " + (Math.abs(moved) < 0.05 ? "" : (moved > 0 ? "up" : "down"));
    el("rx-of").textContent = total ? Math.round(moved / total * 100) + "% of the full move ("
      + bps(total) + ")" : "no overall change";
    el("rx-count").textContent = nsel + " of " + v.components.length + " applied";

    var lo = Math.min(v.roaOld, v.roaNew), hi = Math.max(v.roaOld, v.roaNew), span = (hi-lo)||1;
    var p = Math.max(0, Math.min(100, (scenario - lo) / span * 100));
    var startPct = (v.roaOld - lo) / span * 100;
    var fill = el("rx-fill");
    fill.style.left = Math.min(startPct, p) + "%";
    fill.style.width = Math.abs(p - startPct) + "%";
    fill.className = "rx-fill" + (moved < 0 ? " down" : "");
    el("rx-pin").style.left = p + "%";

    v.components.forEach(function(c){
      var tr = el("row-" + btoa(c.id).replace(/=/g,""));
      if (tr) { tr.classList.toggle("on", !!picked[c.id]);
                tr.querySelector("input").checked = !!picked[c.id]; }
    });
  }

  function buildPanel() {
    var v = DATA.vintages[cur];
    var rows = v.components.map(function(c){
      var rid = "row-" + btoa(c.id).replace(/=/g,"");
      return '<tr id="'+rid+'" data-id="'+encodeURIComponent(c.id)+'">'
        + '<td class="chk"><input type="checkbox" id="cb-'+rid+'" aria-label="Apply '+c.label+'"></td>'
        + '<td class="name">'+c.label+'</td>'
        + '<td class="ref rx-mono">'+c.refOld+(c.refOld!==c.refNew?" → "+c.refNew:"")+'</td>'
        + '<td class="n rx-num rx-mono">'+c.old.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})+'</td>'
        + '<td class="n rx-num rx-mono">'+c.new.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})+'</td>'
        + '<td class="n rx-num rx-mono '+(c.delta>=0?"up":"down")+'">'+money(c.delta)+'</td>'
        + '<td class="n rx-num rx-mono '+(c.solo>=0?"up":"down")+'">'+bps(c.solo)+'</td></tr>';
    }).join("");
    el("rx-body").innerHTML = rows || '<tr><td colspan="7">Nothing feeding this ROA changed.</td></tr>';

    el("rx-f-old").textContent = v.formulaOld;
    el("rx-f-new").textContent = v.formulaNew;
    el("rx-f-newrow").hidden = !v.formulaChanged;
    el("rx-cellref").textContent = v.sheet + "!" + v.refOld + "  →  " + v.sheet + "!" + v.refNew;

    var notes = (v.notes || []);
    el("rx-notes").innerHTML = notes.map(function(n){return '<div class="rx-note">'+n+'</div>'}).join("");
    el("rx-notes-sec").hidden = notes.length === 0;

    var st = v.structural || [];
    var seen = {}, uniqSt = [];
    st.forEach(function(x){ var k = x.label+"|"+x.kind+"|"+x.detail;
                            if(!seen[k]){seen[k]=1; uniqSt.push(x);} });
    el("rx-struct-sec").hidden = uniqSt.length === 0;
    el("rx-struct").innerHTML = uniqSt.map(function(x){
      return '<div class="rx-struct-row"><div class="rx-struct-head">'+x.detail+'</div>'
        + '<div class="rx-formula rx-mono"><span class="k">old</span>'+x.old+'</div>'
        + '<div class="rx-formula rx-mono"><span class="k">new</span>'+x.new+'</div></div>';
    }).join("");
    el("rx-gap").textContent = (v.gap === null || Math.abs(v.gap) < 0.05)
      ? "" : ("Unattributed: " + (v.gap>0?"+":"−") + Math.abs(v.gap).toFixed(1) + " bps");

    el("rx-body").querySelectorAll("tr[data-id]").forEach(function(tr){
      var id = decodeURIComponent(tr.getAttribute("data-id"));
      function toggle(){ var p = on[DATA.vintages[cur].name]; p[id] = !p[id]; render(); }
      tr.addEventListener("click", function(e){ if (e.target.tagName !== "INPUT") toggle(); });
      tr.querySelector("input").addEventListener("change", toggle);
    });
    render();
  }

  function setAll(state) {
    var v = DATA.vintages[cur], p = on[v.name] || (on[v.name] = {});
    v.components.forEach(function(c){ p[c.id] = state; });
    render();
  }

  function uniq(a){ var seen={}, o=[]; a.forEach(function(x){ if(!seen[x]){seen[x]=1;o.push(x);} }); return o; }

  function fillItems(keep){
    var g = el("rx-group").value;
    var opts = DATA.vintages.map(function(v,i){return {v:v,i:i}})
                            .filter(function(r){return r.v.group === g});
    el("rx-item").innerHTML = opts.map(function(r){
      return '<option value="'+r.i+'">'+r.v.item+'</option>'; }).join("");
    // hold the month steady when the sheet changes - you are usually comparing like for like
    var same = opts.filter(function(r){ return r.v.item === keep; });
    cur = (same.length ? same[0].i : (opts.length ? opts[0].i : 0));
    el("rx-item").value = String(cur);
  }

  document.addEventListener("DOMContentLoaded", function(){
    var groups = uniq(DATA.vintages.map(function(v){return v.group}));
    el("rx-group").innerHTML = groups.map(function(g){
      return '<option value="'+g+'">'+g+'</option>'; }).join("");
    el("rx-group").addEventListener("change", function(){
      fillItems(DATA.vintages[cur] && DATA.vintages[cur].item); buildPanel(); });
    el("rx-item").addEventListener("change", function(){ cur = +el("rx-item").value; buildPanel(); });
    el("rx-tabs").hidden = DATA.vintages.length < 2;
    fillItems(null);
    el("rx-all").addEventListener("click", function(){ setAll(true); });
    el("rx-none").addEventListener("click", function(){ setAll(false); });
    buildPanel();
  });
})();
"""


def render_html(payload: Dict[str, Any], title: str = "ROA component explorer",
                subtitle: str = "", sample: bool = False, fragment: bool = True) -> str:
    data = json.dumps(payload, allow_nan=False, separators=(",", ":"))
    sample_band = (
        '<div class="rx-sample"><strong>Sample data.</strong> These figures are invented to show '
        'the format. They are not from any real workbook, and nothing on this page should be read '
        'as a financial result.</div>' if sample else "")

    body = f"""<div class="rx"><div class="rx-wrap">
{sample_band}
<header class="rx-head">
  <div class="rx-eyebrow">Return on assets &middot; component explorer</div>
  <h1 class="rx-title">{_esc(title)}</h1>
  <p class="rx-sub">{_esc(subtitle)}</p>
</header>

<div class="rx-tabs" id="rx-tabs">
  <div class="rx-pick"><label for="rx-group">Sheet</label><select id="rx-group"></select></div>
  <div class="rx-pick"><label for="rx-item">Month</label><select id="rx-item"></select></div>
</div>

<section class="rx-panel">
  <div class="rx-stats">
    <div class="rx-stat lead"><span class="k">Selected impact</span>
      <span class="v roa-num" id="rx-lead">&mdash;</span>
      <span class="n" id="rx-of"></span></div>
    <div class="rx-stat"><span class="k">Old ROA</span>
      <span class="v rx-num rx-mono" id="rx-old">&mdash;</span><span class="n">current process</span></div>
    <div class="rx-stat"><span class="k">With selection</span>
      <span class="v rx-num rx-mono" id="rx-scn">&mdash;</span><span class="n">recomputed from the formula</span></div>
    <div class="rx-stat"><span class="k">New ROA</span>
      <span class="v rx-num rx-mono" id="rx-new">&mdash;</span><span class="n">snow process</span></div>
  </div>

  <div class="rx-meter">
    <div class="rx-track"><div class="rx-fill" id="rx-fill"></div><div class="rx-pin" id="rx-pin"></div></div>
    <div class="rx-ends"><span>old</span><span>new</span></div>
  </div>

  <div>
    <div class="rx-formula rx-mono"><span class="k">cell</span><span id="rx-cellref"></span></div>
    <div class="rx-formula rx-mono" style="margin-top:6px"><span class="k">old</span><span id="rx-f-old"></span></div>
    <div class="rx-formula rx-mono" id="rx-f-newrow" style="margin-top:6px" hidden>
      <span class="k">new</span><span id="rx-f-new"></span></div>
  </div>
</section>

<section>
  <h2 class="rx-sec-h">Components that changed</h2>
  <p class="rx-sec-n">Tick any combination to re-evaluate the real formula with those inputs switched
     to the new process. <strong>Solo</strong> is what each one does on its own &mdash; they will not
     add up to the total, because ROA is a ratio and its drivers interact.</p>
  <div class="rx-actions">
    <button class="rx-btn" id="rx-all" type="button">Select all</button>
    <button class="rx-btn" id="rx-none" type="button">Clear</button>
    <span class="rx-count" id="rx-count"></span>
  </div>
  <div class="rx-tablewrap" style="margin-top:10px"><table>
    <thead><tr><th></th><th>Component</th><th>Cell</th><th class="n">Old</th><th class="n">New</th>
      <th class="n">Change</th><th class="n">Solo effect</th></tr></thead>
    <tbody id="rx-body"></tbody>
  </table></div>
</section>

<section id="rx-struct-sec" hidden>
  <h2 class="rx-sec-h">The calculation itself changed</h2>
  <p class="rx-sec-n">These cells do not compute the same thing in both workbooks, so part of the
     move belongs to none of the components above. <span id="rx-gap"></span></p>
  <div class="rx-struct-list" id="rx-struct"></div>
</section>

<section id="rx-notes-sec" hidden>
  <h2 class="rx-sec-h">Before you rely on this</h2>
  <div class="rx-notes" id="rx-notes"></div>
</section>

<footer class="rx-foot">
  <div>Component names come from column B of the row each figure sits on. Cell references are shown
       in both workbooks where the inserted row moves them.</div>
  <div>Values only &mdash; the formula is read from the workbook and re-evaluated; charts ignored.
       Generated {_esc(payload.get('generated', ''))}.</div>
  {'<div><strong>Sample data, not a real result.</strong></div>' if sample else ''}
</footer>
</div></div>"""

    fonts = ('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
             'family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">')
    head = (f"<title>{_esc(title)}</title>\n{fonts}\n<style>{CSS}</style>")
    scripts = f'<script>window.__ROA__={data};</script>\n<script>{JS}</script>'

    if fragment:
        return f"{head}\n{body}\n{scripts}"
    return (f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">{head}'
            f'<style>html,body{{margin:0;padding:0}}</style></head><body>{body}{scripts}</body></html>')


def write_html(payload: Dict[str, Any], path: str | Path, **kw) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_html(payload, fragment=False, **kw), encoding="utf-8")
    return out.resolve()
