r"""Which WISER tag moves like which logger? Hour-by-hour identity from IMU movement vs WISER speed, whole cohort.

Checks the tag table (cohorts/<c>.yaml `identities` -> wiser/configs/rat_identities_<c>.csv, with validity windows)
against the data, independently of it: in every 1-h block, each logger's per-second IMU movement (VeDBA, ephys/make_imu.py)
is rank-correlated with every tag's per-second WISER speed; the best tag, its r and its margin over the runner-up are
compared with the tag the table expects. Local data only (the local-first rule): IMU per-second tables under
<analysis_root>/imu, WISER incremental exports under --wiser-dir (default the local backup F:/wiser/Wiser_backup/incremental).

Definitions (per 1-h block b, logger a, tag k):
  WISER speed      v_k(s) = || p_k(s+1) - p_k(s-1) || / 2      p_k(s) = median tag position in second s (in); in/s
  IMU movement     m_a(s) = mean VeDBA in second s (m/s^2)
  series           x(s) = log10( 10-s centred running mean + 0.02 )   for both m_a and v_k
  r_ak             Spearman correlation of x_a and x_k over the seconds both cover (>= MIN_PAIRED s)
  best tag         argmax_k r_ak; margin = r_best - r_second
  confident        r_best >= R_MIN and margin >= MARGIN_MIN (0.5 / 0.25). Chosen on the same data it reports on: at the
                   looser 0.3 / 0.15 the NIGHT blocks (20-03 h) already agree 405/409 with the tag table, which is the
                   independent evidence; the stricter rule removes the daytime failures (animals piled together).
A block is informative only when the animals move independently; daytime rest in a pile and the battery rounds
(whole-fleet handling) correlate the animals with each other and are expected to be not confident.

Outputs: results/<c>/ephys_spikes/reports/ephys_spikes_imu_wiser_identity_<c>.csv (one row per block x logger) and .md.
Usage: python ephys/imu_wiser_identity.py --cohort 2026c [--wiser-dir F:/wiser/Wiser_backup/incremental]
"""
from __future__ import annotations

import argparse
import glob
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from _common import PROJECT_ROOT, analysis_root, git_commit, report_dir, resolve_cohort, utc_now_iso
from cohorts import load_cohort

TZ = ZoneInfo("America/New_York")
SMOOTH_S = 10
BLOCK_S = 3600
MIN_PAIRED = 1200          # seconds with both series in a block
MIN_IMU_COVER = 0.5
MIN_TAG_COVER = 0.3
R_MIN, MARGIN_MIN = 0.5, 0.25    # chosen on the 2026-09-28 run (3/403 disagreements, all daytime); see docstring


def load_identities(cohort: str) -> pd.DataFrame:
    rel = load_cohort(cohort).get("identities")
    t = pd.read_csv(PROJECT_ROOT / rel, dtype={"shortid": int, "physical_tag_id": str})
    t["from_ms"] = pd.to_datetime(t["valid_from"], utc=True).astype("int64") // 10**6
    t["until_ms"] = pd.to_datetime(t["valid_until"], utc=True).astype("int64") // 10**6
    return t


def wiser_speed(wiser_dir: str, pattern: str) -> dict[int, pd.Series]:
    files = sorted(glob.glob(str(Path(wiser_dir) / pattern)))
    if not files:
        raise SystemExit(f"no WISER exports matching {pattern} in {wiser_dir}")
    w = pd.concat([pd.read_csv(f, usecols=["shortid", "timestamp", "location_x", "location_y"]) for f in files])
    w = w.drop_duplicates()
    w["sec"] = w["timestamp"] // 1000
    out = {}
    for tag, d in w.groupby("shortid"):
        m = d.groupby("sec")[["location_x", "location_y"]].median()
        idx = np.arange(m.index.min(), m.index.max() + 1)
        xy = m.reindex(idx).to_numpy()
        v = np.full(len(idx), np.nan)
        v[1:-1] = np.linalg.norm(xy[2:] - xy[:-2], axis=1) / 2.0
        out[int(tag)] = pd.Series(v, index=idx)
    return out


