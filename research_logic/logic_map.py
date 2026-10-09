"""Research-logic graph: validate, inspect and build the interactive map.

The graph YAML (research_logic/graphs/<id>.yaml) is the only place the research logic is written. This tool checks it
against the rules in research_logic/README.md and generates, from it alone:
  research_logic/maps/<id>.json   normalised graph (nodes, typed edges, rounds, conflicts, derived summaries)
  research_logic/maps/<id>.html   the interactive map (template research_logic/map_template.html, data embedded)

Usage (from the repo root; base Python + pyyaml):
  python research_logic/logic_map.py check  [--graph research_logic/graphs/sleep_2026c.yaml]
  python research_logic/logic_map.py build  [--graph ...] [--out-dir research_logic/maps]
  python research_logic/logic_map.py show   <node id | branch question id> [--graph ...]
  python research_logic/logic_map.py index  [--graph ...] [--type result] [--status candidate] [--branch q.x]
  python research_logic/logic_map.py figs   [--graph ...]   # Artifact `files` map {figs/<name>: repo path}
  python research_logic/logic_map.py --selftest

`check` exits 1 on any error (warnings do not fail). `build` runs `check` first and refuses to write on errors.
It does not compute statistics and never reads or writes analysis results; it only reads the cited source files to
verify the citations.
"""

import argparse
import copy
import hashlib
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
DEFAULT_GRAPH = HERE / "graphs" / "sleep_2026c.yaml"
TEMPLATE = HERE / "map_template.html"

NODE_TYPES = ("question", "hypothesis", "prediction", "analysis", "result", "judgment", "next_step", "basis")
STATUS = {
    "question": {"open", "answered", "parked"},
    "hypothesis": {"supported", "weakened", "rejected", "mixed", "open", "proposed", "untestable"},
    "prediction": {"held", "failed", "mixed", "open"},
    "result": {"established", "candidate", "unresolved", "rejected", "withdrawn", "superseded", "ledger"},
    "judgment": {"current", "superseded"},
    "next_step": {"proposed", "planned", "in_progress", "done", "dropped"},
}
EFFECTS = {"positive", "not_detected", "mixed", "descriptive"}  # not_detected is not "no effect"
INFERENCE = {"predictive", "association", "descriptive", "intervention"}
LEVELS = {"pattern", "mechanism"}
STRENGTH = {"established", "candidate"}
STAGES = {"now", "measurement", "next_stage_lfp", "needs_video"}
ANSWER_KEYS = ("aim", "answered", "supported_weakened", "indistinguishable", "next")
VERDICT_RELS = ("supports", "weakens", "cannot_distinguish")
ALLOWED = {  # relation -> (allowed source types, allowed target types)
    "proposes": ({"question", "result", "judgment", "hypothesis"}, {"question", "hypothesis", "prediction", "next_step"}),
    "tests": ({"analysis", "next_step"}, {"hypothesis", "prediction"}),
    "yields": ({"analysis"}, {"result"}),
    "supports": ({"result", "judgment"}, {"hypothesis", "prediction"}),
    "weakens": ({"result", "judgment"}, {"hypothesis", "prediction"}),
    "cannot_distinguish": ({"result", "judgment"}, {"hypothesis", "prediction"}),
    "depends_on": ({"result", "judgment", "analysis", "next_step"}, {"basis", "result", "analysis", "next_step"}),
    "revises": (None, None),      # same type on both ends
    "supersedes": (None, None),
}
IMG_EXT = {".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif"}
ID_RE = re.compile(r"^[a-z][a-z0-9_.-]*$")
ANCHOR_SLACK = 3  # an anchor may sit up to this many lines outside the cited range


# ----------------------------------------------------------------------------------------------- loading
def load_graph(path):
    with open(path, encoding="utf-8") as fh:
        g = yaml.safe_load(fh)
    if not isinstance(g, dict):
        raise SystemExit(f"{path}: not a YAML mapping")
    for key in ("meta", "files", "nodes", "conflicts", "rounds"):
        g.setdefault(key, [] if key in ("nodes", "conflicts", "rounds") else {})
    return g


