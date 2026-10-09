"""Multi-unit threshold crossings over all NREM of a session, from the raw 20-kHz amplifier.dat (read-only; no sorting).

Reusable intermediate (save once, never re-extract): the delta-wave DOWN-state check (`delta_detect.py verify`) and any
later spike-timing question can read it instead of the raw card.

Per 60-s piece of every NREM bout (+-50-ms margins): common median reference over the live channels, 600-6000 Hz
Butterworth-3 zero-phase, negative crossings of -4.5 x MAD/0.6745 (per channel and piece), 1-ms refractory - the same
detector as `delta_mua_check.py`. Times are amplifier samples (LFP sample k <-> amplifier sample 16 k; LFP time
(k + 1) / 1250 s). FM65 sessions only (FM64 needs the de-glitched copy; refused).

  python ephys/mua_nrem.py --raw <raw session dir> --states <final 1-s .states.npz | SleepState.states.mat>
         --xml <final XML> --out <file.npz> [--workers 8]

Output npz: spikes (int64, all channels concatenated), offsets (nch + 1; channel c = spikes[offsets[c]:offsets[c+1]]),
pieces (start, stop amplifier samples), thr_uV (pieces x nch), bouts_s, nrem_s, rate_hz (per channel), live, params.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from scipy import signal

sys.path.insert(0, str(Path(__file__).resolve().parent))
import delta_detect as dd  # noqa: E402
import swr_layer_order as slo  # noqa: E402
from wild_ce_params import parse_ce_params  # noqa: E402

FS = 20000.0
PIECE_S = 60.0
MARGIN = int(0.05 * FS)
PARAMS = dict(reference="common median of the live channels", band_hz=[600, 6000], filter="butter 3 sosfiltfilt",
              thr_mad=4.5, refractory_samples=20, piece_s=PIECE_S, margin_s=MARGIN / FS)


def _piece(job):
    raw, nch, live, s0, s1 = job
    mm = np.memmap(raw, dtype=np.int16, mode="r")
    mm = mm[: mm.size // nch * nch].reshape(-1, nch)
    lo = max(s0 - MARGIN, 0)
    x = np.asarray(mm[lo:s1 + MARGIN], np.float32)
    x -= np.median(x[:, live], axis=1, keepdims=True)
    sos = signal.butter(3, PARAMS["band_hz"], btype="bandpass", fs=FS, output="sos")
    y = signal.sosfiltfilt(sos, x, axis=0).astype(np.float32)
    del x
    core = y[s0 - lo:s1 - lo]
    thr = -PARAMS["thr_mad"] * np.median(np.abs(core), axis=0) / 0.6745
    below = y < thr
    on = below[1:] & ~below[:-1]
    out = []
    for c in range(nch):
        t = np.flatnonzero(on[:, c]) + 1
        t = t[(t >= s0 - lo) & (t < s1 - lo)]
        if t.size:
            t = t[np.concatenate([[True], np.diff(t) > PARAMS["refractory_samples"]])]
        out.append((t + lo).astype(np.int64))
    return out, thr * dd.UV_PER_BIT


def extract(raw: Path, states: Path, xml: Path, out: Path, workers: int = 8, nch: int = 64, nrem=None):
    fw = parse_ce_params(raw / "CE_params.bin").firmware_version if (raw / "CE_params.bin").exists() else None
    if fw is not None and int(fw) < 65:
        raise SystemExit(f"{raw.name}: firmware {fw} < 65 needs the de-glitched copy - not supported here")
    groups, skip = slo.read_groups(xml)
    live = [c for c in range(nch) if c not in skip]
    n = (raw / "amplifier.dat").stat().st_size // 2 // nch
    nrem = dd.nrem_from_states(states) if nrem is None else nrem
    pieces = []
    for a, b in nrem:
        s0, s1 = int(np.ceil(a * FS)), min(int(b * FS), n)
        for p in range(s0, s1, int(PIECE_S * FS)):
            pieces.append((p, min(p + int(PIECE_S * FS), s1)))
    t0 = time.time()
    with ProcessPoolExecutor(workers) as ex:
        res = list(ex.map(_piece, [(str(raw / "amplifier.dat"), nch, live, a, b) for a, b in pieces], chunksize=1))
    per = [np.concatenate([r[0][c] for r in res]) if res else np.zeros(0, np.int64) for c in range(nch)]
    offsets = np.concatenate([[0], np.cumsum([p.size for p in per])])
    nrem_s = float(sum(b - a for a, b in pieces) / FS)
    rate = np.array([p.size for p in per]) / max(nrem_s, 1e-9)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out, spikes=np.concatenate(per), offsets=offsets, pieces=np.array(pieces, np.int64),
                        thr_uV=np.array([r[1] for r in res], np.float32), bouts_s=nrem, nrem_s=nrem_s, rate_hz=rate,
                        live=np.array(live), params=json.dumps(dict(PARAMS, raw=str(raw), states=str(states),
                                                                    xml=xml.name, firmware=fw, git=dd._git())))
    return dict(out=str(out), pieces=len(pieces), nrem_min=nrem_s / 60, n_spikes=int(offsets[-1]),
                elapsed_min=(time.time() - t0) / 60)


def load(path) -> tuple[list[np.ndarray], dict]:
    z = np.load(path)
    o = z["offsets"]
    return [z["spikes"][o[c]:o[c + 1]] for c in range(o.size - 1)], dict(rate_hz=z["rate_hz"], live=z["live"],
                                                                          pieces=z["pieces"], nrem_s=float(z["nrem_s"]))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", required=True)
    ap.add_argument("--states", required=True)
    ap.add_argument("--xml", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    print(json.dumps(extract(Path(a.raw), Path(a.states), Path(a.xml), Path(a.out), a.workers)))


if __name__ == "__main__":
    main()
