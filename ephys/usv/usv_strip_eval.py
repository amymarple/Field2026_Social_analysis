"""Presence (per 30-s strip) of the whitened USV detector vs the user's strip labels (ephys/configs/usv_review_2026c/,
2026-10-10). Run: python ephys/usv/usv_strip_eval.py. Paths are those of the first review page (usv_strip_review_20261009_1757)."""
import json
import numpy as np
import pandas as pd
L = pd.read_csv(r"D:/Documents/GitHub/Field2026_Social_analysis/ephys/configs/usv_review_2026c/usv_strip_labels.csv")
M = pd.DataFrame(json.load(open(r"D:/Field2026_analysis_out/2026c/usv_strip_review_20261009_1757/strips.json")))
D = M.merge(L, left_on="id", right_on="strip")
D = D[D.usv.isin(["none", "a few", "many"])].copy()
D["yes"] = D.usv != "none"
# per-strip detector features from the whitened candidate tables (all durations)
rows = []
for r in D.itertuples():
    try:
        C = pd.read_csv(f"D:/Field2026_analysis_out/2026c/usv_whiten_sample/{r.file[:-4]}.csv")
    except Exception:
        C = pd.DataFrame(columns=["begin_s", "dur_s", "tonal", "max_excess_db", "peak_kHz"])
    c = C[(C.begin_s >= r.offset_s) & (C.begin_s < r.offset_s + 30)]
    t = c[c.tonal.astype(bool)] if len(c) else c
    rows.append({"tonal30": int((t.dur_s >= 0.03).sum()) if len(t) else 0, "tonal_any": len(t),
                 "tonal20": int((t.dur_s >= 0.02).sum()) if len(t) else 0,
                 "tonal_dur_s": float(t.dur_s.sum()) if len(t) else 0.0})
D = pd.concat([D.reset_index(drop=True), pd.DataFrame(rows)], axis=1)
D["mic"] = D.file.str[:5]
D["night"] = D.file.str.contains("_23-00|_03-00")
print("strips", len(D), "yes", int(D.yes.sum()), "| by mic/night:")
print(D.groupby(["mic", "night"]).yes.agg(["size", "sum"]))
for feat, ths in (("tonal30", [1, 2, 3, 5, 10]), ("tonal20", [1, 2, 3, 5, 10]), ("tonal_any", [1, 3, 5, 10, 20]), ("tonal_dur_s", [0.05, 0.1, 0.2, 0.5, 1.0])):
    out = []
    for th in ths:
        pred = D[feat] >= th
        tp, fp = int((pred & D.yes).sum()), int((pred & ~D.yes).sum())
        fn, tn = int((~pred & D.yes).sum()), int((~pred & ~D.yes).sum())
        out.append(f"{th}: sens {tp}/{tp+fn}={tp/max(tp+fn,1):.2f} spec {tn}/{tn+fp}={tn/max(tn+fp,1):.2f} prec {tp/max(tp+fp,1):.2f}")
    print(feat, " | ".join(out))
miss = D[D.yes & (D.tonal30 == 0)]
print("\nmissed strips (yes, no tonal>=30ms):", len(miss))
print(miss[["id", "usv", "bands", "tonal_any", "tonal20", "tonal_dur_s"]].to_string(index=False))
fp = D[~D.yes & (D.tonal30 >= 3)]
print("\nno-USV strips with >= 3 tonal>=30ms ticks:", len(fp))
print(fp[["id", "bands", "tonal30", "tonal_any"]].to_string(index=False))

print("\n=== per-mic thresholds, leave-one-window-out (threshold chosen on the other windows by Youden J) ===")
D["window"] = D.file.str[:-4]
for mic in ("MIC01", "MIC02"):
    X = D[D.mic == mic]
    for feat in ("tonal_any", "tonal20", "tonal30", "tonal_dur_s"):
        cand = sorted(set(X[feat].round(3)))
        preds = []
        for w in X.window.unique():
            tr, te = X[X.window != w], X[X.window == w]
            best, bj = None, -1
            for th in cand:
                p = tr[feat] >= th
                if tr.yes.sum() == 0:
                    continue
                j = (p & tr.yes).sum() / tr.yes.sum() + (~p & ~tr.yes).sum() / (~tr.yes).sum() - 1
                if j > bj:
                    best, bj = th, j
            preds.append(pd.DataFrame({"yes": te.yes, "pred": te[feat] >= best, "th": best}))
        P = pd.concat(preds)
        tp, fp, fn = (P.pred & P.yes).sum(), (P.pred & ~P.yes).sum(), (~P.pred & P.yes).sum()
        tn = (~P.pred & ~P.yes).sum()
        print(f"{mic} {feat:12s} sens {tp}/{tp+fn} = {tp/max(tp+fn,1):.2f}  spec {tn}/{tn+fp} = {tn/max(tn+fp,1):.2f}  "
              f"prec {tp/max(tp+fp,1):.2f}  thresholds {sorted(set(P.th.round(3)))}")
