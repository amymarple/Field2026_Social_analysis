r"""
selftest_following_incidents.py — offline, synthetic, no DB. Phase B2.

Checks:
  A. strict-following episodes are extracted from a planted trailing pair, and a
     LAG-VARYING trail merges into ONE episode (across lags);
  B. incident metrics are sane (episodes/hour > 0, fraction-of-bouts > 0);
  C. camera_router ranks the correct fake channel and flags a boundary-straddling event;
  D. the audit classifier returns detected / missed_distance_radius / missed_tag_dropout
     on planted cases.

Run:  python scripts/selftest_following_incidents.py   ->  exit 0 PASS / 1 FAIL
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
import wiser_analysis_utils as w              # noqa: E402
import following_incidents as fi              # noqa: E402
import camera_router as cr                    # noqa: E402

RNG = np.random.default_rng(11)
FAILS = []


def check(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILS.append(name)


def _trail_win(*, lag_s=3, sep_noise=3.0, perp_offset=0.0, n=240, lag_drift=False,
               follower_present_to=1.0, straight=False):
    """Leader '1' walks; follower '2' = leader delayed by lag_s, offset PERPENDICULAR
    to motion by ``perp_offset`` in (for a clean distance test). ``straight`` = a
    straight leader path so the perpendicular is well-defined; else a wandering path.
    ``follower_present_to`` < 1 drops the follower after that fraction (dropout)."""
    if straight:
        lx = 100 + 15.0 * np.arange(n); ly = 100 + np.zeros(n)     # motion along +x
        perp = np.array([0.0, 1.0])                                 # perpendicular = +y
    else:
        ang = np.cumsum(RNG.normal(0, 0.2, n)) + 0.3
        lx = 100 + np.cumsum(15 * np.cos(ang)); ly = 100 + np.cumsum(15 * np.sin(ang))
        perp = np.array([0.0, 0.0])
    rows = [{"shortid": "1", "x": float(lx[k]), "y": float(ly[k]),
             "elapsed_s": float(k), "valid": True} for k in range(n)]
    for k in range(n):
        if k > 0 and k / n > follower_present_to:                  # follower dropout
            continue
        lag = lag_s + (int(3 * k / n) if lag_drift else 0)
        src = max(0, k - lag)
        ox, oy = perp * perp_offset
        rows.append({"shortid": "2", "x": float(lx[src] + ox + RNG.normal(0, sep_noise)),
                     "y": float(ly[src] + oy + RNG.normal(0, sep_noise)),
                     "elapsed_s": float(k), "valid": True})
    return pd.DataFrame(rows)


def _grid(win):
    return w.build_following_grid(win, bin_s=1.0, smooth_s=5.0, moving_thr_inps=2.0)


def test_episodes():
    print("A. strict-following episode extraction (across lags)")
    R = w.follow_radius_in(7.0)                 # 24 in
    grid = _grid(_trail_win(lag_s=3))
    eps = fi.strict_following_episodes(grid, "1", "2", lags=range(1, 31), R=R, min_bout_s=3.0)
    check("planted trail -> >=1 episode", len(eps) >= 1, f"n_episodes={len(eps)}")
    check("episode has meaningful duration", any(e["duration_s"] >= 5 for e in eps),
          f"max_dur={max((e['duration_s'] for e in eps), default=0)}")
    rev = fi.strict_following_episodes(grid, "2", "1", lags=range(1, 31), R=R, min_bout_s=3.0)
    tot_fwd = sum(e["duration_s"] for e in eps); tot_rev = sum(e["duration_s"] for e in rev)
    check("forward (1->2) trailing exceeds reverse", tot_fwd > tot_rev,
          f"fwd={tot_fwd:.0f}s rev={tot_rev:.0f}s")

    # lag-varying trail merges into one episode spanning multiple lags
    gridd = _grid(_trail_win(lag_s=2, lag_drift=True))
    epd = fi.strict_following_episodes(gridd, "1", "2", lags=range(1, 31), R=R, min_bout_s=3.0)
    multilag = any(e["n_lags_fired"] >= 2 for e in epd)
    check("lag-varying trail merges & records >=2 lags", len(epd) >= 1 and multilag,
          f"n_ep={len(epd)} max_lags={max((e['n_lags_fired'] for e in epd), default=0)}")


def test_metrics():
    print("B. incident metrics")
    R = w.follow_radius_in(7.0)
    grid = _grid(_trail_win(lag_s=3, n=300))
    eps = fi.strict_following_episodes(grid, "1", "2", lags=range(1, 31), R=R, min_bout_s=3.0)
    sidx = {str(t): k for k, t in enumerate(grid["tags"])}
    m = fi.pair_incident_metrics(eps, grid, sidx["2"], window_s=grid["X"].shape[0])
    check("episodes_per_hour > 0", m["strict_follow_episode_count_per_hour"] > 0,
          f"{m['strict_follow_episode_count_per_hour']}")
    check("fraction_of_movement_bouts_that_are_following > 0",
          m["fraction_of_movement_bouts_that_are_following"] > 0,
          f"{m['fraction_of_movement_bouts_that_are_following']}")


def _fake_vis():
    left = np.array([[0, 0], [400, 0], [400, 400], [0, 400]], float)
    right = np.array([[400, 0], [800, 0], [800, 400], [400, 400]], float)
    return {"meta": {"confirmed": True}, "confirmed": True, "channels": [
        {"name": "CHL", "_poly": left, "priority": 1.0, "notes": "left"},
        {"name": "CHR", "_poly": right, "priority": 1.0, "notes": "right"}]}


def test_router():
    print("C. camera router")
    vis = _fake_vis()
    fp_left = np.column_stack([RNG.uniform(50, 350, 40), RNG.uniform(50, 350, 40)])
    r = cr.route_event(fp_left, vis)
    check("footprint in left -> CHL ranked first", r["channel_rank_1"] == "CHL",
          f"rank1={r['channel_rank_1']} conf={r['confidence']}")
    fp_edge = np.column_stack([RNG.uniform(350, 450, 60), RNG.uniform(50, 350, 60)])
    r2 = cr.route_event(fp_edge, vis)
    check("boundary-straddling footprint flagged near_boundary", r2["near_boundary"],
          f"near_boundary={r2['near_boundary']} cov={r2['coverages']}")
    fp_out = np.column_stack([RNG.uniform(1000, 1100, 10), RNG.uniform(50, 350, 10)])
    r3 = cr.route_event(fp_out, vis)
    check("footprint outside all polygons -> no channel", r3["channel_rank_1"] is None,
          f"rank1={r3['channel_rank_1']}")


def test_audit_classifier():
    print("D. audit classifier")
    R = w.follow_radius_in(7.0)
    # detected
    g_ok = _grid(_trail_win(lag_s=3))
    c1 = fi.classify_audit_event(g_ok, "1", "2", R=R)
    check("planted trail -> detected", c1["detected"] and c1["classification"] == "detected",
          f"{c1['classification']}")
    # straight parallel walk 40 in to the side -> min separation ~40 in (> R=24, < 2R)
    g_far = _grid(_trail_win(lag_s=1, perp_offset=40.0, sep_noise=1.0, straight=True))
    c2 = fi.classify_audit_event(g_far, "1", "2", R=R)
    check("side-offset (40in) trail -> missed_distance_radius",
          c2["classification"] == "missed_distance_radius", f"{c2['classification']}")
    # follower absent through the window -> dropout
    g_drop = _grid(_trail_win(lag_s=3, follower_present_to=0.0))
    c3 = fi.classify_audit_event(g_drop, "1", "2", R=R)
    check("follower dropout -> missed_tag_dropout",
          c3["classification"] == "missed_tag_dropout",
          f"{c3['classification']} fol_present={c3['follower_present_frac']}")


def test_calibration():
    print("E. camera-map calibration (convex hull from example points)")
    import tempfile
    import calibrate_camera_visibility as cal
    hull = cal.convex_hull(np.array([[0, 0], [10, 0], [10, 10], [0, 10], [5, 5]]))
    check("convex hull of a square -> 4 vertices", len(hull) == 4, f"n={len(hull)}")
    check("buffer grows the polygon", cal.buffer_polygon(hull, 5.0)[:, 0].max() > hull[:, 0].max())
    ex = {"CHX": [[0, 0], [20, 0], [20, 20], [0, 20], [10, 10]]}
    polys = cal.polygons_from_examples(ex, margin_in=2.0)
    check("polygon built from >=3 example points", "CHX" in polys, str(list(polys)))
    inside = bool(w.points_in_polygons([10.0], [10.0], [np.asarray(polys["CHX"])])[0])
    check("a point inside the hull tests inside", inside)
    base = {"meta": {}, "channels": [{"name": "CHX", "priority": 1.0, "notes": ""}]}
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "m.yaml"
        cal.write_visibility_map(p, base, polys, ex, all_calibrated=True)
        vm = cr.load_visibility_map(p)
        r = cr.route_event(np.array([[10.0, 10.0]]), vm)
        check("routing a point inside -> that channel", r["channel_rank_1"] == "CHX",
              f"{r['channel_rank_1']}")
        check("meta.confirmed roundtrips", vm["confirmed"] is True, str(vm["confirmed"]))


def test_homography():
    print("F. image->WISER homography calibration")
    import camera_calibration as cc
    H_true = np.array([[1.2, 0.1, 50.0], [0.05, 0.9, 30.0], [0.0002, 0.0001, 1.0]])
    src = np.array([[0, 0], [100, 0], [100, 100], [0, 100], [50, 60], [80, 20]], float)
    dst = cc.apply_homography(H_true, src)
    H = cc.fit_homography(src, dst)
    check("homography fit recovers landmarks (RMS ~0)", cc.homography_rms(H, src, dst) < 1e-6,
          f"rms={cc.homography_rms(H, src, dst):.2e}")
    q = cc.apply_homography(H, np.array([[25.0, 25.0]]))[0]
    qt = cc.apply_homography(H_true, np.array([[25.0, 25.0]]))[0]
    check("maps a NEW pixel to the right WISER point", np.allclose(q, qt, atol=1e-4),
          f"{np.round(q,2)} vs {np.round(qt,2)}")
    res = cc.build_visibility_polygon(src, dst, region_px=[[0, 0], [100, 0], [100, 100], [0, 100]])
    check("visible region -> 4-vertex WISER polygon", len(res["polygon"]) == 4,
          f"n={len(res['polygon'])}")
    res2 = cc.build_visibility_polygon(src, dst, region_px=None, margin_in=10.0)
    check("no region -> hull(+margin) polygon built", len(res2["polygon"]) >= 3,
          f"n={len(res2['polygon'])}")


def main():
    print("== selftest: following incidents (Phase B2) ==")
    test_episodes()
    test_metrics()
    test_router()
    test_audit_classifier()
    test_calibration()
    test_homography()
    print()
    if FAILS:
        print(f"FAIL — {len(FAILS)} check(s): {FAILS}")
        sys.exit(1)
    print("PASS — Phase B2 incident/router/audit core healthy")
    sys.exit(0)


if __name__ == "__main__":
    main()
