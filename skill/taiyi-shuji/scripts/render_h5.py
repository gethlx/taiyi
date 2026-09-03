#!/usr/bin/env python3
"""Render one validated Taiyi Shuji record as a self-contained read-only H5."""

from __future__ import annotations

import argparse
import base64
import html
import json
import os
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def paragraph(value: str) -> str:
    return "".join(f"<p>{esc(part)}</p>" for part in value.splitlines() if part.strip())


def validate_record(record: dict[str, Any], authoritative: dict[str, Any]) -> None:
    import sys

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from tools.analysis_contract import validate_committed_analysis

    errors = validate_committed_analysis(record, authoritative, workspace=ROOT)
    if errors:
        raise ValueError("record validation failed: " + "; ".join(errors))


def render_formulas(formulas: list[dict[str, Any]]) -> str:
    if not formulas:
        return '<p class="muted">本轮没有方剂对象。</p>'
    cards: list[str] = []
    for formula in formulas:
        ingredients = "".join(
            f"<li>{esc(item['raw_text'])}</li>" for item in formula["composition"]
        )
        name = formula.get("name", "无方名")
        extra = "".join(
            f"<p><strong>{esc(label)}</strong>{esc(formula[key])}</p>"
            for key, label in (
                ("preparation_text", "制备："),
                ("administration_text", "煎服："),
            )
            if key in formula
        )
        cards.append(
            '<article class="formula-card">'
            f"<div class=\"formula-head\"><h3>{esc(name)}</h3>"
            f"<span>{esc(formula['role'])}</span></div>"
            f"<ul>{ingredients}</ul>{extra}</article>"
        )
    return "".join(cards)


def render_sources(sources: list[dict[str, Any]]) -> str:
    if not sources:
        return '<p class="muted">本轮没有取回直接原文。</p>'
    items: list[str] = []
    for item in sources:
        body = (
            f"<p class=\"quote\">{esc(item['excerpt'])}</p>"
            f"<p class=\"meta\">{esc(item['source_path'])} · "
            f"行 {item['start_line']}–{item['end_line']}</p>"
        )
        items.append(
            f'<details class="source"><summary>原文来源 · {esc(item["title"])}</summary>'
            f"{body}</details>"
        )
    return "".join(items)


