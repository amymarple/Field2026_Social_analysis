"""_generate_analyses.py — render the human navigation layer from analyses/registry.yaml.

Builds one card per scientific question (analyses/<direction>/<id>.md) + the top-level map
(analyses/README.md), filling cohort coverage + report/figure links by scanning results/ and archive/.
INDEX ONLY — no implementation code is copied in; every field is a pointer or a status.

Run after a cohort's pipelines finish:  python analyses/_generate_analyses.py
"""
from __future__ import annotations

import glob as _glob
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
ANALYSES = ROOT / "analyses"
RESULTS = ROOT / "results"
ARCHIVE = ROOT / "archive"

MARK = {"confirmed": "✅", "candidate": "⚠️", "blocked": "⛔", "retracted": "❌"}
VERDICT_WORD = {"confirmed": "confirmed", "candidate": "candidate",
                "blocked": "blocked (needs more data / another modality)", "retracted": "retracted / falsified"}


def _cohorts() -> list[str]:
    return sorted(p.name for p in RESULTS.iterdir() if p.is_dir()) if RESULTS.exists() else []


def _match_reports(base: Path, cohort: str, direction: str, report_glob: str) -> list[Path]:
    if not report_glob:
        return []
    d = base / cohort / direction / "reports"
    return sorted(Path(p) for p in _glob.glob(str(d / report_glob)))


def _match_figures(cohort: str, direction: str, report_glob: str) -> list[Path]:
    if not report_glob:
        return []
    stem = report_glob.rstrip("*")
    d = RESULTS / cohort / direction / "figures"
    if not d.exists():
        return []
    return sorted(p for p in d.iterdir() if p.name.startswith(stem.split("_2026")[0]) or stem in p.name)


def _rel_from_card(direction: str, target: Path) -> str:
    """Relative link from analyses/<direction>/<id>.md (depth 2 under repo root) to a repo path."""
    return "../../" + target.relative_to(ROOT).as_posix()


def _coverage(q: dict) -> dict[str, dict]:
    cov: dict[str, dict] = {}
    for c in _cohorts():
        live = _match_reports(RESULTS, c, q["direction"], q.get("report_glob", ""))
        arch = _match_reports(ARCHIVE, c, q["direction"], q.get("report_glob", ""))
        if live or arch or not q.get("report_glob"):
            cov[c] = {"live": live, "archive": arch, "figures": _match_figures(c, q["direction"], q.get("report_glob", ""))}
    return cov


def _card(q: dict) -> str:
    direction = q["direction"]
    verdict = q.get("verdict", "candidate")
    mark = MARK.get(verdict, "⚠️")
    cov = _coverage(q)
    L = [f"# {mark} {q['question']}", "",
         f"**Direction:** `{direction}` · **id:** `{q['id']}`  ", ""]

    L += ["## 1. Verdict", "", f"{mark} **{VERDICT_WORD.get(verdict, verdict)}.** {q.get('claim','').strip()}", ""]

    L += ["## 2. Cohort coverage", ""]
    if cov:
        L += ["| Cohort | Canonical report(s) | Superseded (archive) |", "|---|---|---|"]
        for c, info in cov.items():
            live = ", ".join(f"[{p.name}]({_rel_from_card(direction, p)})" for p in info["live"]) or "—"
            arch = ", ".join(f"[{p.name}]({_rel_from_card(direction, p)})" for p in info["archive"]) or "—"
            L.append(f"| `{c}` | {live} | {arch} |")
        L.append("")
    else:
        L += ["_No in-repo canonical report yet (bulk run is off-repo; see the run_manifest / change log)._", ""]
    L += [f"**Evidence:** {q.get('evidence','').strip() or '—'}", ""]

    L += ["## 3. Canonical driver", "", f"`{q['driver']}`", ""]

    L += ["## 4. Canonical report", ""]
    reports = [p for info in cov.values() for p in info["live"]]
    if reports:
        for p in reports:
            L.append(f"- [{p.name}]({_rel_from_card(direction, p)})")
    else:
        L.append("- _(off-repo run; see change log below)_")
    L.append("")

    L += ["## 5. Figures", ""]
    figs = [p for info in cov.values() for p in info["figures"]]
    if figs:
        for p in figs:
            L.append(f"- [{p.name}]({_rel_from_card(direction, p)})")
    else:
        L.append("- _Dense figure dumps stay off-repo under `$FIELD2026_ANALYSIS_OUT_ROOT/<cohort>/`; the run_manifest points at them._")
    L.append("")

    L += ["## 6. Blockers", ""]
    for b in q.get("blockers", []) or ["—"]:
        L.append(f"- {b}")
    L.append("")

    L += ["## 7. Superseded claims", "", (q.get("superseded") or "_None._"), ""]
    if q.get("changelog"):
        L.append(f"Change log: [`{q['changelog']}`](../../{q['changelog']})")
        L.append("")

    L += ["## 8. Exact rerun command", "", "```bash", q.get("rerun", "").strip(), "```", ""]

    L += ["---", f"*Status source: {q.get('status_ref','')} — see [`wiser/ANALYSIS_STATUS.md`](../../wiser/ANALYSIS_STATUS.md). "
          f"Generated from `analyses/registry.yaml`; do not hand-edit.*", ""]
    return "\n".join(L)


def _readme(questions: list[dict]) -> str:
    cohorts = _cohorts()
    L = ["# Analyses — navigate the science by question", "",
         "Every scientific question, its verdict, and which cohorts it is answered over. Click a question to",
         "open its card (canonical driver, report, figures, blockers, superseded claims, exact rerun command).",
         "**Generated from [`registry.yaml`](registry.yaml) — do not hand-edit.**", "",
         f"Cohorts present: {', '.join('`'+c+'`' for c in cohorts) or '(none)'}", ""]
    by_dir: dict[str, list[dict]] = {}
    for q in questions:
        by_dir.setdefault(q["direction"], []).append(q)
    for direction in sorted(by_dir):
        L += [f"## `{direction}`", "", "| Verdict | Question | Cohorts | Card |", "|---|---|---|---|"]
        for q in by_dir[direction]:
            mark = MARK.get(q.get("verdict", "candidate"), "⚠️")
            cov = ", ".join("`"+c+"`" for c in _coverage(q)) or "—"
            L.append(f"| {mark} | {q['question']} | {cov} | [{q['id']}]({direction}/{q['id']}.md) |")
        L.append("")
    L += ["---", "*Legend: ✅ confirmed · ⚠️ candidate · ⛔ blocked · ❌ retracted. Detail per WISER row in "
          "[`wiser/ANALYSIS_STATUS.md`](../wiser/ANALYSIS_STATUS.md).*", ""]
    return "\n".join(L)


def main() -> int:
    reg = yaml.safe_load((ANALYSES / "registry.yaml").read_text(encoding="utf-8"))
    questions = reg["questions"]
    n = 0
    for q in questions:
        d = ANALYSES / q["direction"]
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{q['id']}.md").write_text(_card(q), encoding="utf-8")
        n += 1
    (ANALYSES / "README.md").write_text(_readme(questions), encoding="utf-8")
    print(f"[analyses] wrote {n} cards + README across {len({q['direction'] for q in questions})} directions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
