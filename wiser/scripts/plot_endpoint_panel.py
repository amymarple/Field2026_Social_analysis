r"""
plot_endpoint_panel.py — inspection panel of route-unit START vs END points, per animal × per night.

A grid (rows = animals, cols = nights) of each animal's route-bout begin points (green o) and end
points (red x), with a faint chord per bout and the mapped ROI landmarks overlaid (house/food = blue,
refuge = purple, water = cyan, boundary = grey) so you can see where endpoints fall relative to
resources. WISER inch frame is UNVERIFIED -> this is a topological/relative inspection only (no
metric/directional claim). Reads the existing route_bouts.csv (no re-load).

    KMP_DUPLICATE_LIB_OK=TRUE C:/Users/Cornell/anaconda3/python.exe scripts/plot_endpoint_panel.py \
      [--bouts <route_bouts.csv>] [--out <png>]
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parent.parent
ROI_COLOR = {"refuge": "#8844cc", "water": "#22aabb", "house": "#3366cc"}


def _roi_class(name):
    if name.startswith(("house", "food")):
        return "house"
    if name.startswith("water"):
        return "water"
    return "refuge"   # refuge_* + tunnel


def _draw_rois(ax, rois, boundary):
    if boundary and "rect" in boundary:
        x0, y0, x1, y1 = boundary["rect"]
        ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, ec="0.7", lw=0.5, ls="--"))
    for r in rois:
        col = ROI_COLOR[_roi_class(r["name"])]
        if r.get("shape") == "circle":
            ax.add_patch(Circle((r["x"], r["y"]), r.get("radius_in", 11), fill=False, ec=col, lw=0.7, alpha=0.8))
        else:
            wd, ht = r.get("width_in", 24), r.get("height_in", 24)
            ax.add_patch(Rectangle((r["x"] - wd / 2, r["y"] - ht / 2), wd, ht, fill=False, ec=col, lw=0.7, alpha=0.8))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bouts", type=Path,
                    default=ROOT / "outputs/route_motifs_2026-06-28_to_2026-07-10/route_bouts.csv")
    ap.add_argument("--rois", type=Path, default=ROOT / "configs/wiser_rois.json")
    ap.add_argument("--ids", type=Path, default=ROOT / "configs/rat_identities.csv")
    ap.add_argument("--out", type=Path,
                    default=ROOT / "outputs/route_vocabulary_validation_2026-06-28_to_2026-07-10/endpoints/endpoints_by_animal_night.png")
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    cfg = json.load(open(args.rois))
    rois, boundary = cfg["rois"], cfg.get("boundary")
    ids = pd.read_csv(args.ids)
    namemap = dict(zip(ids["shortid"].astype(str), ids["name"]))

    df = pd.read_csv(args.bouts)
    df["shortid"] = df["shortid"].astype(str)
    animals = sorted(df["shortid"].unique(), key=lambda s: namemap.get(s, s))
    nights = sorted(df["night"].unique())

    allx = np.concatenate([df["x0"], df["x1"]]); ally = np.concatenate([df["y0"], df["y1"]])
    xlim = (allx.min() - 25, allx.max() + 25); ylim = (ally.min() - 25, ally.max() + 25)

    nr, nc = len(animals), len(nights)
    fig, axes = plt.subplots(nr, nc, figsize=(nc * 1.6, nr * 1.65), squeeze=False)
    for i, a in enumerate(animals):
        for j, n in enumerate(nights):
            ax = axes[i][j]
            _draw_rois(ax, rois, boundary)
            sub = df[(df["shortid"] == a) & (df["night"] == n)]
            for _, b in sub.iterrows():
                ax.plot([b["x0"], b["x1"]], [b["y0"], b["y1"]], "-", color="0.6", lw=0.3, alpha=0.45)
            ax.scatter(sub["x0"], sub["y0"], s=9, c="#1a9850", marker="o", alpha=0.85, edgecolors="none")
            ax.scatter(sub["x1"], sub["y1"], s=11, c="#d73027", marker="x", alpha=0.85, linewidths=0.7)
            ax.set_xlim(*xlim); ax.set_ylim(*ylim); ax.set_aspect("equal")
            ax.set_xticks([]); ax.set_yticks([])
            ax.text(0.03, 0.97, f"n={len(sub)}", transform=ax.transAxes, fontsize=5, va="top", color="0.4")
            if i == 0:
                ax.set_title(n[5:], fontsize=8)
            if j == 0:
                ax.set_ylabel(namemap.get(a, a), fontsize=9, rotation=90)
    handles = [Line2D([], [], marker="o", color="#1a9850", ls="", ms=5, label="START"),
               Line2D([], [], marker="x", color="#d73027", ls="", ms=5, label="END"),
               Line2D([], [], color="0.6", lw=1, label="bout chord"),
               Line2D([], [], marker="s", mfc="none", mec="#3366cc", ls="", ms=6, label="house/food"),
               Line2D([], [], marker="o", mfc="none", mec="#8844cc", ls="", ms=6, label="refuge/tunnel"),
               Line2D([], [], marker="o", mfc="none", mec="#22aabb", ls="", ms=6, label="water")]
    fig.legend(handles=handles, loc="lower center", ncol=6, fontsize=8, frameon=False)
    fig.suptitle("Route-bout START vs END points — per animal (rows) × night (cols). "
                 "WISER inch frame, UNVERIFIED (topological/relative only; night 21:00–04:00).", fontsize=11)
    fig.tight_layout(rect=(0, 0.03, 1, 0.98))
    fig.savefig(args.out, dpi=140); plt.close(fig)
    print(f"DONE -> {args.out}  ({nr} animals × {nc} nights, {len(df)} bouts)")


if __name__ == "__main__":
    main()
