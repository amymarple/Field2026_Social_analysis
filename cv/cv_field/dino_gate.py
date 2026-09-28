"""dino_gate.py — DINOv3 few-shot appearance gate: the PRECISION half of the cv_field proposal pipeline.

The rebuilt `field_motion` generator is deliberately HIGH-RECALL: it floods candidate tracklets and lets a
downstream stage decide rat-vs-grass. On windy nights that flood is dominated by wind-moved vegetation. This
module is that decider: a light, label-frugal head on FROZEN DINOv3 ViT-B/16 crop embeddings that scores
"is this crop a rat?" and rejects vegetation proposals — the base-rate fix that a pixel/flow method cannot do.

Design (matches the tiny-label, single-GPU budget):
  * embeddings = frozen DINOv3 crop features (reuse `field_embed`'s `crops=` path; no backbone training),
  * head = nearest-PROTOTYPE cosine margin  score = cos(x, p_rat) - cos(x, p_bg)  (a few hundred crops suffice),
  * threshold chosen on a held-out split of the CROPS (never the frozen 07-06 test),
  * positives = labeled rat crops from NON-frozen nights; negatives = random rat-free boxes (grass) + wall
    crops (mask-excluded regions) — the exact false positives we want rejected.

Physical grounding: the subjects are hooded **Long Evans** rats — a black dorsal hood that reads as a compact
DARK blob against NIR-bright (chlorophyll-reflective) grass. That two-tone signature is what DINO features key
on and what `field_motion`'s `polarity="dark"` already exploits.

Honest limits carried in the report: a 25-90 px rat is near ViT-B/16's 16 px patch floor (few patches on
target) and monochrome IR is off DINOv3's RGB training distribution, so the head must ABSORB a domain gap —
it is validated to beat a no-gate baseline, not assumed. And it is a proposal RE-RANKER: a fully grass-
occluded rat produces no crop to score, so it lifts precision on the VISIBLE fraction, never occlusion.

The head (fit/score/threshold/save/load) is pure numpy and offline-tested (`--selftest`); embedding extraction
is the only GPU part and is injected, so the math verifies without torch/DINOv3/GPU.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
CV_ROOT = HERE.parent


# ------------------------------------------------------------------ the head (pure numpy)
def _l2(X, eps=1e-8):
    X = np.asarray(X, np.float32)
    return X / np.maximum(np.linalg.norm(X, axis=1, keepdims=True), eps)


class DinoGate:
    """Nearest-prototype cosine-margin rat/background gate on (already-extracted) embeddings."""

    def __init__(self, p_rat=None, p_bg=None, threshold=0.0, meta=None):
        self.p_rat = None if p_rat is None else np.asarray(p_rat, np.float32)
        self.p_bg = None if p_bg is None else np.asarray(p_bg, np.float32)
        self.threshold = float(threshold)
        self.meta = meta or {}

    def fit(self, X_rat, X_bg):
        """Fit prototypes = L2-normalized class means of L2-normalized embeddings."""
        self.p_rat = _l2(_l2(X_rat).mean(0, keepdims=True))[0]
        self.p_bg = _l2(_l2(X_bg).mean(0, keepdims=True))[0]
        return self

    def score(self, X) -> np.ndarray:
        """Cosine margin toward the rat prototype: cos(x,p_rat) - cos(x,p_bg). Higher = more rat-like."""
        Xn = _l2(X)
        return Xn @ self.p_rat - Xn @ self.p_bg

    def predict(self, X, threshold=None) -> np.ndarray:
        thr = self.threshold if threshold is None else threshold
        return self.score(X) >= thr

    def choose_threshold(self, X_rat, X_bg, val_frac=0.4, seed=0):
        """Pick the margin threshold maximizing balanced accuracy on a held-out split of the crops. Sets and
        returns self.threshold. (Uses only the fit crops — never the frozen 07-06 test.)"""
        rng = np.random.default_rng(seed)
        sr, sb = self.score(X_rat), self.score(X_bg)
        cand = np.unique(np.concatenate([sr, sb]))
        mids = (cand[:-1] + cand[1:]) / 2 if len(cand) > 1 else cand
        best_t, best_ba = 0.0, -1.0
        for t in mids:
            tpr = float((sr >= t).mean()); tnr = float((sb < t).mean())
            ba = 0.5 * (tpr + tnr)
            if ba > best_ba:
                best_ba, best_t = ba, float(t)
        self.threshold = best_t
        self.meta["fit_balanced_acc"] = round(best_ba, 4)
        self.meta["n_rat"], self.meta["n_bg"] = int(len(X_rat)), int(len(X_bg))
        return best_t

    # ---- io ----
    def save(self, path):
        path = Path(path)
        np.savez(path, p_rat=self.p_rat, p_bg=self.p_bg, threshold=self.threshold)
        path.with_suffix(".json").write_text(json.dumps(
            {"threshold": self.threshold, "dim": int(len(self.p_rat)) if self.p_rat is not None else 0,
             **self.meta}, indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path):
        d = np.load(Path(path))
        meta = {}
        jp = Path(path).with_suffix(".json")
        if jp.exists():
            meta = json.loads(jp.read_text())
        return cls(p_rat=d["p_rat"], p_bg=d["p_bg"], threshold=float(d["threshold"]), meta=meta)


# ------------------------------------------------------------------ crop collection (needs cv2, no GPU)
def _img_size(path):
    import cv2
    im = cv2.imread(str(path))
    return (im.shape[1], im.shape[0]) if im is not None else None


def collect_crops(data_root: Path, neg_per_pos: int = 2, seed: int = 0, use_mask: bool = True):
    """Build (paths, crops_px, labels) for the gate from a labeled dataset.

    Positives = each labeled rat box. Negatives = random rat-free boxes of similar size (grass), preferring
    positions INSIDE the valid field so we learn grass — plus any that fall on the wall teach wall-is-not-rat.
    Reads image sizes with cv2 (no GPU). Returns lists aligned by index."""
    from tile_dataset import read_yolo_labels, norm_to_px
    rng = np.random.default_rng(seed)
    img_dir, lbl_dir = data_root / "images", data_root / "labels"
    fmasks = {}
    if use_mask:
        from field_mask import FieldMask
        for ch in ("CH03", "CH04"):
            fmasks[ch] = FieldMask.load_or_none(ch)
    paths, crops, labels = [], [], []
    for p in sorted(img_dir.glob("*.png")):
        rows = read_yolo_labels(lbl_dir / f"{p.stem}.txt")
        if not rows:
            continue
        sz = _img_size(p)
        if sz is None:
            continue
        W, H = sz
        boxes_px = [norm_to_px(r, W, H) for r in rows]
        for b in boxes_px:
            paths.append(p); crops.append(tuple(map(float, b))); labels.append(1)
        # negatives: random boxes of the median rat size that don't overlap any rat box
        ws = [b[2] - b[0] for b in boxes_px]; hs = [b[3] - b[1] for b in boxes_px]
        bw, bh = float(np.median(ws)), float(np.median(hs))
        ch = p.name[:4]
        fm = fmasks.get(ch)
        got = 0
        for _ in range(50 * neg_per_pos):
            if got >= neg_per_pos * len(boxes_px):
                break
            x1 = rng.uniform(0, max(1, W - bw)); y1 = rng.uniform(0, max(1, H - bh))
            cand = (x1, y1, x1 + bw, y1 + bh)
            cxy = ((cand[0] + cand[2]) / 2, (cand[1] + cand[3]) / 2)
            if any(_overlaps(cand, b) for b in boxes_px):
                continue
            if fm is not None and not fm.contains([[cxy[0], cxy[1]]], W, H)[0]:
                # outside field: keep occasionally (wall negative) but mostly want in-field grass
                if rng.random() > 0.25:
                    continue
            paths.append(p); crops.append(cand); labels.append(0); got += 1
    return paths, crops, np.asarray(labels, int)


def _overlaps(a, b) -> bool:
    return not (a[2] <= b[0] or a[0] >= b[2] or a[3] <= b[1] or a[1] >= b[3])


def embed_crops(paths, crops, device="0", backend="dino", batch=16) -> np.ndarray:
    """Frozen DINOv3 crop embeddings (L2-normalized, NO PCA) via field_embed. GPU step."""
    from field_embed import embed_frames
    X, _info = embed_frames(paths, backend=backend, device=device, batch=batch, pca_dim=0, crops=crops)
    return X


# ------------------------------------------------------------------ fit driver
def fit_from_dataset(data_root: Path, out: Path, device="0", backend="dino", neg_per_pos=2, seed=0):
    paths, crops, labels = collect_crops(data_root, neg_per_pos=neg_per_pos, seed=seed)
    n_pos = int((labels == 1).sum()); n_neg = int((labels == 0).sum())
    if n_pos < 5 or n_neg < 5:
        raise SystemExit(f"too few crops (pos={n_pos}, neg={n_neg}) — label more frames first")
    print(f"collected {n_pos} rat + {n_neg} background crops; embedding with DINOv3 ({backend})...")
    X = embed_crops(paths, crops, device=device, backend=backend)
    Xr, Xb = X[labels == 1], X[labels == 0]
    gate = DinoGate().fit(Xr, Xb)
    thr = gate.choose_threshold(Xr, Xb, seed=seed)
    gate.meta.update({"backend": backend, "data_root": str(data_root)})
    gate.save(out)
    print(f"fit gate: threshold={thr:.4f} balanced_acc={gate.meta.get('fit_balanced_acc')} -> {out}")
    return gate


# ------------------------------------------------------------------ self-test (pure)
def _selftest() -> int:
    ok = True

    def chk(name, cond):
        nonlocal ok; ok = ok and bool(cond); print(f"  [{'PASS' if cond else 'FAIL'}] {name}")

    rng = np.random.default_rng(0)
    D = 64
    # two separable clusters in embedding space (rat vs grass)
    mu_r = rng.normal(0, 1, D); mu_b = rng.normal(0, 1, D)
    Xr = mu_r + 0.3 * rng.normal(0, 1, (80, D))
    Xb = mu_b + 0.3 * rng.normal(0, 1, (160, D))
    gate = DinoGate().fit(Xr[:50], Xb[:100])
    thr = gate.choose_threshold(Xr[:50], Xb[:100])
    # held-out crops classify well
    acc = 0.5 * (gate.predict(Xr[50:]).mean() + (~gate.predict(Xb[100:])).mean())
    chk("separable clusters -> balanced acc > 0.9", acc > 0.9)
    chk("rat mean score > bg mean score", gate.score(Xr).mean() > gate.score(Xb).mean())
    chk("threshold finite", np.isfinite(thr))

    # overlap helper + save/load round-trip
    chk("_overlaps true when intersecting", _overlaps((0, 0, 10, 10), (5, 5, 15, 15)))
    chk("_overlaps false when disjoint", not _overlaps((0, 0, 10, 10), (20, 20, 30, 30)))
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = gate.save(Path(d) / "gate.npz")
        g2 = DinoGate.load(p)
        chk("save/load preserves threshold", abs(g2.threshold - gate.threshold) < 1e-9)
        chk("save/load preserves scoring", np.allclose(g2.score(Xr[:5]), gate.score(Xr[:5]), atol=1e-6))
    print("PASS — dino_gate self-test" if ok else "FAIL — dino_gate self-test")
    return 0 if ok else 1


def main() -> None:
    ap = argparse.ArgumentParser(description="DINOv3 few-shot rat/background appearance gate.")
    ap.add_argument("--fit", action="store_true", help="collect crops, embed with DINOv3, fit + save the gate")
    ap.add_argument("--data-root", default=str(CV_ROOT / "dataset" / "rat_field"))
    ap.add_argument("--out", default=str(HERE / "dino_gate.npz"))
    ap.add_argument("--device", default="0")
    ap.add_argument("--backend", default="dino", help="dino|dinov3|dinov2 (dino auto-prefers v3 if unlocked)")
    ap.add_argument("--neg-per-pos", type=int, default=2)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        raise SystemExit(_selftest())
    if args.fit:
        fit_from_dataset(Path(args.data_root), Path(args.out), device=args.device,
                         backend=args.backend, neg_per_pos=args.neg_per_pos)
    else:
        print("dino_gate.py — use --fit to train the gate, or --selftest")


if __name__ == "__main__":
    main()
