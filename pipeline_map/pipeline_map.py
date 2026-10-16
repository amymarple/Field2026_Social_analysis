"""Preprocessing tree: validate, inspect and build the progress map.

The graph YAML (pipeline_map/graphs/<id>.yaml) is the only place the preprocessing progress is written: one node per
preprocessing stage, placed in a trunk (ephys / behaviour), a lane (branch) and a layer (level), with a status, its
outputs, how it was validated, who owns it, what waits on the user, its next step and cited sources. Edges are
`requires` (a hard input) and `aids` (a helper). This tool checks it and generates, from it alone:
  pipeline_map/maps/<id>.json   normalised graph + derived summaries
  pipeline_map/maps/<id>.html   the interactive tree (template pipeline_map/map_template.html, data embedded)

Usage (from the repo root; base Python + pyyaml):
  python pipeline_map/pipeline_map.py check  [--graph pipeline_map/graphs/preprocessing_2026c.yaml]
  python pipeline_map/pipeline_map.py build  [--graph ...] [--out-dir pipeline_map/maps]
  python pipeline_map/pipeline_map.py show   <node id | trunk id> [--graph ...]
  python pipeline_map/pipeline_map.py index  [--graph ...] [--status in_progress] [--trunk behavior]
  python pipeline_map/pipeline_map.py figs   [--graph ...]   # Artifact `files` map {figs/<name>: repo path}
  python pipeline_map/pipeline_map.py relocate [--graph ...] # re-find citations whose anchor moved (CLAUDE.md shifts)
  python pipeline_map/pipeline_map.py --selftest

Citations ({f, l, a}) and figures are verified with the research-logic checker (research_logic/logic_map.py); a path may
point into a sibling repo ("../Field_2026_Social_Recording/…"). `check` exits 1 on errors; `build` refuses on errors.
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
sys.path.insert(0, str(REPO / "research_logic"))
import logic_map as lm  # noqa: E402  (citation + figure checks, shared with the research-logic map)

DEFAULT_GRAPH = HERE / "graphs" / "preprocessing_2026c.yaml"
TEMPLATE = HERE / "map_template.html"
STATUS = ("done", "in_progress", "waiting_user", "blocked", "planned", "not_started", "closed")
OPEN_INPUT = {"planned", "not_started"}
ID_RE = re.compile(r"^[a-z][a-z0-9_.-]*$")
REQUIRED_BY_STATUS = {  # status -> field that must be filled
    "done": ("outputs", "validation"),
    "waiting_user": ("waiting_on_user",),
    "blocked": ("blocker",),
    "in_progress": ("next", "evidence"),
    "closed": ("reason",),
}


def load_graph(path):
    with open(path, encoding="utf-8") as fh:
        g = yaml.safe_load(fh)
    if not isinstance(g, dict):
        raise SystemExit(f"{path}: not a YAML mapping")
    g.setdefault("meta", {})
    g.setdefault("files", {})
    g.setdefault("nodes", [])
    g.setdefault("updates", [])
    return g


class Checker:
    def __init__(self, g, root=REPO):
        self.g, self.root = g, Path(root)
        self.errors, self.warnings = [], []
        self.nodes, self.edges = {}, []
        # the research-logic checker resolves sources ({f, l, a}) and figures for us
        self.src = lm.Checker({"meta": g.get("meta", {}), "files": g.get("files", {}), "nodes": [], "conflicts": [],
                               "rounds": []}, root=root)

    def err(self, m):
        self.errors.append(m)

    def warn(self, m):
        self.warnings.append(m)

    def run(self):
        g, meta = self.g, self.g["meta"]
        trunks = {t.get("id"): t for t in meta.get("trunks") or []}
        if not trunks:
            self.err("meta.trunks is empty")
        lanes = {tid: {ln["id"] for ln in t.get("lanes") or []} for tid, t in trunks.items()}
        layers = {tid: {ly["id"] for ly in t.get("layers") or []} for tid, t in trunks.items()}
        for tid, t in trunks.items():
            if not t.get("title") or not lanes[tid] or not layers[tid]:
                self.err(f"trunk {tid}: needs title, lanes and layers")
        for n in g["nodes"]:
            nid = n.get("id")
            if not nid or not ID_RE.match(str(nid)):
                self.err(f"bad node id {nid!r}")
                continue
            if nid in self.nodes:
                self.err(f"duplicate id {nid}")
            self.nodes[nid] = n
        for nid, n in self.nodes.items():
            for k in ("title", "short", "done_when", "summary", "status", "trunk", "layer", "updated"):
                if not n.get(k):
                    self.err(f"{nid}: missing {k}")
            t = n.get("trunk")
            if t not in trunks:
                self.err(f"{nid}: trunk {t!r} not in meta.trunks")
            else:
                if n.get("lane") != "all" and n.get("lane") not in lanes[t]:
                    self.err(f"{nid}: lane {n.get('lane')!r} not in trunk {t} (or 'all')")
                if n.get("layer") not in layers[t]:
                    self.err(f"{nid}: layer {n.get('layer')!r} not in trunk {t}")
            st = n.get("status")
            if st not in STATUS:
                self.err(f"{nid}: status {st!r} not in {STATUS}")
            for k in REQUIRED_BY_STATUS.get(st, ()):
                if not n.get(k):
                    self.err(f"{nid}: status {st} needs `{k}`")
            if n.get("progress") is not None and not (isinstance(n["progress"], (int, float)) and 0 <= n["progress"] <= 100):
                self.err(f"{nid}: progress must be 0-100")
            srcs = n.get("src") or []
            if not srcs:
                self.err(f"{nid}: no source (src)")
            n["_src"] = [r for r in (self.src.resolve_src(nid, s) for s in srcs) if r]
            self.src.resolve_figs(nid, n)
            for rel in ("requires", "aids"):
                for d in n.get(rel) or []:
                    if d not in self.nodes:
                        self.err(f"{nid}: {rel} {d!r} is not a node")
                    elif d == nid:
                        self.err(f"{nid}: {rel} itself")
                    else:
                        self.edges.append({"id": f"{d}|{rel}|{nid}", "src": d, "dst": nid, "rel": rel,
                                           "cross": self.nodes[d].get("trunk") != n.get("trunk")})
        self.errors += self.src.errors
        self.warnings += self.src.warnings
        # done downstream of an input that has not started
        for e in self.edges:
            if e["rel"] == "requires" and self.nodes[e["dst"]].get("status") == "done" \
                    and self.nodes[e["src"]].get("status") in OPEN_INPUT:
                self.warn(f"{e['dst']} is done but its required input {e['src']} is {self.nodes[e['src']]['status']}")
        # cycles over requires
        req = {nid: [e["src"] for e in self.edges if e["dst"] == nid and e["rel"] == "requires"] for nid in self.nodes}
        seen, stack = set(), set()

        def visit(v):
            if v in stack:
                self.err(f"requires-cycle through {v}")
                return
            if v in seen:
                return
            stack.add(v)
            for u in req.get(v, []):
                visit(u)
            stack.discard(v)
            seen.add(v)
        for v in self.nodes:
            visit(v)
        for u in g.get("updates") or []:
            if not (u.get("date") and u.get("by") and u.get("summary")):
                self.err(f"update needs date, by, summary: {u!r}")
            for x in u.get("nodes") or []:
                if x not in self.nodes:
                    self.err(f"update lists unknown node {x!r}")
        return self


def derive(ck):
    g, nodes = ck.g, ck.nodes
    trunks = g["meta"].get("trunks") or []
    counts = {}
    for t in trunks:
        c = {s: 0 for s in STATUS}
        for n in nodes.values():
            if n.get("trunk") == t["id"]:
                c[n["status"]] += 1
        counts[t["id"]] = c
    waiting = [{"id": nid, "what": n["waiting_on_user"]} for nid, n in nodes.items() if n.get("waiting_on_user")]
    owners = {}
    for nid, n in nodes.items():
        for o in n.get("owner") or []:
            owners.setdefault(o, []).append(nid)
    figs = [dict(f) for f in ck.src.figs.values()]
    return {"counts": counts, "waiting": waiting, "owners": owners, "figures": figs,
            "updates": sorted(g.get("updates") or [], key=lambda u: str(u.get("date")), reverse=True)}


def normalise(ck, graph_path):
    nodes = []
    for n in ck.g["nodes"]:
        m = {k: v for k, v in n.items() if not k.startswith("_") and k not in ("src", "figs")}
        m["sources"] = n.get("_src", [])
        if n.get("_figs"):
            m["figs"] = n["_figs"]
        nodes.append(m)
    raw = Path(graph_path).read_bytes()
    return {"meta": ck.g["meta"], "nodes": nodes, "edges": ck.edges, "derived": derive(ck),
            "generated": {"by": "pipeline_map/pipeline_map.py build", "from": lm._rel(graph_path),
                          "sha256_of_source": hashlib.sha256(raw).hexdigest()}}


def _js_escape(match):
    o = ord(match.group())
    if o < 0x10000:
        return chr(92) + "u%04x" % o
    o -= 0x10000
    return chr(92) + "u%04x" % (0xD800 + (o >> 10)) + chr(92) + "u%04x" % (0xDC00 + (o & 0x3FF))


def asciify(html):
    """Non-ASCII -> JS escapes inside <script>, -> &#x...; elsewhere (the template may be written in plain Unicode)."""
    out, pos = [], 0
    ent = lambda c: f"&#x{ord(c.group()):x};"
    for m in re.finditer(r"<script\b[^>]*>.*?</script>", html, flags=re.S):
        out.append(re.sub(r"[^\x00-\x7f]", ent, html[pos:m.start()]))
        out.append(re.sub(r"[^\x00-\x7f]", _js_escape, m.group()))
        pos = m.end()
    out.append(re.sub(r"[^\x00-\x7f]", ent, html[pos:]))
    return "".join(out)


