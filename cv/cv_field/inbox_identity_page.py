r"""inbox_identity_page.py — in-box cameras CH07 / CH08, phase 0, part C: the identity click page for the user.

Specification: implementation_plan/2026-10-10-inbox-ch0708-wiser-identity-p0.md (section C) + its dated amendments.
Reads an inbox_p0.py run (colour_segments.csv, colour_threshold.json, states_1s.npz, scan/ key-frame tables) and writes
<run>/identity_page/: index.html (self-contained, file://, no network), frames/ (full-resolution JPEG, quality 95,
upright as recorded), closeups/ (the six in-hand clips $OUT/2026c/inhand_closeups/SF07.MOV ... SF12.MOV - read-only,
sha256 checked against that folder's MANIFEST_sha256.csv - transcoded ONCE to H.264 MP4; sources untouched, their
sha256 recorded before and after), page_data.json, page_check.json.

One entry per colour segment (deduplicated by configuration = one entry per segment):
  frames   colour_mid = the first frame with time >= (start + end) / 2; ir_p06 / ir_p15 = the first frames with time >=
           end + 6 s / end + 15 s (after the ~3-s IR white-out); time = file-name start + PTS (field-PC local); each frame's
           chroma is recomputed and flagged if a colour frame is < thr or an IR frame >= thr.
  lid      each frame's lid-closed segment and its correction (frame px -> the 09-04 12:00 reference px, the 2 x 3 matrix B
           of frame_correction.Corrections("2026c").correction(cam, t)), with the flag; recorded only, nothing fitted.
  WISER    roster of the camera's house (CH07 -> house_2, CH08 -> house_1) at the segment middle from the cleaned per-second
           states (inbox_p0 states_1s.npz); "SF11 untagged after 09-07 06:10:45 — may be present"; per roster animal the
           mean position over [start - 60 s, start) in the house frame (along / across the ridge, inches), SE = sd(raw
           fixes) / sqrt(n), +-1 SD of the raw fixes, and the IMU still / active / locomoting shares of that minute.
The user clicks each visible rat's head (colour frame; optionally IR frames), picks SF07-SF12 / unknown and sure /
likely, and answers "pile composition complete? yes / no" per segment. localStorage autosave; Export CSV + JSON (named
inbox_identity_2026c_<timestamp>.*, to be saved into cv/configs/inbox_identity_2026c/); Import JSON. The page carries
NO pre-filled identity; the agent never looks at the frames.

Usage (cv env, PYTHONIOENCODING=utf-8):
  python cv/cv_field/inbox_identity_page.py --run <inbox_p0 run dir> [--closeups <folder with SF07.MOV ...>]
  python cv/cv_field/inbox_identity_page.py --selftest
"""
from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import inbox_p0 as ip  # noqa: E402

FFMPEG = Path("C:/ffmpeg/bin/ffmpeg.exe")
CLOSEUP_SRC = ip.OUT_ROOT / "2026c" / "inhand_closeups"     # read-only; MANIFEST_sha256.csv + README.md there
CLOSEUP_LABELS = ("SF07", "SF08", "SF09", "SF10", "SF11", "SF12")
IR_OFFSETS = (("ir_p06", 6.0), ("ir_p15", 15.0))
JPEG_Q = 95
PRE_WINDOW_S = 60.0
BODY_IN = (62.55 / 2.54, 45.72 / 2.54)           # house body, long side along the ridge (CAMERA_GEOMETRY_2026c.md section 4)
PAGE_VERSION = "inbox_identity_2026c_v1"
EXPORT_DIR = "cv/configs/inbox_identity_2026c/"
LEGEND = [
    {"animal": "SF07", "tag": "3079", "coban": "green", "sticker": "orange", "ir_pattern": "x", "note": ""},
    {"animal": "SF08", "tag": "3062", "coban": "red", "sticker": "silver", "ir_pattern": "none", "note": ""},
    {"animal": "SF09", "tag": "3077", "coban": "pink/black/brown", "sticker": "blue", "ir_pattern": "star", "note": ""},
    {"animal": "SF10", "tag": "306b", "coban": "blue -> yellow from 08-31", "sticker": "yellow", "ir_pattern": "square with cross", "note": ""},
    {"animal": "SF11", "tag": "305a -> 3058 from 09-02", "coban": "white", "sticker": "green", "ir_pattern": "circle",
     "note": "tag retired 09-07 06:10:45; the animal stays in the paddock untagged (invisible to WISER)"},
    {"animal": "SF12", "tag": "3059", "coban": "yellow -> blue from 08-31", "sticker": "red", "ir_pattern": "two lines", "note": ""},
]


# ----------------------------------------------------------------------------------------------- frames
def key_index(run: Path) -> dict:
    """file path -> {pts: frame index} for every scanned key frame."""
    kf = ip.load_scan(run, "scan")
    return {f: dict(zip(g.pts.astype(int), g.frame_idx.astype(int))) for f, g in kf.groupby("file")}, kf


def grab_frame(files: pd.DataFrame, kidx: dict, cam: str, t: datetime) -> tuple[np.ndarray | None, dict]:
    """The first frame with time >= t (file-name start + PTS): RGB full resolution + its file, frame index, pts, time, chroma."""
    import av
    r = files[(files.camera == cam) & (files.start_t <= t) & (files.end_t > t)]
    if r.empty:
        return None, {"error": f"no file of {cam} covers {t}"}
    r = r.iloc[0]
    st = r.start_t.to_pydatetime()
    rel = (t - st).total_seconds()
    ki = kidx.get(r.file, {})
    with av.open(r.file) as c:
        s = c.streams.video[0]
        tb = float(s.time_base)
        c.seek(max(0, int((rel - 0.001) / tb)), stream=s, backward=True, any_frame=False)
        cur = None
        for f in c.decode(s):
            if f.pts is None:
                continue
            cur = ki.get(int(f.pts), None) if cur is None else cur + 1
            if cur is None:
                cur = -10**9
            trel = f.pts * tb
            if trel >= rel - 1e-6:
                c_val, _ = ip.frame_measures(f)
                img = f.to_ndarray(format="rgb24")
                tt = st + timedelta(seconds=trel)
                return img, {"file": Path(r.file).name, "file_path": r.file, "frame_idx": cur if cur >= 0 else None, "pts": int(f.pts),
                             "time": f"{tt:%Y-%m-%d %H:%M:%S.%f}"[:-3], "chroma": round(c_val, 4)}
    return None, {"error": f"no frame at/after {t} in {r.file}"}


def write_jpeg(img: np.ndarray, path: Path) -> None:
    import cv2
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), cv2.cvtColor(img, cv2.COLOR_RGB2BGR), [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_Q]):
        raise IOError(f"could not write {path}")


