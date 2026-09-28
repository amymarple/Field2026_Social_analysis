"""field_embed.py — frame -> embedding for the cv_field active-learning selector.

Turns a list of harvested frames into an L2-normalized, PCA-reduced embedding matrix ``X (N, d')`` that the
selector clusters and space-fills. Two interchangeable backends behind one interface so the SAME selector
code runs on the GPU in production and numpy-only in the offline self-test:

  * ``"dino"`` — DINO self-supervised ViT CLS-token features via ``torch.hub``. This is the intended
    *unsupervised representation* for cold-start selection: DINO is trained with no labels, so at round 0
    (no rat detector yet) its features are far more semantic than a COCO detection backbone. **Default
    backend.** ``dino`` auto-prefers **DINOv3** (facebookresearch/dinov3, /16) when a license-gated
    checkpoint is present (``$DINOV3_WEIGHTS`` or the hub cache), else falls back to **DINOv2**
    (facebookresearch/dinov2, /14, free ~85 MB auto-download). Force one with ``"dinov2"`` / ``"dinov3"``.
  * ``"yolo"`` — YOLO11 backbone features via ultralytics ``model.embed(...)`` (no new heavy dep; round 0
    uses the pretrained COCO ``yolo11s.pt``, later rounds the seed rat detector's backbone).
  * ``"gray"`` — the cheap ``gray64`` thumbnail (reused idea from ``scan_for_rats._gray64``) flattened to
    4096-d. CPU-only, no model download; this is what makes the selector synthetically testable.

``backend="auto"`` picks ``yolo`` when torch+ultralytics import, else ``gray``. Everything heavy (cv2, torch,
ultralytics) is imported LAZILY inside the backend functions, so this module imports with only numpy — the
offline self-test drives the pure-numpy path (``embed_matrix``) without any of them installed.

Annotation/provenance only: nothing here changes a detector output. ``embedding_fingerprint`` feeds
``measurement_context.build_context(..., embedding=...)`` so every selection round is auditable.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

GRAY_TAG = "gray64_pca/1"
GRAY_RAW_DIM = 64 * 64


# ------------------------------------------------------------------ backend choice
def available_backend() -> str:
    """"yolo" if torch + ultralytics import, else "gray" (never raises)."""
    try:
        import torch  # noqa: F401
        import ultralytics  # noqa: F401
        return "yolo"
    except Exception:  # noqa: BLE001
        return "gray"


def _resolve_backend(backend: str) -> str:
    return available_backend() if backend == "auto" else backend


# ------------------------------------------------------------------ numpy PCA + L2 (pure)
def l2_normalize(X, eps: float = 1e-8) -> np.ndarray:
    X = np.asarray(X, dtype=np.float32)
    n = np.linalg.norm(X, axis=1, keepdims=True)
    return X / np.maximum(n, eps)


def fit_pca(X, dim: int):
    """PCA basis via economy SVD (numpy only). Returns (basis (dim, D), mean (D,)), both float32."""
    X = np.asarray(X, dtype=np.float64)
    mean = X.mean(axis=0)
    _, _, Vt = np.linalg.svd(X - mean, full_matrices=False)
    dim = int(min(dim, Vt.shape[0]))
    return Vt[:dim].astype(np.float32), mean.astype(np.float32)


def apply_pca(X, basis, mean) -> np.ndarray:
    X = np.asarray(X, dtype=np.float32)
    return (X - np.asarray(mean, np.float32)) @ np.asarray(basis, np.float32).T


def embed_matrix(X_raw, pca_dim: int = 50, pca_basis=None, pca_mean=None):
    """PCA(optional) + L2 on an already-extracted raw feature matrix. Pure numpy — no cv2/torch.

    Fit PCA on the fly when no basis is given (and the raw dim exceeds ``pca_dim``); otherwise apply the
    supplied basis so multiple rounds share one projection. Returns ``(X (N, d'), info)``."""
    X_raw = np.asarray(X_raw, dtype=np.float32)
    if pca_dim and X_raw.shape[1] > pca_dim:
        if pca_basis is None:
            pca_basis, pca_mean = fit_pca(X_raw, pca_dim)
        Xr = apply_pca(X_raw, pca_basis, pca_mean)
    else:
        Xr = X_raw
    X = l2_normalize(Xr)
    return X, {"pca_basis": pca_basis, "pca_mean": pca_mean, "dim": int(X.shape[1])}


# ------------------------------------------------------------------ backends (lazy heavy imports)
def _read_bgr(path, crop=None):
    """Read a frame (BGR); optionally crop to (x1,y1,x2,y2) px. A degenerate/empty crop falls back to the
    full frame so the embedding never sees a 0-sized image."""
    import cv2
    img = cv2.imread(str(path))
    if img is None:
        raise FileNotFoundError(f"could not read image {path}")
    if crop is not None:
        x1, y1, x2, y2 = (int(v) for v in crop)
        if x2 - x1 >= 2 and y2 - y1 >= 2:
            sub = img[y1:y2, x1:x2]
            if sub.size:
                return sub
    return img


def _gray64_vecs(paths, crops=None) -> np.ndarray:
    """Read each frame (optionally cropped) -> 64x64 gray -> flattened 4096-d row. Needs cv2 (lazy)."""
    import cv2
    vecs = []
    for i, p in enumerate(paths):
        img = _read_bgr(p, crops[i] if crops else None)
        g = cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (64, 64)).astype(np.float32)
        vecs.append(g.ravel())
    return np.asarray(vecs, dtype=np.float32)


_DINO_CACHE: dict = {}
_IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], np.float32)
_IMAGENET_STD = np.array([0.229, 0.224, 0.225], np.float32)
# patch size differs: DINOv2 = /14, DINOv3 = /16. Resize each frame to a multiple of it.
_DINO_SPEC = {
    "dinov2": {"repo": "facebookresearch/dinov2", "variant": "dinov2_vits14", "patch": 14},
    "dinov3": {"repo": "facebookresearch/dinov3", "variant": "dinov3_vits16", "patch": 16},
}


