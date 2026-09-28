"""Integrity scan of raw WILD sessions: repeated / overlaid data and per-channel corruption.

Two independent tests per session (nothing is written into the raw folder):

A. REPEATED DATA (block hashes). Every BLOCK_BYTES block of amplifier.dat is hashed (blake2b, 16 B). A block that
   recurs at another offset is a "repeat"; all-constant blocks (e.g. zeros) are excluded because they repeat trivially.
   Real 64-channel neural data never produces an identical 64 KiB block twice, so any repeat = the card re-wrote or
   the offload re-read a region ("repetitive overwriting"). Repeats are reported as runs (offset_a -> offset_b, length),
   and the first/last 5 min of each session are also compared with the neighbouring sessions of the same logger
   (old data leaking into a new session, or a session's tail re-appearing in the next one).

B. CHANNEL CORRUPTION (sampled windows). N_WINDOWS windows of WINDOW_S seconds spread over the session; per channel:
   rail fraction (|x| >= 32000), zero fraction, flat (std < 5 ADC), stuck (fraction of samples equal to the previous
   sample > 0.5), exact duplicate of another channel (identical samples over the window) or near-duplicate
   (Pearson r > 0.999 in the 500-5000 Hz band, which real neighbouring sites do not reach), and the channel's
   band-limited correlation fingerprint (its 63-vector of LFP correlations). A fingerprint that changes abruptly
   between windows (min correlation of a channel's fingerprint with the session-median fingerprint < 0.5 while the
   window is otherwise normal) flags a channel whose identity moved during the session (a mid-session channel-order
   change or a bank rotation). Windows in a broadband/handling regime are reported but not counted as corruption.

Usage:
  python ephys/integrity_scan.py --cohort 2026c --animals SF07 [--firmware 65] [--full-hash] [--sessions <name> ...]
Writes results/<cohort>/ephys_spikes/reports/ephys_spikes_integrity_scan_<cohort>[_suffix].{md,csv}
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import os
from collections import defaultdict
from pathlib import Path

import numpy as np

from _common import ephys_block, git_commit, iter_raw_sessions, parse_session_name, raw_ephys_root, report_dir, utc_now_iso
from wild_ce_params import parse_ce_params

BLOCK_BYTES = 65536
N_WINDOWS = 40
WINDOW_S = 5.0
EDGE_S = 300.0
RAIL = 32000
NEAR_DUP_R = 0.999


def block_hashes(path: Path, start: int = 0, stop: int | None = None) -> tuple[list[bytes], np.ndarray]:
    """Hashes of consecutive BLOCK_BYTES blocks in [start, stop); constant blocks get hash b'' (ignored)."""
    size = os.path.getsize(path)
    stop = size if stop is None else min(stop, size)
    hashes: list[bytes] = []
    const = []
    with open(path, "rb") as f:
        f.seek(start)
        pos = start
        while pos < stop:
            b = f.read(min(BLOCK_BYTES, stop - pos))
            if not b:
                break
            arr = np.frombuffer(b, dtype=np.int16)
            if arr.size and arr.min() == arr.max():
                hashes.append(b"")
                const.append(True)
            else:
                hashes.append(hashlib.blake2b(b, digest_size=16).digest())
                const.append(False)
            pos += len(b)
    return hashes, np.asarray(const, dtype=bool)


def find_repeats(hashes: list[bytes]) -> tuple[int, list[tuple[int, int, int]]]:
    """Return (n_repeated_blocks, runs of (first_block, later_block, length)) for non-constant blocks seen before."""
    first: dict[bytes, int] = {}
    pairs: list[tuple[int, int]] = []
    for i, h in enumerate(hashes):
        if not h:
            continue
        if h in first:
            pairs.append((first[h], i))
        else:
            first[h] = i
    runs: list[tuple[int, int, int]] = []
    if pairs:
        pairs.sort(key=lambda p: p[1])
        a0, b0, n = pairs[0][0], pairs[0][1], 1
        for a, b in pairs[1:]:
            if a == a0 + n and b == b0 + n:
                n += 1
            else:
                runs.append((a0, b0, n))
                a0, b0, n = a, b, 1
        runs.append((a0, b0, n))
    return len(pairs), runs


def channel_scan(path: Path, nch: int, fs: float) -> dict:
    from scipy import signal
    ns = os.path.getsize(path) // (2 * nch)
    d = np.memmap(path, dtype=np.int16, mode="r", shape=(ns, nch))
    win = int(WINDOW_S * fs)
    starts = np.linspace(0, max(0, ns - win), N_WINDOWS).astype(int) if ns > win else [0]
    bh, ah = signal.butter(2, [500 / (fs / 2), 5000 / (fs / 2)], "band")
    bl, al = signal.butter(2, [1 / (fs / 2), 300 / (fs / 2)], "band")
    rail = np.zeros(nch); zero = np.zeros(nch); flat = np.zeros(nch); stuck = np.zeros(nch)
    exact_dup: dict[tuple[int, int], int] = defaultdict(int); near_dup: dict[tuple[int, int], int] = defaultdict(int)
    fps = []; regimes = []; stds = []
    for a in starts:
        x = np.asarray(d[a:a + win]).astype(np.float32)
        rail += (np.abs(x) >= RAIL).mean(0); zero += (x == 0).mean(0)
        sd = x.std(0); stds.append(sd); flat += (sd < 5); stuck += ((np.diff(x, axis=0) == 0).mean(0) > 0.5)
        regimes.append("broadband" if np.median(sd) > 2500 else "normal")
        for i in range(nch):
            for j in range(i + 1, nch):
                if sd[i] >= 5 and sd[j] >= 5 and np.array_equal(x[:, i], x[:, j]):
                    exact_dup[(i, j)] += 1
        hp = signal.filtfilt(bh, ah, x, axis=0)
        ok = sd >= 5
        if ok.sum() > 1:
            c = np.corrcoef(hp[:, ok].T)
            idx = np.where(ok)[0]
            ii, jj = np.where(np.triu(c, 1) > NEAR_DUP_R)
            for p, q in zip(ii, jj):
                near_dup[(int(idx[p]), int(idx[q]))] += 1
        lf = signal.filtfilt(bl, al, x, axis=0)[::16]
        C = np.corrcoef(lf.T); np.fill_diagonal(C, np.nan)
        fps.append(np.nan_to_num(C))
    fps = np.asarray(fps)                      # windows x nch x nch
    median_fp = np.median(fps, axis=0)
    ident_min = np.ones(nch)
    for w in range(fps.shape[0]):
        if regimes[w] != "normal":
            continue
        for c in range(nch):
            a_ = fps[w, c]; b_ = median_fp[c]
            m = np.isfinite(a_) & np.isfinite(b_) & (np.arange(nch) != c)
            if m.sum() > 5 and a_[m].std() > 0 and b_[m].std() > 0:
                r = float(np.corrcoef(a_[m], b_[m])[0, 1])
                ident_min[c] = min(ident_min[c], r)
    nw = len(starts)
    return {
        "n_windows": nw, "n_broadband_windows": sum(1 for r in regimes if r != "normal"),
        "rail_frac": rail / nw, "zero_frac": zero / nw, "flat_windows": flat.astype(int), "stuck_windows": stuck.astype(int),
        "exact_dup_pairs": {k: v for k, v in exact_dup.items()}, "near_dup_pairs": {k: v for k, v in near_dup.items()},
        "identity_min_r": ident_min, "median_std": np.median(np.asarray(stds), axis=0),
    }


def scan_session(sdir: Path, prev: Path | None, nxt: Path | None, nch: int, fs: float, full_hash: bool, verbose: bool = True) -> dict:
    amp = sdir / "amplifier.dat"
    size = os.path.getsize(amp)
    bytes_per_s = 2 * nch * fs
    out = {"session": sdir.name, "size_gb": size / 1e9, "duration_s": size / bytes_per_s}
    # A: repeats
    edge = int(EDGE_S * bytes_per_s) // BLOCK_BYTES * BLOCK_BYTES
    if full_hash:
        hashes, const = block_hashes(amp)
        n_rep, runs = find_repeats(hashes)
        out.update({"hashed_gb": size / 1e9, "n_blocks": len(hashes), "n_const_blocks": int(const.sum()), "n_repeated_blocks": n_rep,
                    "repeat_runs": [(a * BLOCK_BYTES / bytes_per_s, b * BLOCK_BYTES / bytes_per_s, n * BLOCK_BYTES / bytes_per_s) for a, b, n in runs[:20]]})
        head = set(h for h in hashes[: edge // BLOCK_BYTES] if h); tail = set(h for h in hashes[-(edge // BLOCK_BYTES):] if h)
    else:
        hh, _ = block_hashes(amp, 0, edge); th, _ = block_hashes(amp, max(0, size - edge), size)
        n_rep, runs = find_repeats(hh + th)
        out.update({"hashed_gb": 2 * edge / 1e9, "n_blocks": len(hh) + len(th), "n_const_blocks": 0, "n_repeated_blocks": n_rep,
                    "repeat_runs": [(a, b, n) for a, b, n in runs[:20]]})
        head = set(h for h in hh if h); tail = set(h for h in th if h)
    cross = {}
    if prev is not None:
        ph, _ = block_hashes(prev / "amplifier.dat", max(0, os.path.getsize(prev / "amplifier.dat") - edge))
        cross["blocks_shared_with_prev_tail"] = len(head & set(h for h in ph if h))
    if nxt is not None:
        nh, _ = block_hashes(nxt / "amplifier.dat", 0, edge)
        cross["blocks_shared_with_next_head"] = len(tail & set(h for h in nh if h))
    out.update(cross)
    # B: channels
    cs = channel_scan(amp, nch, fs)
    out.update({
        "n_windows": cs["n_windows"], "n_broadband_windows": cs["n_broadband_windows"],
        "rail_channels": [int(c) for c in np.where(cs["rail_frac"] > 0.001)[0]],
        "flat_channels": [int(c) for c in np.where(cs["flat_windows"] >= 0.5 * cs["n_windows"])[0]],
        "stuck_channels": [int(c) for c in np.where(cs["stuck_windows"] >= 0.5 * cs["n_windows"])[0]],
        "exact_dup_pairs": [f"{i}-{j}:{n}" for (i, j), n in sorted(cs["exact_dup_pairs"].items())],
        "near_dup_pairs": [f"{i}-{j}:{n}" for (i, j), n in sorted(cs["near_dup_pairs"].items()) if n >= 2],
        "identity_unstable_channels": [int(c) for c in np.where(cs["identity_min_r"] < 0.5)[0]],
        "identity_min_r_median": float(np.median(cs["identity_min_r"])),
        "median_std_adc": float(np.median(cs["median_std"])),
    })
    if verbose:
        print(f"  {sdir.name}: {out['size_gb']:.1f} GB, repeats {out['n_repeated_blocks']} (const {out['n_const_blocks']}), "
              f"shared prev/next {out.get('blocks_shared_with_prev_tail', '-')}/{out.get('blocks_shared_with_next_head', '-')}, "
              f"rail {out['rail_channels']} flat {out['flat_channels']} stuck {out['stuck_channels']} exact-dup {out['exact_dup_pairs'][:3]} "
              f"near-dup {out['near_dup_pairs'][:3]} identity-unstable {out['identity_unstable_channels']} (min-r median {out['identity_min_r_median']:.2f})", flush=True)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cohort", required=True)
    ap.add_argument("--animals", nargs="*", default=None)
    ap.add_argument("--firmware", type=int, default=None, help="only sessions with this firmware_version")
    ap.add_argument("--sessions", nargs="*", default=None)
    ap.add_argument("--full-hash", action="store_true", help="hash the whole amplifier.dat (default: first/last 5 min + neighbours)")
    ap.add_argument("--suffix", default="")
    a = ap.parse_args()
    cfg = ephys_block(a.cohort)
    raw = raw_ephys_root(a.cohort)
    per: dict[str, list[Path]] = defaultdict(list)
    for animal, mac, sdir in iter_raw_sessions(raw, cfg.get("session_glob", "*"), cohort=a.cohort):
        key = f"SF{int(animal[2:]):02d}" if animal.upper().startswith("SF") and animal[2:].isdigit() else animal
        if a.animals and key not in {x.upper() for x in a.animals}:
            continue
        per[key].append(sdir)
    rows = []
    for animal in sorted(per):
        sess = sorted(per[animal], key=lambda p: parse_session_name(p.name)["start"])
        for i, sdir in enumerate(sess):
            cp = parse_ce_params(sdir)
            if a.firmware is not None and cp.firmware_version != a.firmware:
                continue
            if a.sessions and sdir.name not in a.sessions:
                continue
            prev = sess[i - 1] if i > 0 else None
            nxt = sess[i + 1] if i + 1 < len(sess) else None
            r = scan_session(sdir, prev, nxt, cp.n_channels or 64, float(cp.fs or cfg.get("sampling_rate_hz", 20000)), a.full_hash)
            r.update({"animal": animal, "firmware": cp.firmware_version})
            rows.append(r)
    rd = report_dir(a.cohort)
    stem = rd / f"ephys_spikes_integrity_scan_{a.cohort}{a.suffix}"
    cols = ["animal", "session", "firmware", "size_gb", "duration_s", "hashed_gb", "n_blocks", "n_const_blocks", "n_repeated_blocks", "repeat_runs",
            "blocks_shared_with_prev_tail", "blocks_shared_with_next_head", "n_windows", "n_broadband_windows", "rail_channels", "flat_channels",
            "stuck_channels", "exact_dup_pairs", "near_dup_pairs", "identity_unstable_channels", "identity_min_r_median", "median_std_adc"]
    with open(f"{stem}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: (";".join(map(str, v)) if isinstance(v, list) else v) for k, v in r.items()})
    L = [f"# Integrity scan, cohort `{a.cohort}`" + (f" (firmware {a.firmware})" if a.firmware else ""),
         f"\nGenerated {utc_now_iso()} by `ephys/integrity_scan.py` (git {git_commit()}); block = {BLOCK_BYTES} B; "
         f"{'whole-file' if a.full_hash else 'first/last 5 min'} hashing; {N_WINDOWS} x {WINDOW_S:g}-s channel windows. Definitions in the docstring.\n",
         "| animal | session | FW | GB | hashed GB | repeated blocks | shared w/ prev tail | shared w/ next head | rail ch | flat ch | stuck ch | exact-dup pairs | near-dup pairs (r>0.999, >=2 windows) | identity-unstable ch | broadband windows |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['animal']} | `{r['session']}` | FM{r['firmware']} | {r['size_gb']:.1f} | {r['hashed_gb']:.1f} | {r['n_repeated_blocks']} | "
                 f"{r.get('blocks_shared_with_prev_tail', '-')} | {r.get('blocks_shared_with_next_head', '-')} | {r['rail_channels']} | {r['flat_channels']} | {r['stuck_channels']} | "
                 f"{r['exact_dup_pairs'][:5]} | {r['near_dup_pairs'][:5]} | {r['identity_unstable_channels']} | {r['n_broadband_windows']}/{r['n_windows']} |")
    Path(f"{stem}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"csv -> {stem}.csv\nmd  -> {stem}.md")


if __name__ == "__main__":
    main()
