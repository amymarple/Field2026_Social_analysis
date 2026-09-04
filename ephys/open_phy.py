"""Open a sorted shank in Phy (template-gui) for manual inspection / curation.

Sorting outputs live under <analysis_root>/sort/<SFxx>/<session>/:
    Kilosort4_<ts>_probe1_shank<k>/        raw Kilosort4 output (params.py, dat_path = ../<session>.dat, 64-ch filtered file)
    Kilosort4_<ts>_probe1_shank<k>_spi/    PreprocessPipeline postprocess output (dedupe/merge/split + quality_metrics.csv +
                                           noise labels in cluster_group.tsv) — the folder to curate; opened by default
Phy edits are saved in the folder you open (cluster_group.tsv / cluster_info.tsv); the raw Kilosort4 folder stays untouched
when you curate the _spi copy. Phy runs in the `phy2` conda env (phy 2.0b6). The window is launched detached, so this
command returns immediately; loading 8 h of spikes takes ~1-2 min.

Usage:
  python ephys/open_phy.py --cohort 2026c --list                                  # what is sorted, per shank
  python ephys/open_phy.py --cohort 2026c --animal SF07 --session 15_20260902_082418.755 --shank 1
  python ephys/open_phy.py --cohort 2026c --animal SF07 --session 15_20260902_082418.755 --shank 1 --raw   # KS4 folder
"""
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

from _common import sort_root

PHY_ENV_PYTHON = Path(r"C:/Users/Cornell/anaconda3/envs/phy2/python.exe")
PHY_EXE = Path(r"C:/Users/Cornell/anaconda3/envs/phy2/Scripts/phy.exe")


def _norm(animal: str) -> str:
    a = animal.upper()
    return f"SF{int(a[2:]):02d}" if a.startswith("SF") and a[2:].isdigit() else a


def list_sorted(root: Path) -> list[dict]:
    out = []
    for sess in sorted(root.glob("*/*/")):
        if not (sess / "sort_manifest.json").exists() and not list(sess.glob("Kilosort4_*")):
            continue
        for k in sorted(sess.glob("Kilosort4_*_probe*_shank*")):
            if k.name.endswith("_spi"):
                continue
            m = re.search(r"_shank(\d+)$", k.name)
            sh = int(m.group(1)) if m else 0
            spi = sess / (k.name + "_spi")
            done = (k / "spike_clusters.npy").exists()
            out.append({"animal": sess.parent.name, "session": sess.name, "shank": sh, "raw": k, "spi": spi if spi.exists() else None, "ks4_done": done})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cohort", required=True)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--animal")
    ap.add_argument("--session")
    ap.add_argument("--shank", type=int, default=1)
    ap.add_argument("--raw", action="store_true", help="open the raw Kilosort4 folder instead of the postprocessed _spi folder")
    ap.add_argument("--ssd-cache", default=None, metavar="DIR",
                    help="copy the session's filtered .dat to <DIR>/<SFxx>/<session>/ (an SSD) once and point this shank's params.py at it: "
                         "Phy's per-cluster waveform reads then hit the SSD instead of the busy E: HDD (params.py.orig keeps the original)")
    a = ap.parse_args()
    root = sort_root(a.cohort)
    entries = list_sorted(root)
    if a.list or not (a.animal and a.session):
        print(f"sorted shanks under {root}:")
        for e in entries:
            print(f"  {e['animal']} {e['session']} shank {e['shank']}: KS4 {'done' if e['ks4_done'] else 'running/absent'}; postprocessed: {'yes' if e['spi'] else 'no'}")
        if not (a.animal and a.session):
            return
    animal = _norm(a.animal)
    cands = [e for e in entries if e["animal"] == animal and e["session"] == a.session and e["shank"] == a.shank]
    if not cands:
        raise SystemExit(f"no sorted shank {a.shank} for {animal} {a.session} (use --list)")
    e = cands[-1]
    folder = e["raw"] if (a.raw or e["spi"] is None) else e["spi"]
    if not (folder / "params.py").exists():
        raise SystemExit(f"no params.py in {folder} (Kilosort4 still running?)")
    if e["spi"] is None and not a.raw:
        print("note: postprocess output not present yet; opening the raw Kilosort4 folder")
    if a.ssd_cache:
        import shutil, time
        session_dir = folder.parent
        dat_src = session_dir / f"{a.session}.dat"
        if not dat_src.exists():
            raise SystemExit(f"filtered .dat not found: {dat_src}")
        dat_dst = Path(a.ssd_cache) / animal / a.session / dat_src.name
        if not dat_dst.exists() or dat_dst.stat().st_size != dat_src.stat().st_size:
            dat_dst.parent.mkdir(parents=True, exist_ok=True)
            print(f"copying {dat_src.stat().st_size / 1e9:.1f} GB to {dat_dst} (one-off; reads the busy E: disk once) ...")
            t0 = time.time()
            shutil.copyfile(dat_src, dat_dst)
            print(f"  done in {(time.time() - t0) / 60:.1f} min")
        params = folder / "params.py"
        orig = folder / "params.py.orig"
        if not orig.exists():
            shutil.copyfile(params, orig)
        txt = re.sub(r"dat_path\s*=.*", "dat_path = r'" + str(dat_dst) + "'", orig.read_text(encoding="utf-8"))
        params.write_text(txt, encoding="utf-8")
        print(f"params.py now points at the SSD copy ({dat_dst}); restore with params.py.orig")
    exe = PHY_EXE if PHY_EXE.exists() else None
    if exe is None:
        raise SystemExit(f"phy not found at {PHY_EXE}; conda env phy2 missing?")
    print(f"launching Phy on {folder}")
    subprocess.Popen([str(exe), "template-gui", "params.py"], cwd=str(folder), creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    print("Phy window opening (1-2 min to load 8 h of spikes). Curation is saved in that folder's cluster_group.tsv.")


if __name__ == "__main__":
    main()