def _norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[*`]", "", str(s))).strip()


def _lines(v):
    if isinstance(v, (list, tuple)):
        return int(v[0]), int(v[-1])
    return int(v), int(v)


class Checker:
    def __init__(self, g, root=REPO):
        self.g = g
        self.root = Path(root)
        self.errors, self.warnings = [], []
        self.nodes = {}
        self.edges = []
        self.figs = {}       # published name -> {path, cap, nodes}
        self.unmapped = []   # watched figures not linked to any node
        self._file_cache = {}

    def err(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)

    # ------------------------------------------------------------------- sources
    def _file_lines(self, rel):
        if rel not in self._file_cache:
            p = self.root / rel
            self._file_cache[rel] = p.read_text(encoding="utf-8", errors="replace").splitlines() if p.is_file() else None
        return self._file_cache[rel]

    def resolve_src(self, owner, s):
        files = self.g.get("files") or {}
        if not isinstance(s, dict) or "f" not in s or "l" not in s:
            self.err(f"{owner}: source needs f (file alias or path) and l (line or [first, last]): {s!r}")
            return None
        path = files.get(s["f"], s["f"])
        try:
            l0, l1 = _lines(s["l"])
        except (TypeError, ValueError):
            self.err(f"{owner}: bad line spec {s['l']!r}")
            return None
        lines = self._file_lines(path)
        out = {"path": path, "l0": l0, "l1": l1, "anchor": s.get("a")}
        if lines is None:
            self.err(f"{owner}: source file not found: {path}")
            return out
        if not (1 <= l0 <= l1 <= len(lines)):
            self.err(f"{owner}: lines {l0}-{l1} outside {path} ({len(lines)} lines)")
            return out
        a = s.get("a")
        if a:
            lo, hi = max(1, l0 - ANCHOR_SLACK), min(len(lines), l1 + ANCHOR_SLACK)
            window = lines[lo - 1:hi]
            if not any(a in ln for ln in window) and not any(_norm(a) in _norm(ln) for ln in window):
                self.err(f"{owner}: anchor {a!r} not found near {path}:{l0}-{l1}")
        else:
            self.warn(f"{owner}: source {path}:{l0} has no anchor (citation not verifiable)")
        return out

    # ------------------------------------------------------------------- figures
    def resolve_figs(self, nid, n):
        """Validate a node's `figs` ([{p: path or bare file name in meta.figure_dir, cap: caption}])."""
        fdir = (self.g.get("meta") or {}).get("figure_dir", "")
        out = []
        for f in n.get("figs") or []:
            if not isinstance(f, dict) or not f.get("p") or not f.get("cap"):
                self.err(f"{nid}: each figure needs p (path) and cap (caption): {f!r}")
                continue
            path = f["p"] if ("/" in f["p"] or not fdir) else f"{fdir.rstrip('/')}/{f['p']}"
            if Path(path).suffix.lower() not in IMG_EXT:
                self.err(f"{nid}: {path} is not an image ({sorted(IMG_EXT)})")
            if not (self.root / path).is_file():
                self.err(f"{nid}: figure not found: {path}")
            name = Path(path).name
            prev = self.figs.get(name)
            if prev and prev["path"] != path:
                self.err(f"{nid}: figure name {name} also used for {prev['path']} (published names must be unique)")
                continue
            rec = self.figs.setdefault(name, {"name": name, "path": path, "pub": f"figs/{name}", "cap": f["cap"], "nodes": []})
            rec["nodes"].append(nid)
            out.append({"name": name, "path": path, "pub": rec["pub"], "cap": f["cap"]})
        n["_figs"] = out

    def watch_figs(self):
        """Figures matching meta.figure_watch that no node links yet (reported as warnings and in the gallery)."""
        seen = set()
        for pat in (self.g.get("meta") or {}).get("figure_watch") or []:
            for p in sorted(self.root.glob(pat)):
                rel = p.relative_to(self.root).as_posix()
                if p.suffix.lower() in IMG_EXT and p.name not in self.figs and rel not in seen:
                    seen.add(rel)
                    self.unmapped.append({"name": p.name, "path": rel, "pub": f"figs/{p.name}"})
                    self.warn(f"figure not linked in the map yet: {rel}")

    # ------------------------------------------------------------------- edges
    def add_edge(self, src, rel, dst, auto=False, **attrs):
        e = {"src": src, "rel": rel, "dst": dst}
        e.update({k: v for k, v in attrs.items() if v not in (None, "", [])})
        if auto:
            e["auto"] = True
        self.edges.append(e)

    def expand(self):
        g = self.g
        meta = g.get("meta") or {}
        for n in g["nodes"]:
            nid = n.get("id")
            if not nid:
                self.err(f"node without id: {n.get('title')!r}")
                continue
            if nid in self.nodes:
                self.err(f"duplicate id {nid}")
            if not ID_RE.match(nid):
                self.err(f"{nid}: id must match {ID_RE.pattern}")
            self.nodes[nid] = n
        core = meta.get("core")
        for q in meta.get("branches") or []:
            if core:
                self.add_edge(core, "proposes", q, auto=True)
        for n in g["nodes"]:
            nid, t = n.get("id"), n.get("type")
            if not nid:
                continue
            for a in n.get("from") or []:
                self.add_edge(a, "yields", nid, auto=True)
            for d in n.get("depends") or []:
                self.add_edge(nid, "depends_on", d, auto=True)
            for d in n.get("basis") or []:
                self.add_edge(nid, "depends_on", d, auto=True)
            for x in n.get("tests") or []:
                self.add_edge(nid, "tests", x, auto=True)
            if t == "prediction" and n.get("of"):
                self.add_edge(n["of"], "proposes", nid, auto=True)
            if t == "hypothesis":
                for p in n.get("proposed_by") or [n.get("branch")]:
                    if p:
                        self.add_edge(p, "proposes", nid, auto=True)
            if n.get("superseded_by"):
                self.add_edge(n["superseded_by"], "supersedes", nid, auto=True)
            for lk in n.get("links") or []:
                if not isinstance(lk, dict) or "rel" not in lk or "to" not in lk:
                    self.err(f"{nid}: link needs rel and to: {lk!r}")
                    continue
                self.add_edge(nid, lk["rel"], lk["to"], vs=lk.get("vs"), scope=lk.get("scope"),
                              note=lk.get("note"), strength=lk.get("strength"))
        # current judgment of a branch proposes its next steps
        cur = self.current_judgments()
        for n in g["nodes"]:
            if n.get("type") == "next_step":
                for p in n.get("proposed_by") or [cur.get(n.get("branch"))]:
                    if p:
                        self.add_edge(p, "proposes", n["id"], auto=True)
        # stable ids
        seen = {}
        for e in self.edges:
            base = f"{e['src']}|{e['rel']}|{e['dst']}"
            seen[base] = seen.get(base, 0) + 1
            e["id"] = base if seen[base] == 1 else f"{base}#{seen[base]}"

    def current_judgments(self):
        out = {}
        for n in self.g["nodes"]:
            if n.get("type") == "judgment" and n.get("status") == "current" and n.get("branch"):
                out.setdefault(n["branch"], n["id"])
        return out

    # ------------------------------------------------------------------- checks
    def run(self):
        self.expand()
        g, nodes = self.g, self.nodes
        meta = g.get("meta") or {}
        rounds = {r.get("id"): r for r in g.get("rounds") or []}
        if not rounds:
            self.err("no rounds: every graph has at least one round")
        branch_ids = set(meta.get("branches") or [])
        core = meta.get("core")
        if core not in nodes or nodes[core].get("type") != "question":
            self.err(f"meta.core {core!r} is not a question node")
        for q in branch_ids:
            if q not in nodes or nodes[q].get("type") != "question":
                self.err(f"meta.branches: {q!r} is not a question node")
            elif not nodes[q].get("short"):
                self.err(f"{q}: a branch question needs `short` (card label)")
        valid_branches = branch_ids | ({core} if core else set())

        for nid, n in nodes.items():
            t = n.get("type")
            if t not in NODE_TYPES:
                self.err(f"{nid}: unknown type {t!r}")
                continue
            if not n.get("title"):
                self.err(f"{nid}: missing title")
            if n.get("round_added") not in rounds:
                self.err(f"{nid}: round_added {n.get('round_added')!r} is not a round id")
            for c in n.get("changes") or []:
                if c.get("round") not in rounds or not c.get("what"):
                    self.err(f"{nid}: each change needs an existing round and `what`: {c!r}")
            if t in STATUS and n.get("status") not in STATUS[t]:
                self.err(f"{nid}: status {n.get('status')!r} not allowed for {t} ({sorted(STATUS[t])})")
            if t in ("hypothesis", "prediction", "result", "judgment", "next_step"):
                if n.get("branch") not in valid_branches:
                    self.err(f"{nid}: branch {n.get('branch')!r} is not a branch question")
            srcs = n.get("src") or []
            if not srcs:
                self.err(f"{nid}: no source (src)")
            n["_src"] = [r for r in (self.resolve_src(nid, s) for s in srcs) if r]
            self.resolve_figs(nid, n)
            if n.get("status") == "superseded" or n.get("superseded_by"):
                rep = n.get("superseded_by")
                if n.get("status") != "superseded":
                    self.err(f"{nid}: has superseded_by but status is {n.get('status')!r}")
                elif not rep or rep not in nodes:
                    self.err(f"{nid}: superseded without an existing superseded_by ({rep!r})")
                elif nodes[rep].get("type") != t:
                    self.err(f"{nid}: superseded_by {rep} is a {nodes[rep].get('type')}, not a {t}")
                if t == "result" and not n.get("previous_status"):
                    self.err(f"{nid}: a superseded result keeps its previous_status")
            if t == "hypothesis":
                if n.get("level") not in LEVELS:
                    self.err(f"{nid}: level must be one of {sorted(LEVELS)}")
                if not n.get("short"):
                    self.err(f"{nid}: hypothesis needs `short` (pill label)")
            if t == "result":
                if n.get("effect") not in EFFECTS:
                    self.err(f"{nid}: effect must be one of {sorted(EFFECTS)}")
                if n.get("inference") not in INFERENCE:
                    self.err(f"{nid}: inference must be one of {sorted(INFERENCE)}")
                if n.get("effect") == "not_detected" and not n.get("null_reading"):
                    self.err(f"{nid}: a null result states its null_reading (precise null in scope, or underpowered)")
                if n.get("status") == "withdrawn" and not (n.get("note") or n.get("changes")):
                    self.err(f"{nid}: a withdrawn result says why (note or changes)")
                if n.get("status") != "superseded" and not n.get("from") and n.get("branch") != core:
                    self.warn(f"{nid}: result without an analysis (from)")
            if t == "prediction":
                if n.get("of") not in nodes or nodes[n["of"]].get("type") != "hypothesis":
                    self.err(f"{nid}: `of` must be a hypothesis")
            if t == "next_step":
                if not isinstance(n.get("priority"), int):
                    self.err(f"{nid}: priority must be an integer (1 = first)")
                if n.get("stage") not in STAGES:
                    self.err(f"{nid}: stage must be one of {sorted(STAGES)}")
                if not n.get("tests"):
                    self.err(f"{nid}: a next step names the hypotheses it would separate (tests)")
                outs = n.get("outcomes") or []
                if len(outs) < 2:
                    self.err(f"{nid}: a next step lists >= 2 outcomes and what each would change")
                for o in outs:
                    if not (isinstance(o, dict) and o.get("if") and o.get("then") and o.get("changes")):
                        self.err(f"{nid}: each outcome needs if / then / changes: {o!r}")
                        continue
                    for c in o["changes"]:
                        if c not in nodes or nodes[c].get("type") != "judgment":
                            self.err(f"{nid}: outcome changes {c!r}, which is not a judgment")

        # edges
        for e in self.edges:
            s, d, rel = e["src"], e["dst"], e["rel"]
            if rel not in ALLOWED:
                self.err(f"edge {e['id']}: unknown relation {rel!r}")
                continue
            if s not in nodes or d not in nodes:
                self.err(f"edge {e['id']}: endpoint missing ({s if s not in nodes else d})")
                continue
            ts, td = nodes[s].get("type"), nodes[d].get("type")
            src_ok, dst_ok = ALLOWED[rel]
            if src_ok is None:
                if ts != td:
                    self.err(f"edge {e['id']}: {rel} joins a {ts} to a {td}")
            elif ts not in src_ok or td not in dst_ok:
                self.err(f"edge {e['id']}: {rel} cannot go from {ts} to {td}")
            if e.get("vs") and (e["vs"] not in nodes or nodes[e["vs"]].get("type") not in ("hypothesis", "prediction")):
                self.err(f"edge {e['id']}: vs {e['vs']!r} is not a hypothesis / prediction")
            if ts == "judgment" and rel in VERDICT_RELS and e.get("strength") not in STRENGTH:
                self.err(f"edge {e['id']}: a judgment verdict carries strength (established / candidate)")
            if s == d:
                self.err(f"edge {e['id']}: self-loop")

        # one current judgment per branch
        cur = {}
        for nid, n in nodes.items():
            if n.get("type") == "judgment" and n.get("status") == "current":
                if n.get("branch") in cur:
                    self.err(f"two current judgments for {n.get('branch')}: {cur[n['branch']]}, {nid}")
                cur[n.get("branch")] = nid
        for q in valid_branches:
            if q not in cur:
                self.err(f"{q}: no current judgment")
        cur_ids = set(cur.values())

        # hypothesis status = verdict edges of the current judgments
        for nid, n in nodes.items():
            if n.get("type") != "hypothesis":
                continue
            rels = {e["rel"] for e in self.edges if e["dst"] == nid and e["src"] in cur_ids and e["rel"] in VERDICT_RELS}
            st = n.get("status")
            S, W, C = "supports" in rels, "weakens" in rels, "cannot_distinguish" in rels
            if S and not W and not C:
                ok = {"supported"}
            elif W and not S and not C:
                ok = {"weakened", "rejected"}
            elif (S and (W or C)) or (W and C):
                ok = {"mixed"}
            elif C:
                ok = {"open", "untestable"}
            else:
                ok = {"open", "proposed", "untestable"}
            if st not in ok:
                self.err(f"{nid}: status {st!r} does not match the current judgments' verdicts "
                         f"({'+'.join(sorted(rels)) or 'none'} -> {sorted(ok)})")
            if n.get("level") == "mechanism" and st == "supported":
                causal = [e for e in self.edges if e["dst"] == nid and e["rel"] == "supports"
                          and nodes.get(e["src"], {}).get("inference") == "intervention"]
                if not causal:
                    self.err(f"{nid}: a mechanism hypothesis cannot be supported without an intervention-design result")

        # prediction status = verdict edges of current (not superseded) results
        live = {nid for nid, n in nodes.items() if n.get("type") == "result" and n.get("status") != "superseded"}
        for nid, n in nodes.items():
            if n.get("type") != "prediction":
                continue
            rels = {e["rel"] for e in self.edges if e["dst"] == nid and e["src"] in live and e["rel"] in VERDICT_RELS}
            S, W, C = "supports" in rels, "weakens" in rels, "cannot_distinguish" in rels
            if S and not W and not C:
                ok = {"held"}
            elif W and not S and not C:
                ok = {"failed"}
            elif S or W:
                ok = {"mixed"}
            else:
                ok = {"open"}
            if n.get("status") not in ok:
                self.err(f"{nid}: status {n.get('status')!r} does not match its results ({sorted(rels)} -> {sorted(ok)})")

        # superseded results should not carry a current judgment
        for jid in cur_ids:
            for e in self.edges:
                if e["src"] == jid and e["rel"] == "depends_on" and nodes.get(e["dst"], {}).get("status") == "superseded":
                    self.warn(f"{jid}: rests on superseded {e['dst']}")

        # analyses
        for nid, n in nodes.items():
            if n.get("type") == "analysis" and not any(e["src"] == nid and e["rel"] == "yields" for e in self.edges):
                self.warn(f"{nid}: analysis yields no result")

        # next-step priorities
        pri = {}
        for nid, n in nodes.items():
            if n.get("type") == "next_step" and n.get("status") not in ("done", "dropped"):
                pri.setdefault(n.get("priority"), []).append(nid)
        for p, ids in pri.items():
            if len(ids) > 1:
                self.warn(f"next steps share priority {p}: {ids}")

        # rounds
        for rid, r in rounds.items():
            ans = r.get("answers") or {}
            for k in ANSWER_KEYS:
                if not str(ans.get(k) or "").strip():
                    self.err(f"round {rid}: answer `{k}` is missing")
            for x in r.get("next_steps") or []:
                if x not in nodes or nodes[x].get("type") != "next_step":
                    self.err(f"round {rid}: next_steps lists {x!r}, not a next step")
            if not r.get("next_steps"):
                self.err(f"round {rid}: name the prioritised next step(s) (next_steps)")
            for rv in r.get("reviews") or []:
                if not rv.get("by") or not rv.get("summary"):
                    self.err(f"round {rid}: each review needs by and summary")

        # conflicts
        for c in g.get("conflicts") or []:
            cid = c.get("id")
            sides = c.get("sides") or []
            if len(sides) < 2:
                self.err(f"conflict {cid}: needs >= 2 sides")
            for sd in sides:
                if sd.get("node") not in nodes:
                    self.err(f"conflict {cid}: side node {sd.get('node')!r} missing")
                if not sd.get("says"):
                    self.err(f"conflict {cid}: each side states what it says")
            if c.get("status") not in ("open", "resolved"):
                self.err(f"conflict {cid}: status must be open or resolved")
            if c.get("status") == "resolved" and not (c.get("resolution") and c.get("resolved_by")):
                self.err(f"conflict {cid}: a resolved conflict states its resolution and resolved_by")
            if c.get("round") not in rounds:
                self.err(f"conflict {cid}: round {c.get('round')!r} is not a round id")
        self.watch_figs()
        return self


# ----------------------------------------------------------------------------------------------- derived
def derive(ck):
    g, nodes, edges = ck.g, ck.nodes, ck.edges
    meta = g["meta"]
    core = meta["core"]
    branches = list(meta.get("branches") or [])
    cur = ck.current_judgments()
    out_e, in_e = {}, {}
    for e in edges:
        out_e.setdefault(e["src"], []).append(e)
        in_e.setdefault(e["dst"], []).append(e)
    order = {n["id"]: i for i, n in enumerate(g["nodes"])}
    rounds = [r["id"] for r in g["rounds"]]
    latest = rounds[-1] if rounds else None
    per_round = {rid: {"added": [], "modified": []} for rid in rounds}
    for n in g["nodes"]:
        if n.get("round_added") in per_round:
            per_round[n["round_added"]]["added"].append(n["id"])
        for c in n.get("changes") or []:
            if c.get("round") in per_round and n["id"] not in per_round[c["round"]]["modified"]:
                per_round[c["round"]]["modified"].append(n["id"])

    open_conf = {}
    for c in g.get("conflicts") or []:
        if c.get("status") == "open":
            for sd in c.get("sides") or []:
                open_conf.setdefault(sd["node"], []).append(c["id"])

    bdata = {}
    for i, q in enumerate([core] + branches):
        member = [n["id"] for n in g["nodes"] if n.get("branch") == q]
        hyps = [x for x in member if nodes[x]["type"] == "hypothesis"]
        preds = [x for x in member if nodes[x]["type"] == "prediction"]
        local = set(hyps) | set(preds)
        results = [x for x in member if nodes[x]["type"] == "result"]
        for e in edges:  # results filed elsewhere that bear on this branch's hypotheses
            if e["dst"] in local and nodes.get(e["src"], {}).get("type") == "result" and e["src"] not in results:
                results.append(e["src"])
        results.sort(key=lambda x: order[x])
        analyses = []
        for r in results:
            for e in in_e.get(r, []):
                if e["rel"] == "yields" and e["src"] not in analyses:
                    analyses.append(e["src"])
        analyses.sort(key=lambda x: order[x])
        own = [x for x in member if nodes[x]["type"] == "result"]
        counts = {}
        for r in own:
            counts[nodes[r]["status"]] = counts.get(nodes[r]["status"], 0) + 1
        phases = []
        for r in own:
            for p in nodes[r].get("ph") or []:
                if p not in phases:
                    phases.append(p)
        nxt = sorted([x for x in member if nodes[x]["type"] == "next_step"], key=lambda x: nodes[x]["priority"])
        old_j = [x for x in member if nodes[x]["type"] == "judgment" and nodes[x].get("status") != "current"]
        conf = sorted({c for x in member for c in open_conf.get(x, [])})
        new_ids = [x for x in member if x in per_round.get(latest, {}).get("added", [])]
        mod_ids = [x for x in member if x in per_round.get(latest, {}).get("modified", [])]
        bdata[q] = {"num": "Q0" if q == core else f"Q{i}", "hyps": hyps, "preds": preds, "results": results,
                    "analyses": analyses, "judgment": cur.get(q), "old_judgments": old_j, "next": nxt,
                    "counts": counts, "phases": phases, "open_conflicts": conf, "new": new_ids, "modified": mod_ids}

    accounts = [x for x in bdata[core]["hyps"]]
    matrix = {}
    for h in accounts:
        row = {}
        for q in branches:
            j = cur.get(q)
            cell = [{"rel": e["rel"], "strength": e.get("strength"), "scope": e.get("scope")}
                    for e in out_e.get(j, []) if e["dst"] == h and e["rel"] in VERDICT_RELS]
            if cell:
                row[q] = cell
        matrix[h] = row

    competing, seen = [], set()
    for q, j in cur.items():
        for e in out_e.get(j, []):
            if e["rel"] == "cannot_distinguish":
                pair = tuple(sorted([e["dst"], e.get("vs") or ""]))
                if pair in seen:
                    continue
                seen.add(pair)
                competing.append({"a": e["dst"], "b": e.get("vs"), "branch": q, "strength": e.get("strength")})

    counts = {}
    for n in g["nodes"]:
        if n.get("type") == "result" and n.get("status") != "superseded":
            counts[n["status"]] = counts.get(n["status"], 0) + 1
    ranked = sorted([n["id"] for n in g["nodes"] if n.get("type") == "next_step"
                     and n.get("status") not in ("done", "dropped")], key=lambda x: nodes[x]["priority"])

    # figures: which branches show each one, and where reports / change logs cite it
    cites = _figure_citations(ck.root, [f["name"] for f in ck.figs.values()] + [u["name"] for u in ck.unmapped])
    an_branch = {}
    for q, b in bdata.items():
        for a in b["analyses"]:
            an_branch.setdefault(a, []).append(q)
    figures = []
    for f in sorted(ck.figs.values(), key=lambda f: min(order[x] for x in f["nodes"])):
        br = []
        for nid in f["nodes"]:
            for q in ([nodes[nid]["branch"]] if nodes[nid].get("branch") else an_branch.get(nid, [])):
                if q not in br:
                    br.append(q)
        figures.append(dict(f, branches=br, cited_in=cites.get(f["name"], [])))
    unmapped = [dict(u, cited_in=cites.get(u["name"], [])) for u in ck.unmapped]
    return {"branches": bdata, "branch_order": [core] + branches, "accounts": accounts, "matrix": matrix,
            "competing": competing, "result_counts": counts, "ranked_next": ranked, "latest_round": latest,
            "rounds": per_round, "figures": figures, "unmapped_figures": unmapped}


def _figure_citations(root, names):
    """name -> ['path:line', ...] for every report or change log line that mentions the figure file."""
    names = set(names)
    out = {}
    root = Path(root)
    files = sorted(root.glob("results/*/*/reports/*.md")) + sorted(root.glob("change_log/*.md"))
    for p in files:
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        rel = p.relative_to(root).as_posix()
        for i, ln in enumerate(lines, 1):
            if "." not in ln:
                continue
            for nm in names:
                if nm in ln:
                    out.setdefault(nm, []).append(f"{rel}:{i}")
    return out


def normalise(ck, graph_path):
    g = ck.g
    nodes = []
    for n in g["nodes"]:
        m = {k: v for k, v in n.items() if not k.startswith("_") and k not in ("src", "from", "depends", "basis", "links", "tests")}
        m["sources"] = n.get("_src", [])
        if n.get("_figs"):
            m["figs"] = n["_figs"]
        nodes.append(m)
    raw = Path(graph_path).read_bytes()
    return {
        "meta": g["meta"],
        "nodes": nodes,
        "edges": ck.edges,
        "conflicts": g.get("conflicts") or [],
        "rounds": g.get("rounds") or [],
        "derived": derive(ck),
        "generated": {"by": "research_logic/logic_map.py build", "from": _rel(graph_path),
                      "sha256_of_source": hashlib.sha256(raw).hexdigest()},
    }


def _rel(p):
    try:
        return Path(p).resolve().relative_to(REPO).as_posix()
    except ValueError:
        return Path(p).as_posix()


def _json_default(o):
    return str(o)  # dates from YAML


# ----------------------------------------------------------------------------------------------- commands
def run_check(graph_path, root=REPO, quiet=False):
    ck = Checker(load_graph(graph_path), root=root).run()
    if not quiet:
        for w in ck.warnings:
            print(f"warning: {w}")
        for e in ck.errors:
            print(f"ERROR: {e}")
        n_t = {}
        for n in ck.nodes.values():
            n_t[n.get("type")] = n_t.get(n.get("type"), 0) + 1
        print(f"{_rel(graph_path)}: {len(ck.nodes)} nodes ({', '.join(f'{k} {v}' for k, v in sorted(n_t.items()))}), "
              f"{len(ck.edges)} edges, {len(ck.g.get('conflicts') or [])} conflicts, {len(ck.g.get('rounds') or [])} rounds; "
              f"{len(ck.errors)} errors, {len(ck.warnings)} warnings")
    return ck


def run_build(graph_path, out_dir, root=REPO, template=TEMPLATE):
    ck = run_check(graph_path, root=root)
    if ck.errors:
        print("build refused: fix the errors first")
        return 1
    data = normalise(ck, graph_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    gid = data["meta"].get("id") or Path(graph_path).stem
    js = json.dumps(data, ensure_ascii=False, indent=1, default=_json_default)
    (out_dir / f"{gid}.json").write_text(js + "\n", encoding="utf-8", newline="\n")
    tpl = Path(template).read_text(encoding="utf-8")
    try:
        tpl.encode("ascii")
    except UnicodeEncodeError as exc:
        raise SystemExit(f"{template}: keep the template ASCII (use \\u escapes / entities): {exc}")
    embedded = json.dumps(data, ensure_ascii=True, separators=(",", ":"), default=_json_default).replace("</", "<\\/")
    title = str(data["meta"].get("title") or gid)
    title_html = title.encode("ascii", "xmlcharrefreplace").decode("ascii").replace("<", "&lt;")
    html = tpl.replace("__TITLE__", title_html).replace("__DATA__", embedded)
    (out_dir / f"{gid}.html").write_text(html, encoding="ascii", newline="\n")
    print(f"wrote {_rel(out_dir / (gid + '.html'))} ({len(html) // 1024} KB) and {_rel(out_dir / (gid + '.json'))}")
    return 0


def run_show(graph_path, target):
    ck = run_check(graph_path, quiet=True)
    nodes, edges = ck.nodes, ck.edges
    meta = ck.g["meta"]

    def line(nid):
        n = nodes.get(nid, {})
        return f"  {nid:<26} {n.get('type', '?'):<10} {str(n.get('status', '')):<12} {n.get('title', '')}"

    if target in nodes and nodes[target].get("type") == "question" and (
            target in (meta.get("branches") or []) or target == meta.get("core")):
        d = derive(ck)["branches"][target]
        print(f"{d['num']} {target}: {nodes[target]['title']}")
        for label, key in (("hypotheses", "hyps"), ("predictions", "preds"), ("analyses", "analyses"),
                           ("results", "results"), ("next steps", "next")):
            print(f"{label}:")
            for x in d[key]:
                print(line(x))
        print("judgment:")
        if d["judgment"]:
            print(line(d["judgment"]))
        print(f"open conflicts: {d['open_conflicts'] or 'none'}")
        return 0
    if target not in nodes:
        print(f"no node {target!r}")
        return 1
    n = nodes[target]
    print(yaml.safe_dump({k: v for k, v in n.items() if not k.startswith("_")}, allow_unicode=True, sort_keys=False,
                         width=120).rstrip())
    print("out:")
    for e in edges:
        if e["src"] == target:
            print(f"  -{e['rel']}-> {line(e['dst']).strip()}" + (f"  [scope: {e['scope']}]" if e.get("scope") else ""))
    print("in:")
    for e in edges:
        if e["dst"] == target:
            print(f"  <-{e['rel']}- {line(e['src']).strip()}")
    for c in ck.g.get("conflicts") or []:
        if any(sd.get("node") == target for sd in c.get("sides") or []):
            print(f"conflict {c['id']} ({c['status']}): {c['title']}")
    return 0


def run_figs(graph_path):
    """Print the Artifact `files` map {published path: repo path} for every linked and watched figure."""
    ck = run_check(graph_path, quiet=True)
    m = {f["pub"]: f["path"] for f in ck.figs.values()}
    m.update({u["pub"]: u["path"] for u in ck.unmapped})
    print(json.dumps(m, indent=1, ensure_ascii=False))
    return 0


def run_index(graph_path, typ=None, status=None, branch=None):
    ck = run_check(graph_path, quiet=True)
    for n in ck.g["nodes"]:
        if typ and n.get("type") != typ or status and n.get("status") != status or branch and n.get("branch") != branch:
            continue
        print(f"{n['id']:<26} {n.get('type', ''):<10} {str(n.get('status', '')):<12} {str(n.get('branch', '')):<16} "
              f"{n.get('title', '')}")
    return 0


# ----------------------------------------------------------------------------------------------- selftest
def _selftest():
    tmp = Path(tempfile.mkdtemp(prefix="rlm_selftest_"))
    try:
        (tmp / "doc.md").write_text("\n".join([
            "# Report", "line two", "| 1 | History predicts the end of NREM | Established |",
            "| 2 | Carry-over after brief wakes | Established |", "next step text", "end"]) + "\n", encoding="utf-8")
        (tmp / "fig.png").write_bytes(bytes([137, 80, 78, 71, 13, 10, 26, 10]))
        tpl = tmp / "tpl.html"
        tpl.write_text("<title>__TITLE__</title><script id=\"d\" type=\"application/json\">__DATA__</script>\n",
                       encoding="ascii")
        base = {
            "meta": {"id": "t", "title": "Test map", "core": "q.core", "branches": ["q.a"]},
            "files": {"doc": "doc.md"},
            "nodes": [
                {"id": "q.core", "type": "question", "title": "Core?", "status": "open", "round_added": "r1",
                 "src": [{"f": "doc", "l": 1, "a": "Report"}]},
                {"id": "q.a", "type": "question", "short": "A?", "title": "Branch A?", "status": "open",
                 "round_added": "r1", "src": [{"f": "doc", "l": 2, "a": "line two"}]},
                {"id": "h.x", "type": "hypothesis", "branch": "q.a", "short": "x", "title": "X", "level": "pattern",
                 "status": "supported", "round_added": "r1", "src": [{"f": "doc", "l": 3, "a": "History predicts"}]},
                {"id": "h.y", "type": "hypothesis", "branch": "q.a", "short": "y", "title": "Y", "level": "pattern",
                 "status": "weakened", "round_added": "r1", "src": [{"f": "doc", "l": 3, "a": "History predicts"}]},
                {"id": "an.1", "type": "analysis", "title": "Analysis 1", "tests": ["h.x", "h.y"], "round_added": "r1",
                 "src": [{"f": "doc", "l": 3, "a": "History"}]},
                {"id": "r.1", "type": "result", "branch": "q.a", "title": "R1", "status": "established",
                 "effect": "positive", "inference": "predictive", "from": ["an.1"], "round_added": "r1",
                 "links": [{"rel": "supports", "to": "h.x"}, {"rel": "weakens", "to": "h.y"}],
                 "figs": [{"p": "fig.png", "cap": "a figure"}],
                 "src": [{"f": "doc", "l": [3, 4], "a": "Carry-over"}]},
                {"id": "j.core", "type": "judgment", "branch": "q.core", "title": "J core", "text": "t",
                 "status": "current", "round_added": "r1", "src": [{"f": "doc", "l": 1, "a": "Report"}]},
                {"id": "j.a", "type": "judgment", "branch": "q.a", "title": "J A", "text": "t", "status": "current",
                 "basis": ["r.1"], "round_added": "r1", "src": [{"f": "doc", "l": 3, "a": "History"}],
                 "links": [{"rel": "supports", "to": "h.x", "strength": "established"},
                           {"rel": "weakens", "to": "h.y", "strength": "established"}]},
                {"id": "n.1", "type": "next_step", "branch": "q.a", "title": "Do", "priority": 1, "status": "proposed",
                 "stage": "now", "tests": ["h.x"], "round_added": "r1", "src": [{"f": "doc", "l": 5, "a": "next step"}],
                 "outcomes": [{"if": "a", "then": "b", "changes": ["j.a"]}, {"if": "c", "then": "d", "changes": ["j.a"]}]},
            ],
            "conflicts": [],
            "rounds": [{"id": "r1", "date": "2026-10-08", "label": "t", "next_steps": ["n.1"],
                        "answers": {k: "x" for k in ANSWER_KEYS}}],
        }

        def check(g):
            p = tmp / "g.yaml"
            p.write_text(yaml.safe_dump(g, allow_unicode=True, sort_keys=False), encoding="utf-8")
            return run_check(p, root=tmp, quiet=True), p

        ck, p = check(base)
        assert not ck.errors, ck.errors
        assert run_build(p, tmp / "out", root=tmp, template=tpl) == 0
        html = (tmp / "out" / "t.html").read_text(encoding="ascii")
        data = json.loads(re.search(r'application/json">(.*)</script>', html).group(1))
        assert data["derived"]["branches"]["q.a"]["judgment"] == "j.a"
        assert any(e["rel"] == "yields" and e["src"] == "an.1" for e in data["edges"])
        assert data["derived"]["figures"][0]["pub"] == "figs/fig.png"
        print("selftest 1 (valid graph checks and builds): ok")

        def expect(mutate, needle, label):
            g = copy.deepcopy(base)
            mutate(g)
            ck2, _ = check(g)
            assert any(needle in e for e in ck2.errors), (label, ck2.errors)
            print(f"selftest ({label}): ok")

        node = lambda g, i: next(n for n in g["nodes"] if n["id"] == i)
        expect(lambda g: node(g, "r.1")["links"].append({"rel": "supports", "to": "h.nope"}), "endpoint missing",
               "dangling edge")
        expect(lambda g: node(g, "r.1")["src"].__setitem__(0, {"f": "doc", "l": 5, "a": "Carry-over xyz"}),
               "not found near", "anchor not at the cited line")
        expect(lambda g: node(g, "r.1")["src"].__setitem__(0, {"f": "doc", "l": 99, "a": "x"}), "outside",
               "line out of range")
        expect(lambda g: node(g, "h.y").__setitem__("status", "supported"), "does not match the current judgments",
               "hypothesis status vs judgment")
        expect(lambda g: node(g, "r.1").__setitem__("effect", "not_detected"), "null_reading", "null result without reading")
        expect(lambda g: node(g, "r.1").__setitem__("status", "superseded"), "superseded without",
               "superseded without replacement")
        def mech(g):
            node(g, "h.x")["level"] = "mechanism"
        expect(mech, "intervention-design", "mechanism supported by predictive evidence")
        expect(lambda g: node(g, "n.1")["outcomes"].pop(), ">= 2 outcomes", "next step with one outcome")
        expect(lambda g: g["rounds"][0]["answers"].pop("indistinguishable"), "indistinguishable", "round missing answer")
        expect(lambda g: node(g, "r.1")["links"].append({"rel": "yields", "to": "h.x"}), "cannot go from",
               "relation between wrong node types")
        expect(lambda g: g["conflicts"].append({"id": "c", "title": "c", "status": "resolved", "round": "r1",
                                                "sides": [{"node": "r.1", "says": "a"}, {"node": "j.a", "says": "b"}]}),
               "resolution", "resolved conflict without resolution")
        expect(lambda g: node(g, "r.1")["figs"].append({"p": "missing.png", "cap": "x"}), "figure not found",
               "figure file missing")
        print("selftest: all ok")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252; titles carry →, κ, …
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    for name in ("check", "build", "show", "index", "figs"):
        sp = sub.add_parser(name)
        sp.add_argument("--graph", default=str(DEFAULT_GRAPH))
        if name == "build":
            sp.add_argument("--out-dir", default=str(HERE / "maps"))
        if name == "show":
            sp.add_argument("target")
        if name == "index":
            sp.add_argument("--type")
            sp.add_argument("--status")
            sp.add_argument("--branch")
    a = ap.parse_args(argv)
    if a.selftest:
        return _selftest()
    if a.cmd == "check":
        return 1 if run_check(a.graph).errors else 0
    if a.cmd == "build":
        return run_build(a.graph, a.out_dir)
    if a.cmd == "show":
        return run_show(a.graph, a.target)
    if a.cmd == "index":
        return run_index(a.graph, a.type, a.status, a.branch)
    if a.cmd == "figs":
        return run_figs(a.graph)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