def find_dinov3_weights():
    """Local DINOv3 checkpoint IF the user has unlocked it (license-gated), else None.

    Looks at ``$DINOV3_WEIGHTS`` then the torch-hub checkpoints cache for a real ``dinov3_*pretrain*.pth``
    (skips <1 MB stubs a failed 403 download may leave). This is what lets ``backend='dino'`` silently
    upgrade to v3 the moment a checkpoint appears — no code change."""
    import glob
    import os
    env = os.environ.get("DINOV3_WEIGHTS")
    if env and Path(env).is_file() and Path(env).stat().st_size > 1_000_000:
        return env
    cache = Path.home() / ".cache" / "torch" / "hub" / "checkpoints"
    hits = [h for h in glob.glob(str(cache / "dinov3_*pretrain*.pth")) if Path(h).stat().st_size > 1_000_000]
    return hits[0] if hits else None


def dinov3_entrypoint(weights_path) -> str:
    """torch.hub entrypoint for a DINOv3 checkpoint, inferred from its filename (or ``$DINOV3_VARIANT``).

    Meta names the files ``<entrypoint>_pretrain_<dataset>-<hash>.pth`` (e.g.
    ``dinov3_vitb16_pretrain_lvd1689m-73cec8be.pth`` -> ``dinov3_vitb16``), so the entrypoint is exactly the
    prefix before ``_pretrain`` — which means ANY variant you download (vits16/vitb16/vitl16/vith16plus/
    vit7b16/convnext_*) just works, no config."""
    import os
    env = os.environ.get("DINOV3_VARIANT")
    if env:
        return env
    name = Path(weights_path).name
    return name.split("_pretrain")[0] if "_pretrain" in name else _DINO_SPEC["dinov3"]["variant"]


def resolve_dino_source(backend: str):
    """Map a dino backend request -> (family, repo, variant, patch, weights).

    ``dino`` = best available (v3 if a checkpoint is unlocked, else v2). ``dinov2`` / ``dinov3`` force one;
    ``dinov3`` without a checkpoint raises with the unlock instructions."""
    v3 = find_dinov3_weights()
    if backend == "dinov3" or (backend == "dino" and v3):
        if not v3:
            raise RuntimeError(
                "dinov3 requested but no checkpoint found (weights are license-gated, HTTP 403 auto-download). "
                "Accept Meta's DINOv3 license, download a dinov3_vit*16 *_pretrain_*.pth, and set "
                "DINOV3_WEIGHTS=<path>. Use backend='dino' to auto-fall back to dinov2 until then.")
        s = _DINO_SPEC["dinov3"]
        return "dinov3", s["repo"], dinov3_entrypoint(v3), s["patch"], v3
    s = _DINO_SPEC["dinov2"]
    return "dinov2", s["repo"], s["variant"], s["patch"], None


def _load_dino(repo: str, variant: str, weights, dev: str):
    """Load + cache a DINO backbone from torch.hub. v2 auto-downloads (~85 MB); v3 needs a local ``weights``."""
    import torch
    key = (repo, variant, weights, dev)
    if key not in _DINO_CACHE:
        kw = {"weights": weights} if weights else {}
        model = torch.hub.load(repo, variant, verbose=False, **kw)
        _DINO_CACHE[key] = model.eval().to(dev)
    return _DINO_CACHE[key]