def run_check(graph_path, root=REPO, quiet=False):
    ck = Checker(load_graph(graph_path), root=root).run()
    if not quiet:
        for w in ck.warnings:
            print(f"warning: {w}")
        for e in ck.errors:
            print(f"ERROR: {e}")
        st = {}
        for n in ck.nodes.values():
            st[n.get("status")] = st.get(n.get("status"), 0) + 1
        print(f"{lm._rel(graph_path)}: {len(ck.nodes)} stages ({', '.join(f'{k} {v}' for k, v in sorted(st.items()))}), "
              f"{len(ck.edges)} edges; {len(ck.errors)} errors, {len(ck.warnings)} warnings")
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
    (out_dir / f"{gid}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str) + "\n",
                                         encoding="utf-8", newline="\n")
    embedded = json.dumps(data, ensure_ascii=True, separators=(",", ":"), default=str).replace("</", "<\\/")
    title = str(data["meta"].get("title") or gid).replace("<", "&lt;")
    html = Path(template).read_text(encoding="utf-8").replace("__TITLE__", title).replace("__DATA__", embedded)
    html = asciify(html)
    (out_dir / f"{gid}.html").write_text(html, encoding="ascii", newline="\n")
    print(f"wrote {lm._rel(out_dir / (gid + '.html'))} ({len(html) // 1024} KB) and {lm._rel(out_dir / (gid + '.json'))}")
    return 0


