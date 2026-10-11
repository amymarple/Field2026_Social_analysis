"""USV strip presence: detector v1 vs v2 against the user's strip labels (plan Amendment 2).

Per labelled 30-s strip (page usv_strip_review_20261009_1757, labels ephys/configs/usv_review_2026c/usv_strip_labels.csv):
- v1 features from usv_whiten_detect.py (tonal candidates >= 30 ms / >= 20 ms / any, total duration);
- v2 features from usv_detect_v2.py (call contours >= 10 / 20 / 30 ms, total call duration, longest call).
Per mic, a threshold on one feature is chosen on the other recording windows (Youden J; leave-one-window-out) and
applied to the held-out window. Reported: sensitivity, specificity, precision.

    python ephys/usv/usv_eval_v2.py [--v1 <dir>] [--v2 <dir>] [--strips <strips.json>] [--labels <csv>]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path("D:/Field2026_analysis_out/2026c")
REPO = Path(__file__).resolve().parents[2]


def strip_features(D: pd.DataFrame, v1: Path, v2: Path) -> pd.DataFrame:
    rows = []
    cache: dict[str, tuple] = {}
    for r in D.itertuples():
        stem = r.file[:-4]
        if stem not in cache:
            try:
                c1 = pd.read_csv(v1 / f"{stem}.csv")
            except (FileNotFoundError, pd.errors.EmptyDataError):
                c1 = pd.DataFrame(columns=["begin_s", "dur_s", "tonal"])
            c2 = pd.read_csv(v2 / f"{stem}.contours.csv")
            cache[stem] = (c1, c2[c2.is_call.astype(bool)])
        c1, c2 = cache[stem]
        a, b = r.offset_s, r.offset_s + 30
        t1 = c1[(c1.begin_s >= a) & (c1.begin_s < b) & c1.tonal.astype(bool)] if len(c1) else c1
        t2 = c2[(c2.begin_s >= a) & (c2.begin_s < b)]
        rows.append({"v1_tonal30": int((t1.dur_s >= 0.03).sum()) if len(t1) else 0, "v1_tonal20": int((t1.dur_s >= 0.02).sum()) if len(t1) else 0,
                     "v1_tonal_any": len(t1), "v1_tonal_dur_s": float(t1.dur_s.sum()) if len(t1) else 0.0,
                     "v2_calls10": int((t2.dur_s >= 0.01).sum()), "v2_calls20": int((t2.dur_s >= 0.02).sum()),
                     "v2_calls30": int((t2.dur_s >= 0.03).sum()), "v2_call_dur_s": float(t2.dur_s.sum()),
                     "v2_longest_s": float(t2.dur_s.max()) if len(t2) else 0.0})
    return pd.concat([D.reset_index(drop=True), pd.DataFrame(rows)], axis=1)


def lowo(X: pd.DataFrame, feat: str) -> dict:
    cand = sorted(set(np.round(X[feat], 3)))
    preds = []
    for w in X.window.unique():
        tr, te = X[X.window != w], X[X.window == w]
        best, bj = cand[0], -1.0
        if tr.yes.sum() and (~tr.yes).sum():
            for th in cand:
                p = tr[feat] >= th
                j = (p & tr.yes).sum() / tr.yes.sum() + (~p & ~tr.yes).sum() / (~tr.yes).sum() - 1
                if j > bj:
                    best, bj = th, j
        preds.append(pd.DataFrame({"yes": te.yes, "pred": te[feat] >= best}))
    P = pd.concat(preds)
    tp, fp = int((P.pred & P.yes).sum()), int((P.pred & ~P.yes).sum())
    fn, tn = int((~P.pred & P.yes).sum()), int((~P.pred & ~P.yes).sum())
    return {"sens": tp / max(tp + fn, 1), "spec": tn / max(tn + fp, 1), "prec": tp / max(tp + fp, 1),
            "tp": tp, "fn": fn, "fp": fp, "tn": tn}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--v1", default=str(OUT / "usv_whiten_sample"))
    ap.add_argument("--v2", default=str(OUT / "usv_v2_sample"))
    ap.add_argument("--strips", default=str(OUT / "usv_strip_review_20261009_1757/strips.json"))
    ap.add_argument("--labels", default=str(REPO / "ephys/configs/usv_review_2026c/usv_strip_labels.csv"))
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    L = pd.read_csv(a.labels)
    M = pd.DataFrame(json.load(open(a.strips)))
    D = M.merge(L, left_on="id", right_on="strip")
    D = D[D.usv.isin(["none", "a few", "many"])].copy()
    D["yes"] = D.usv != "none"
    D["mic"] = D.file.str[:5]
    D["window"] = D.file.str[:-4]
    F = strip_features(D, Path(a.v1), Path(a.v2))
    rows = []
    for mic in ("MIC01", "MIC02", "both"):
        X = F if mic == "both" else F[F.mic == mic]
        for feat in [c for c in F.columns if c.startswith(("v1_", "v2_"))]:
            rows.append({"mic": mic, "feature": feat, "strips": len(X), "usv_strips": int(X.yes.sum()), **lowo(X, feat)})
    R = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    print(R.round(2).to_string(index=False))
    if a.out:
        Path(a.out).mkdir(parents=True, exist_ok=True)
        R.to_csv(Path(a.out) / "usv_presence_v1_v2.csv", index=False)
        F.to_csv(Path(a.out) / "usv_strip_features.csv", index=False)


if __name__ == "__main__":
    main()
