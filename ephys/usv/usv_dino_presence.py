r"""USV strip presence from DINOv3 image embeddings (plan implementation_plan/2026-10-08-mic-imu-sync.md, Amendment 3).

Run in the cv env (GPU torch + the local DINOv3 checkpoint):
    C:\Users\Cornell\.conda\envs\cv\python.exe ephys\usv\usv_dino_presence.py [--page <usv_strip_review run>] [--out <dir>]

1. Each 30-s strip PNG of the review page (whitened 15-100 kHz, 3600 x 320 px) is cropped to its axes and cut into three
   10-s tiles, each resized to 960 x 240 px (ImageNet-normalised RGB).
2. DINOv3 ViT-B/16 forward_features: per tile the CLS token, the mean and the maximum of the patch tokens (3 x 768).
   Strip embedding = the maximum and the mean over its tiles (4608 numbers). Cached in <out>/embeddings.npz.
3. Classifier: StandardScaler -> PCA(20) -> LogisticRegression(class_weight=balanced, C=1), fitted inside each fold;
   leave-one-window-out over the recording windows (both mics pooled with a mic indicator, and per mic); also the
   embedding + v1 counts (log1p of tonal-any / tonal >= 20 ms).
4. Reported: AUC, sensitivity / specificity / precision at p >= 0.5, Youden J; per-strip held-out p in strip_p.csv
   (for choosing what to label next).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "cv" / "cv_field"))
OUT = Path("D:/Field2026_analysis_out/2026c")
CROP = (7, 294, 44, 3592)                      # rows, cols of the axes inside the 3600 x 320 strip image
TILE = (960, 240)


def embed(paths: list[Path]) -> np.ndarray:
    import cv2
    import torch
    from field_embed import _IMAGENET_MEAN, _IMAGENET_STD, _load_dino, resolve_dino_source
    fam, repo, variant, patch, weights = resolve_dino_source("dinov3")
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    model = _load_dino(repo, variant, weights, dev)
    out = []
    for i, p in enumerate(paths):
        img = cv2.cvtColor(cv2.imread(str(p)), cv2.COLOR_BGR2RGB)[CROP[0]:CROP[1], CROP[2]:CROP[3]]
        w = img.shape[1] // 3
        tiles = []
        for k in range(3):
            t = cv2.resize(img[:, k * w:(k + 1) * w], TILE).astype(np.float32) / 255.0
            tiles.append(np.transpose((t - _IMAGENET_MEAN) / _IMAGENET_STD, (2, 0, 1)))
        x = torch.from_numpy(np.stack(tiles)).float().to(dev)
        with torch.no_grad():
            f = model.forward_features(x)
        cls = f["x_norm_clstoken"].cpu().numpy()
        pt = f["x_norm_patchtokens"].cpu().numpy()
        per_tile = np.concatenate([cls, pt.mean(1), pt.max(1)], axis=1)            # 3 x 2304
        out.append(np.concatenate([per_tile.max(0), per_tile.mean(0)]).astype(np.float32))
        if i % 50 == 0:
            print("embedded", i, "/", len(paths), flush=True)
    return np.vstack(out)


def lowo(X: np.ndarray, y: np.ndarray, groups: np.ndarray) -> np.ndarray:
    from sklearn.decomposition import PCA
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    p = np.full(len(y), np.nan)
    for g in np.unique(groups):
        tr, te = groups != g, groups == g
        if len(np.unique(y[tr])) < 2:
            continue
        m = make_pipeline(StandardScaler(), PCA(min(20, tr.sum() - 1), random_state=0),
                          LogisticRegression(class_weight="balanced", C=1.0, max_iter=2000))
        m.fit(X[tr], y[tr])
        p[te] = m.predict_proba(X[te])[:, 1]
    return p


def scores(y: np.ndarray, p: np.ndarray) -> dict:
    from sklearn.metrics import roc_auc_score
    ok = np.isfinite(p)
    y, p = y[ok], p[ok]
    pr = p >= 0.5
    tp, fp, fn, tn = (pr & y).sum(), (pr & ~y).sum(), (~pr & y).sum(), (~pr & ~y).sum()
    sens, spec = tp / max(tp + fn, 1), tn / max(tn + fp, 1)
    return {"auc": roc_auc_score(y, p) if len(np.unique(y)) == 2 else np.nan, "sens": sens, "spec": spec,
            "prec": tp / max(tp + fp, 1), "youden": sens + spec - 1, "tp": int(tp), "fn": int(fn), "fp": int(fp), "tn": int(tn)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--page", default=str(OUT / "usv_strip_review_20261009_1757"))
    ap.add_argument("--features", default=str(OUT / "usv_v2_sample/eval/usv_strip_features.csv"))
    ap.add_argument("--out", default=str(OUT / "usv_dino_presence"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    F = pd.read_csv(a.features)                                   # labelled strips + v1 / v2 features (usv_eval_v2.py)
    paths = [Path(pg) / "media" / f"{s}.png" for pg, s in zip(F.page if "page" in F else [a.page] * len(F), F.id)]
    cache = out / "embeddings.npz"
    if cache.exists() and list(np.load(cache, allow_pickle=True)["ids"]) == list(F.id):
        E = np.load(cache)["E"]
    else:
        E = embed(paths)
        np.savez(cache, E=E, ids=np.array(F.id))
    y = F.yes.to_numpy(bool)
    g = F.window.to_numpy()
    mic = (F.mic == "MIC02").to_numpy(float)[:, None]
    cnt = np.log1p(F[["v1_tonal_any", "v1_tonal20"]].to_numpy(float))
    rows, P = [], pd.DataFrame({"id": F.id, "mic": F.mic, "window": F.window, "yes": y})
    for name, X in (("dino", np.hstack([E, mic])), ("dino+v1counts", np.hstack([E, mic, cnt]))):
        p = lowo(X, y, g)
        P[f"p_{name}"] = p
        for m in ("both", "MIC01", "MIC02"):
            sel = np.ones(len(y), bool) if m == "both" else (F.mic == m).to_numpy()
            rows.append({"model": name, "fit": "pooled", "mic": m, **scores(y[sel], p[sel])})
        for m in ("MIC01", "MIC02"):                                 # per-mic fits
            sel = (F.mic == m).to_numpy()
            pm = lowo(X[sel], y[sel], g[sel])
            rows.append({"model": name, "fit": "per mic", "mic": m, **scores(y[sel], pm)})
    for m, feat in (("MIC01", "v1_tonal20"), ("MIC02", "v1_tonal_any")):     # v1 best (usv_eval_v2.py), for reference
        rows.append({"model": f"v1 {feat} (LOWO threshold)", "fit": "per mic", "mic": m})
    R = pd.DataFrame(rows)
    R.to_csv(out / "dino_presence_scores.csv", index=False)
    P.to_csv(out / "strip_p.csv", index=False)
    pd.set_option("display.width", 200)
    print(R.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
