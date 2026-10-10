"""Make one Kilosort1 block ready for manual curation in Phy on this PC (plan implementation_plan/2026-10-09-k1-block-sorting.md).

The production queue deletes each block's joined .dat after sorting, to save working disk. Phy reads waveforms from
that .dat (`dat_path` in params.py), so it has to be provided again. This tool:
1. Copies the block's output folder (chanMap, XML, k1_run.json, <block>.segments.json, kilosort1/ = Phy; never a
   .dat) from storage, `<src-root>/<SFxx>/<block>/`, to `<out>/<SFxx>/<block>/`. With --from-server it fetches from the
   BioHPC workdir over the shared SSH connection (before the storage copy has run).
2. Points `dat_path` at the right data:
   - single-file block (the block is one session from sample 0): the original amplifier.dat under --raw-root, read in
     place. With --local-copy it is first copied next to the Phy folder (smoother Phy).
   - multi-file block: the joined .dat is rebuilt into `<out>/<SFxx>/<block>/<block>.dat` from the original files
     (ephys/server/build_block_dat.py, the same code as for sorting), and its size is checked.
3. Keeps the original params.py as params.py.orig and prints the Phy command.

Speed (2026-10-10, sequential 4 GB): storage Q: 427 MB/s, the local USB HDD E: 175 MB/s. So --raw-root defaults to
storage, and rebuilding from Q: is as fast as copying a stored joined file, without 3.5 TB of duplicates on storage.
Never writes outside --out (the raw files and storage are only read).

Usage (base Python; Phy itself runs in the phy2 env):
  python ephys/k1_prepare_phy.py --block SF10_20260902_083247 [--out G:/3rd_rat_spikes/analysis/curation]
         [--raw-root Q:/hc997/SocialFieldRat2026/3rd_rat/WILD | E:/3rd_rat_spikes] [--local-copy] [--from-server]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "server"))
from build_block_dat import MACS  # noqa: E402

REPO = HERE.parent
TABLE = REPO / "results/2026c/ephys_spikes/reports/ephys_spikes_k1_blocks_2026c.csv"
SRC_ROOT = "Q:/hc997/SocialFieldRat2026/3rd_rat/analysis/sort_k1"
SERVER_ROOT = "/workdir/hc997/ephys_2026c/sort_k1"
NCH, BYTES = 64, 2


def raw_path(raw_root: Path, padded: str, session: str) -> Path:
    raw_animal = f"SF{int(padded[2:])}"
    return raw_root / raw_animal / MACS[raw_animal] / session / "amplifier.dat"


def set_dat_path(params: Path, dat: Path) -> None:
    orig = params.with_name("params.py.orig")
    if not orig.exists():
        shutil.copy2(params, orig)
    text = params.read_text(encoding="utf-8")
    new = re.sub(r"^dat_path\s*=.*$", f"dat_path = r'{dat.as_posix()}'", text, count=1, flags=re.M)
    params.write_text(new, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--block", required=True)
    ap.add_argument("--out", default="G:/3rd_rat_spikes/analysis/curation")
    ap.add_argument("--raw-root", default="Q:/hc997/SocialFieldRat2026/3rd_rat/WILD")
    ap.add_argument("--src-root", default=SRC_ROOT)
    ap.add_argument("--local-copy", action="store_true", help="single-file blocks: copy the raw file locally too")
    ap.add_argument("--from-server", action="store_true", help="fetch the output folder from the BioHPC workdir (scp)")
    a = ap.parse_args()
    padded = a.block.split("_")[0]
    dest = Path(a.out) / padded / a.block
    dest.parent.mkdir(parents=True, exist_ok=True)

    src = Path(a.src_root) / padded / a.block
    if not (dest / "kilosort1" / "params.py").exists():
        if src.exists():
            shutil.copytree(src, dest, ignore=shutil.ignore_patterns("*.dat"), dirs_exist_ok=True)
        elif a.from_server:
            subprocess.run(["scp", "-q", "-r", "-o", "ControlPath=~/.ssh/cm-gpu",
                            f"gpu:{SERVER_ROOT}/{padded}/{a.block}", str(dest.parent)], check=True)
        else:
            sys.exit(f"not on storage yet: {src} (use --from-server)")
    seg = json.loads((dest / f"{a.block}.segments.json").read_text())
    segs = seg["segments"]
    params = dest / "kilosort1" / "params.py"
    if len(segs) == 1 and segs[0]["session_start_sample"] == 0:
        raw = raw_path(Path(a.raw_root), padded, segs[0]["session"])
        if not raw.exists():
            sys.exit(f"raw file not found: {raw}")
        dat = raw
        if a.local_copy:
            dat = dest / f"{a.block}.dat"
            if not (dat.exists() and dat.stat().st_size == raw.stat().st_size):
                print(f"copying {raw} -> {dat} ({raw.stat().st_size / 1e9:.1f} GB)")
                shutil.copyfile(raw, dat)
        kind = "single-file"
    else:
        dat = dest / f"{a.block}.dat"
        if not (dat.exists() and dat.stat().st_size == seg["n_samples"] * NCH * BYTES):
            print(f"rebuilding the joined file ({seg['hours']:.1f} h, {len(segs)} segments) from {a.raw_root}")
            subprocess.run([sys.executable, str(HERE / "server" / "build_block_dat.py"), "--blocks", str(TABLE),
                            "--block", a.block, "--out-root", str(dest.parent), "--stage-root", str(Path(a.out) / "_none"),
                            "--raw-root", a.raw_root], check=True)
        kind = "multi-file (rebuilt)"
    size_ok = dat.stat().st_size >= seg["n_samples"] * NCH * BYTES
    set_dat_path(params, dat)
    print(f"{a.block}: {kind}; dat_path -> {dat} ({dat.stat().st_size / 1e9:.1f} GB, covers the sorted samples: {size_ok})")
    print(f"open in Phy (phy2 env):  phy template-gui \"{params}\"")


if __name__ == "__main__":
    main()
