"""Did the SF07 / SF11 probes really move at the logged 1/4-turn advances (2026c, 2026-09-04/05/06)? Compare per-channel
signal profiles (LFP band powers, MUA rate, ripple-band bursts) in 10-min windows before and after each move against no-move
control pairs; a real displacement re-maps tissue to channels and lowers the fingerprint correlation toward the shifted-self value.
The windows are the 2026c ones (edit WINDOWS/PAIRS for a new move). Usage: python ephys/probe_move_check.py --cohort 2026c
Outputs: results/<cohort>/ephys_spikes/reports/ephys_spikes_probe_move_check_<cohort>_{features,pairs}.csv + figures/...png;
the md report is written by hand from these numbers (see ephys_spikes_probe_move_check_2026c.md, Definitions section)."""
import csv, os, time
from pathlib import Path
import numpy as np
from scipy import signal

import argparse
from _common import figure_dir, raw_ephys_root, report_dir

ROOT = OUT_R = OUT_F = None    # set in main() from --cohort
FS = 20000; NCH = 64; WIN_S = 600; CHUNK_S = 120; DEC = 16; FS_LFP = FS // DEC
SHANKS = {0: [57, 54, 56, 55, 59, 52, 58, 53, 61, 50, 60, 51, 63, 48, 62, 49],
          1: [42, 41, 44, 40, 45, 38, 46, 37, 47, 36, 43, 34, 39, 33, 35, 32],
          2: [9, 12, 10, 14, 8, 13, 5, 17, 6, 15, 4, 11, 1, 7, 2, 3],
          3: [22, 27, 25, 24, 20, 29, 23, 26, 18, 31, 21, 28, 16, 0, 19, 30]}
BANDS = {"delta": (1, 4), "theta": (5, 10), "beta": (15, 30), "gamma": (30, 80), "ripple": (120, 200)}

# (label, session, where): where = "last" (last 10 min, ending 60 s before the end), "early" (30-40 min in), or a start second
WINDOWS = {
    "SF07": [("A0 pre-0904 early", "8_20260904_080936.435", "early"), ("A pre-0904", "8_20260904_080936.435", "last"),
             ("B0 post-0904 +30min", "11_20260904_140054.476", "early"), ("B post-0904 +5.3h", "11_20260904_140054.476", "last"),
             ("C night-end 0905 08:24", "14_20260904_201825.406", "last"),
             ("D pre-0905", "2_20260905_093310.289", "last"),
             ("E0 post-0905 +30min", "6_20260905_133118.469", "early"), ("E post-0905 +4.3h", "6_20260905_133118.469", "last"),
             ("F test-0906 12:44", "1_20260906_123931.995", 300)],
    "SF11": [("A0 pre-0904 early", "7_20260904_082050.456", "early"), ("A pre-0904", "7_20260904_082050.456", "last"),
             ("B0 post-0904 +30min", "9_20260904_135650.425", "early"), ("B post-0904 +5.5h", "9_20260904_135650.425", "last"),
             ("C night-end 0905 08:32", "12_20260904_202856.246", "last"),
             ("D pre-0905", "3_20260905_094205.930", "last"),
             ("E0 post-0905 +30min", "7_20260905_151133.499", "early"), ("E post-0905 +2.8h", "7_20260905_151133.499", "last"),
             ("F test-0906 12:46", "0_20260906_124136.884", 300)],
}
PAIRS = [("move 09-04 (settled)", "A", "B"), ("move 09-04 (+30 min)", "A", "B0"), ("move 09-05 (settled)", "D", "E"),
         ("move 09-05 (+30 min)", "D", "E0"), ("move 09-06 (test rec.)", "E", "F"),
         ("control: same session 5 h apart", "A0", "A"), ("control: across the night, swap, no move", "B", "C"),
         ("control: morning swap, no move", "C", "D")]
FOLDER = {"SF07": "SF7", "SF11": "SF11"}
FEATS = ["log_theta", "log_gamma", "log_ripple", "mua_rate_hz", "ripple_events_per_min", "spike_band_mad_adc"]


def find_session(animal, name):
    hits = list((ROOT / FOLDER[animal]).glob(f"*/{name}"))
    assert len(hits) == 1, (animal, name, hits)
    return hits[0]


