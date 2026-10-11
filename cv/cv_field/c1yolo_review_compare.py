r"""c1yolo_review_compare.py — the two pre-registered "after the user's verdicts" comparisons of the CH01 YOLO review.

Input (read-only): the user's review export (cv/configs/c1yolo_review_2026c/*.json, from the review GUI) — saved verdicts
only (`verdict` = the last saved verdict; unsaved drafts are not verdicts).
  1. Phase-0 part B (plan implementation_plan/2026-10-05-wiser-assisted-yolo-p0.md): the sealed wiser_spots.csv of run
     cv_field_wiser_assist_p0_20261005_2211 against the user's fixed-spot verdicts — per spot the plan's quantities as
     written (minutes on / off, with a tagged animal within 14 / 30 in, with a still animal within 14 in, Spearman rho).
  2. CH01 occlusion v2 (plan implementation_plan/2026-10-06-ch01-occlusion-geometry.md): the sealed episodes.csv of run
     cv_field_ch01_occlusion_20261006_1555 against the user's episode verdicts (GUI items ep<id> -> episode_id).
     Mapping fixed in this script before tabulating: user occluded = "occluded", not = visible_missed + box_present
     (unsure excluded); geometry occluded = class hidden or partly, not = clear; ambiguous excluded from the primary
     Cohen's kappa, with two bracketing variants (ambiguous = occluded / = not). Occluder kinds: geometry house_1 /
     house_2 -> house, pole_* -> pole, none -> none; user house / pole / grass / other.
  3. The label-loop rule (plan implementation_plan/2026-10-06-wiser-label-loop.md, B4): p = share visible_missed among the
     judged episodes (unsure excluded); p >= 0.5 -> 60, 0.25 <= p < 0.5 -> 40, p < 0.25 -> 20 visible-suspected-miss frames.

Usage: python cv/cv_field/c1yolo_review_compare.py --run [--export <json>] [--out <dir>]
       python cv/cv_field/c1yolo_review_compare.py --selftest
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for _p in (str(HERE), str(HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

OUT_ROOT = Path(os.environ.get("FIELD2026_ANALYSIS_OUT_ROOT", "D:/Field2026_analysis_out"))
EXPORT = REPO / "cv" / "configs" / "c1yolo_review_2026c" / "cv-configs-c1yolo_review_2026c__review_anon_20261007_1402.json"
P0_RUN = OUT_ROOT / "2026c" / "cv_field_wiser_assist_p0_20261005_2211"
OCC_RUN = OUT_ROOT / "2026c" / "cv_field_ch01_occlusion_20261006_1555"
NAME = "cv_field_c1yolo_review_compare"
GEO_CLASSES = ("hidden", "partly", "clear", "ambiguous")
USER_V = ("visible_missed", "occluded", "box_present", "not_there_wiser_wrong", "unsure")


def sha256(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def cohen_kappa(a: list, b: list) -> float:
    """kappa = (p_o - p_e) / (1 - p_e) for two raters over the same items (binary or categorical)."""
    a, b = np.asarray(a), np.asarray(b)
    if len(a) == 0:
        return float("nan")
    cats = sorted(set(a) | set(b))
    po = float(np.mean(a == b))
    pe = float(sum(np.mean(a == c) * np.mean(b == c) for c in cats))
    return float("nan") if pe >= 1 else (po - pe) / (1 - pe)


def geo_kind(occ: str) -> str:
    occ = str(occ)
    return "house" if occ.startswith("house") else "pole" if occ.startswith("pole") else "none"


def load_export(p: Path) -> tuple[dict, pd.DataFrame]:
    o = json.loads(Path(p).read_text(encoding="utf-8"))
    return o, pd.DataFrame(o["rows"])


def part_b(rows: pd.DataFrame, ws: pd.DataFrame) -> pd.DataFrame:
    """The plan's per-spot quantities next to the user's verdict (no new criterion)."""
    sp = ws[ws["level"] == "spot"].copy()
    user = rows[rows["step"] == 1].set_index("item_id")
    out = []
    for r in sp.itertuples():
        u = user.loc[f"spot_{int(r.spot_id)}"] if f"spot_{int(r.spot_id)}" in user.index else None
        out.append({"spot_id": int(r.spot_id), "user_verdict": "" if u is None else u["verdict"], "user_notes": "" if u is None else u["notes"],
                    "pano_centre": f"{r.pano_cx:.0f}, {r.pano_cy:.0f}", "paddock_in": f"{r.paddock_x_in:.1f}, {r.paddock_y_in:.1f}",
                    "in_support": bool(r.in_support), "minutes_on": int(r.n_min_on), "on_within14": r.n_on_within14,
                    "on_within30": r.n_on_within30, "on_still_within14": r.n_on_still_within14, "minutes_off": int(r.n_min_off),
                    "off_within14": r.n_off_within14, "off_within30": r.n_off_within30, "off_still_within14": r.n_off_still_within14,
                    "spearman_rho": r.spearman_rho_occ_vs_within14, "spearman_p": r.spearman_p})
    return pd.DataFrame(out)


def part_c(rows: pd.DataFrame, ep: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    s2 = rows[(rows["step"] == 2) & (rows["verdict"].astype(str) != "")].copy()
    s2["episode_id"] = s2["episode_id"].astype(int)
    m = s2.merge(ep, on="episode_id", how="left", suffixes=("", "_geo"))
    m["geo_kind"] = m["occluder"].map(geo_kind)
    m["user_occ"] = m["verdict"] == "occluded"
    judged = m[m["verdict"] != "unsure"]
    res = {"n_judged": int(len(judged)), "n_unmapped": int(m["class"].isna().sum()),
           "confusion": pd.crosstab(judged["verdict"], judged["class"]).reindex(columns=list(GEO_CLASSES), fill_value=0).to_dict("index")}
    kap = {}
    for name, amb in (("primary (ambiguous excluded)", None), ("ambiguous = occluded", True), ("ambiguous = not occluded", False)):
        d = judged if amb is not None else judged[judged["class"] != "ambiguous"]
        g = d["class"].isin(["hidden", "partly"]) | ((d["class"] == "ambiguous") & bool(amb))
        kap[name] = {"n": int(len(d)), "agreement": float(np.mean(g.values == d["user_occ"].values)) if len(d) else float("nan"),
                     "kappa": cohen_kappa(list(d["user_occ"]), list(g)),
                     "table": {"user_occ & geo_occ": int((d["user_occ"] & g).sum()), "user_occ & geo_not": int((d["user_occ"] & ~g).sum()),
                               "user_not & geo_occ": int((~d["user_occ"] & g).sum()), "user_not & geo_not": int((~d["user_occ"] & ~g).sum())}}
    res["kappa"] = kap
    occ = judged[judged["user_occ"]]
    res["occluder"] = pd.crosstab(occ["occluder_kind"], occ["geo_kind"]).to_dict("index")
    res["occluder_agree"] = {"n": int(len(occ)), "same_kind": int((occ["occluder_kind"] == occ["geo_kind"]).sum())}
    res["by_user_kind"] = {k: {"n": int(len(g)), "geo_class": g["class"].value_counts().to_dict(), "geo_kind": g["geo_kind"].value_counts().to_dict()}
                           for k, g in occ.groupby("occluder_kind")}
    return m, res


def label_loop_p(rows: pd.DataFrame) -> dict:
    s2 = rows[(rows["step"] == 2) & (rows["verdict"].astype(str) != "")]
    j = s2[s2["verdict"] != "unsure"]
    p = float((j["verdict"] == "visible_missed").mean()) if len(j) else float("nan")
    q = 60 if p >= 0.5 else 40 if p >= 0.25 else 20
    return {"n_judged_excl_unsure": int(len(j)), "n_visible_missed": int((j["verdict"] == "visible_missed").sum()), "p": p,
            "visible_suspected_miss_quota_round2": q, "to_wiser_strata": 60 - q}


def run(export: Path, out: Path | None) -> int:
    if out is None:
        import output_paths as op
        out = op.run_dir(NAME, "2026c", make_figures=False)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    o, rows = load_export(export)
    s2 = rows[rows["step"] == 2]
    info = {"export": export.as_posix(), "export_sha256": sha256(export), "exported_local": o.get("exported_local"),
            "page_run": o.get("run_id"), "n_rows": int(len(rows)),
            "step2_saved_verdicts": int((s2["verdict"].astype(str) != "").sum()),
            "step2_unsaved_drafts_excluded": int(((s2["status"] == "draft") & (s2["verdict"].astype(str) == "")).sum()),
            "step2_saved_then_changed_unsaved": int(((s2["status"] == "draft") & (s2["verdict"].astype(str) != "")).sum()),
            "fn_notes": rows.loc[rows["item_id"] == "fn_notes", "notes"].tolist(),
            "notes": rows.loc[rows["notes"].astype(str) != "", ["item_id", "verdict", "occluder_kind", "notes"]].to_dict("records"),
            "ep204_rows": s2[s2["episode_id"].astype(str) == "204"][["item_id", "verdict", "occluder_kind", "status"]].to_dict("records"),
            "old_state_keys_ep204": sorted(k for k in o.get("state", {}) if k.endswith("_ep204"))}
    ws = pd.read_csv(P0_RUN / "wiser_spots.csv")
    b = part_b(rows, ws)
    b.to_csv(out / "part_b_spots_vs_user.csv", index=False)
    ep = pd.read_csv(OCC_RUN / "episodes.csv")
    m, c = part_c(rows, ep)
    m.to_csv(out / "occlusion_vs_user.csv", index=False)
    ll = label_loop_p(rows)
    res = {"made": datetime.now().isoformat(timespec="seconds"), "input": info, "part_b": b.to_dict("records"), "occlusion": c,
           "label_loop": ll, "sources": {"wiser_spots": (P0_RUN / "wiser_spots.csv").as_posix(), "episodes": (OCC_RUN / "episodes.csv").as_posix()}}
    (out / "compare.json").write_text(json.dumps(res, indent=2, default=lambda v: v.item() if hasattr(v, "item") else str(v)), encoding="utf-8")
    pd.set_option("display.width", 220)
    print(f"-> {out.as_posix()}")
    print(json.dumps(info, indent=1, default=str)[:3000])
    print(b.to_string())
    print(json.dumps(c, indent=1, default=str))
    print(json.dumps(ll, indent=1))
    return 0


def selftest() -> int:
    ok = True

    def check(name, cond, info=""):
        nonlocal ok
        ok &= bool(cond)
        print(f"[{'PASS' if cond else 'FAIL'}] {name} {info}")
    check("kappa: perfect agreement 1, chance 0, known 2x2 value", abs(cohen_kappa([1, 0, 1, 0], [1, 0, 1, 0]) - 1) < 1e-12
          and abs(cohen_kappa([1, 1, 0, 0], [1, 0, 1, 0])) < 1e-12
          and abs(cohen_kappa([1] * 20 + [0] * 30, [1] * 15 + [0] * 5 + [1] * 10 + [0] * 20) - (0.7 - 0.5) / 0.5) < 1e-12)
    rows = pd.DataFrame([{"step": 2, "item_id": f"ep{i}", "episode_id": i, "verdict": v, "occluder_kind": k, "notes": "", "status": "saved"}
                         for i, v, k in ((1, "occluded", "house"), (2, "visible_missed", ""), (3, "occluded", "pole"), (4, "box_present", ""),
                                         (5, "unsure", ""), (6, "", ""))])
    ep = pd.DataFrame({"episode_id": [1, 2, 3, 4, 5, 6], "class": ["hidden", "clear", "ambiguous", "partly", "clear", "clear"],
                       "occluder": ["house_2", "none", "pole_B3", "pole_B2", "none", "none"]})
    m, c = part_c(rows, ep)
    k = c["kappa"]
    check("part C: unsure and unsaved excluded; ambiguous excluded from the primary kappa, bracketed by the two variants",
          c["n_judged"] == 4 and k["primary (ambiguous excluded)"]["n"] == 3 and k["ambiguous = occluded"]["table"]["user_occ & geo_occ"] == 2
          and k["ambiguous = not occluded"]["table"]["user_occ & geo_not"] == 1 and c["occluder_agree"] == {"n": 2, "same_kind": 2}, str(c["kappa"]))
    ll = label_loop_p(rows)
    check("label-loop p = visible_missed / judged (unsure excluded) -> quota", ll["p"] == 0.25 and ll["visible_suspected_miss_quota_round2"] == 40)
    print(("PASS" if ok else "FAIL") + " — c1yolo_review_compare self-test")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], allow_abbrev=False)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--export", default=str(EXPORT))
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.run:
        return run(Path(a.export), Path(a.out) if a.out else None)
    ap.error("nothing to do (--run or --selftest)")


if __name__ == "__main__":
    sys.exit(main())
