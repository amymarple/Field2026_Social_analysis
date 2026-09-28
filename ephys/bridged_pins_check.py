"""Bridged connector pins vs two very close electrodes: the DIFFERENCE signal of a column pair (2026-09-08).

Context: on SF12 (and SF08's 53/55) groups of exported columns carry one signal each (spike-band r 0.90-0.97, identical SPW / ripple /
theta). The user's objection: "未必是重复可能是更 high density" - sites of a high-density design would also share their LFP. A correlation
cannot separate the two cases; the difference a-b can. Two amplifier inputs on ONE electrode node (bridged pins) differ only by the
amplifiers' own input noise: the difference is Gaussian at ~sqrt(2) x 1.7 uV in the spike band, carries no spikes and no LFP gradient.
Two electrodes, even 20 um apart, differ in spike amplitude (spike fields decay over ~50 um) and in LFP (any depth gradient), so their
difference contains spike events (kurtosis >> 0, events/s comparable to the channel's own spike rate) and a sizeable LFP residual.

Per pair: spike-band (300-3000 Hz) rms of a, b and a-b with the ratio rms(a-b)/rms(a); 1-100 Hz rms of a and a-b with the ratio;
excess kurtosis of the spike-band difference; threshold crossings > 6 sigma per second in the difference and on channel a alone.
Bridged: ratio ~0.3-0.4, LFP ratio ~0.01-0.03, kurtosis ~0, events ~0 while a alone has spikes. Distinct neighbours: ratio ~1,
LFP ratio 0.3-1.0, kurtosis 3-70, events 4-12/s.
Result SF12 (last 10 min of 15_20260903_002228.142, 120 s): all 11 cluster pairs bridged-like (ratio 0.33-0.43, LFP 1.4-3 %, events
<= 0.16/s vs 1-12/s on the channel); 8 neighbouring distinct-site controls: ratio 0.8-1.6, LFP 32-97 %, events 3.7-11.7/s.

Usage: python ephys/bridged_pins_check.py <staged_raw_dir> <seconds> a-b a-b ...   (exported-column pairs; reads amplifier.dat read-only)
"""
import sys
from pathlib import Path
import numpy as np
from scipy.signal import butter, sosfiltfilt
from scipy.stats import kurtosis
raw = Path(sys.argv[1]); secs = float(sys.argv[2]); pairs = [tuple(int(x) for x in p.split("-")) for p in sys.argv[3:]]
fs = 20000.0; n = int(secs * fs)
mm = np.memmap(raw / "amplifier.dat", dtype=np.int16, mode="r")
nch = 64; X = np.asarray(mm[: n * nch]).reshape(n, nch).astype(np.float32) * 0.195   # uV
sos_hp = butter(3, [300, 3000], btype="band", fs=fs, output="sos"); sos_lf = butter(3, [1, 100], btype="band", fs=fs, output="sos")
print(f"{secs:.0f} s at 20 kHz; per channel: spike-band rms (uV); per pair: rms of (a-b) in spike band and in 1-100 Hz, kurtosis of the spike-band difference,")
print("  events/s where |a-b| > 6 sigma of the difference, and the same counts on channel a alone (spikes present in the recording)")
print(f"{'pair':>8} {'rmsA':>6} {'rmsB':>6} {'rms(A-B)':>9} {'ratio':>6} {'lfp rms A':>9} {'lfp(A-B)':>9} {'lfp ratio':>9} {'kurt(A-B)':>9} {'ev/s A-B':>9} {'ev/s A':>7}")
for a, b in pairs:
    ha = sosfiltfilt(sos_hp, X[:, a]); hb = sosfiltfilt(sos_hp, X[:, b]); d = ha - hb
    la = sosfiltfilt(sos_lf, X[:, a]); lb = sosfiltfilt(sos_lf, X[:, b]); dl = la - lb
    sd = d.std(); ev = int(np.sum(np.abs(d) > 6 * sd)); ev_a = int(np.sum(np.abs(ha) > 6 * ha.std()))
    # count events as separate threshold crossings (not samples): crossings from below
    def nev(x, thr):
        m = np.abs(x) > thr; return int(np.sum(m[1:] & ~m[:-1]))
    print(f"{a:3d}-{b:<3d} {ha.std():6.1f} {hb.std():6.1f} {sd:9.2f} {sd/ha.std():6.2f} {la.std():9.0f} {dl.std():9.1f} {dl.std()/la.std():9.3f} {kurtosis(d):9.2f} {nev(d, 6*sd)/secs:9.2f} {nev(ha, 6*ha.std())/secs:7.2f}")
