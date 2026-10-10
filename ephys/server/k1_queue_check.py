"""Exit 0 only if every block of a K1 queue list has a finished sort (k1_run.json + kilosort1/spike_times.npy) under
the sort root; prints the missing ones. Used before the verified storage copy (run_then_store.sh, part sort_k1)."""
import json
import sys
from pathlib import Path

ROOT = Path("/workdir/hc997/ephys_2026c/sort_k1")
blocks = [b.strip() for b in open(sys.argv[1]) if b.strip()]
missing, qc = [], []
for b in blocks:
    d = ROOT / b.split("_")[0] / b
    if not ((d / "k1_run.json").exists() and (d / "kilosort1" / "spike_times.npy").exists()):
        missing.append(b); continue
    r = json.loads((d / "k1_run.json").read_text())["results"][0]
    qc.append((b, r.get("spikes"), r.get("clusters"), r.get("cross_shank_spike_share")))
print(f"{len(blocks) - len(missing)} / {len(blocks)} blocks sorted")
for b, n, c, x in qc:
    print(f"  {b}: {n} spikes, {c} clusters, cross-shank share {x if x is None else round(x, 3)}")
if missing:
    print("MISSING:", " ".join(missing))
    sys.exit(1)
