"""Quality and validation of the automatic SWR events of a cohort (ephys/swr_auto.py output), for the people and agents
who use them (plan: implementation_plan/2026-10-07-swr-detection-automation.md).

  validate  the production events vs the user's own GUI scoring (configs/swr_validation_<c>.yaml): event F1 of all and of
            kept events (peak match +-10 ms), and, where a local pilot run of the same session exists, the server-vs-local
            agreement (the local-first rule's spot check) -> reports/ephys_spikes_swr_validation_<c>.csv
  build     one row per session with its quality tier and the reasons -> reports/ephys_spikes_swr_quality_<c>.{csv,md}
            (the .md is the user guide: where the files are, how to filter, definitions, per-block table)
  --selftest  synthetic checks of the tier rules

Tiers (a session gets the lowest that applies):
  exclude       the user marked the session noise in the sleep review; a field-flagged session (test card, zombie restart,
                open connector, home cage, ADC lane); a skipped block; the whole session after its use_until
  low_contrast  a block whose flags say "low ripple contrast" (SF11 from 09-02 19:08, SF12 block 3): the boundary finds no
                ripple cluster (19-29 % selected) -> not SWR-specific, a negative control only
  check         a drift check fails (selected fraction outside 1-10 %; NREM rate of all events outside 20-110/min with
                >= 10 min NREM; NREM amplitude ratio to the block reference outside 0.7-1.4) or the session has no sleep states
  validated     a block with a user-scored session whose kept-event F1 >= 0.80
  good          any other normal-contrast block
use_until = the earliest of the cohort's valid_until for the session, the paddock end 2026-09-12 10:10, and a quality flag
that ends the record (SF12_contact_failing); events after it are not data.

  python ephys/swr_quality.py validate --swr-root <root> [--gui-root …] [--local-root …]
  python ephys/swr_quality.py build --swr-root <root>
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _common import git_commit, report_dir, utc_now_iso  # noqa: E402

COHORT = "2026c"
PADDOCK_END = datetime(2026, 9, 12, 10, 10)
FEMALES = datetime(2026, 9, 11, 19, 40)
SEL_RANGE, NREM_RATE_RANGE, AMP_RANGE, F1_VALID = (0.01, 0.10), (20.0, 110.0), (0.7, 1.4), 0.80
END_FLAGS = ("SF12_contact_failing",)


def session_start(s: str) -> datetime:
    m = re.match(r"\d+_(\d{8})_(\d{6})\.(\d+)", s)
    return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S") + timedelta(milliseconds=int(m.group(3)[:3]))


def block_label(cfg: dict, animal: str, valid_from) -> str:
    blocks = [b for b in cfg[animal]]
    i = [str(b.get("valid_from")) for b in blocks].index(str(valid_from))
    return blocks[i].get("label") or f"block {i + 1}"


def match_f1(user: np.ndarray, auto: np.ndarray, tol: float = 0.010):
    import swr_detect as sd
    ia, _ = sd.match_peaks(np.sort(user), np.sort(auto), tol)
    p, r = ia.size / max(auto.size, 1), ia.size / max(user.size, 1)
    return dict(n_user=int(user.size), n_auto=int(auto.size), matched=int(ia.size), precision=round(p, 3), recall=round(r, 3),
                f1=round(2 * p * r / max(p + r, 1e-9), 3))


def user_events(v: dict, gui_root: str, lfp_root: str) -> np.ndarray:
    """The user's event peaks (s). Sessions scored with flagged candidates hidden are rebuilt the way the user saw them:
    their clicks propagated by 1-NN over the non-bad, unflagged candidates only, then DetectSWR check-mode localisation
    (the GUI's own events file propagates over every candidate)."""
    import swr_detect as sd
    D = Path(gui_root) / v["animal"] / v["session"] / v["tag"]
    if not v.get("hide_flagged"):
        return np.load(D / f"{v['events']}.npz")["peak"].astype(float)
    prep, fz = np.load(D / "prep.npz"), np.load(D / "flags.npz", allow_pickle=True)
    clicks = json.loads((D / "scores_latest.json").read_text())["scores"]
    sv = np.full(prep["featureTs"].size, np.nan)
    for k, x in clicks.items():
        sv[int(k)] = float(x)
    lab, _ = sd.propagate_clicks(prep["swDiffAll"], prep["ripPowerAll"], sv, prep["bad"] | (fz["flags"] > 0))
    ch = [int(c) for c in v["tag"][2:].split("-")]  # GUI tag ch<ripple>-<sw>-<noise>, 1-based
    lfp3 = sd.load_channels(str(Path(lfp_root) / v["animal"] / f"{v['session']}.lfp"), 64, ch)
    fe = dict(swDiff=np.fromfile(D / "swDiff.f32", np.float32).astype(float),
              ripPower0=np.fromfile(D / "ripPower0.f32", np.float32).astype(float),
              featureTs=prep["featureTs"], swDiffAll=prep["swDiffAll"], ripPowerAll=prep["ripPowerAll"])
    p = sd.Params(thresSDswD=(0.25, 0.5), thresSDrip=(0.25, 0.5), maxDurSW=0.8, useSPW=False)
    return np.sort(sd.events_from_mask(fe, lfp3[:, 0], lab, 1250.0, p)[0]["peak"]).astype(float)


def validate(a):
    import pandas as pd
    val = yaml.safe_load(open(a.validation))["sessions"]
    rows = []
    for v in val:
        an, s = v["animal"], v["session"]
        user = user_events(v, a.gui_root, a.lfp_root)
        z = np.load(Path(a.swr_root) / an / s / f"{s}.swr_events.npz", allow_pickle=True)
        pk, ex = z["peak_s"].astype(float), z["excluded"].astype(bool)
        row = dict(animal=an, session=s, note=v.get("note", ""), hide_flagged=v.get("hide_flagged"))
        for k, m in (("all", np.ones(pk.size, bool)), ("kept", ~ex)):
            row.update({f"{k}_{kk}": vv for kk, vv in match_f1(user, pk[m]).items()})
        loc = Path(a.local_root) / an / s / f"{s}.swr_events.npz" if a.local_root else None
        if loc is not None and loc.exists():
            zl = np.load(loc, allow_pickle=True)
            pl = zl["peak_s"].astype(float)
            same = pl.size == pk.size and np.allclose(np.sort(pl), np.sort(pk), atol=1e-4)
            row.update(local_n=int(pl.size), server_n=int(pk.size), server_equals_local=bool(same),
                       server_vs_local_f1=match_f1(pl, pk, 0.0005)["f1"])
        rows.append(row)
        print(f"{an} {s}: kept F1 {row['kept_f1']} (P {row['kept_precision']} R {row['kept_recall']}; user {row['kept_n_user']}, "
              f"auto kept {row['kept_n_auto']}); all F1 {row['all_f1']}" + (f"; server == local: {row.get('server_equals_local')}"
                                                                             if "server_equals_local" in row else ""), flush=True)
    df = pd.DataFrame(rows)
    out = Path(a.validation_csv)
    df.to_csv(out, index=False)
    print(f"wrote {out}")


def tier_of(rec: dict) -> tuple[str, list]:
    """(tier, reasons) for one session record (see the module docstring)."""
    why = []
    if rec.get("exclude_reasons"):
        return "exclude", list(rec["exclude_reasons"])
    if rec.get("low_contrast"):
        return "low_contrast", ["block: low ripple contrast (not SWR-specific)"]
    if rec.get("no_states"):
        why.append("no sleep states (REM / theta exclusion impossible)")
    sel = rec.get("selected_frac")
    if sel is not None and not (SEL_RANGE[0] <= sel <= SEL_RANGE[1]):
        why.append(f"selected fraction {100 * sel:.1f} % outside {100 * SEL_RANGE[0]:.0f}-{100 * SEL_RANGE[1]:.0f} %")
    if (rec.get("nrem_min") or 0) >= 10 and rec.get("rate_nrem") is not None and not (NREM_RATE_RANGE[0] <= rec["rate_nrem"] <= NREM_RATE_RANGE[1]):
        why.append(f"NREM rate {rec['rate_nrem']:.1f}/min outside {NREM_RATE_RANGE[0]:.0f}-{NREM_RATE_RANGE[1]:.0f}")
    amp = rec.get("amp_ratio")
    if amp is not None and not (AMP_RANGE[0] <= amp <= AMP_RANGE[1]):
        why.append(f"NREM amplitude {amp:.2f} x the block reference (outside {AMP_RANGE[0]}-{AMP_RANGE[1]})")
    if why:
        return "check", why
    return ("validated" if rec.get("block_validated") else "good"), []


def build(a):
    import pandas as pd
    cfg = yaml.safe_load(open(a.channels))
    co = yaml.safe_load(open(a.cohort_yaml))
    eph = co["ephys"]
    rev = pd.read_csv(a.review) if Path(a.review).exists() else pd.DataFrame(columns=["animal", "session", "verdict", "tags"])
    idx = pd.read_csv(a.session_index) if Path(a.session_index).exists() else pd.DataFrame(columns=["animal", "session", "firmware"])
    val = pd.read_csv(a.validation_csv) if Path(a.validation_csv).exists() else pd.DataFrame()
    run_cfg = Path(a.swr_root) / f"swr_channels_{COHORT}.yaml"
    cfg_note = ""
    if run_cfg.exists():
        rc = yaml.safe_load(open(run_cfg))
        keys = ("boundary_features", "valid_from", "reference_session", "ripple_col", "sharpwave_col", "noise_col", "exclude_cols", "skip")
        same = all([{k: b.get(k) for k in keys} for b in rc.get(an, [])] == [{k: b.get(k) for k in keys} for b in cfg[an]] for an in cfg)
        cfg_note = "identical" if same else "DIFFERS from the repo config (the run used its own copy)"
    ff = {(f["animal"], s): f["flag"] for f in eph.get("field_flags", []) for s in f.get("sessions", [])}
    vu = {(v["animal"], v["session"]): datetime.fromisoformat(v["valid_until"]) for v in eph.get("valid_until", [])}
    qf = [dict(q, t=datetime.fromisoformat(q["from"])) for q in eph.get("quality_flags", [])]
    moves = [dict(m, t=datetime.fromisoformat(m["time"])) for m in eph.get("probe_moves", [])]
    validated_blocks = set()
    if len(val):
        for _, r in val[val.kept_f1 >= F1_VALID].iterrows():
            from swr_auto import channels_for
            validated_blocks.add((r.animal, str(channels_for(cfg, r.animal, r.session).get("valid_from"))))
    rows = []
    for f in sorted(Path(a.swr_root).glob("SF*/*/*.swr_summary.json")):
        d = json.loads(f.read_text())
        an, s = d["animal"], d["session"]
        t0 = session_start(s)
        t1 = t0 + timedelta(hours=float(d.get("hours") or 0))
        from swr_auto import channels_for
        blk = channels_for(cfg, an, s)
        rv = rev[(rev.animal == an) & (rev.session == s)]
        verdict = str(rv.verdict.iloc[0]) if len(rv) and pd.notna(rv.verdict.iloc[0]) else ""
        tags = str(rv.tags.iloc[0]) if len(rv) and pd.notna(rv.tags.iloc[0]) else ""
        fw = idx[(idx.animal == an) & (idx.session == s)].firmware
        excl = []
        if d.get("skipped"):
            excl.append("block skipped (no usable channels)")
        if verdict == "noise":
            excl.append("user sleep review: noise")
        if (an, s) in ff:
            excl.append("field flag: " + ff[(an, s)][:90])
        cuts = [(PADDOCK_END, "paddock end 09-12 10:10")]
        if (an, s) in vu:
            cuts.append((vu[(an, s)], "valid_until"))
        cuts += [(q["t"], q["tag"]) for q in qf if q["animal"] == an and q["tag"] in END_FLAGS]
        cut = min((c for c in cuts if c[0] < t1), default=None, key=lambda c: c[0])
        use_until = None
        if cut is not None:
            if cut[0] <= t0:
                excl.append(f"after {cut[1]} ({cut[0]:%m-%d %H:%M})")
            else:
                use_until = cut
        info = []
        if verdict == "bad":
            info.append("sleep review 'bad' (REM uncertain)")
        for q in qf:
            if q["animal"] == an and q["tag"] not in END_FLAGS and t1 > q["t"]:
                info.append(f"{q['tag']} from {q['t']:%m-%d %H:%M}")
        for m in moves:
            if m["animal"] == an and m["t"] <= t0 < m["t"] + timedelta(hours=float(m.get("settle_h", 4))):
                info.append(f"starts in the {m.get('settle_h', 4)} h after the {m['t']:%m-%d %H:%M} probe advance")
        if t1 > FEMALES and t0 < PADDOCK_END:
            info.append("five females present from 09-11 19:40 (population 10)")
        if len(fw) and int(fw.iloc[0]) < 65:
            info.append(f"FM{int(fw.iloc[0])} (de-glitched LFP)")
        if d.get("boundary_fit_on") == "donor":
            info.append(f"< 10 min NREM: boundary borrowed from {d.get('boundary_from')}")
        sm = d.get("state_minutes") or {}
        rate = d.get("rate_per_min") or {}
        kept = d.get("kept_rate_per_min") or {}
        rec = dict(animal=an, session=s, start=f"{t0:%Y-%m-%d %H:%M:%S}", end=f"{t1:%Y-%m-%d %H:%M:%S}",
                   hours=round(float(d.get("hours") or 0), 3),
                   block=block_label(cfg, an, blk.get("valid_from")), block_from=str(blk.get("valid_from")),
                   reference=blk.get("reference_session"), is_reference=bool(d.get("is_block_reference")),
                   boundary=d.get("boundary_features"), channels=json.dumps(d.get("channels_0based", {}).get("ripple")) + "/" +
                   json.dumps(d.get("channels_0based", {}).get("sharpwave")) + "/" + json.dumps(d.get("channels_0based", {}).get("noise"))
                   if d.get("channels_0based") else "",
                   n_events=d.get("n_events"), n_kept=(d.get("n_events") or 0) - (d.get("n_excluded") or 0),
                   nrem_min=sm.get("NREM"), rem_min=sm.get("REM"), wake_min=sm.get("WAKE"),
                   rate_nrem=rate.get("NREM"), rate_rem=rate.get("REM"), rate_wake=rate.get("WAKE"),
                   kept_rate_nrem=kept.get("NREM"), kept_rate_wake=kept.get("WAKE"),
                   selected_frac=d.get("kmeans_selected_frac"), own_fit_frac=d.get("own_nrem_fit_selected_frac"),
                   amp_ratio=d.get("amplitude_ratio_to_reference"),
                   use_until=f"{use_until[0]:%Y-%m-%d %H:%M:%S} ({use_until[1]})" if use_until else "",
                   low_contrast=any(str(x).startswith("low ripple contrast") for x in blk.get("flags", [])),
                   block_validated=(an, str(blk.get("valid_from"))) in validated_blocks,
                   no_states=not d.get("skipped") and not any((sm or {}).values()),
                   exclude_reasons=excl, info="; ".join(info), sleep_verdict=verdict, sleep_tags=tags)
        tier, why = tier_of(rec)
        rec["tier"], rec["reasons"] = tier, "; ".join(why)
        rows.append(rec)
    df = pd.DataFrame(rows)
    df["exclude_reasons"] = df.exclude_reasons.map(lambda x: "; ".join(x))
    order = {"validated": 0, "good": 1, "check": 2, "low_contrast": 3, "exclude": 4}
    df = df.sort_values(["animal", "start"]).reset_index(drop=True)
    rd = Path(a.report_dir) if a.report_dir else report_dir(COHORT)
    rd.mkdir(parents=True, exist_ok=True)
    csv = rd / f"ephys_spikes_swr_quality_{COHORT}.csv"
    df.drop(columns=["low_contrast", "block_validated", "no_states"]).to_csv(csv, index=False)
    write_md(a, df, val, rd / f"ephys_spikes_swr_quality_{COHORT}.md", cfg, cfg_note, order)
    print(f"wrote {csv} ({len(df)} sessions): " + ", ".join(f"{k} {int((df.tier == k).sum())}" for k in order))


def write_md(a, df, val, out, cfg, cfg_note, order):
    import pandas as pd
    L = []
    w = L.append
    w(f"# Automatic SWR events, cohort {COHORT}: quality and how to use them")
    w("")
    w(f"Generated by `ephys/swr_quality.py build` ({utc_now_iso()}, repo `{git_commit()}`) from the session summaries in "
      f"`{a.swr_root}`; one row per session in [`ephys_spikes_swr_quality_{COHORT}.csv`](ephys_spikes_swr_quality_{COHORT}.csv). "
      f"Method: `ephys/swr_auto.py` (the lab's DetectSWR, exact port, with the manual check replaced by one k-means boundary per "
      f"animal x probe block); plan `implementation_plan/2026-10-07-swr-detection-automation.md`, record "
      f"`change_log/2026-10-07-swr-detection-automation.md`. Channel config used by the run (its copy in the run folder) vs "
      f"`ephys/configs/swr_channels_{COHORT}.yaml`: {cfg_note or 'no copy in the run folder'}.")
    w("")
    w("## How to use")
    w("")
    w("- **Files** (BioHPC storage, read-only: `Q:/hc997/SocialFieldRat2026/3rd_rat/analysis/swr/`, server "
      "`/fs/cbsuruizfs1/storage/hc997/SocialFieldRat2026/3rd_rat/analysis/swr/`; `README_swr.txt`, `VERIFY.txt`, `MD5SUMS`):")
    w("  `<SFxx>/<session>/<session>.swr_events.npz|.csv` (one row per event: `start_s`, `stop_s`, `peak_s` in session seconds = "
      "LFP sample / 1250; `state` at the peak; flags; `excluded`), `.SWR.evt` (Neuroscope), `.swr_summary.json`, `.swr_qc.png`.")
    w("- **Event filter:** keep `excluded == False`. `excluded` = REM + theta everywhere, plus head movement + LFP-EMG on the "
      "ripple-only blocks (SF07, SF11, SF12 block 3). Session time -> field-PC time with the session's `pc_time.dat` "
      "(storage `analysis/pc_time/`).")
    w("- **Session filter (the `tier` column):** use `validated` and `good`; look at `check` before use (the reason says why); "
      "`low_contrast` = not SWR-specific, a negative control only (SF11 after 09-02 19:08, SF12 block 3); never use `exclude`. "
      "Drop events after `use_until` (valid_until / paddock end / SF12 contact failure).")
    w("- **Read the `info` column** for regime context that does not change the tier: post-advance settle windows, FM64 "
      "sessions, the five females from 09-11 19:40, SF12 shank-1 degradation, sleep review 'bad'.")
    w("- **Rates** are per minute of the final 1-s sleep state (`ephys/configs/sleep_final_2026c.yaml`). Compare across "
      "animals with care: the detection threshold is each block's own boundary (the user judged ripples by absolute amplitude).")
    w("")
    w("## Tiers")
    w("")
    w("| Tier | Sessions | Hours | NREM h | Kept events |")
    w("|---|---|---|---|---|")
    for k in order:
        s = df[df.tier == k]
        w(f"| `{k}` | {len(s)} | {s.hours.sum():.1f} | {s.nrem_min.fillna(0).sum() / 60:.1f} | {int(s.n_kept.fillna(0).sum()):,} |")
    w("")
    w("## Per animal x block")
    w("")
    w("| Animal | Block (from) | Channels ripple/SW/noise | Boundary | Reference | Sessions by tier | NREM h (usable) | "
      "Median selected % | Median kept NREM /min (usable) |")
    w("|---|---|---|---|---|---|---|---|---|")
    for (an, bf), g in df.groupby(["animal", "block_from"], sort=False):
        use = g[g.tier.isin(["validated", "good", "check"])]
        tiers = ", ".join(f"{k} {int((g.tier == k).sum())}" for k in order if (g.tier == k).any())
        sel = g.selected_frac.dropna()
        w(f"| {an} | {g.block.iloc[0]} ({bf if bf != 'None' else 'start'}) | {g.channels.iloc[0]} | {g.boundary.iloc[0] or '-'} | "
          f"`{g.reference.iloc[0]}` | {tiers} | {use.nrem_min.fillna(0).sum() / 60:.1f} | "
          f"{100 * sel.median():.1f} | {use.kept_rate_nrem.dropna().median() if len(use) else float('nan'):.1f} |")
    w("")
    w("## Validation against the user")
    w("")
    if len(val):
        w("The user scored these sessions in `swr_check_gui.py` (blind to the automatic labels; clicks in "
          "`ephys/configs/swr_review_2026c/`); the production files are compared with the user's events "
          f"([`ephys_spikes_swr_validation_{COHORT}.csv`](ephys_spikes_swr_validation_{COHORT}.csv)).")
        w("")
        w("| Animal | Session | Note | User events | Kept auto | Precision | Recall | F1 (kept) | F1 (all) | Server = local pilot |")
        w("|---|---|---|---|---|---|---|---|---|---|")
        for _, r in val.iterrows():
            w(f"| {r.animal} | `{r.session}` | {r.note} | {r.kept_n_user} | {r.kept_n_auto} | {r.kept_precision} | {r.kept_recall} | "
              f"**{r.kept_f1}** | {r.all_f1} | {r.get('server_equals_local', '')} |")
        w("")
        w("Reference points: the lab's inter-expert F1 is 0.70 +- 0.13 (Navas-Olive 2022); the user's own consistency across "
          "days of the same lab animal is 0.92 (median, 17 lab sessions).")
    else:
        w("Not run yet (`swr_quality.py validate`).")
    w("")
    w("## Sessions to look at (`check`)")
    w("")
    c = df[df.tier == "check"]
    if len(c):
        w("| Animal | Session | Block | Reason |")
        w("|---|---|---|---|")
        for _, r in c.iterrows():
            w(f"| {r.animal} | `{r.session}` | {r.block} | {r.reasons} |")
    else:
        w("None.")
    w("")
    w("## Excluded sessions")
    w("")
    x = df[df.tier == "exclude"]
    w("| Animal | Session | Reason |")
    w("|---|---|---|")
    for _, r in x.iterrows():
        w(f"| {r.animal} | `{r.session}` | {r.exclude_reasons} |")
    w("")
    w("## Definitions")
    w("")
    w("Units: events per minute; fractions in %; times are session seconds (sample / 1250 Hz) unless stated.")
    w("")
    w("### Candidate and selected fraction ($f_{sel}$)")
    w("$$ f_{sel} = \\frac{\\#\\{i \\in C_{ok} : \\lVert z_i - c_{sel} \\rVert < \\lVert z_i - c_{rest} \\rVert\\}}{|C_{ok}|} $$")
    w("where $C_{ok}$ = the non-artefact DetectSWR candidates (the maximum per 40-ms window of the swDiff / ripPower features), "
      "$z_i$ = their features standardised with the block reference's NREM mean and SD, and $c_{sel}, c_{rest}$ = the block "
      "reference's 2-cluster k-means centres (minority = selected). **Text:** the share of candidates on the ripple side of the "
      "block boundary. Range 0-100 %; validated sessions 2.8-8.2 %; > 10 % = the boundary cuts into the bulk (no ripple cluster). "
      "`own_fit_frac` = the same with the session's own NREM fit (a drift diagnostic).")
    w("")
    w("### Event rate ($r_X$, $r^{kept}_X$)")
    w("$$ r_X = \\frac{\\#\\{\\text{events with the 1-s state } X \\text{ at the peak}\\}}{\\text{minutes of state } X \\text{ in the session}} $$")
    w("**Text:** events per minute of NREM / REM / WAKE (all events, or `excluded == False`). Validated NREM 36-79/min, the "
      f"user's own 44-68/min. Check range for all events in NREM: {NREM_RATE_RANGE[0]:.0f}-{NREM_RATE_RANGE[1]:.0f}/min (with >= 10 min NREM).")
    w("")
    w("### NREM amplitude ratio ($A$)")
    w("$$ A = \\frac{\\operatorname{median}_{\\text{NREM events of the session}} \\text{amplitude}}{\\operatorname{median}_{\\text{NREM events of the block reference}} \\text{amplitude}} $$")
    w(f"**Text:** ripple amplitude relative to the session that set the boundary; it drifts with the probe / contact. "
      f"Check range {AMP_RANGE[0]}-{AMP_RANGE[1]} (SF09 09-09 night 0.6 = fewer events).")
    w("")
    w("### Event F1 against the user")
    w("$$ P = \\frac{n_{match}}{n_{auto}},\\quad R = \\frac{n_{match}}{n_{user}},\\quad F1 = \\frac{2PR}{P+R} $$")
    w("where a match = an automatic and a user event whose trough peaks are within 10 ms (greedy one-to-one on sorted peaks); "
      f"the user's events = their GUI clicks propagated and localised exactly as DetectSWR's check mode. A block is `validated` "
      f"when a user-scored session in it has kept-event F1 >= {F1_VALID}.")
    w("")
    w("### Flags at the event peak")
    w("- `x_rem`: the 1-s state is REM. `x_theta`: theta/delta (+-0.5 s, ripple channel) above the block reference's NREM 95th "
      "percentile. `x_moving`: head-IMU EMG proxy above the sleep scorer's own EMG threshold of the session. `x_emg_lfp`: the "
      "pipeline's EMGFromLFP (300-450 Hz cross-shank correlation, +-0.5 s) above the block reference's NREM 95th percentile.")
    w("")
    w("## Known limits")
    w("")
    w("- **SF11** has CA1 ripples only from the start to the 09-02 evening round (block 1a; `quality_flags` SF11_ripples_lost "
      "from 09-02 19:08:52). After that the ripple-band contrast is 2.0-3.4 (normal 3.2-8.6) and the lab's 09-06 assessment puts "
      "the probe above CA1; its events there are a negative control.")
    w("- **SF12 block 3** (09-10 08:35 ->) is low-contrast (19-20 % selected); the record ends at the connector failure "
      "(09-10 14:53:45, `SF12_contact_failing`); 09-09 18:47 -> 09-10 08:35 has no detection (block skipped).")
    w("- **SF07** (all blocks), SF11 and SF12 block 3 have no clear sharp-wave reversal: ripple-power-only boundary, movement + "
      "LFP-EMG excluded. Blocks with a reversal (SF08, SF09, SF10, SF12 block 1) use both features.")
    w("- Only SF07 (blocks 1, 4), SF09 and SF10 are validated against the user; SF08, SF07 blocks 2-3, SF11 block 1a and SF12 "
      "block 1 are `good` by the drift checks only.")
    w("- Strength tiers (strict / inclusive) are not cut here: use `SwMax_z` / `RipMax_z` per event.")
    w("- SF11's last night (09-06 19:52 -> 09-07 06:10) has no sleep states (not scored): no state flags there.")
    out.write_text("\n".join(L) + "\n", encoding="utf-8")


def selftest():
    base = dict(selected_frac=0.05, nrem_min=100, rate_nrem=60, amp_ratio=1.0)
    checks = [
        (dict(base, block_validated=True), "validated"),
        (dict(base), "good"),
        (dict(base, selected_frac=0.25), "check"),
        (dict(base, rate_nrem=150), "check"),
        (dict(base, rate_nrem=150, nrem_min=5), "good"),
        (dict(base, amp_ratio=0.6), "check"),
        (dict(base, low_contrast=True, selected_frac=0.25), "low_contrast"),
        (dict(base, exclude_reasons=["user sleep review: noise"], low_contrast=True), "exclude"),
        (dict(base, no_states=True), "check"),
    ]
    ok = True
    for rec, want in checks:
        got = tier_of(rec)[0]
        ok &= got == want
        print(f"{'PASS' if got == want else 'FAIL'} {want:13s} <- {got}")
    assert session_start("17_20260902_190852.526") == datetime(2026, 9, 2, 19, 8, 52, 526000)
    print("SELFTEST " + ("PASS" if ok else "FAIL"))
    sys.exit(0 if ok else 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["validate", "build"], nargs="?")
    ap.add_argument("--swr-root", default="Q:/hc997/SocialFieldRat2026/3rd_rat/analysis/swr")
    ap.add_argument("--gui-root", default="D:/Field2026_analysis_out/2026c/swr_check")
    ap.add_argument("--local-root", default="D:/Field2026_analysis_out/2026c/swr_auto_pilot_v7")
    ap.add_argument("--lfp-root", default="D:/3rd_rat_spikes/analysis/lfp", help="local LFP copies (rebuild of hide-flagged scorings)")
    ap.add_argument("--validation", default=str(HERE / f"configs/swr_validation_{COHORT}.yaml"))
    ap.add_argument("--channels", default=str(HERE / f"configs/swr_channels_{COHORT}.yaml"))
    ap.add_argument("--cohort-yaml", default=str(HERE.parent / f"cohorts/{COHORT}.yaml"))
    ap.add_argument("--review", default=str(report_dir(COHORT) / f"ephys_spikes_sleep_review_{COHORT}.csv"))
    ap.add_argument("--session-index", default=str(report_dir(COHORT) / f"ephys_spikes_session_index_{COHORT}.csv"))
    ap.add_argument("--validation-csv", default=str(report_dir(COHORT) / f"ephys_spikes_swr_validation_{COHORT}.csv"))
    ap.add_argument("--report-dir", default=None, help="build: write here instead of results/<c>/ephys_spikes/reports")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
    {"validate": validate, "build": build}[a.cmd](a)


if __name__ == "__main__":
    main()
