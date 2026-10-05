"""backup_social_field_rat.py — hashed, verified local backup of the cohort-1 panorama rat detector folder.

Why (plan implementation_plan/2026-10-05-c1-yolo-transfer-sam3.md, step 0): `D:/Documents/GitHub/social-field-rat`
(another lab member's work, last edited 2026-09-14) holds the only CH01/CH02 panorama rat labels (887 frames, 1 692
boxes, cohort 1 = 2026a) and the YOLO11 models trained on them (v1-v5). It is not a working git repository (`.git/`
holds only `refs/`) and `data/` + `outputs/` were gitignored, so the labels and weights exist in this one place. This
driver copies them, preserving relative paths, to `$FIELD2026_ANALYSIS_OUT_ROOT/2026a/social_field_rat_backup_<date>/`,
writes `MANIFEST_sha256.csv` (relpath, bytes, mtime, sha256 of the SOURCE, computed on the same read that feeds the
copy) and `README.md`, then re-hashes every destination file against the manifest. The step passes only with
0 mismatches and 0 missing files. The source is only ever read.

Inclusion rules (plan, step 0; first matching rule wins):
  exclude  any path through `.venv/` or `__pycache__/`; `*.avi`; `trails.mp4` (prediction / tracking videos, ~49 GB,
           regenerable from the weights + raw video)
  include  `computer_vision/data/**`  (frames, labels, manifests, previews, labeled_yolo, label backups + zip)
  include  `computer_vision/outputs/runs/**`  (weights best.pt/last.pt, args.yaml, results.csv, curves)
  include  `computer_vision/outputs/tracks/**/tracks.csv`
  include  `*.md *.yml *.yaml *.py *.ipynb *.slurm` anywhere else (docs, configs, code, notebooks)
  include  (amendment 2026-10-05, before results) `computer_vision/weights/*.pt` (the pretrained yolo11/yolo26 start
           checkpoints, 71 MB), `.git/refs/**` (records the last commit hash of the broken repo), `*.gitkeep`
  exclude  everything else (listed with its reason in `EXCLUDED_files.csv`)

Usage (base Python or the cv env; stdlib only):
  python cv/cv_field/backup_social_field_rat.py [--src D:/Documents/GitHub/social-field-rat] [--dest <dir>]
  python cv/cv_field/backup_social_field_rat.py --verify-only [--dest <dir>]    # re-hash an existing backup
  python cv/cv_field/backup_social_field_rat.py --selftest                       # synthetic tree, no field data
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

DEFAULT_SRC = Path("D:/Documents/GitHub/social-field-rat")
OUT_ROOT = Path(os.environ.get("FIELD2026_ANALYSIS_OUT_ROOT", "D:/Field2026_analysis_out"))
DEFAULT_DEST = OUT_ROOT / "2026a" / "social_field_rat_backup_20261005"
CHUNK = 8 << 20
DOC_EXT = {".md", ".yml", ".yaml", ".py", ".ipynb", ".slurm"}
MANIFEST = "MANIFEST_sha256.csv"
EXCLUDED = "EXCLUDED_files.csv"
OWN_FILES = {MANIFEST, EXCLUDED, "README.md", "VERIFY.json"}


def rule(rel: str) -> tuple[bool, str]:
    """(include?, reason) for one source-relative path with forward slashes."""
    parts = rel.split("/")
    name = parts[-1]
    low = name.lower()
    if ".venv" in parts[:-1] or "__pycache__" in parts[:-1]:
        return False, "venv_or_pycache"
    if low.endswith(".avi") or low == "trails.mp4":
        return False, "prediction_or_tracking_video"
    if rel.startswith("computer_vision/data/"):
        return True, "data"
    if rel.startswith("computer_vision/outputs/runs/"):
        return True, "runs"
    if rel.startswith("computer_vision/outputs/tracks/") and name == "tracks.csv":
        return True, "tracks_csv"
    if Path(name).suffix.lower() in DOC_EXT:
        return True, "docs_code"
    if (rel.startswith("computer_vision/weights/") and low.endswith(".pt")) or rel.startswith(".git/refs/") \
            or low == ".gitkeep":
        return True, "amendment_20261005"
    return False, "not_in_inclusion_list"


def scan(src: Path) -> tuple[list[tuple[str, int, float, str]], list[tuple[str, int, str]]]:
    """Walk the source (pruning .venv / __pycache__ dirs) -> (included [(rel, bytes, mtime, rule)], excluded)."""
    inc, exc = [], []
    for dirpath, dirnames, filenames in os.walk(src):
        rel_dir = Path(dirpath).relative_to(src).as_posix()
        keep = []
        for d in dirnames:
            if d in (".venv", "__pycache__"):
                n = sum(len(fs) for _, _, fs in os.walk(Path(dirpath) / d))
                exc.append(((f"{rel_dir}/{d}/" if rel_dir != "." else f"{d}/") + f"** ({n} files)", 0, "venv_or_pycache"))
            else:
                keep.append(d)
        dirnames[:] = sorted(keep)
        for fn in sorted(filenames):
            p = Path(dirpath) / fn
            rel = p.relative_to(src).as_posix()
            st = p.stat()
            ok, why = rule(rel)
            (inc.append((rel, st.st_size, st.st_mtime, why)) if ok else exc.append((rel, st.st_size, why)))
    return inc, exc


def copy_hash(s: Path, d: Path) -> tuple[str, int]:
    """Copy s -> d in one read pass, returning (sha256 of the bytes read, bytes). Preserves mtime/atime."""
    d.parent.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256()
    n = 0
    tmp = d.with_name(d.name + ".partial")
    with open(s, "rb") as fi, open(tmp, "wb") as fo:
        while True:
            b = fi.read(CHUNK)
            if not b:
                break
            h.update(b)
            fo.write(b)
            n += len(b)
    os.replace(tmp, d)
    st = s.stat()
    os.utime(d, ns=(st.st_atime_ns, st.st_mtime_ns))
    return h.hexdigest(), n


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(CHUNK), b""):
            h.update(b)
    return h.hexdigest()


def verify(dest: Path) -> dict:
    """Re-hash every manifest entry in dest. Also lists files in dest that the manifest does not name."""
    rows = list(csv.DictReader(open(dest / MANIFEST, newline="", encoding="utf-8")))
    mism, missing = [], []
    nbytes = 0
    for r in rows:
        p = dest / r["relpath"]
        if not p.is_file():
            missing.append(r["relpath"])
            continue
        if p.stat().st_size != int(r["bytes"]) or sha256(p) != r["sha256"]:
            mism.append(r["relpath"])
            continue
        nbytes += int(r["bytes"])
    named = {r["relpath"] for r in rows}
    extra = [p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file()
             and p.relative_to(dest).as_posix() not in named and p.relative_to(dest).as_posix() not in OWN_FILES]
    return {"n_manifest": len(rows), "n_verified": len(rows) - len(mism) - len(missing), "bytes_verified": nbytes,
            "n_mismatch": len(mism), "n_missing": len(missing), "n_extra": len(extra), "mismatch": mism[:50],
            "missing": missing[:50], "extra": extra[:50], "pass": not mism and not missing,
            "verified_at": datetime.now().isoformat(timespec="seconds")}


def write_readme(dest: Path, src: Path, inc, exc, ver: dict, secs: float) -> None:
    by_rule: dict[str, list[int]] = {}
    for _, b, _, why in inc:
        by_rule.setdefault(why, [0, 0])
        by_rule[why][0] += 1
        by_rule[why][1] += b
    ex_rule: dict[str, list[int]] = {}
    for _, b, why in exc:
        ex_rule.setdefault(why, [0, 0])
        ex_rule[why][0] += 1
        ex_rule[why][1] += b
    tot = sum(b for _, b, _, _ in inc)
    lines = [
        "# Backup of `social-field-rat` (cohort-1 CH01/CH02 panorama rat detector)", "",
        f"Made {datetime.now():%Y-%m-%d %H:%M} by `Field2026_Social_analysis/cv/cv_field/backup_social_field_rat.py`",
        "(plan `implementation_plan/2026-10-05-c1-yolo-transfer-sam3.md`, step 0). Read-only copy: do not edit here.", "",
        f"- **Source:** `{src.as_posix()}` (another lab member's work, last edited 2026-09-14). It is **not a working git",
        "  repository**: `.git/` holds only `refs/` (copied here: they name the last commit), no objects; `data/` and",
        "  `outputs/` were gitignored, so the labels and weights below existed only in that folder (plus",
        "  `labels_snapshot_20260914.zip`, labels only).",
        f"- **Files:** {len(inc)} files, {tot:,} bytes ({tot / 1e9:.2f} GB). `MANIFEST_sha256.csv` = relpath, bytes,",
        "  mtime (source, ISO local), sha256 of the SOURCE bytes (hashed on the read that fed the copy), rule.",
        f"- **Verification:** every destination file re-hashed against the manifest: {ver['n_verified']} ok, "
        f"{ver['n_mismatch']} mismatches, {ver['n_missing']} missing, {ver['n_extra']} unlisted extra files → "
        f"**{'PASS' if ver['pass'] else 'FAIL'}** ({ver['verified_at']}). Re-check any time with",
        "  `python cv/cv_field/backup_social_field_rat.py --verify-only`.",
        f"- Copy + verify wall time {secs / 60:.1f} min.", "",
        "## Included (rule → files, bytes)", "", "| rule | files | bytes |", "|---|---:|---:|"]
    lines += [f"| {k} | {v[0]} | {v[1]:,} |" for k, v in sorted(by_rule.items())]
    lines += ["", "Rules: `data` = `computer_vision/data/**` (raw_frames, the five `frames_*` folders incl. `manifest.csv`",
              "and `preview/`, `labeled_yolo/`, `labels_backup_20260914/`, `labels_snapshot_20260914.zip`); `runs` =",
              "`computer_vision/outputs/runs/**` (weights `best.pt`/`last.pt`, `args.yaml`, `results.csv`, curves,",
              "`_resolved_data.yaml`); `tracks_csv` = the two `tracks.csv`; `docs_code` = `*.md *.yml *.yaml *.py *.ipynb",
              "*.slurm` outside `.venv`; `amendment_20261005` = the pretrained start checkpoints `computer_vision/weights/*.pt`,",
              "`.git/refs/**`, `.gitkeep` (added before any result; see the plan's amendment).", "",
              "## Excluded (reason → files, bytes; full list in `EXCLUDED_files.csv`)", "",
              "| reason | entries | bytes |", "|---|---:|---:|"]
    lines += [f"| {k} | {v[0]} | {v[1]:,} |" for k, v in sorted(ex_rule.items())]
    lines += ["", "`.venv/` (the author's Python env) and `__pycache__/` are not data. The prediction / tracking videos",
              "(`*.avi`, `trails.mp4`) are regenerable from the weights and the raw cohort-1 video; their `tracks.csv` are kept.",
              "", "## What matters most", "",
              "- Labels: `computer_vision/data/labeled_yolo/labels/{train,val}` (710 / 177 frames, YOLO txt `0 cx cy w h`",
              "  normalised, upright 7680 × 2160 = raw portrait rotated 90° ccw) + the per-clip source folders",
              "  (`raw_frames/CH01_2026-06-30…`, `raw_frames/CH01_2026-07-04…`, `frames_0707_selective`,",
              "  `frames_0630_CH02_selective`, `frames_0706_CH02_selective`) and the two partly labelled, never-trained clips",
              "  `frames_0704_CH02_selective` (60/75 labelled) and `frames_0705_CH01_selective` (33/75).",
              "- Models: `computer_vision/outputs/runs/rat_m_v5/weights/best.pt` (yolo11m, imgsz 1280, the author's best),",
              "  v1-v4 beside it; metrics in `computer_vision/models.md`; pipeline in `computer_vision/WORKFLOW.md`."]
    (dest / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(src: Path, dest: Path) -> int:
    src, dest = Path(src), Path(dest)
    if dest.resolve() == src.resolve() or src.resolve() in dest.resolve().parents:
        raise SystemExit("destination must not be inside the source")
    t0 = time.perf_counter()
    inc, exc = scan(src)
    tot = sum(b for _, b, _, _ in inc)
    print(f"scan: {len(inc)} files to copy ({tot / 1e9:.2f} GB); {len(exc)} excluded entries")
    dest.mkdir(parents=True, exist_ok=True)
    rows = []
    done = 0
    last = time.perf_counter()
    for i, (rel, b, mt, why) in enumerate(inc):
        sha, n = copy_hash(src / rel, dest / rel)
        if n != b:
            raise RuntimeError(f"{rel}: source changed during copy ({b} -> {n} bytes)")
        rows.append({"relpath": rel, "bytes": n, "mtime": datetime.fromtimestamp(mt).isoformat(timespec="seconds"),
                     "sha256": sha, "rule": why})
        done += n
        if time.perf_counter() - last > 60:
            last = time.perf_counter()
            print(f"  {i + 1}/{len(inc)} files, {done / 1e9:.1f}/{tot / 1e9:.1f} GB, {(last - t0) / 60:.1f} min", flush=True)
    with open(dest / MANIFEST, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["relpath", "bytes", "mtime", "sha256", "rule"])
        w.writeheader()
        w.writerows(rows)
    with open(dest / EXCLUDED, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["relpath", "bytes", "reason"])
        w.writerows(exc)
    print(f"copied {len(rows)} files ({done / 1e9:.2f} GB) in {(time.perf_counter() - t0) / 60:.1f} min; verifying ...", flush=True)
    ver = verify(dest)
    secs = time.perf_counter() - t0
    ver["wall_s"] = round(secs, 1)
    ver["src"] = src.as_posix()
    (dest / "VERIFY.json").write_text(json.dumps(ver, indent=2), encoding="utf-8")
    write_readme(dest, src, inc, exc, ver, secs)
    print(json.dumps({k: v for k, v in ver.items() if k not in ("mismatch", "missing", "extra")}, indent=2))
    print(("PASS" if ver["pass"] else "FAIL") + f" — backup verified -> {dest}")
    return 0 if ver["pass"] else 1


def selftest() -> int:
    ok = True

    def rec(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")

    with tempfile.TemporaryDirectory() as tmp:
        src, dest = Path(tmp) / "src", Path(tmp) / "out" / "bk"
        files = {
            "computer_vision/data/labeled_yolo/labels/val/a.txt": b"0 0.5 0.5 0.01 0.03\n",
            "computer_vision/data/labeled_yolo/images/val/a.png": os.urandom(30000),
            "computer_vision/data/frames_x/images/b.txt": b"",
            "computer_vision/data/frames_x/manifest.csv.bak": b"x",
            "computer_vision/outputs/runs/rat_m_v5/weights/best.pt": os.urandom(20000),
            "computer_vision/outputs/runs/rat_m_v5/results.csv": b"epoch\n1\n",
            "computer_vision/outputs/tracks/model_v5/track-2/tracks.csv": b"frame\n",
            "computer_vision/outputs/tracks/model_v5/track-2/trails.mp4": b"v" * 100,
            "computer_vision/outputs/tracks/model_v5/track-2/clip_ccw.avi": b"v" * 100,
            "computer_vision/outputs/predictions/model_v5/predict/x.avi": b"v",
            "computer_vision/weights/yolo11m.pt": b"w",
            "computer_vision/scripts/orientation.py": b"print(1)\n",
            "computer_vision/scripts/__pycache__/orientation.cpython-311.pyc": b"pyc",
            "computer_vision/models.md": b"# m\n",
            "notebooks/n.ipynb": b"{}",
            ".git/refs/heads/main": b"abc\n",
            ".venv/Lib/site.py": b"no",
            "labeling/environment.yml": b"name: x\n",
            "misc/other.bin": b"zz",
        }
        for rel, data in files.items():
            p = src / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        inc, exc = scan(src)
        got = {r for r, _, _, _ in inc}
        want = {k for k in files if not any(s in k for s in (".venv", "__pycache__", ".avi", "trails.mp4", "misc/"))}
        rec("selection = data + runs + tracks.csv + docs/code + amendment; no venv/pycache/videos/other", got == want,
            f"extra {sorted(got - want)} missing {sorted(want - got)}")
        rec("excluded list names the videos, the venv and the unlisted file",
            {"misc/other.bin", "computer_vision/outputs/tracks/model_v5/track-2/trails.mp4"} <= {e[0] for e in exc}
            and any(e[0].startswith(".venv/") for e in exc))
        before = {rel: (src / rel).read_bytes() for rel in files}
        rc = run(src, dest)
        rec("run passes on a clean copy", rc == 0)
        rec("source untouched", all((src / rel).read_bytes() == b for rel, b in before.items())
            and not any(p.name.endswith(".partial") for p in src.rglob("*")))
        man = list(csv.DictReader(open(dest / MANIFEST, encoding="utf-8")))
        rec("manifest sha = sha of the source bytes", all(hashlib.sha256(before[r["relpath"]]).hexdigest() == r["sha256"]
                                                         for r in man))
        rec("mtime preserved", abs((dest / "computer_vision/models.md").stat().st_mtime
                                   - (src / "computer_vision/models.md").stat().st_mtime) < 1e-3)
        p = dest / "computer_vision/outputs/runs/rat_m_v5/weights/best.pt"
        b = bytearray(p.read_bytes())
        b[100] ^= 0xFF
        p.write_bytes(bytes(b))
        (dest / "computer_vision/data/frames_x/images/b.txt").unlink()
        v = verify(dest)
        rec("verify catches 1 flipped byte and 1 deleted file", v["n_mismatch"] == 1 and v["n_missing"] == 1 and not v["pass"],
            f"{v['n_mismatch']} mismatch, {v['n_missing']} missing")
        rec("README + EXCLUDED list written", (dest / "README.md").is_file() and (dest / EXCLUDED).is_file())
        try:
            run(src, src / "inner")
            rec("refuses a destination inside the source", False)
        except SystemExit:
            rec("refuses a destination inside the source", True)
    print(("PASS" if ok else "FAIL") + " — backup_social_field_rat self-test")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], allow_abbrev=False)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--verify-only", action="store_true")
    ap.add_argument("--src", default=str(DEFAULT_SRC))
    ap.add_argument("--dest", default=str(DEFAULT_DEST))
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.verify_only:
        v = verify(Path(a.dest))
        print(json.dumps(v, indent=2))
        return 0 if v["pass"] else 1
    return run(Path(a.src), Path(a.dest))


if __name__ == "__main__":
    sys.exit(main())
