"""Block table for sorting cohort-3 ephys with Kilosort1 (plan implementation_plan/2026-10-09-k1-block-sorting.md).

A block is the continuous recording of one logger between two handling events.
- Joining: consecutive sessions are joined while the gap is < 5 min (file roll-overs and BLE Stop->Start splits).
- Boundaries: a new block starts at any gap >= 5 min (battery round, auto-stop, outage), at a probe advance
  (`ephys.probe_moves`) and at a firmware change.
- Excluded sessions:
  - field-flagged sessions (home cage, test cards, zombie restarts, the SF12 09-11 open connector);
  - FM62;
  - sessions < 5 min.
- Clipping: every block is clipped at the paddock end (09-12 10:10) and at the logger's `ephys.valid_until`.
- Handling trim: the first TRIM_S seconds of every block are cut, because the animal is still in hand after a
  round. K1 seeds its templates from the first isolated peaks of the file.
- Disconnected channels: failing shanks get `disconnect` channels from `ephys.quality_flags`:
  - SF12_shank1_degraded: shank 1;
  - SF12_contact_failing: shanks 1 and 4.
- Matching chains: a chain is an interval where units may be matched across blocks. It changes at:
  - probe advances;
  - the LFP regime steps (`results/2026c/ephys_spikes/reports/ephys_spikes_swr_session_drift_2026c.md`): SF11
    09-02 19:08:52, SF08 09-06 19:43 (slow settling before), SF12 09-06 08:09 and 09-08 07:26.
- Tiers: 1 = CA1, usable; 2 = SF11 after 09-02 19:08 (not CA1); 3 = SF12 after 09-08 07:26 (connector regime).
- Flags: `settle` (the first 4 h after an advance), `fm64` (needs the de-glitched copy), `deeper_profile` (SF10's
  last 3 sessions, 09-10 21:00 -> 09-11 19:22, sit 1-2 sites deeper).

Times are the logger clock (the session-index start_local + seconds); samples are 20 kHz.

Output:
- results/2026c/ephys_spikes/reports/ephys_spikes_k1_blocks_2026c.csv, one row per block. `segments` is JSON:
  [[session, raw animal folder, start_sample, end_sample], ...].
- the same .md summary.

Usage: python ephys/plan_blocks.py [--cohort 2026c] [--trim-min 20] [--min-block-min 30]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import PROJECT_ROOT, ephys_block, report_dir  # noqa: E402
from make_session_xml import load_probe  # noqa: E402

FS = 20000
PADDOCK_END = pd.Timestamp("2026-09-12 10:10:00")
GAP_S = 300
SETTLE_H = 4
LFP_STEPS = {   # LFP-found regime steps without a probe advance (SWR session, commit c47f8e5)
    "SF11": [("2026-09-02 19:08:52", "SF11 probe out of CA1 from the 09-02 evening round")],
    "SF08": [("2026-09-06 19:43:00", "SF08 slow settling (2-3 sites) ends; chain split only")],
    "SF12": [("2026-09-06 08:09:00", "SF12 step at the 09-06 morning round"),
             ("2026-09-08 07:26:00", "SF12 SW profile inverts (connector regime)")],
}
TIER_FROM = {"SF11": ("2026-09-02 19:08:52", 2), "SF12": ("2026-09-08 07:26:00", 3)}
DEEPER = {"SF10": ("2026-09-10 21:00:00", "2026-09-11 19:23:00")}
SHANK_FLAGS = {"SF12_shank1_degraded": [0], "SF12_contact_failing": [0, 3]}   # 0-based group index in the XML order


def pad(animal: str) -> str:
    return f"SF{int(animal[2:]):02d}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cohort", default="2026c")
    ap.add_argument("--trim-min", type=float, default=20.0)
    ap.add_argument("--min-block-min", type=float, default=30.0, help="drop blocks shorter than this after trimming")
    a = ap.parse_args()
    eph = ephys_block(a.cohort)
    rep = report_dir(a.cohort, "ephys_spikes")
    d = pd.read_csv(rep / f"ephys_spikes_session_index_{a.cohort}.csv")
    d["raw_animal"] = d.animal
    d["animal"] = d.animal.map(pad)
    d["start"] = pd.to_datetime(d.start_local)
    d["end"] = d.start + pd.to_timedelta(d.duration_s, unit="s")
    keep = d.firmware.isin([64, 65]) & d.field_flag.isna() & (d.duration_s >= 300) & (d.start < PADDOCK_END)
    s = d[keep].sort_values(["animal", "start"]).copy()

    valid_until = {v["animal"]: pd.Timestamp(v["valid_until"]) for v in eph.get("valid_until", [])}
    moves: dict[str, list[pd.Timestamp]] = {}
    for m in eph.get("probe_moves", []):
        moves.setdefault(m["animal"], []).append(pd.Timestamp(m["time"]))
    qflags = eph.get("quality_flags", [])
    probe_cfg = PROJECT_ROOT / eph["probe_config"]

    rows = []
    for animal, g in s.groupby("animal"):
        groups = load_probe(probe_cfg, animal)["groups"]
        end_lim = min(PADDOCK_END, valid_until.get(animal, PADDOCK_END))
        cuts = sorted(moves.get(animal, []))
        chain_cuts = sorted(cuts + [pd.Timestamp(t) for t, _ in LFP_STEPS.get(animal, [])])
        blocks, cur = [], []
        for _, r in g.iterrows():
            if r.start >= end_lim:
                continue
            if cur:
                prev = cur[-1]
                gap = (r.start - prev.end).total_seconds()
                crossed = any(prev.end <= c <= r.start + pd.Timedelta(minutes=1) for c in cuts)
                if gap >= GAP_S or crossed or r.firmware != prev.firmware:
                    blocks.append(cur); cur = []
            cur.append(r)
        if cur:
            blocks.append(cur)
        for b in blocks:
            t0 = b[0].start + pd.Timedelta(seconds=a.trim_min * 60)
            t1 = min(b[-1].end, end_lim)
            segs, hours = [], 0.0
            for r in b:
                s0 = max(r.start, t0); s1 = min(r.end, t1)
                if s1 <= s0:
                    continue
                i0 = int(round((s0 - r.start).total_seconds() * FS)); i1 = int(round((s1 - r.start).total_seconds() * FS))
                segs.append([r.session, r.raw_animal, i0, min(i1, int(r.n_samples))])
                hours += (segs[-1][3] - segs[-1][2]) / FS / 3600
            if hours * 60 < a.min_block_min:
                continue
            chain = sum(t0 >= c - pd.Timedelta(minutes=30) for c in chain_cuts)
            tier = 1
            if animal in TIER_FROM and t0 >= pd.Timestamp(TIER_FROM[animal][0]) - pd.Timedelta(minutes=30):
                tier = TIER_FROM[animal][1]
            # the post-move session can start a second before the logged turn time (rounded / BLE clock)
            settle = any(pd.Timedelta(minutes=-10) <= (b[0].start - m) <= pd.Timedelta(hours=1) for m in moves.get(animal, []))
            disc = set()
            for q in qflags:   # a flag counts when it covers > 30 min of the block
                if q["animal"] == animal and q["tag"] in SHANK_FLAGS and t1 - max(t0, pd.Timestamp(q["from"])) > pd.Timedelta(minutes=30):
                    for gi in SHANK_FLAGS[q["tag"]]:
                        disc |= set(groups[gi])
            deeper = animal in DEEPER and t1 > pd.Timestamp(DEEPER[animal][0]) and t0 < pd.Timestamp(DEEPER[animal][1])
            rows.append(dict(
                block=f"{animal}_{b[0].start:%Y%m%d_%H%M%S}", animal=animal, firmware=int(b[0].firmware),
                start=t0, end=t1, hours=round(hours, 3), n_sessions=len(segs), chain=chain, tier=tier,
                settle_window_h=SETTLE_H if settle else 0, fm64=int(b[0].firmware) == 64, deeper_profile=deeper,
                disconnect=" ".join(str(c) for c in sorted(disc)),
                gb=round(sum((x[3] - x[2]) * 64 * 2 for x in segs) / 1e9, 2), segments=json.dumps(segs)))
    bt = pd.DataFrame(rows)
    csv = rep / f"ephys_spikes_k1_blocks_{a.cohort}.csv"
    bt.to_csv(csv, index=False)
    lines = [f"# K1 sorting blocks, cohort {a.cohort}", "",
             "Made by `ephys/plan_blocks.py` (plan `implementation_plan/2026-10-09-k1-block-sorting.md`).", "",
             f"- Trim: first {a.trim_min:g} min of every block (handling). Blocks shorter than {a.min_block_min:g} min "
             f"after trimming are dropped. Clipped at the paddock end {PADDOCK_END} and at `valid_until`.",
             f"- **{len(bt)} blocks**, {bt.hours.sum():.0f} h ({bt[~bt.fm64].hours.sum():.0f} h FM65 in "
             f"{(~bt.fm64).sum()} blocks, {bt[bt.fm64].hours.sum():.0f} h FM64 in {bt.fm64.sum()} blocks), "
             f"{bt.gb.sum() / 1000:.1f} TB.",
             f"- Hours per block: median {bt.hours.median():.1f}, maximum {bt.hours.max():.1f}. "
             f"{(bt.n_sessions > 1).sum()} blocks join several files.",
             f"- Tier 2 (SF11 out of CA1): {(bt.tier == 2).sum()} blocks; tier 3 (SF12 connector regime): {(bt.tier == 3).sum()}. "
             f"Blocks with disconnected shanks: {(bt.disconnect != '').sum()}; settle windows: {(bt.settle_window_h > 0).sum()}.",
             "", "| animal | blocks | hours | chains | FM64 blocks | max h |", "|---|---|---|---|---|---|"]
    for an, gg in bt.groupby("animal"):
        lines.append(f"| {an} | {len(gg)} | {gg.hours.sum():.1f} | {gg.chain.nunique()} | {gg.fm64.sum()} | {gg.hours.max():.1f} |")
    (rep / f"ephys_spikes_k1_blocks_{a.cohort}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"-> {csv}")


if __name__ == "__main__":
    main()
