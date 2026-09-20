#!/usr/bin/env python
"""SHA-256 manifest of a raw-data tree, and comparison of two manifests.

Used to verify the backup copy of the raw neurologger tree (E:\\3rd_rat_spikes -> L:\\3rd_rat_spikes,
2026-09-18) beyond robocopy's size+timestamp check: every byte of both copies is read once and hashed,
which also serves as a full-surface read verification of each drive. One instance per drive, run in
parallel; sequential reads only (one file at a time, 16 MB chunks), so it adds no seek load.

    python ephys/backup_manifest.py hash    --root E:\\3rd_rat_spikes --out <manifest_E.csv> [--resume]
    python ephys/backup_manifest.py compare --a <manifest_E.csv> --b <manifest_L.csv> [--report <md>]

Manifest CSV columns: relpath, size, mtime_utc (ISO 8601), sha256.  Rows are flushed after every file,
and --resume skips files whose size and mtime already match a row in the existing manifest, so an
interrupted run loses at most the file it was reading.

compare exits 0 only when both manifests list the same files with identical size and sha256; a
timestamp difference is reported as a warning (it does not change the data) but does not fail.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import os
import queue
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

CHUNK = 16 * 1024 * 1024
FIELDS = ["relpath", "size", "mtime_utc", "sha256"]


def _mtime_iso(st: os.stat_result) -> str:
    return datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(timespec="microseconds")


def _walk(root: Path) -> list[tuple[str, int, str]]:
    """All regular files under root as (relpath, size, mtime_utc), sorted by relpath."""
    out = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames.sort()
        for fn in sorted(filenames):
            p = Path(dirpath) / fn
            if p.is_symlink():
                continue
            st = p.stat()
            out.append((p.relative_to(root).as_posix(), st.st_size, _mtime_iso(st)))
    out.sort()
    return out


def _sha256(path: Path) -> str:
    """Hash a file with the read and the digest overlapped.

    A reader thread fills a short queue of CHUNK-sized blocks while the main thread digests them.
    Both the read and hashlib.update release the GIL, so the disk stays busy while the CPU hashes;
    a plain read-then-hash loop tops out at 1/(1/disk + 1/sha) - about 150 MB/s for a 210 MB/s disk
    and a 535 MB/s SHA-256 (this PC) - whereas the overlapped loop is disk-bound.
    """
    q: queue.Queue = queue.Queue(maxsize=3)
    err: list[BaseException] = []

    def reader() -> None:
        try:
            with open(path, "rb", buffering=0) as f:
                while True:
                    b = f.read(CHUNK)
                    if not b:
                        break
                    q.put(b)
        except BaseException as e:  # propagate to the consumer
            err.append(e)
        finally:
            q.put(None)

    t = threading.Thread(target=reader, name="reader", daemon=True)
    t.start()
    h = hashlib.sha256()
    while True:
        b = q.get()
        if b is None:
            break
        h.update(b)
    t.join()
    if err:
        raise err[0]
    return h.hexdigest()


def _load(path: Path) -> dict[str, dict]:
    """Rows of a manifest keyed by relpath; a truncated last line (killed mid-write) is dropped."""
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    out = {}
    for r in rows:
        sha = r.get("sha256") or ""
        if len(sha) == 64 and r.get("size") and r.get("mtime_utc") and r.get("relpath"):
            out[r["relpath"]] = r
    return out


def _load_for_resume(out: Path) -> dict[str, dict]:
    """Rows from the finished manifest AND from an interrupted run's .partial file (both are valid)."""
    prev = _load(out)
    prev.update(_load(out.with_suffix(out.suffix + ".partial")))
    return prev