def build_html(record: dict[str, Any]) -> str:
    subject = record["input"]["subject"]
    reasoning = record["reasoning"]
    outcome = record["outcome"]
    role_labels = {
        "r0": "R0 元典关系",
        "r1": "R1 辨证求机",
        "r2": "R2 治法方药",
        "red_team": "隔离红方",
        "stage_c": "Stage C 综合",
    }
    reasoning_html = "".join(
        f'<article class="reason-card" id="{role}"><h3>{esc(role_labels[role])}</h3>'
        f"{paragraph(reasoning[role]['text'])}</article>"
        for role in role_labels
        if role in reasoning
    )
    fact_lists = (
        "<div class=\"fact-grid\"><article><h3>已确认</h3><ul>"
        + "".join(f"<li>{esc(item)}</li>" for item in record["input"]["confirmed_facts"])
        + "</ul></article><article><h3>含混／待核</h3><ul>"
        + (
            "".join(f"<li>{esc(item)}</li>" for item in record["input"]["ambiguous_facts"])
            or "<li>无</li>"
        )
        + "</ul></article></div>"
    )
    days = "".join(
        '<article class="day-card">'
        f"<span>Day {item['day']}</span><p>{esc(item['text'])}</p></article>"
        for item in outcome["day_progression"]
    )
    risks = "".join(f"<li>{esc(item)}</li>" for item in outcome["risks"]) or "<li>无</li>"
    questions = (
        "".join(f"<li>{esc(item)}</li>" for item in outcome["minimum_questions"])
        or "<li>无</li>"
    )
    conflicts = "".join(
        f"<li>{esc(item)}</li>" for item in reasoning["unresolved_conflicts"]
    ) or "<li>无未解实质冲突</li>"
    record_bytes = json.dumps(record, ensure_ascii=False, indent=2).encode("utf-8")
    download = base64.b64encode(record_bytes).decode("ascii")
    return f"""<!doctype html>
<html lang="zh-CN" data-run-id="{esc(record['run_id'])}" data-result-id="{esc(outcome['result_id'])}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{esc(subject['label'])}｜太乙枢机</title>
<style>
:root{{--ink:#18221d;--muted:#66736b;--paper:#f6f2e8;--card:#fffdf7;--line:#d8d1c2;
--jade:#236a54;--jade-soft:#e5f0ea;--cinnabar:#a44732;--gold:#b88a3d}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);
font-family:"Songti SC","Noto Serif CJK SC",serif;line-height:1.7}}
.shell{{max-width:760px;margin:auto;padding:18px 16px 64px}}header{{padding:28px 20px;
background:linear-gradient(145deg,#143e33,#275f4d);color:#fff;border-radius:0 0 24px 24px;
box-shadow:0 10px 30px #173d3026}}.brand{{letter-spacing:.18em;font-size:.82rem;opacity:.8}}
h1{{font-size:1.9rem;line-height:1.25;margin:.5rem 0}}h2{{font-size:1.35rem;margin:.2rem 0 1rem}}
h3{{font-size:1.05rem;margin:.15rem 0 .6rem}}.lead{{font-size:1.04rem;margin:.6rem 0}}
.badges{{display:flex;flex-wrap:wrap;gap:7px;margin-top:14px}}.badges span,.formula-head span{{
font-family:ui-monospace,monospace;font-size:.72rem;padding:4px 8px;border-radius:99px;
background:#ffffff1f;border:1px solid #ffffff42}}main{{display:grid;gap:14px;margin-top:18px}}
section,.relationship-graph{{margin:0;background:var(--card);border:1px solid var(--line);
border-radius:18px;padding:18px;box-shadow:0 5px 18px #594d3410}}.meta{{color:var(--muted);
font-size:.82rem}}.muted{{color:var(--muted)}}.raw{{border-left:3px solid var(--gold);
padding-left:14px}}ul,ol{{padding-left:1.25rem}}.fact-grid{{display:grid;gap:10px}}
.fact-grid article,.reason-card,.formula-card,.day-card,.node{{background:#fff;border:1px solid #e7e0d4;
border-radius:13px;padding:14px;margin-top:10px}}.reason-card h3,.formula-head h3{{color:var(--jade)}}
.formula-head{{display:flex;justify-content:space-between;gap:10px;align-items:start}}
.formula-head span{{background:var(--jade-soft);color:var(--jade);border-color:#bdd4c8}}
.days{{display:grid;gap:9px}}.day-card span{{display:inline-block;color:#fff;background:var(--jade);
border-radius:99px;padding:2px 10px;font-family:ui-monospace,monospace;font-size:.8rem}}
details.source{{border-top:1px solid var(--line);padding:11px 0}}details.source:first-child{{border-top:0}}
summary{{cursor:pointer;color:var(--jade);font-weight:700}}.quote{{font-size:1.08rem;
border-left:3px solid var(--cinnabar);padding-left:13px}}.nodes{{display:grid;gap:9px}}
.node h3{{color:var(--cinnabar)}}.edges{{list-style:none;padding:0;display:grid;gap:8px}}
.edges li{{display:grid;grid-template-columns:1fr auto 1fr;gap:7px;align-items:center;
font-size:.8rem;background:var(--jade-soft);border-radius:10px;padding:9px}}
.edges b{{color:var(--jade);font-weight:600}}.edge-to{{text-align:right}}
.download{{display:inline-block;color:#fff;background:var(--cinnabar);padding:10px 15px;
border-radius:12px;text-decoration:none;font-weight:700}}footer{{color:var(--muted);font-size:.78rem;
padding:20px 6px}}@media(min-width:620px){{.fact-grid{{grid-template-columns:1fr 1fr}}
.nodes{{grid-template-columns:repeat(2,1fr)}}}}
</style>
</head>
<body>
<header><div class="shell"><div class="brand">太乙枢机 · 只读正式报告</div>
<h1>{esc(subject['label'])}</h1><p class="lead">{esc(outcome['summary'])}</p>
<div class="badges"><span>{esc(record['task_type'])}</span><span>{esc(outcome['identity'])}</span>
<span>{esc(record['run_id'])}</span><span>{esc(outcome['result_id'])}</span></div></div></header>
<div class="shell"><main>
<section><h2>本轮输入</h2><p class="raw">{esc(record['input']['raw_text'])}</p>{fact_lists}</section>
<section><h2>推理主链与审计</h2>{reasoning_html}</section>
<section><h2>方剂身份</h2>{render_formulas(record['formulas'])}</section>
<section><h2>Day 1／2／3</h2><div class="days">{days or '<p class="muted">本任务不适用三日预测。</p>'}</div></section>
<section><h2>边界、风险与补问</h2><h3>未解冲突</h3><ul>{conflicts}</ul>
<h3>风险</h3><ul>{risks}</ul><h3>最小补问</h3><ol>{questions}</ol></section>
<section><h2>相关短原文与来源</h2>{render_sources(record['sources'])}</section>
<section><h2>同一作品</h2><p class="meta">报告与下载均绑定
<code>{esc(record['run_id'])}</code>／<code>{esc(outcome['result_id'])}</code>。</p>
<a class="download" download="{esc(record['run_id'])}.json"
href="data:application/json;base64,{download}">下载规范记录 JSON</a></section>
</main><footer>本页只读，不接收医学输入，不改变病例或沙盘，不调用模型。
补充、纠正与复察请回到宿主 Agent 对话。</footer></div>
</body></html>"""


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            temp_name = handle.name
        os.replace(temp_name, path)
    except Exception:
        if temp_name is not None:
            Path(temp_name).unlink(missing_ok=True)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--authoritative", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    record = load_object(args.record)
    authoritative = load_object(args.authoritative)
    validate_record(record, authoritative)
    requested_output = args.output.resolve()
    if not requested_output.is_relative_to(ROOT):
        raise ValueError("h5 output path escapes project root")
    atomic_write(requested_output, build_html(record))
    print(
        f"PASS: rendered read-only H5 {requested_output.relative_to(ROOT)} "
        f"for {record['run_id']}/{record['outcome']['result_id']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