def imu_movement(cohort: str) -> dict[str, pd.Series]:
    root = analysis_root(cohort) / "imu"
    out = {}
    for d in sorted(root.glob("SF*")):
        parts = [pd.read_csv(f, usecols=["t_pc_unix_ms", "vedba_mean"]) for f in d.glob("*.imu_1s.csv")]
        if not parts:
            continue
        x = pd.concat(parts)
        x["sec"] = (x["t_pc_unix_ms"] // 1000).astype(np.int64)
        out[d.name] = x.groupby("sec")["vedba_mean"].mean()
    return out


def smooth_log(s: pd.Series) -> pd.Series:
    return np.log10(s.rolling(SMOOTH_S, center=True, min_periods=SMOOTH_S // 2).mean() + 0.02)


def expected_tags(ids: pd.DataFrame, animal: str, t_ms: int) -> set[int]:
    r = ids[(ids.animal == animal) & (ids.from_ms <= t_ms) & (ids.until_ms > t_ms)]
    return set(int(x) for x in r.shortid)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cohort", default=None)
    ap.add_argument("--wiser-dir", default="F:/wiser/Wiser_backup/incremental")
    ap.add_argument("--wiser-pattern", default="3rdcohort_Spike_2026_3*.csv.gz")
    a = ap.parse_args()
    c = resolve_cohort(a.cohort)
    ids = load_identities(c)
    hexof = {int(r.shortid): str(r.physical_tag_id) for r in ids.itertuples()}
    print("loading WISER ...", flush=True)
    ws = wiser_speed(a.wiser_dir, a.wiser_pattern)
    print(f"  {len(ws)} tags: {sorted(ws)}", flush=True)
    im = imu_movement(c)
    print(f"  IMU loggers: {sorted(im)}", flush=True)
    t_lo = max(min(s.index.min() for s in im.values()), min(s.index.min() for s in ws.values()))
    t_hi = min(max(s.index.max() for s in im.values()), max(s.index.max() for s in ws.values()))
    grid = np.arange(t_lo, t_hi + 1)
    L_im = {k: smooth_log(v.reindex(grid)) for k, v in im.items()}
    L_ws = {k: smooth_log(v.reindex(grid)) for k, v in ws.items()}
    first = datetime.fromtimestamp(int(t_lo), TZ).replace(minute=0, second=0)
    b0 = int(first.timestamp())
    rows = []
    for bs in range(b0, int(t_hi), BLOCK_S):
        sl = (grid >= bs) & (grid < bs + BLOCK_S)
        if sl.sum() < BLOCK_S // 2:
            continue
        tags = [k for k, v in L_ws.items() if v[sl].notna().mean() >= MIN_TAG_COVER]
        for an, x in L_im.items():
            xb = x[sl]
            if xb.notna().mean() < MIN_IMU_COVER:
                continue
            rs = {}
            for k in tags:
                yb = L_ws[k][sl]
                ok = xb.notna() & yb.notna()
                if ok.sum() >= MIN_PAIRED:
                    rs[k] = xb[ok].rank().corr(yb[ok].rank())
            exp = expected_tags(ids, an, (bs + BLOCK_S // 2) * 1000)
            srt = sorted(rs.items(), key=lambda kv: -kv[1])
            best, rb = srt[0] if srt else (None, np.nan)
            second, r2 = srt[1] if len(srt) > 1 else (None, np.nan)
            margin = rb - r2 if np.isfinite(r2) else np.nan
            conf = bool(np.isfinite(rb) and rb >= R_MIN and np.isfinite(margin) and margin >= MARGIN_MIN)
            rows.append({
                "block_start_local": datetime.fromtimestamp(bs, TZ).strftime("%Y-%m-%d %H:%M"),
                "logger": an, "n_tags": len(rs), "best_shortid": best, "best_tag": hexof.get(best, "") if best else "",
                "r_best": round(rb, 3) if np.isfinite(rb) else None, "second_tag": hexof.get(second, "") if second else "",
                "r_second": round(r2, 3) if np.isfinite(r2) else None,
                "margin": round(margin, 3) if np.isfinite(margin) else None, "confident": conf,
                "expected_tags": "+".join(hexof.get(t, str(t)) for t in sorted(exp)),
                "r_expected": round(max((rs.get(t, np.nan) for t in exp), default=np.nan), 3) if exp else None,
                "agrees": (best in exp) if (conf and exp) else None,
            })
    df = pd.DataFrame(rows)
    rd = report_dir(c)
    csv_path = rd / f"ephys_spikes_imu_wiser_identity_{c}.csv"
    df.to_csv(csv_path, index=False)
    # summary
    lines = [f"# IMU movement vs WISER tag identity, cohort `{c}`", "",
             f"Generated {utc_now_iso()} by `ephys/imu_wiser_identity.py` (git {git_commit()}). Definitions in the script docstring. "
             f"Blocks of {BLOCK_S // 60} min; confident = r_best >= {R_MIN} and margin >= {MARGIN_MIN} (provisional). "
             f"Expected tags from `{load_cohort(c).get('identities')}`.", "",
             "| logger | blocks | confident | confident & agrees | confident & disagrees | median r(expected) | median margin (confident) |",
             "|---|---|---|---|---|---|---|"]
    for an, g in df.groupby("logger"):
        cf = g[g.confident]
        lines.append(f"| {an} | {len(g)} | {len(cf)} | {int((cf.agrees == True).sum())} | {int((cf.agrees == False).sum())} | "  # noqa: E712
                     f"{g.r_expected.median():.2f} | {cf.margin.median():.2f} |")
    hour = df.block_start_local.str[11:13].astype(int)
    lines += ["", "| time of day | blocks | confident | agrees | disagrees |", "|---|---|---|---|---|"]
    for name, m in (("night 20-03 h", (hour >= 20) | (hour <= 3)), ("rounds / dawn / dusk 04-08, 17-19 h", hour.isin([4, 5, 6, 7, 8, 17, 18, 19])),
                    ("day 09-16 h", (hour >= 9) & (hour <= 16))):
        g = df[m]
        cf = g[g.confident]
        lines.append(f"| {name} | {len(g)} | {len(cf)} | {int((cf.agrees == True).sum())} | {int((cf.agrees == False).sum())} |")  # noqa: E712
    dis = df[(df.confident) & (df.agrees == False)]  # noqa: E712
    lines += ["", f"## Confident disagreements ({len(dis)})", ""]
    if len(dis):
        lines += ["| block | logger | best tag (r) | expected (r) |", "|---|---|---|---|"]
        lines += [f"| {r.block_start_local} | {r.logger} | {r.best_tag} ({r.r_best}) | {r.expected_tags or '-'} ({r.r_expected}) |"
                  for r in dis.itertuples()]
    (rd / f"ephys_spikes_imu_wiser_identity_{c}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[5:]))
    print(f"\n-> {csv_path}")


if __name__ == "__main__":
    main()