def run_show(graph_path, target):
    ck = run_check(graph_path, quiet=True)
    trunks = {t["id"]: t for t in ck.g["meta"].get("trunks") or []}
    if target in trunks:
        t = trunks[target]
        for ly in t["layers"]:
            print(f"[{ly['id']}] {ly['title']}")
            for n in ck.g["nodes"]:
                if n.get("trunk") == target and n.get("layer") == ly["id"]:
                    print(f"   {n['id']:<24} {n['status']:<12} {n.get('lane', ''):<10} {n['title']}")
        return 0
    n = ck.nodes.get(target)
    if not n:
        print(f"no node or trunk {target!r}")
        return 1
    print(yaml.safe_dump({k: v for k, v in n.items() if not k.startswith("_")}, allow_unicode=True, sort_keys=False,
                         width=120).rstrip())
    for e in ck.edges:
        if e["dst"] == target:
            print(f"  <- {e['rel']} {e['src']} ({ck.nodes[e['src']]['status']})")
        if e["src"] == target:
            print(f"  -> {e['rel']} of {e['dst']} ({ck.nodes[e['dst']]['status']})")
    return 0


def run_index(graph_path, status=None, trunk=None):
    ck = run_check(graph_path, quiet=True)
    for n in ck.g["nodes"]:
        if status and n.get("status") != status or trunk and n.get("trunk") != trunk:
            continue
        print(f"{n['id']:<24} {n.get('status', ''):<12} {n.get('trunk', ''):<9} {n.get('layer', ''):<5} {n.get('title', '')}")
    return 0