def cmd_hash(a: argparse.Namespace) -> int:
    root = Path(a.root)
    out = Path(a.out)
    if not root.is_dir():
        print(f"ERROR: root is not a directory: {root}", file=sys.stderr)
        return 2
    files = _walk(root)
    total_bytes = sum(s for _, s, _ in files)
    prev = _load_for_resume(out) if a.resume else {}
    kept = {rp: prev[rp] for rp, s, m in files
            if rp in prev and int(prev[rp]["size"]) == s and prev[rp]["mtime_utc"] == m}
    todo = [(rp, s, m) for rp, s, m in files if rp not in kept]
    todo_bytes = sum(s for _, s, _ in todo)
    print(f"{root}: {len(files)} files, {total_bytes/1e12:.3f} TB; "
          f"{len(kept)} already in manifest, {len(todo)} to hash ({todo_bytes/1e12:.3f} TB)", flush=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".partial")
    done_bytes = 0
    t0 = time.time()
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for rp, s, m in files:
            if rp in kept:
                w.writerow(kept[rp])
                continue
            t1 = time.time()
            digest = _sha256(root / rp)
            st = (root / rp).stat()   # re-stat after the read: catch a file that changed underneath us
            if st.st_size != s or _mtime_iso(st) != m:
                print(f"WARNING: {rp} changed while being hashed (size {s}->{st.st_size}); "
                      f"recorded with the post-read metadata", file=sys.stderr, flush=True)
                s, m = st.st_size, _mtime_iso(st)
            w.writerow({"relpath": rp, "size": s, "mtime_utc": m, "sha256": digest})
            f.flush()
            os.fsync(f.fileno())
            done_bytes += s
            dt = max(time.time() - t1, 1e-6)
            el = time.time() - t0
            rate = done_bytes / max(el, 1e-6)
            eta_h = (todo_bytes - done_bytes) / rate / 3600 if rate > 0 else float("nan")
            print(f"{done_bytes/max(todo_bytes,1)*100:6.2f}%  {s/1e9:8.3f} GB  {s/dt/1e6:7.1f} MB/s  "
                  f"avg {rate/1e6:7.1f} MB/s  eta {eta_h:5.2f} h  {rp}", flush=True)
    os.replace(tmp, out)
    print(f"manifest written: {out}  ({len(files)} rows, {(time.time()-t0)/3600:.2f} h)", flush=True)
    return 0


def cmd_compare(a: argparse.Namespace) -> int:
    ma, mb = _load(Path(a.a)), _load(Path(a.b))
    only_a = sorted(set(ma) - set(mb))
    only_b = sorted(set(mb) - set(ma))
    common = sorted(set(ma) & set(mb))
    size_bad, hash_bad, mtime_warn = [], [], []
    bytes_ok = 0
    for rp in common:
        ra, rb = ma[rp], mb[rp]
        if int(ra["size"]) != int(rb["size"]):
            size_bad.append(rp)
        elif ra["sha256"] != rb["sha256"]:
            hash_bad.append(rp)
        else:
            bytes_ok += int(ra["size"])
            if ra["mtime_utc"] != rb["mtime_utc"]:
                mtime_warn.append(rp)
    ok = not (only_a or only_b or size_bad or hash_bad)
    lines = [
        f"# Manifest comparison - {'IDENTICAL' if ok else 'MISMATCH'}",
        "",
        f"- A: `{a.a}` - {len(ma)} files",
        f"- B: `{a.b}` - {len(mb)} files",
        f"- files in both with identical size and SHA-256: **{len(common) - len(size_bad) - len(hash_bad)}** "
        f"({bytes_ok/1e12:.3f} TB)",
        f"- only in A: {len(only_a)}",
        f"- only in B: {len(only_b)}",
        f"- size mismatch: {len(size_bad)}",
        f"- SHA-256 mismatch (same size): {len(hash_bad)}",
        f"- timestamp differs (data identical): {len(mtime_warn)}",
        "",
    ]
    for title, lst in (("Only in A", only_a), ("Only in B", only_b), ("Size mismatch", size_bad),
                       ("SHA-256 mismatch", hash_bad), ("Timestamp differs", mtime_warn)):
        if lst:
            lines.append(f"## {title} ({len(lst)})")
            lines.extend(f"- `{rp}`" for rp in lst[:200])
            if len(lst) > 200:
                lines.append(f"- ... {len(lst) - 200} more")
            lines.append("")
    text = "\n".join(lines)
    print(text)
    if a.report:
        Path(a.report).parent.mkdir(parents=True, exist_ok=True)
        Path(a.report).write_text(text + "\n", encoding="utf-8")
    return 0 if ok else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("hash", help="hash every file under --root into a manifest CSV")
    h.add_argument("--root", required=True)
    h.add_argument("--out", required=True)
    h.add_argument("--resume", action="store_true", help="keep rows whose size+mtime still match")
    h.set_defaults(func=cmd_hash)
    c = sub.add_parser("compare", help="compare two manifests")
    c.add_argument("--a", required=True)
    c.add_argument("--b", required=True)
    c.add_argument("--report", help="write the markdown summary here as well")
    c.set_defaults(func=cmd_compare)
    a = p.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