def _dino_vecs(paths, device: str = "0", batch: int = 16, backend: str = "dino",
               imgsz: int = 224, crops=None) -> np.ndarray:
    """DINO self-supervised ViT CLS-token embeddings — the unsupervised representation for selection.

    ``backend`` selects the family (``dino`` auto-prefers v3 when unlocked). ``crops`` (optional, aligned with
    ``paths``) crops each frame to a motion box before resize, so the embedding describes the rat region, not
    the static background. Frames are ImageNet-normalized RGB resized to a multiple of the model's patch size;
    returns ``(N, embed_dim)`` float32 (384 for ViT-S). Batched to bound VRAM."""
    import cv2
    import torch
    _, repo, variant, patch, weights = resolve_dino_source(backend)
    dev = "cuda" if (str(device) not in ("cpu", "None") and torch.cuda.is_available()) else "cpu"
    model = _load_dino(repo, variant, weights, dev)
    s = max((int(imgsz) // patch) * patch, patch)
    out = []
    for i in range(0, len(paths), batch):
        tens = []
        for j, p in enumerate(paths[i:i + batch]):
            img = _read_bgr(p, crops[i + j] if crops else None)
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            img = cv2.resize(img, (s, s)).astype(np.float32) / 255.0
            img = (img - _IMAGENET_MEAN) / _IMAGENET_STD
            tens.append(np.transpose(img, (2, 0, 1)))
        x = torch.from_numpy(np.stack(tens)).float().to(dev)
        with torch.no_grad():
            f = model(x)                       # (B, embed_dim) CLS token
        out.append(f.detach().cpu().numpy().astype(np.float32))
    return np.concatenate(out, axis=0)


def _yolo_vecs(paths, weights=None, device="0", batch: int = 16) -> np.ndarray:
    """YOLO11 backbone embeddings via ultralytics .embed(). Needs torch + ultralytics (lazy).

    .embed() returns one feature tensor per image (CUDA tensors when device is a GPU), so move each to
    CPU/numpy before stacking."""
    from ultralytics import YOLO
    model = YOLO(weights or "yolo11s.pt")
    embs = model.embed([str(p) for p in paths], device=device, verbose=False)
    out = []
    for e in embs:
        if hasattr(e, "detach"):        # torch tensor (possibly on GPU) -> host numpy
            e = e.detach().cpu().numpy()
        out.append(np.asarray(e, dtype=np.float32).ravel())
    return np.asarray(out, dtype=np.float32)


def embed_frames(paths, backend: str = "auto", weights=None, device: str = "0", batch: int = 16,
                 pca_dim: int = 50, pca_basis=None, pca_mean=None, crops=None):
    """Embed a list of frame paths -> (X (N, d') L2-normalized, info). Backend per ``_resolve_backend``.

    ``crops`` (optional): per-frame (x1,y1,x2,y2) px box to embed instead of the whole frame — used by the
    motion-aware selector so diversity tracks rat content. Supported by the dino/gray backends (yolo's
    ``.embed`` takes paths, not arrays, so crops+yolo is rejected)."""
    backend = _resolve_backend(backend)
    if crops is not None and len(crops) != len(paths):
        raise ValueError("crops must align with paths")
    if backend in ("dino", "dinov2", "dinov3"):
        raw = _dino_vecs(paths, device=device, batch=batch, backend=backend, crops=crops)
    elif backend == "yolo":
        if crops is not None:
            raise ValueError("crops are not supported with the yolo backend; use dino")
        raw = _yolo_vecs(paths, weights=weights, device=device, batch=batch)
    elif backend == "gray":
        raw = _gray64_vecs(paths, crops=crops)
    else:
        raise ValueError(f"unknown embed backend {backend!r} (expected dino|dinov2|dinov3|yolo|gray|auto)")
    X, info = embed_matrix(raw, pca_dim=pca_dim, pca_basis=pca_basis, pca_mean=pca_mean)
    info["backend"] = backend
    info["raw_dim"] = int(raw.shape[1])
    return X, info


# ------------------------------------------------------------------ provenance
def _file_fp(path):
    p = Path(path)
    if not p.exists():
        return {"path": str(p), "status": "missing"}
    data = p.read_bytes()
    return {"path": str(p), "sha256_16": hashlib.sha256(data).hexdigest()[:16], "size": len(data)}


def embedding_fingerprint(backend: str = "auto", weights=None, pca_dim: int = 50) -> dict:
    """Small dict identifying the embedding model + reduction, for measurement_context's detector block."""
    backend = _resolve_backend(backend)
    if backend in ("dino", "dinov2", "dinov3"):
        try:
            family, repo, variant, _patch, weights = resolve_dino_source(backend)
            return {"backend": "dino", "family": family, "variant": variant, "repo": repo,
                    "self_supervised": True, "pca_dim": pca_dim,
                    "weights": _file_fp(weights) if weights else "auto-download (dinov2, license-free)"}
        except Exception as e:  # noqa: BLE001 — dinov3 requested but not unlocked
            return {"backend": backend, "unavailable": str(e)[:200], "pca_dim": pca_dim}
    if backend == "yolo":
        return {"backend": "yolo", "model": "yolo11 backbone (ultralytics .embed)",
                "weights": _file_fp(weights) if weights else "yolo11s.pt (pretrained COCO)",
                "pca_dim": pca_dim}
    return {"backend": "gray64_pca", "tag": GRAY_TAG, "raw_dim": GRAY_RAW_DIM, "pca_dim": pca_dim}