def window_features(sdir, where):
    amp = sdir / "amplifier.dat"
    n = os.path.getsize(amp) // (2 * NCH)
    dur = n / FS
    if where == "last":
        t0 = dur - WIN_S - 60
    elif where == "early":
        t0 = 1800.0
    else:
        t0 = float(where)
    t0 = max(0.0, min(t0, dur - WIN_S - 1))
    mm = np.memmap(amp, dtype=np.int16, mode="r", shape=(n, NCH))
    sos_mua = signal.butter(3, [300, 3000], btype="bandpass", fs=FS, output="sos")
    lfp_parts, mua_events, mua_rms = [], np.zeros(NCH), []
    for c0 in np.arange(t0, t0 + WIN_S, CHUNK_S):
        i0 = int(c0 * FS); i1 = int(min(c0 + CHUNK_S, t0 + WIN_S) * FS)
        x = np.asarray(mm[i0:i1], dtype=np.float32)
        x -= np.median(x, axis=0)
        lfp_parts.append(signal.resample_poly(x, 1, DEC, axis=0).astype(np.float32))
        hp = signal.sosfiltfilt(sos_mua, x, axis=0)
        mad = np.median(np.abs(hp), axis=0) * 1.4826 + 1e-6
        mua_rms.append(mad)
        below = hp < (-5.0 * mad)
        onset = below[1:] & ~below[:-1]          # False -> True transitions = event onsets per channel
        mua_events += onset.sum(axis=0)
        del x, hp, below, onset
    lfp = np.concatenate(lfp_parts, axis=0)
    f, pxx = signal.welch(lfp, fs=FS_LFP, nperseg=2 * FS_LFP, axis=0)
    feats = {}
    for b, (lo, hi) in BANDS.items():
        sel = (f >= lo) & (f < hi)
        feats[f"log_{b}"] = np.log10(pxx[sel].mean(axis=0) + 1e-9)
    feats["mua_rate_hz"] = mua_events / WIN_S
    feats["spike_band_mad_adc"] = np.median(np.array(mua_rms), axis=0)
    # ripple events: 120-200 Hz envelope z > 4 for >= 20 ms
    sos_r = signal.butter(3, [120, 200], btype="bandpass", fs=FS_LFP, output="sos")
    rb = signal.sosfiltfilt(sos_r, lfp, axis=0)
    env = np.abs(signal.hilbert(rb, axis=0))
    k = int(0.01 * FS_LFP)
    kern = np.ones(k) / k
    env = np.stack([np.convolve(env[:, ch], kern, mode="same") for ch in range(NCH)], axis=1)
    med = np.median(env, axis=0); mad = np.median(np.abs(env - med), axis=0) * 1.4826 + 1e-9
    z = (env - med) / mad
    above = z > 4.0
    rates = np.zeros(NCH)
    min_len = int(0.02 * FS_LFP)
    for ch in range(NCH):
        a = above[:, ch].astype(np.int8)
        d = np.diff(np.concatenate([[0], a, [0]]))
        starts, ends = np.where(d == 1)[0], np.where(d == -1)[0]
        rates[ch] = ((ends - starts) >= min_len).sum() / (WIN_S / 60.0)
    feats["ripple_events_per_min"] = rates
    feats["log_ripple_env"] = np.log10(med + 1e-9)
    return feats, t0, dur


def rel(v):
    return v - np.median(v)


def best_shift(pa, pb):
    pa, pb = pa - pa.mean(), pb - pb.mean()
    best, bestc, c0 = 0, -2.0, -2.0
    for s in range(-3, 4):
        if s >= 0:
            x1, x2 = pa[:16 - s], pb[s:]
        else:
            x1, x2 = pa[-s:], pb[:16 + s]
        c = float(np.corrcoef(x1, x2)[0, 1]) if x1.std() > 0 and x2.std() > 0 else -2.0
        if s == 0:
            c0 = c
        if c > bestc:
            best, bestc = s, c
    return best, bestc, c0


