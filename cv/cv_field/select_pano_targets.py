"""select_pano_targets.py — WISER-guided choice of frame times for the cohort-3 CH01/CH02 labelling pool.

For every 5-s bin of the cohort-3 WISER data it counts how many TAGGED animals are outside the two houses (house
rectangle grown by 14 in, the same zone rule as the cohort-3 WISER accuracy report), then draws frame times stratified
by that count (0 / 1-2 / >=3 outside) and spread over nights and hours. WISER is used only for presence/count — never
for boxes (the CH01/CH02 pixel<->paddock correction is being worked out separately).

Input: the per-tag 5-s bin medians written by the cohort-3 WISER accuracy run
(`$FIELD2026_ANALYSIS_OUT_ROOT/2026c/wiser_working/c3_bins5.pkl`; producer
`.../wiser_cohort3_accuracy_20260928_1405/scripts/s03_prepare.py`, report
`results/2026c/wiser_baseline/reports/wiser_baseline_cohort3_accuracy_2026c.md`) — only on-animal tag epochs, off-animal
and static-reference epochs already separated there. Handling windows: `cv/configs/cohort3_handling_windows.json`.

Caveats carried into every tag: the count is of TAGGED animals, a lower bound whenever an animal is untracked (SF12 has
no track on night 1; SF11 is untracked 09-02 00:03 -> 08:20 and, still in the paddock, after its implant+tag came off
09-07 06:10:45; the five females from 09-11 19:40 carry no tag). Before the 09-03 13:59 WISER restart the WISER frame
is shifted 7-18 in, so bins near a house can be misclassified.

Usage:
  python cv/cv_field/select_pano_targets.py --stats                          # per-night strata, writes nothing
  python cv/cv_field/select_pano_targets.py --test-night 2026-09-05 --out <dir> [--per-camera 30 --test-per-camera 20]
      -> <dir>/targets_round0.csv, targets_test.csv (camera,time,tag for grab_frames.py) + selection_summary.json
  python cv/cv_field/select_pano_targets.py --selftest
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "wiser" / "src"))

EDT = pd.Timedelta(hours=-4)
NIGHT_START, NIGHT_END = (21, 0), (4, 20)
STRATA = ("zero", "few", "many")                 # 0 / 1-2 / >=3 tagged animals outside the houses
DEFAULT_BINS = Path(os.environ.get("FIELD2026_ANALYSIS_OUT_ROOT", r"D:\Field2026_analysis_out")) / "2026c" / "wiser_working" / "c3_bins5.pkl"
EXPECTED_ANIMALS_BEFORE_POPCHANGE = 6


def stratum(n_out: int) -> str:
    return "zero" if n_out == 0 else ("few" if n_out <= 2 else "many")


def night_of(t: pd.Timestamp) -> date | None:
    """Night D = D 21:00 -> D+1 04:20; None outside the night window."""
    m = t.hour * 60 + t.minute
    if m >= NIGHT_START[0] * 60 + NIGHT_START[1]:
        return t.date()
    if m < NIGHT_END[0] * 60 + NIGHT_END[1]:
        return (t - pd.Timedelta(days=1)).date()
    return None


def load_handling(path: Path):
    cfg = json.loads(path.read_text(encoding="utf-8"))
    win = [(pd.Timestamp(a), pd.Timestamp(b)) for a, b, _ in cfg["windows"]]
    return win, pd.Timestamp(cfg["popchange"]), pd.Timestamp(cfg["release"]), pd.Timestamp(cfg["end"])


def bin_table(bins: pd.DataFrame, rois: dict, buffer_in: float = 14.0) -> pd.DataFrame:
    """One row per 5-s bin: local time (bin start, EDT), tagged animals located, outside the houses, and the list."""
    import wiser_analysis_utils as wau
    b = bins[bins["period"].isin(["main", "popchange"])].copy()
    R = {r["name"]: r for r in rois["rois"]}
    inside = np.zeros(len(b), bool)
    for nm in ("house_1", "house_2"):
        _, inbuf = wau._rect_membership(b["x"].to_numpy(), b["y"].to_numpy(), R[nm], buffer_in)
        inside |= inbuf
    b["outside"] = ~inside
    g = b.groupby("b5")
    t = pd.DataFrame({"n_tagged": g["shortid"].nunique(), "n_outside": g["outside"].sum().astype(int),
                      "tags_outside": g.apply(lambda d: ",".join(sorted(d.loc[d["outside"], "tag_epoch"].str.split("_").str[1])),
                                              include_groups=False)})
    t["local"] = pd.to_datetime(t.index.to_numpy() * 5, unit="s") + EDT
    return t.reset_index()


def candidates(tab: pd.DataFrame, handling, popchange, include_popchange=False, handling_margin_min=5.0) -> pd.DataFrame:
    c = tab.copy()
    c["night"] = [night_of(t) for t in c["local"]]
    c = c[c["night"].notna()]
    m = pd.Timedelta(minutes=handling_margin_min)
    bad = np.zeros(len(c), bool)
    v = c["local"].to_numpy()
    for a, b_ in handling:
        bad |= (v >= np.datetime64(a - m)) & (v < np.datetime64(b_ + m))
    c = c[~bad]
    if not include_popchange:
        c = c[c["local"] < popchange]
    c["stratum"] = c["n_outside"].map(stratum)
    return c


def draw(c: pd.DataFrame, n: int, mix: dict, rng: random.Random, min_sep_s: float, taken=None) -> list[int]:
    """Stratified draw of n bin rows: per stratum its share of n, nights visited round-robin, a random bin of that
    night+stratum at least min_sep_s from every earlier pick. Returns row labels."""
    taken = list(taken or [])
    times = c["local"]
    picks = []
    want = {s: int(round(n * mix[s])) for s in STRATA}
    want[STRATA[-1]] += n - sum(want.values())
    for s in STRATA:
        sub = c[c["stratum"] == s]
        nights = sorted(sub["night"].unique())
        rng.shuffle(nights)
        by_night = {nt: list(sub.index[sub["night"] == nt]) for nt in nights}
        for idx in by_night.values():
            rng.shuffle(idx)
        k, stalled = 0, 0
        while want[s] > 0 and nights and stalled < len(nights):
            nt = nights[k % len(nights)]
            k += 1
            pool = by_night[nt]
            while pool:
                i = pool.pop()
                ti = times[i]
                if all(abs((ti - times[j]).total_seconds()) >= min_sep_s for j in picks + taken):
                    picks.append(i); want[s] -= 1; stalled = 0
                    break
            else:
                stalled += 1
    return picks


def to_rows(c: pd.DataFrame, idx: list[int], cam: str, split: str, untracked) -> list[dict]:
    out = []
    for i in idx:
        r = c.loc[i]
        t = r["local"] + pd.Timedelta(seconds=2.5)             # bin centre (grab_frames' default exact mode lands within ~0.1 s)
        out.append({"camera": cam, "time": t.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                    "tag": f"{split}|night={r['night']}|stratum={r['stratum']}|out={r['n_outside']}|tagged={r['n_tagged']}"
                           f"|untracked={untracked(r['local'])}|outside_tags={r['tags_outside']}"})
    return out


def make_untracked(popchange):
    def f(t):
        base = EXPECTED_ANIMALS_BEFORE_POPCHANGE + (5 if t >= popchange else 0)
        tracked = 5                                                      # 3079 3062 3077 306b + (3059 from 08-31 06:36)
        if t < pd.Timestamp("2026-08-31 06:36"):
            tracked -= 1
        if t < pd.Timestamp("2026-09-02 00:03:27") or pd.Timestamp("2026-09-02 08:20") <= t < pd.Timestamp("2026-09-07 06:10:45"):
            tracked += 1                                                 # SF11 via 305a, then 3058
        return base - tracked
    return f


def sha12(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], allow_abbrev=False)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--stats", action="store_true", help="print per-night strata and exit (writes nothing)")
    ap.add_argument("--bins", default=str(DEFAULT_BINS))
    ap.add_argument("--handling", default=str(REPO / "cv" / "configs" / "cohort3_handling_windows.json"))
    ap.add_argument("--rois", default=str(REPO / "wiser" / "configs" / "wiser_rois.json"))
    ap.add_argument("--cameras", nargs="+", default=["CH01", "CH02"])
    ap.add_argument("--per-camera", type=int, default=30)
    ap.add_argument("--test-night", default=None, help="night D (D 21:00 -> D+1 04:20) held out as the frozen test night")
    ap.add_argument("--test-per-camera", type=int, default=20)
    ap.add_argument("--mix", default="0.2,0.4,0.4", help="shares of zero,few,many")
    ap.add_argument("--min-sep-min", type=float, default=10.0)
    ap.add_argument("--include-popchange", action="store_true", help="also draw after 09-11 19:40 (untagged females)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    bins_path = Path(args.bins)
    bins = pd.read_pickle(bins_path)
    rois = json.loads(Path(args.rois).read_text(encoding="utf-8"))
    handling, popchange, release, end = load_handling(Path(args.handling))
    tab = bin_table(bins, rois)
    cand = candidates(tab, handling, popchange, args.include_popchange)
    per = cand.groupby(["night", "stratum"]).size().unstack(fill_value=0).reindex(columns=list(STRATA), fill_value=0)
    per_h = (per * 5 / 3600).round(2)
    per_h["total_h"] = per_h.sum(axis=1)
    print("hours of usable night bins per stratum (tagged animals outside the houses: zero=0, few=1-2, many>=3):")
    print(per_h.to_string())
    if args.stats:
        return 0
    if not (args.test_night and args.out):
        ap.error("--test-night and --out are required to write targets (or use --stats)")
    mix = dict(zip(STRATA, (float(v) for v in args.mix.split(","))))
    tn = date.fromisoformat(args.test_night)
    untracked = make_untracked(popchange)
    train_c, test_c = cand[cand["night"] != tn], cand[cand["night"] == tn]
    rows_r0, rows_test = [], []
    for k, cam in enumerate(args.cameras):
        rng = random.Random(args.seed * 100 + k)
        rows_r0 += to_rows(train_c, draw(train_c, args.per_camera, mix, rng, args.min_sep_min * 60), cam, "round0", untracked)
        rows_test += to_rows(test_c, draw(test_c, args.test_per_camera, mix, rng, args.min_sep_min * 60), cam, "test", untracked)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows_r0).to_csv(out / "targets_round0.csv", index=False)
    pd.DataFrame(rows_test).to_csv(out / "targets_test.csv", index=False)
    summ = {"bins": str(bins_path), "bins_sha256_12": sha12(bins_path), "handling": args.handling, "test_night": args.test_night,
            "mix": mix, "per_camera": args.per_camera, "test_per_camera": args.test_per_camera, "min_sep_min": args.min_sep_min,
            "include_popchange": args.include_popchange, "seed": args.seed,
            "round0_strata": pd.Series([r["tag"].split("|")[2] for r in rows_r0]).value_counts().to_dict(),
            "test_strata": pd.Series([r["tag"].split("|")[2] for r in rows_test]).value_counts().to_dict(),
            "usable_night_hours": {str(k): v for k, v in per_h["total_h"].to_dict().items()}}
    (out / "selection_summary.json").write_text(json.dumps(summ, indent=2, default=str), encoding="utf-8")
    print(f"round0 {len(rows_r0)} + test {len(rows_test)} targets -> {out}")
    return 0


def selftest() -> int:
    ok = True

    def rec(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")

    rec("night_of 23:00 -> same date", night_of(pd.Timestamp("2026-09-04 23:00")) == date(2026, 9, 4))
    rec("night_of 03:00 -> previous date", night_of(pd.Timestamp("2026-09-05 03:00")) == date(2026, 9, 4))
    rec("night_of 12:00 -> None", night_of(pd.Timestamp("2026-09-05 12:00")) is None)
    rec("strata 0/2/3", (stratum(0), stratum(2), stratum(3)) == ("zero", "few", "many"))
    # synthetic bin table: 3 nights x 2 h, 5-s bins, n_outside cycling 0..4
    rows = []
    for d in (date(2026, 9, 3), date(2026, 9, 4), date(2026, 9, 5)):
        t0 = pd.Timestamp(datetime.combine(d, datetime.min.time())) + pd.Timedelta(hours=22)
        for i in range(0, 1440):
            rows.append({"b5": i, "local": t0 + pd.Timedelta(seconds=5 * i), "n_tagged": 5, "n_outside": (i // 120) % 5, "tags_outside": ""})
    tab = pd.DataFrame(rows)
    cand = candidates(tab, [(pd.Timestamp("2026-09-04 22:00"), pd.Timestamp("2026-09-04 22:30"))], pd.Timestamp("2026-09-11 19:40"))
    rec("handling window (+5 min margin) removed", not ((cand["local"] >= pd.Timestamp("2026-09-04 21:55")) &
                                                        (cand["local"] < pd.Timestamp("2026-09-04 22:35"))).any())
    picks = draw(cand, 20, {"zero": 0.2, "few": 0.4, "many": 0.4}, random.Random(0), 600)
    got = cand.loc[picks]
    ts = sorted(got["local"])
    rec("draw: 20 picks, strata 4/8/8", len(picks) == 20 and got["stratum"].value_counts().to_dict() == {"few": 8, "many": 8, "zero": 4},
        str(got["stratum"].value_counts().to_dict()))
    rec("draw: >= 10 min apart", all((b - a).total_seconds() >= 600 for a, b in zip(ts, ts[1:])))
    rec("draw: spread over all 3 nights", got["night"].nunique() == 3)
    unt = make_untracked(pd.Timestamp("2026-09-11 19:40"))
    rec("untracked: night 1 = 1 (SF12), 09-05 = 0, 09-08 = 1 (SF11), after females = 6",
        (unt(pd.Timestamp("2026-08-30 22:00")), unt(pd.Timestamp("2026-09-05 22:00")), unt(pd.Timestamp("2026-09-08 22:00")),
         unt(pd.Timestamp("2026-09-11 22:00"))) == (1, 0, 1, 6))
    print(("PASS" if ok else "FAIL") + " — select_pano_targets self-test")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