def lid_correction(C, cam: str, t: datetime) -> dict:
    try:
        B, info = C.correction(cam, t)
    except Exception as ex:  # noqa: BLE001
        return {"error": repr(ex)}
    return {"lid_segment": info.get("segment"), "lid_open": bool(info.get("lid_open")), "flag": info.get("flag"),
            "target_frame": info.get("target_frame"), "used": info.get("used"),
            "B_frame_to_ref": None if B is None else [[round(float(v), 8) for v in row] for row in np.asarray(B)]}


# ----------------------------------------------------------------------------------------------- WISER panel
def wiser_panel(run: Path, seg: pd.Series, z: dict, track_root: Path | None = None, cache: dict | None = None) -> dict:
    t0 = datetime.fromisoformat(str(z["t0"]))
    labs = [str(x) for x in z["labels"]]
    start, mid = datetime.fromisoformat(seg.start), datetime.fromisoformat(seg.mid)
    house = ip.CAM_HOUSE[seg.camera]
    code = ip.HOUSE_CODE[house]
    k = int((mid - t0).total_seconds())
    n = z["states"].shape[1]
    roster, other, out, unknown = [], [], [], []
    for j, lab in enumerate(labs):
        if lab not in ip.LABELS:
            continue
        s = int(z["states"][j, k]) if 0 <= k < n else ip.S_UNK
        if lab == "SF11" and ip.untagged("SF11", mid):
            continue
        if s == code:
            roster.append(lab)
        elif s in (ip.S_H1, ip.S_H2):
            other.append(f"{lab} ({ip.STATE_NAME[s]})")
        elif s == ip.S_OUT:
            out.append(lab)
        else:
            unknown.append(lab)
    mp, poses = ip.load_map(), ip.house_poses()
    cache = cache if cache is not None else {}
    pos = []
    a = start - timedelta(seconds=PRE_WINDOW_S)
    for lab in roster:
        key = (lab, a.date())
        if key not in cache:
            days = sorted({a.strftime("%Y-%m-%d"), start.strftime("%Y-%m-%d")})
            df = ip.load_label(lab, days, track_root)
            cache[key] = df.loc[ip.fix_mask(df, "primary")].reset_index(drop=True)
        df = cache[key]
        j = labs.index(lab)
        d = df[(df.t >= a) & (df.t < start)]
        if len(d):
            sec = ((d["t"] - pd.Timestamp(t0)).dt.total_seconds().to_numpy() // 1).astype(np.int64)
            inside = (sec >= 0) & (sec < n)
            keep = np.zeros(len(d), bool)
            keep[inside] = z["states"][j, sec[inside]] == code
            keep &= ip.house_membership(d["x"].to_numpy(), d["y"].to_numpy(), ip.load_rois())[house]   # as inbox_p0 in-house fixes
            d = d.loc[keep]
        st = ip.window_stats(d, mp, poses[house])
        pos.append({"animal": lab, **{kk: (round(v, 4) if isinstance(v, float) else v) for kk, v in st.items()}})
    sf11_note = ("SF11 untagged after 09-07 06:10:45 - may be present" if mid >= ip.SF11_UNTAGGED[1][0]
                 else "SF11 untagged 09-02 00:03-08:15 - may be present" if ip.untagged("SF11", mid) else "")
    return {"house": house, "at": seg.mid, "roster": roster, "other_house": other, "out": out, "untracked": unknown,
            "sf11_note": sf11_note, "window": f"{a:%H:%M:%S}-{start:%H:%M:%S} (the minute before colour ON)",
            "positions": pos, "pose": poses[house], "body_in": [round(BODY_IN[0], 3), round(BODY_IN[1], 3)]}


# ----------------------------------------------------------------------------------------------- close-ups
def transcode_closeups(src_dir: Path, out_dir: Path, ffmpeg: Path = FFMPEG, labels=CLOSEUP_LABELS) -> list[dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    man = {}
    if (src_dir / "MANIFEST_sha256.csv").exists():
        man = dict(pd.read_csv(src_dir / "MANIFEST_sha256.csv")[["file", "sha256"]].itertuples(index=False, name=None))
    rows = []
    for lab in labels:
        src = src_dir / f"{lab}.MOV"
        dst = out_dir / f"{lab}.mp4"
        if not src.exists():
            rows.append({"animal": lab, "src": src.as_posix(), "error": "missing"})
            continue
        h0, m0 = ip.sha256(src), src.stat().st_mtime
        if man and man.get(src.name) != h0:
            rows.append({"animal": lab, "src": src.as_posix(), "error": f"sha256 {h0} does not match the folder manifest"})
            continue
        if not dst.exists():
            cmd = [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-n", "-i", str(src), "-c:v", "libx264", "-preset", "medium",
                   "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(dst)]
            p = subprocess.run(cmd, capture_output=True, text=True)
            if p.returncode != 0:
                rows.append({"animal": lab, "src": src.as_posix(), "error": p.stderr[-500:]})
                continue
        h1, m1 = ip.sha256(src), src.stat().st_mtime
        rows.append({"animal": lab, "src": src.as_posix(), "dst": f"closeups/{lab}.mp4", "src_sha256": h0,
                     "manifest_match": (man.get(src.name) == h0) if man else None,
                     "src_unchanged": bool(h0 == h1 and m0 == m1), "dst_bytes": dst.stat().st_size})
    return rows


# ----------------------------------------------------------------------------------------------- page
def build(run: Path, closeup_src: Path = CLOSEUP_SRC, track_root: Path | None = None, corrections=None, ffmpeg: Path = FFMPEG) -> dict:
    page = run / "identity_page"
    (page / "frames").mkdir(parents=True, exist_ok=True)
    seg = pd.read_csv(run / "colour_segments.csv")
    thr = json.loads((run / "colour_threshold.json").read_text(encoding="utf-8"))["thr"]
    kidx, kf = key_index(run)
    files = ip.file_table(kf, run)
    z = dict(np.load(run / "states_1s.npz", allow_pickle=False))
    if corrections is None:
        from frame_correction import Corrections
        corrections = Corrections("2026c")
    cache, entries = {}, []
    for s in seg.itertuples():
        sid = s.segment_id
        start, end, mid = (datetime.fromisoformat(x) for x in (s.start, s.end, s.mid))
        frames = []
        for kind, t in (("colour_mid", mid),) + tuple((k, end + timedelta(seconds=o)) for k, o in IR_OFFSETS):
            img, info = grab_frame(files, kidx, s.camera, t)
            fn = f"frames/{sid}_{kind}.jpg"
            if img is not None:
                write_jpeg(img, page / fn)
                info["path"] = fn
                info["width"], info["height"] = int(img.shape[1]), int(img.shape[0])
                tt = datetime.fromisoformat(info["time"])
                info["mode_check"] = ("ok" if (info["chroma"] >= thr) == (kind == "colour_mid") else
                                      f"MISMATCH: chroma {info['chroma']} vs thr {thr:.4g}")
                info["lid"] = lid_correction(corrections, s.camera, tt)
            info.update({"kind": kind, "target_time": f"{t:%Y-%m-%d %H:%M:%S.%f}"[:-3]})
            info.pop("file_path", None)
            frames.append(info)
        panel = wiser_panel(run, pd.Series(s._asdict()), z, track_root, cache)
        entries.append({"segment_id": sid, "camera": s.camera, "house": s.house, "start": s.start, "end": s.end, "mid": s.mid,
                        "duration_s": s.duration_s, "median_chroma": s.median_chroma, "n_colour_keyframes": int(s.n_colour_keyframes),
                        "flags": "" if pd.isna(s.flags) else str(s.flags), "lid_event": "" if pd.isna(s.lid_event) else str(s.lid_event),
                        "log_row": None if pd.isna(s.log_row) else int(s.log_row), "log_kind": "" if pd.isna(s.log_kind) else str(s.log_kind),
                        "frames": frames, "wiser": panel})
        print(f"[page] {sid}: {[f.get('mode_check', f.get('error')) for f in frames]} roster {panel['roster']}", flush=True)
    clips = transcode_closeups(closeup_src, page / "closeups", ffmpeg)
    meta = {"page_version": PAGE_VERSION, "run": run.as_posix(), "made": datetime.now().isoformat(timespec="seconds"),
            "plan": ip.PLAN, "export_dir": EXPORT_DIR, "threshold": thr, "n_segments": len(entries)}
    data = {"meta": meta, "legend": LEGEND, "closeups": clips, "segments": entries}
    (page / "page_data.json").write_text(json.dumps(data, indent=1, default=str), encoding="utf-8")
    (page / "index.html").write_text(render_html(data), encoding="utf-8")
    chk = check_page(page)
    (page / "page_check.json").write_text(json.dumps(chk, indent=2), encoding="utf-8")
    print(f"[page] {len(entries)} segments -> {(page / 'index.html').as_posix()}; check: {chk['verdict']}", flush=True)
    return chk


def check_page(page: Path) -> dict:
    """Every media path referenced by the page resolves; no network URL anywhere in the page."""
    txt = (page / "index.html").read_text(encoding="utf-8")
    m = re.search(r"<script id=\"page-data\" type=\"application/json\">(.*?)</script>", txt, re.S)
    data = json.loads(html.unescape(m.group(1))) if m else {}
    paths = [f["path"] for s in data.get("segments", []) for f in s["frames"] if f.get("path")]
    paths += [c["dst"] for c in data.get("closeups", []) if c.get("dst")]
    static = re.sub(r"<script[^>]*>.*?</script>", "", txt, flags=re.S)
    paths += re.findall(r"(?:src|href)=\"([^\"#][^\"]*)\"", static)
    missing = sorted({p for p in paths if not re.match(r"(?i)[a-z][a-z0-9+.-]*:", p) and not (page / p).exists()})
    net = sorted(set(re.findall(r"(?i)(?:https?:|ftp:|wss?:)//[^\s\"'<>]*", txt)) | set(re.findall(r"(?i)[\"'(]//[a-z0-9.-]+\.[a-z]{2,}", txt)))
    n_frames = sum(1 for s in data.get("segments", []) for f in s["frames"] if f.get("path"))
    mism = [f"{s['segment_id']} {f['kind']}" for s in data.get("segments", []) for f in s["frames"] if str(f.get("mode_check", "")).startswith("MISMATCH")]
    errs = [f"{s['segment_id']} {f['kind']}: {f['error']}" for s in data.get("segments", []) for f in s["frames"] if f.get("error")]
    prefilled = [c for s in data.get("segments", []) for c in s.get("clicks", [])]
    return {"verdict": "PASS" if not missing and not net and not prefilled else "FAIL", "n_paths": len(set(paths)),
            "missing": missing, "network_urls": net, "n_segments": len(data.get("segments", [])), "n_frames": n_frames,
            "frame_errors": errs, "mode_mismatches": mism, "prefilled_identities": len(prefilled),
            "closeups": [c.get("dst") or c.get("error") for c in data.get("closeups", [])]}


PAGE_CSS = """
:root{--bg:#f6f6f4;--fg:#1d1d1b;--mut:#6b6b66;--card:#fff;--line:#d9d9d4;--acc:#1f6feb;--warn:#b54708;--ok:#1a7f37}
@media (prefers-color-scheme: dark){:root{--bg:#161615;--fg:#ecece8;--mut:#a3a39c;--card:#20201e;--line:#3a3a36;--acc:#6ea8fe;--warn:#f79009;--ok:#4ac26b}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.4 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
header{padding:10px 16px;border-bottom:1px solid var(--line);display:flex;gap:16px;align-items:center;flex-wrap:wrap}
header h1{font-size:17px;margin:0}header .sp{flex:1}button,select,input{font:inherit}
button{border:1px solid var(--line);background:var(--card);color:var(--fg);border-radius:6px;padding:4px 10px;cursor:pointer}
button.on{background:var(--acc);color:#fff;border-color:var(--acc)}
#wrap{display:grid;grid-template-columns:250px minmax(0,1fr) 380px;gap:0;height:calc(100vh - 54px)}
#list{overflow:auto;border-right:1px solid var(--line)}#side{overflow:auto;border-left:1px solid var(--line);padding:10px}
.seg{padding:7px 10px;border-bottom:1px solid var(--line);cursor:pointer}.seg.cur{background:var(--card);box-shadow:inset 3px 0 0 var(--acc)}
.seg small{color:var(--mut);display:block}.badge{font-size:11px;padding:0 5px;border-radius:8px;border:1px solid var(--line);margin-left:4px}
#main{display:flex;flex-direction:column;min-width:0}
#tabs{display:flex;gap:6px;padding:8px;border-bottom:1px solid var(--line);flex-wrap:wrap;align-items:center}
#viewer{position:relative;flex:1;overflow:hidden;background:#000;cursor:crosshair;min-height:300px}
#stage{position:absolute;left:0;top:0;transform-origin:0 0}#stage img{display:block;user-select:none;-webkit-user-drag:none}
#stage svg{position:absolute;left:0;top:0;pointer-events:none}
#pop{position:absolute;display:none;background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px;z-index:5;box-shadow:0 4px 16px rgba(0,0,0,.35)}
#pop .ids button{margin:2px}#below{max-height:30vh;overflow:auto;padding:8px;border-top:1px solid var(--line)}
table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid var(--line);padding:3px 5px;text-align:left;font-size:12.5px;vertical-align:top}
h2{font-size:14px;margin:12px 0 6px}.mut{color:var(--mut)}.warn{color:var(--warn)}.ok{color:var(--ok)}
video{width:100%;max-height:260px;background:#000}details{margin:6px 0}code{font-size:12px}
#help{font-size:12.5px;color:var(--mut)}
@media (max-width:1100px){#wrap{grid-template-columns:1fr;height:auto}#viewer{height:70vh}#list,#side{max-height:40vh;border:0}}
"""

PAGE_JS = r"""
(function(){
'use strict';
const DATA = JSON.parse(document.getElementById('page-data').textContent);
const SEGS = DATA.segments;
const IDS = ['SF07','SF08','SF09','SF10','SF11','SF12','unknown'];
const KEYS = {'7':'SF07','8':'SF08','9':'SF09','0':'SF10','1':'SF11','2':'SF12','u':'unknown'};
const COLS = {'SF07':'#e6194b','SF08':'#3cb44b','SF09':'#4363d8','SF10':'#f58231','SF11':'#911eb4','SF12':'#42d4f4','unknown':'#bfbfbf'};
const LSKEY = DATA.meta.page_version + '::' + DATA.meta.run;
let state = {clicks: [], segments: {}};
let cur = 0, kind = 'colour_mid', sel = null, conf = 'sure';
let view = {s: 1, tx: 0, ty: 0};
function load(){ try { const s = localStorage.getItem(LSKEY); if (s) { const o = JSON.parse(s); if (o && o.clicks) state = o; } } catch (e) {} }
function save(){ try { localStorage.setItem(LSKEY, JSON.stringify(state)); } catch (e) {} renderList(); }
function el(t, a, h){ const e = document.createElement(t); if (a) for (const k in a) e.setAttribute(k, a[k]); if (h !== undefined) e.innerHTML = h; return e; }
function esc(s){ return String(s === null || s === undefined ? '' : s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
function seg(){ return SEGS[cur]; }
function frame(){ return seg().frames.find(f => f.kind === kind); }
function segClicks(id){ return state.clicks.filter(c => c.segment_id === id); }
function renderList(){
  const L = document.getElementById('list'); L.innerHTML = '';
  SEGS.forEach((s, i) => {
    const n = segClicks(s.segment_id).length, st = (state.segments[s.segment_id] || {}).complete || '';
    const d = el('div', {class: 'seg' + (i === cur ? ' cur' : '')});
    d.innerHTML = '<b>' + esc(s.camera) + '</b> ' + esc(s.start.slice(5, 19)) + '<span class="badge">' + n + ' clicks</span>' +
      (st ? '<span class="badge">complete: ' + esc(st) + '</span>' : '') +
      '<small>' + esc(s.duration_s) + ' s · ' + esc(s.house) + (s.lid_event ? ' · lid event' : '') + (s.log_kind ? ' · log: ' + esc(s.log_kind) : ' · not in the log') + '</small>';
    d.onclick = () => { cur = i; sel = null; kind = 'colour_mid'; show(); };
    L.appendChild(d);
  });
}
function fit(){
  const V = document.getElementById('viewer'), f = frame(); if (!f) return;
  const W = f.width || 2560, H = f.height || 1920;
  view.s = Math.min(V.clientWidth / W, V.clientHeight / H); view.tx = (V.clientWidth - W * view.s) / 2; view.ty = (V.clientHeight - H * view.s) / 2; apply();
}
function apply(){ document.getElementById('stage').style.transform = 'translate(' + view.tx + 'px,' + view.ty + 'px) scale(' + view.s + ')'; }
function drawPoints(){
  const svg = document.getElementById('pts'), f = frame(); svg.innerHTML = '';
  if (!f) return;
  svg.setAttribute('viewBox', '0 0 ' + (f.width || 2560) + ' ' + (f.height || 1920));
  svg.setAttribute('width', f.width || 2560); svg.setAttribute('height', f.height || 1920);
  state.clicks.forEach((c, i) => {
    if (c.segment_id !== seg().segment_id || c.frame_kind !== kind) return;
    const col = COLS[c.animal] || '#fff', r = 16;
    const g = document.createElementNS(svg.namespaceURI, 'g');
    g.innerHTML = '<circle cx="' + c.u_px + '" cy="' + c.v_px + '" r="' + r + '" fill="none" stroke="' + col + '" stroke-width="' + (i === sel ? 7 : 4) + '"/>' +
      '<circle cx="' + c.u_px + '" cy="' + c.v_px + '" r="3" fill="' + col + '"/>' +
      '<text x="' + (c.u_px + 22) + '" y="' + (c.v_px - 18) + '" fill="' + col + '" font-size="40" font-weight="700" stroke="#000" stroke-width="1.5">' + esc(c.animal || '?') + (c.confidence === 'likely' ? '?' : '') + '</text>';
    svg.appendChild(g);
  });
}
function renderTable(){
  const s = seg(), rows = state.clicks.map((c, i) => [c, i]).filter(x => x[0].segment_id === s.segment_id);
  let h = '<table><tr><th>#</th><th>frame</th><th>u, v (px)</th><th>id</th><th>confidence</th><th></th></tr>';
  rows.forEach(([c, i]) => {
    h += '<tr' + (i === sel ? ' style="background:var(--card)"' : '') + '><td>' + i + '</td><td>' + esc(c.frame_kind) + '</td><td>' + c.u_px.toFixed(1) + ', ' + c.v_px.toFixed(1) +
      '</td><td><select data-i="' + i + '" class="sid">' + ['<option value="">(pick)</option>'].concat(IDS.map(x => '<option' + (x === c.animal ? ' selected' : '') + '>' + x + '</option>')).join('') +
      '</select></td><td><select data-i="' + i + '" class="scf"><option' + (c.confidence === 'sure' ? ' selected' : '') + '>sure</option><option' + (c.confidence === 'likely' ? ' selected' : '') + '>likely</option></select></td>' +
      '<td><button data-i="' + i + '" class="del">delete</button></td></tr>';
  });
  h += '</table>';
  const ss = state.segments[s.segment_id] || {};
  h += '<p><b>Pile composition complete?</b> <label><input type="radio" name="pc" value="yes"' + (ss.complete === 'yes' ? ' checked' : '') + '> yes</label> ' +
       '<label><input type="radio" name="pc" value="no"' + (ss.complete === 'no' ? ' checked' : '') + '> no</label> ' +
       '<label><input type="radio" name="pc" value=""' + (!ss.complete ? ' checked' : '') + '> not answered</label> &nbsp; note: <input id="snote" size="40" value="' + esc(ss.note || '') + '"></p>';
  const B = document.getElementById('below'); B.innerHTML = h;
  B.querySelectorAll('.sid').forEach(e => e.onchange = () => { state.clicks[+e.dataset.i].animal = e.value || null; save(); drawPoints(); });
  B.querySelectorAll('.scf').forEach(e => e.onchange = () => { state.clicks[+e.dataset.i].confidence = e.value; save(); drawPoints(); });
  B.querySelectorAll('.del').forEach(e => e.onclick = () => { state.clicks.splice(+e.dataset.i, 1); sel = null; save(); show(false); });
  B.querySelectorAll('input[name=pc]').forEach(e => e.onchange = () => { (state.segments[s.segment_id] = state.segments[s.segment_id] || {}).complete = e.value; save(); });
  document.getElementById('snote').onchange = e => { (state.segments[s.segment_id] = state.segments[s.segment_id] || {}).note = e.target.value; save(); };
}
function renderSide(){
  const s = seg(), w = s.wiser, f = frame();
  let h = '<h2>Segment ' + esc(s.segment_id) + '</h2><table>' +
    '<tr><td>camera / house</td><td>' + esc(s.camera) + ' / ' + esc(s.house) + '</td></tr>' +
    '<tr><td>colour ON-OFF</td><td>' + esc(s.start.slice(11)) + ' - ' + esc(s.end.slice(11)) + ' (' + esc(s.duration_s) + ' s)</td></tr>' +
    '<tr><td>colour log</td><td>' + (s.log_kind ? 'row ' + esc(s.log_row) + ': ' + esc(s.log_kind) : '<span class="warn">no matching row</span>') + '</td></tr>' +
    '<tr><td>lid event</td><td>' + esc(s.lid_event || '-') + '</td></tr>' + (s.flags ? '<tr><td>flags</td><td class="warn">' + esc(s.flags) + '</td></tr>' : '') + '</table>';
  if (f) {
    h += '<h2>This frame</h2><table><tr><td>kind</td><td>' + esc(f.kind) + '</td></tr><tr><td>time</td><td>' + esc(f.time || '') + '</td></tr>' +
      '<tr><td>file / frame</td><td>' + esc(f.file || '') + ' / ' + esc(f.frame_idx) + '</td></tr><tr><td>chroma</td><td>' + esc(f.chroma) + ' (' + esc(f.mode_check || '') + ')</td></tr>';
    if (f.lid) h += '<tr><td>lid segment</td><td>' + esc(f.lid.lid_segment) + ' (' + esc(f.lid.flag) + ', target ' + esc(f.lid.target_frame) + ')</td></tr>';
    h += '</table>';
  }
  h += '<h2>WISER at the flash (' + esc(w.house) + ')</h2><p>Roster (tagged animals in this house at the segment middle): <b>' + (w.roster.length ? esc(w.roster.join(', ')) : 'none') + '</b>' +
    (w.sf11_note ? '<br><span class="warn">' + esc(w.sf11_note) + '</span>' : '') +
    (w.other_house.length ? '<br>other house: ' + esc(w.other_house.join(', ')) : '') + (w.out.length ? '<br>outside: ' + esc(w.out.join(', ')) : '') +
    (w.untracked.length ? '<br>untracked: ' + esc(w.untracked.join(', ')) : '') + '</p>' + topView(w) +
    '<p class="mut">Top view of the house in the house frame (inches; the camera image may be rotated or mirrored relative to it - that mapping is what your clicks will fit). Mean of ' + esc(w.window) +
    '; thick bar = +-1 SE of the mean, thin = +-1 SD of the fixes. The WISER tag sits on the head.</p>' +
    '<table><tr><th>animal</th><th>along</th><th>across</th><th>SE</th><th>n fixes</th><th>IMU still / active / loco</th></tr>' +
    w.positions.map(p => '<tr><td>' + esc(p.animal) + '</td><td>' + num(p.along_in) + '</td><td>' + num(p.across_in) + '</td><td>' + num(p.along_se_in, 2) + ', ' + num(p.across_se_in, 2) +
      '</td><td>' + esc(p.n_fix) + '</td><td>' + num(p.still_share, 2) + ' / ' + num(p.active_share, 2) + ' / ' + num(p.loco_share, 2) + '</td></tr>').join('') + '</table>';
  h += '<h2>Identity legend</h2><table><tr><th>animal</th><th>tag</th><th>coban</th><th>sticker</th><th>IR pattern</th></tr>' +
    DATA.legend.map(r => '<tr><td>' + esc(r.animal) + '</td><td>' + esc(r.tag) + '</td><td>' + esc(r.coban) + '</td><td>' + esc(r.sticker) + '</td><td>' + esc(r.ir_pattern) + (r.note ? '<br><span class="mut">' + esc(r.note) + '</span>' : '') + '</td></tr>').join('') + '</table>';
  h += '<h2>In-hand close-up clips (phone)</h2><p class="mut">SF07, SF08, SF09, SF10, SF12 filmed 2026-09-10 07:54-08:19 (AM round); SF11 filmed 2026-08-30 (its implant came off early, so an earlier clip is used).</p>' + DATA.closeups.map(c => c.dst ? '<details><summary>' + esc(c.animal) + '</summary><video controls preload="none" src="' + esc(c.dst) + '"></video></details>' : '<p class="warn">' + esc(c.animal) + ': ' + esc(c.error) + '</p>').join('');
  document.getElementById('side').innerHTML = h;
}
function num(v, d){ return (v === null || v === undefined || v === '') ? '-' : Number(v).toFixed(d === undefined ? 1 : d); }
function topView(w){
  const L = w.body_in[0], Wd = w.body_in[1], P = 40, S = 9, cx = P + 20 * S, cy = P + 14 * S;
  const X = a => cx + a * S, Y = c => cy - c * S;
  let s = '<svg viewBox="0 0 ' + (2 * cx) + ' ' + (2 * cy) + '" width="100%" style="max-width:360px;background:var(--card);border:1px solid var(--line)">' +
    '<rect x="' + X(-L / 2) + '" y="' + Y(Wd / 2) + '" width="' + L * S + '" height="' + Wd * S + '" fill="none" stroke="currentColor" stroke-dasharray="5 4"/>' +
    '<line x1="' + X(-L / 2 - 4) + '" y1="' + cy + '" x2="' + X(L / 2 + 4) + '" y2="' + cy + '" stroke="currentColor" opacity=".25"/>' +
    '<text x="' + X(L / 2 + 1) + '" y="' + (cy - 6) + '" font-size="11" fill="currentColor">+along</text>' +
    '<text x="' + (cx + 4) + '" y="' + Y(Wd / 2 + 3) + '" font-size="11" fill="currentColor">+across</text>';
  w.positions.forEach(p => {
    if (p.along_in === undefined || p.along_in === null) return;
    const col = COLS[p.animal] || '#888', x = X(p.along_in), y = Y(p.across_in);
    const sdA = (p.sd_along_raw_in || 0) * S, sdC = (p.sd_across_raw_in || 0) * S, seA = Math.max((p.along_se_in || 0) * S, 1.5), seC = Math.max((p.across_se_in || 0) * S, 1.5);
    s += '<line x1="' + (x - sdA) + '" y1="' + y + '" x2="' + (x + sdA) + '" y2="' + y + '" stroke="' + col + '" stroke-width="1" opacity=".6"/>' +
         '<line x1="' + x + '" y1="' + (y - sdC) + '" x2="' + x + '" y2="' + (y + sdC) + '" stroke="' + col + '" stroke-width="1" opacity=".6"/>' +
         '<line x1="' + (x - seA) + '" y1="' + y + '" x2="' + (x + seA) + '" y2="' + y + '" stroke="' + col + '" stroke-width="4"/>' +
         '<line x1="' + x + '" y1="' + (y - seC) + '" x2="' + x + '" y2="' + (y + seC) + '" stroke="' + col + '" stroke-width="4"/>' +
         '<circle cx="' + x + '" cy="' + y + '" r="4" fill="' + col + '"/><text x="' + (x + 6) + '" y="' + (y - 6) + '" font-size="12" fill="' + col + '">' + esc(p.animal) + '</text>';
  });
  return s + '</svg><p class="mut">+along = toward ' + esc(w.pose.ridge_deg) + ' deg in the paddock (about +y, the y = 240 wall); +across = 90 deg counter-clockwise from it (about -x). House body ' + num(L) + ' x ' + num(Wd) + ' in (dashed).</p>';
}
function show(refit){
  const s = seg(), f = frame();
  document.querySelectorAll('#tabs button[data-k]').forEach(b => b.classList.toggle('on', b.dataset.k === kind));
  const img = document.getElementById('img');
  if (f && f.path) { if (img.getAttribute('src') !== f.path) { img.setAttribute('src', f.path); img.onload = () => { if (refit !== false) fit(); drawPoints(); }; } else { if (refit !== false) fit(); } }
  else { img.removeAttribute('src'); }
  document.getElementById('fname').textContent = f ? (f.kind + ' · ' + (f.time || f.error || '')) : '';
  hidePop(); renderList(); renderTable(); renderSide(); drawPoints();
}
function hidePop(){ document.getElementById('pop').style.display = 'none'; }
function showPop(i, px, py){
  const P = document.getElementById('pop'), c = state.clicks[i];
  P.innerHTML = '<div class="ids">' + IDS.map(x => '<button data-id="' + x + '"' + (c.animal === x ? ' class="on"' : '') + '>' + x + '</button>').join('') + '</div>' +
    '<div>confidence: <button data-c="sure"' + (c.confidence === 'sure' ? ' class="on"' : '') + '>sure</button> <button data-c="likely"' + (c.confidence === 'likely' ? ' class="on"' : '') + '>likely</button> ' +
    '<button data-x="1">delete</button> <button data-o="1">ok</button></div><div class="mut">keys: 7 8 9 0 1 2 = SF07..SF12, u = unknown, s / l = sure / likely, Del</div>';
  P.style.left = Math.max(4, px + 12) + 'px'; P.style.top = Math.max(4, py + 12) + 'px'; P.style.display = 'block';
  P.querySelectorAll('[data-id]').forEach(b => b.onclick = ev => { ev.stopPropagation(); c.animal = b.dataset.id; save(); show(false); });
  P.querySelectorAll('[data-c]').forEach(b => b.onclick = ev => { ev.stopPropagation(); c.confidence = b.dataset.c; conf = c.confidence; save(); showPop(i, px, py); drawPoints(); });
  P.querySelector('[data-x]').onclick = ev => { ev.stopPropagation(); state.clicks.splice(i, 1); sel = null; save(); show(false); };
  P.querySelector('[data-o]').onclick = ev => { ev.stopPropagation(); hidePop(); };
}
function addClick(u, v, px, py){
  const s = seg(), f = frame();
  const lid = f.lid || {};
  const c = {segment_id: s.segment_id, camera: s.camera, house: s.house, frame_kind: f.kind, frame_file: f.file, frame_idx: f.frame_idx, frame_time: f.time,
    frame_path: f.path, u_px: Math.round(u * 10) / 10, v_px: Math.round(v * 10) / 10, animal: null, confidence: conf,
    lid_segment: lid.lid_segment, lid_flag: lid.flag, lid_target_frame: lid.target_frame, B_frame_to_ref: lid.B_frame_to_ref || null,
    clicked_at: new Date().toISOString()};
  state.clicks.push(c); sel = state.clicks.length - 1; save(); drawPoints(); renderTable(); showPop(sel, px, py);
}
function setup(){
  const V = document.getElementById('viewer');
  let drag = null;
  V.addEventListener('mousedown', e => { if (e.button !== 0) return; drag = {x: e.clientX, y: e.clientY, tx: view.tx, ty: view.ty, moved: false}; });
  window.addEventListener('mousemove', e => { if (!drag) return; const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (Math.abs(dx) + Math.abs(dy) > 4) drag.moved = true; if (drag.moved) { view.tx = drag.tx + dx; view.ty = drag.ty + dy; apply(); } });
  window.addEventListener('mouseup', e => { if (!drag) return; const d = drag; drag = null;
    if (!d.moved && e.target.closest('#viewer') && !e.target.closest('#pop')) { const r = V.getBoundingClientRect(), f = frame(); if (!f || !f.path) return;
      const u = (e.clientX - r.left - view.tx) / view.s, v = (e.clientY - r.top - view.ty) / view.s;
      if (u < 0 || v < 0 || u > (f.width || 2560) || v > (f.height || 1920)) return; addClick(u, v, e.clientX - r.left, e.clientY - r.top); } });
  V.addEventListener('wheel', e => { e.preventDefault(); const r = V.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top;
    const k = Math.exp(-e.deltaY * 0.0015), s2 = Math.min(Math.max(view.s * k, 0.05), 8); view.tx = mx - (mx - view.tx) * s2 / view.s; view.ty = my - (my - view.ty) * s2 / view.s; view.s = s2; apply(); }, {passive: false});
  window.addEventListener('resize', () => fit());
  window.addEventListener('keydown', e => { if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
    if (sel !== null && state.clicks[sel]) { const c = state.clicks[sel];
      if (KEYS[e.key]) { c.animal = KEYS[e.key]; save(); show(false); return; }
      if (e.key === 's' || e.key === 'l') { c.confidence = e.key === 's' ? 'sure' : 'likely'; conf = c.confidence; save(); drawPoints(); renderTable(); return; }
      if (e.key === 'Delete' || e.key === 'Backspace') { state.clicks.splice(sel, 1); sel = null; save(); show(false); return; } }
    if (e.key === 'ArrowDown' || e.key === 'n') { cur = Math.min(cur + 1, SEGS.length - 1); sel = null; kind = 'colour_mid'; show(); }
    if (e.key === 'ArrowUp' || e.key === 'p') { cur = Math.max(cur - 1, 0); sel = null; kind = 'colour_mid'; show(); }
    if (e.key === 'f') fit(); if (e.key === 'Escape') hidePop(); });
  document.querySelectorAll('#tabs button[data-k]').forEach(b => b.onclick = () => { kind = b.dataset.k; sel = null; show(); });
  document.getElementById('bfit').onclick = () => fit();
  document.getElementById('bjson').onclick = exportJSON;
  document.getElementById('bcsv').onclick = exportCSV;
  document.getElementById('bimp').onclick = () => document.getElementById('fimp').click();
  document.getElementById('fimp').onchange = importJSON;
}
function stamp(){ const d = new Date(), p = n => String(n).padStart(2, '0'); return d.getFullYear() + p(d.getMonth() + 1) + p(d.getDate()) + '_' + p(d.getHours()) + p(d.getMinutes()) + p(d.getSeconds()); }
function download(name, text, type){ const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([text], {type: type})); a.download = name; document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500); }
function payload(){ return {page_version: DATA.meta.page_version, run: DATA.meta.run, exported_at: new Date().toISOString(), save_into: DATA.meta.export_dir,
  clicks: state.clicks, segments: SEGS.map(s => ({segment_id: s.segment_id, camera: s.camera, house: s.house, start: s.start, end: s.end,
  complete: (state.segments[s.segment_id] || {}).complete || '', note: (state.segments[s.segment_id] || {}).note || '', n_clicks: segClicks(s.segment_id).length}))}; }
function exportJSON(){ download('inbox_identity_2026c_' + stamp() + '.json', JSON.stringify(payload(), null, 1), 'application/json'); }
function csvq(v){ v = (v === null || v === undefined) ? '' : String(v); return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; }
function exportCSV(){
  const cols = ['record','segment_id','camera','house','frame_kind','frame_file','frame_idx','frame_time','u_px','v_px','animal','confidence','lid_segment','lid_flag','lid_target_frame','b11','b12','b13','b21','b22','b23','pile_complete','note','clicked_at'];
  const lines = [cols.join(',')];
  state.clicks.forEach(c => { const B = c.B_frame_to_ref || [[null, null, null], [null, null, null]], ss = state.segments[c.segment_id] || {};
    lines.push(['click', c.segment_id, c.camera, c.house, c.frame_kind, c.frame_file, c.frame_idx, c.frame_time, c.u_px, c.v_px, c.animal, c.confidence, c.lid_segment, c.lid_flag, c.lid_target_frame,
      B[0][0], B[0][1], B[0][2], B[1][0], B[1][1], B[1][2], ss.complete || '', '', c.clicked_at].map(csvq).join(',')); });
  payload().segments.forEach(s => lines.push(['segment', s.segment_id, s.camera, s.house, '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', s.complete, s.note, ''].map(csvq).join(',')));
  download('inbox_identity_2026c_' + stamp() + '.csv', lines.join('\n') + '\n', 'text/csv');
}
function importJSON(ev){
  const f = ev.target.files[0]; if (!f) return; const r = new FileReader();
  r.onload = () => { try { const o = JSON.parse(r.result); if (!o.clicks) throw new Error('no clicks in file');
      if (!confirm('Replace the current clicks (' + state.clicks.length + ') with the ' + o.clicks.length + ' clicks in ' + f.name + '?')) return;
      state = {clicks: o.clicks, segments: {}}; (o.segments || []).forEach(s => { state.segments[s.segment_id] = {complete: s.complete || '', note: s.note || ''}; });
      save(); show(); } catch (e) { alert('Import failed: ' + e.message); } };
  r.readAsText(f); ev.target.value = '';
}
load(); setup(); show();
})();
"""


def render_html(data: dict) -> str:
    blob = json.dumps(data, default=str).replace("</", "<\\/")
    m = data["meta"]
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>In-box identity clicks</title><style>{PAGE_CSS}</style></head><body>
<header><h1>In-box identity clicks (CH07 / CH08, cohort 3)</h1>
<span id="help">Pick a segment; on the colour frame click each visible rat's <b>head</b>, then choose its id (SF07-SF12 / unknown) and sure / likely.
Optionally do the same on the IR frames. Answer "pile composition complete?". Drag = pan, wheel = zoom, f = fit, n / p = next / previous segment.
Autosaved in this browser. Export, then move the files into <code>{html.escape(m['export_dir'])}</code>.</span>
<span class="sp"></span><button id="bjson">Export JSON</button><button id="bcsv">Export CSV</button><button id="bimp">Import JSON</button>
<input type="file" id="fimp" accept=".json,application/json" style="display:none"></header>
<div id="wrap"><div id="list"></div>
<div id="main"><div id="tabs"><button data-k="colour_mid">colour (segment middle)</button><button data-k="ir_p06">IR +6 s after OFF</button>
<button data-k="ir_p15">IR +15 s after OFF</button><button id="bfit">fit</button><span id="fname" class="mut"></span></div>
<div id="viewer"><div id="stage"><img id="img" alt="frame"><svg id="pts"></svg></div><div id="pop"></div></div>
<div id="below"></div></div>
<div id="side"></div></div>
<script id="page-data" type="application/json">{blob}</script>
<script>{PAGE_JS}</script></body></html>
"""


# ----------------------------------------------------------------------------------------------- self-test
def selftest() -> int:
    ok = True

    def rec(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")

    try:
        import av  # noqa: F401
        import cv2  # noqa: F401
    except ImportError:
        print("[SKIP] needs PyAV + OpenCV (cv env)")
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        run = tmp / "run"
        (run / "scan" / "CH07").mkdir(parents=True)
        day = "2026-09-10"
        vid = tmp / "video" / day / "CH07"
        vid.mkdir(parents=True)
        vp = vid / "CH07_2026-09-10_12-00-00_to_12-00-40.mp4"
        if not ip._synthetic_video(vp, 10.3, 18.75, dur=40.0):
            print("[SKIP] could not write a synthetic video")
            return 0
        csvp = run / "scan" / "CH07" / (vp.stem + ".csv")
        ip.scan_file(vp.as_posix(), "2026-09-10T12:00:00", csvp.as_posix())
        pd.DataFrame([{"set": "scan", "camera": "CH07", "file": vp.as_posix(), "start": "2026-09-10 12:00:00", "csv": csvp.as_posix()}]).to_csv(
            run / "scan_inventory.csv", index=False)
        (run / "colour_threshold.json").write_text(json.dumps({"thr": 1.0}), encoding="utf-8")
        pd.DataFrame([{"segment_id": "CH07_20260910_120010", "camera": "CH07", "house": "house_2", "start": "2026-09-10 12:00:10.300",
                       "end": "2026-09-10 12:00:18.750", "duration_s": 8.45, "mid": "2026-09-10 12:00:14.525", "n_colour_keyframes": 4,
                       "median_chroma": 100.0, "flags": "", "lid_event": "", "log_row": None, "log_kind": ""}]).to_csv(run / "colour_segments.csv", index=False)
        # tracks: SF07, SF09 in house_2 at different ends, SF08 outside; states from the WISER phase on the synthetic tracks
        rois = ip.load_rois()
        root = tmp / "tracks"
        for lab, (dx, dy) in {"SF07": (0, 8), "SF09": (0, -8), "SF08": (-150, -80)}.items():
            t_local = pd.date_range(f"{day} 11:55:00", f"{day} 12:05:00", freq="250ms")
            x = rois["house_2"]["x"] + dx + np.random.default_rng(1).normal(0, 1.5, len(t_local))
            y = rois["house_2"]["y"] + dy + np.random.default_rng(2).normal(0, 1.5, len(t_local))
            t_ms = ((t_local.tz_localize(ip.TZ).tz_convert("UTC") - pd.Timestamp(0, tz="UTC")) // pd.Timedelta(milliseconds=1)).to_numpy(np.int64)
            (root / lab).mkdir(parents=True, exist_ok=True)
            pd.DataFrame({"t_ms": t_ms, "t_al_ms": t_ms, "shortid": 1, "x_raw": x, "y_raw": y, "anchors_used": 8, "valid": 1, "m_handling": 0,
                          "m_silence": 0, "m_tag_validity": 0, "m_adc_lane": 0, "m_off_animal": 0, "x": x, "y": y, "vx": 0.0, "vy": 0.0,
                          "method": "V3", "imu_ok": 1, "imu_state": 1, "zupt": 0, "loco_boost": 0}).to_csv(root / lab / "20260910.csv.gz", index=False)
        ip.phase_wiser(run, track_root=root, t0=datetime(2026, 9, 10, 11, 55), t1=datetime(2026, 9, 10, 12, 5), labels=("SF07", "SF08", "SF09"),
                       days=[day])
        # close-ups: two tiny synthetic clips named like the phone files
        cs = tmp / "downloads"
        cs.mkdir()
        for lab in ("SF07", "SF08"):
            ip._synthetic_video(cs / f"{lab}.mp4", 0, 1, dur=2.0)
            shutil.move(str(cs / f"{lab}.mp4"), str(cs / f"{lab}.MOV"))

        class FakeCorr:
            def correction(self, cam, t):
                return np.array([[1.0, 0.0, 2.5], [0.0, 1.0, -1.0]]), {"segment": 27, "lid_open": False, "flag": "ok",
                                                                       "target_frame": "09-04 12:00 (user-labelled frame)", "used": "median"}
        chk = build(run, closeup_src=cs, track_root=root, corrections=FakeCorr())
        data = json.loads((run / "identity_page" / "page_data.json").read_text(encoding="utf-8"))
        s0 = data["segments"][0]
        fr = {f["kind"]: f for f in s0["frames"]}
        rec("three frames per segment, colour at the middle, IR at +6 / +15 s", set(fr) == {"colour_mid", "ir_p06", "ir_p15"}
            and fr["colour_mid"]["time"] == "2026-09-10 12:00:14.550" and fr["ir_p06"]["time"] == "2026-09-10 12:00:24.750"
            and fr["ir_p15"]["time"] == "2026-09-10 12:00:33.750", str({k: v.get("time") for k, v in fr.items()}))
        rec("frame index counted from the key frame (colour mid = frame 291)", fr["colour_mid"]["frame_idx"] == 291, str(fr["colour_mid"]["frame_idx"]))
        rec("mode check: colour frame >= thr, IR frames < thr", all(f["mode_check"] == "ok" for f in s0["frames"]))
        rec("lid segment and correction stored per frame", fr["ir_p15"]["lid"]["lid_segment"] == 27 and fr["colour_mid"]["lid"]["B_frame_to_ref"][0][2] == 2.5)
        w = s0["wiser"]
        rec("WISER roster: SF07 + SF09 in house_2, SF08 outside", sorted(w["roster"]) == ["SF07", "SF09"] and w["out"] == ["SF08"], str(w))
        p = {q["animal"]: q for q in w["positions"]}
        rec("WISER positions: the two animals ~16 in apart in the house frame, SE < 0.5 in",
            abs(np.hypot(p["SF07"]["along_in"] - p["SF09"]["along_in"], p["SF07"]["across_in"] - p["SF09"]["across_in"]) - 16 * 0.9634) < 1.0
            and p["SF07"]["along_se_in"] < 0.5)
        rec("close-ups transcoded, originals unchanged", all(c.get("src_unchanged") for c in data["closeups"] if c["animal"] in ("SF07", "SF08"))
            and (run / "identity_page" / "closeups" / "SF07.mp4").exists())
        rec("page check: paths resolve, no network URL, no pre-filled identity", chk["verdict"] == "PASS" and not chk["missing"], str(chk))
        txt = (run / "identity_page" / "index.html").read_text(encoding="utf-8")
        rec("no identity pre-filled in the page data", '"clicks"' not in txt.split("<script>")[0] and "animal\": \"SF" not in json.dumps(data["segments"][0]["frames"]))
        node = shutil.which("node")
        if node:
            js = tmp / "page.js"
            js.write_text(PAGE_JS, encoding="utf-8")
            r = subprocess.run([node, "--check", str(js)], capture_output=True, text=True)
            rec("page script parses (node --check)", r.returncode == 0, r.stderr[-300:])
        else:
            print("[SKIP] node not on PATH: page script not syntax-checked")
        # check_page catches a missing file and a network URL
        bad = tmp / "bad"
        bad.mkdir()
        (bad / "index.html").write_text('<script id="page-data" type="application/json">{"segments": [], "closeups": []}</script>'
                                        '<img src="frames/x.jpg"><a href="https://example.org/a">x</a>', encoding="utf-8")
        cb = check_page(bad)
        rec("page check flags a missing file and a network URL", cb["verdict"] == "FAIL" and cb["missing"] == ["frames/x.jpg"] and cb["network_urls"])
    print(("PASS" if ok else "FAIL") + " - inbox_identity_page self-test")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], allow_abbrev=False)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--run", default=None)
    ap.add_argument("--closeups", default=str(CLOSEUP_SRC))
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.run:
        ap.error("--run <inbox_p0 run dir> or --selftest")
    chk = build(Path(args.run), Path(args.closeups))
    return 0 if chk["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