def run_relocate(graph_path, root=REPO):
    """Re-find each citation whose anchor moved (files such as CLAUDE.md shift under other sessions' edits) and rewrite
    its line spec in the YAML, keeping a range's width. Anchors found nowhere are reported, never guessed."""
    g = load_graph(graph_path)
    files = g.get("files") or {}
    text = Path(graph_path).read_text(encoding="utf-8")
    moved, missing = 0, 0
    for n in g["nodes"]:
        for s in n.get("src") or []:
            a = s.get("a")
            path = files.get(s.get("f"), s.get("f"))
            p = Path(root) / path
            if not a or not p.is_file():
                continue
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
            l0, l1 = lm._lines(s["l"])
            lo, hi = max(1, l0 - lm.ANCHOR_SLACK), min(len(lines), l1 + lm.ANCHOR_SLACK)
            hit = lambda ln: a in ln or lm._norm(a) in lm._norm(ln)
            if any(hit(ln) for ln in lines[lo - 1:hi]):
                continue
            hits = [i + 1 for i, ln in enumerate(lines) if hit(ln)]
            if not hits:
                print(f"{n['id']}: anchor {a!r} not found anywhere in {path}")
                missing += 1
                continue
            new0 = min(hits, key=lambda h: abs(h - l0))
            d = new0 - l0
            old_spec = f"[{l0}, {l1}]" if isinstance(s["l"], list) else f"{l0}"
            new_spec = f"[{l0 + d}, {l1 + d}]" if isinstance(s["l"], list) else f"{l0 + d}"
            pat = re.compile(r"(\{f: " + re.escape(str(s["f"])) + r", l: )" + re.escape(old_spec)
                             + r"(, a: " + re.escape(chr(34) + a + chr(34)) + ")")
            text, k = pat.subn(lambda m: m.group(1) + new_spec + m.group(2), text)
            if k:
                moved += 1
                print(f"{n['id']}: {path} {old_spec} -> {new_spec} ({a!r})")
    Path(graph_path).write_text(text, encoding="utf-8")
    print(f"relocated {moved} citation(s); {missing} anchor(s) not found")
    return 1 if missing else 0


def run_figs(graph_path):
    ck = run_check(graph_path, quiet=True)
    print(json.dumps({f["pub"]: f["path"] for f in ck.src.figs.values()}, indent=1, ensure_ascii=False))
    return 0