def main():
    global ROOT, OUT_R, OUT_F
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cohort", default="2026c")
    ap.add_argument("--raw-root", default=None)
    a = ap.parse_args()
    ROOT, OUT_R, OUT_F = raw_ephys_root(a.cohort, a.raw_root), report_dir(a.cohort), figure_dir(a.cohort)
    OUT_R.mkdir(parents=True, exist_ok=True); OUT_F.mkdir(parents=True, exist_ok=True)
    all_feats, rows = {}, []
    for animal, wins in WINDOWS.items():
        for label, sess, where in wins:
            sdir = find_session(animal, sess)
            t1 = time.time()
            feats, t0, dur = window_features(sdir, where)
            print(f"{animal} {label:26} {sess} t0={t0:7.0f}s of {dur:7.0f}s  ({time.time() - t1:.0f} s)", flush=True)
            all_feats[(animal, label.split()[0])] = (label, sess, t0, feats)
            for ch in range(NCH):
                rows.append({"animal": animal, "window": label, "session": sess, "t0_s": round(t0), "channel": ch,
                             **{k: round(float(v[ch]), 4) for k, v in feats.items()}})
    with open(OUT_R / f"ephys_spikes_probe_move_check_{a.cohort}_features.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

    summary = []
    for animal in WINDOWS:
        for pname, a, b in PAIRS:
            if (animal, a) not in all_feats or (animal, b) not in all_feats:
                continue
            la, _, _, fa = all_feats[(animal, a)]; lb, _, _, fb = all_feats[(animal, b)]
            rec = {"animal": animal, "pair": pname, "from": la, "to": lb}
            for ft in FEATS:
                va, vb = fa[ft], fb[ft]
                if ft in ("mua_rate_hz", "ripple_events_per_min"):
                    va, vb = np.log10(va + 0.01), np.log10(vb + 0.01)
                ra, rb_ = rel(va), rel(vb)
                rec[f"{ft}_corr"] = round(float(np.corrcoef(ra, rb_)[0, 1]), 3)
                rec[f"{ft}_medabsdiff"] = round(float(np.median(np.abs(rb_ - ra))), 3)
                shifts, gains = [], []
                for sh, chans in SHANKS.items():
                    s, c, c0 = best_shift(ra[chans], rb_[chans])
                    shifts.append(s); gains.append(c - c0)
                rec[f"{ft}_shift_sites"] = " ".join(f"{s:+d}" for s in shifts)
                rec[f"{ft}_shift_gain"] = " ".join(f"{g:.2f}" for g in gains)   # corr(best shift) - corr(shift 0)
            summary.append(rec)
    with open(OUT_R / f"ephys_spikes_probe_move_check_{a.cohort}_pairs.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0].keys())); w.writeheader(); w.writerows(summary)
    print("\n=== pair summary: profile correlation over 64 ch (relative to the window median) / median |diff| / per-shank best shift (sites) and its corr gain over shift 0 ===")
    for r in summary:
        print(f"{r['animal']} {r['pair']:42}")
        for ft in FEATS[:5]:
            print(f"      {ft:22} r={r[ft + '_corr']:+.2f}  d={r[ft + '_medabsdiff']:.3f}  shift=[{r[ft + '_shift_sites']}]  gain=[{r[ft + '_shift_gain']}]")

    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    show = ["A", "B", "D", "E", "F", "C"]
    colors = {"A": "tab:blue", "B": "tab:cyan", "D": "tab:orange", "E": "tab:red", "F": "tab:purple", "C": "gray"}
    fig, axes = plt.subplots(8, 4, figsize=(16, 22), squeeze=False)
    for ai, animal in enumerate(WINDOWS):
        for fi, ft in enumerate(["mua_rate_hz", "ripple_events_per_min", "log_theta", "log_gamma"]):
            for sh, chans in SHANKS.items():
                ax = axes[ai * 4 + fi, sh]
                for key in show:
                    if (animal, key) not in all_feats:
                        continue
                    label, _, _, feats = all_feats[(animal, key)]
                    ax.plot(feats[ft][chans], np.arange(16), "-o", ms=3, color=colors[key], label=label)
                ax.invert_yaxis()
                ax.set_title(f"{animal} shank {sh + 1} - {ft}" + ("" if animal == "SF07" else " (site order UNVERIFIED)"), fontsize=8)
                ax.set_ylabel("site (xml order)", fontsize=7); ax.tick_params(labelsize=7)
                if ft.startswith("mua") or ft.startswith("ripple"):
                    ax.set_xscale("symlog", linthresh=0.1)
                if sh == 0 and fi == 0:
                    ax.legend(fontsize=6)
    fig.suptitle("Probe-move check: per-channel profiles before/after each logged 1/4-turn advance (10-min windows)", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.98))
    fig.savefig(OUT_F / f"ephys_spikes_probe_move_check_{a.cohort}.png", dpi=110)
    print("figure written")


if __name__ == "__main__":
    main()