def _selftest():
    tmp = Path(tempfile.mkdtemp(prefix="pipemap_selftest_"))
    try:
        (tmp / "doc.md").write_text("# Plan\nLFP done for every session\nsorting in progress\n", encoding="utf-8")
        (tmp / "tpl.html").write_text("<title>__TITLE__</title>é<script id=\"d\" type=\"application/json\">"
                                      "__DATA__</script><script>var a='→';</script>\n", encoding="utf-8")
        base = {
            "meta": {"id": "t", "title": "Test tree", "trunks": [
                {"id": "ephys", "title": "Ephys", "lanes": [{"id": "lfp", "title": "LFP"}],
                 "layers": [{"id": "e0", "title": "raw"}, {"id": "e1", "title": "events"}]}]},
            "files": {"doc": "doc.md"},
            "nodes": [
                {"id": "e.lfp", "title": "LFP", "short": "LFP", "done_when": "d", "summary": "s", "status": "done", "trunk": "ephys",
                 "lane": "lfp", "layer": "e0", "updated": "2026-10-10", "outputs": ["x"], "validation": "v",
                 "src": [{"f": "doc", "l": 2, "a": "LFP done"}]},
                {"id": "e.sort", "title": "Sort", "short": "Sort", "done_when": "d", "summary": "s", "status": "in_progress",
                 "trunk": "ephys", "lane": "lfp", "layer": "e1", "updated": "2026-10-10", "next": "n", "evidence": "e",
                 "requires": ["e.lfp"], "src": [{"f": "doc", "l": 3, "a": "sorting"}]},
            ],
            "updates": [{"date": "2026-10-10", "by": "t", "summary": "s", "nodes": ["e.lfp"]}],
        }

        def check(g):
            p = tmp / "g.yaml"
            p.write_text(yaml.safe_dump(g, allow_unicode=True, sort_keys=False), encoding="utf-8")
            return run_check(p, root=tmp, quiet=True), p

        ck, p = check(base)
        assert not ck.errors, ck.errors
        assert run_build(p, tmp / "out", root=tmp, template=tmp / "tpl.html") == 0
        html = (tmp / "out" / "t.html").read_text(encoding="ascii")
        assert "&#xe9;" in html and "\\u2192" in html
        print("selftest 1 (valid tree checks and builds, output ASCII): ok")

        def expect(mutate, needle, label):
            g = copy.deepcopy(base)
            mutate(g)
            ck2, _ = check(g)
            assert any(needle in e for e in ck2.errors), (label, ck2.errors)
            print(f"selftest ({label}): ok")

        nd = lambda g, i: next(n for n in g["nodes"] if n["id"] == i)
        expect(lambda g: nd(g, "e.sort").__setitem__("requires", ["e.nope"]), "is not a node", "dangling requires")
        expect(lambda g: nd(g, "e.lfp").pop("validation"), "needs `validation`", "done without validation")
        expect(lambda g: nd(g, "e.sort").__setitem__("status", "waiting_user"), "needs `waiting_on_user`",
               "waiting without what")
        expect(lambda g: nd(g, "e.sort").__setitem__("layer", "e9"), "not in trunk", "unknown layer")
        expect(lambda g: nd(g, "e.sort").pop("evidence"), "needs `evidence`", "in progress without evidence")
        expect(lambda g: nd(g, "e.lfp").pop("done_when"), "missing done_when", "stage without done_when")
        expect(lambda g: nd(g, "e.lfp").__setitem__("requires", ["e.sort"]), "requires-cycle", "cycle")
        expect(lambda g: nd(g, "e.lfp")["src"].__setitem__(0, {"f": "doc", "l": 3, "a": "no such words"}),
               "not found near", "anchor not at the cited line")
        g = copy.deepcopy(base)
        nd(g, "e.sort")["status"] = "done"
        nd(g, "e.sort").update({"outputs": ["y"], "validation": "v"})
        nd(g, "e.lfp")["status"] = "planned"
        ck3, _ = check(g)
        assert any("required input" in w for w in ck3.warnings), ck3.warnings
        print("selftest (done downstream of a planned input warns): ok")
        print("selftest: all ok")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    for name in ("check", "build", "show", "index", "figs", "relocate"):
        sp = sub.add_parser(name)
        sp.add_argument("--graph", default=str(DEFAULT_GRAPH))
        if name == "build":
            sp.add_argument("--out-dir", default=str(HERE / "maps"))
        if name == "show":
            sp.add_argument("target")
        if name == "index":
            sp.add_argument("--status")
            sp.add_argument("--trunk")
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
        return run_index(a.graph, a.status, a.trunk)
    if a.cmd == "figs":
        return run_figs(a.graph)
    if a.cmd == "relocate":
        return run_relocate(a.graph)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
