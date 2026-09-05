"""Offload size check: is the copy on disk byte-complete against the WILD console's card listing, so the card can be formatted?

The console shows, per card, "Records: N" and "Total File Size (MB)" (= bytes / 1e6, a multiple of 512 bytes). A card
record is the raw 65-lane stream (64 amplifier + 1 misc lane, all int16) plus ~6.5 MB of per-record overhead, while the
export on disk splits it into amplifier.dat (64 lanes), analogin.dat (2 bytes/sample) and time.dat (4 bytes/sample).
So the card bytes predicted from a copied folder are  bytes(amplifier.dat) x 65/64 , and

    listing - sum(predicted)  =  overhead (~6.5 MB x N records)  +  data of any record NOT copied

which is how a few-second undownloaded test record (common: slot 0 of a freshly formatted card) is told apart from a
missing session. Sidecar sizes (time.dat = 4 n, analogin.dat = 2 n, amplifier a whole number of 128-byte samples) and a
"still growing" check (amplifier.dat modified in the last 2 min) guard against reading a copy that is still in progress.

Which folders belong to THIS card: the slot number in a folder name (<slot>_<date>_<time>) is the card's write order and
restarts at 0 every time the card is formatted, so it is NOT unique across offloads (SF7 has a 4_20260903_001558 and a
4_20260903_171804). The card's listing therefore corresponds to the N NEWEST session folders of that animal on disk
(N = Records). If the operator skipped a few-second test record, those N newest would reach one folder too far back and
the predicted bytes would exceed the listing; the tool then drops the oldest folder(s) until the prediction fits and
reports the record(s) that were not downloaded. Raw folder names are never changed.

Usage:
    python ephys/check_offload_sizes.py --cohort 2026c --card SF7=15:432815.446 --card SF8=8:... --card SF9=9:...
      --card <animal>=<records>:<total MB from the console>   (repeat per card)
      --since  optional override "YYYY-MM-DD HH:MM": only folders starting at/after it count (else the N-newest rule)
      --roots  extra roots to scan besides the cohort's raw root (e.g. an SSD inbox), same <root>/<SFxx>/<MAC>/<session> layout

Writes results/<cohort>/ephys_spikes/reports/ephys_spikes_offload_sizes_<cohort>_<date>.csv (+ mirror under <analysis_root>/index/).
"""
from __future__ import annotations

import argparse
import csv
import os
import time
from datetime import datetime
from pathlib import Path

from _common import analysis_root, ephys_block, iter_raw_sessions, parse_session_name, raw_ephys_root, report_dir, resolve_cohort

OVERHEAD_PER_RECORD = 6.5e6      # bytes the card keeps per record beyond the 65-lane stream (measured on 2026-09-02..05 checks)
BYTES_PER_SAMPLE_CARD = 130.0    # 65 lanes x int16
BYTES_PER_SAMPLE_AMP = 128       # 64 lanes x int16
GROWING_S = 120.0
TEST_RECORD_MAX_S = 60.0         # an undownloaded record shorter than this is a round-time test record, not a session


def norm(animal: str) -> str:
    a = animal.upper()
    return f"SF{int(a[2:]):02d}" if a.startswith("SF") and a[2:].isdigit() else a


def parse_card(spec: str) -> tuple[str, int, float]:
    animal, rest = spec.split("=", 1)
    n, mb = rest.split(":", 1)
    return norm(animal), int(n), float(mb)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cohort", required=True)
    ap.add_argument("--card", action="append", default=[], help="SFxx=<records>:<total MB> from the console listing")
    ap.add_argument("--since", default=None, help='optional "YYYY-MM-DD HH:MM"; else the N newest folders per card (N = listed records)')
    ap.add_argument("--roots", nargs="*", default=[], help="extra roots with the same <SFxx>/<MAC>/<session> layout")
    ap.add_argument("--raw-root", default=None)
    a = ap.parse_args()
    cfg = ephys_block(a.cohort)
    fs = float(cfg["sampling_rate_hz"])
    since = datetime.strptime(a.since, "%Y-%m-%d %H:%M") if a.since else None
    cards = {an: (n, mb) for an, n, mb in (parse_card(c) for c in a.card)}
    roots = [raw_ephys_root(a.cohort, a.raw_root)] + [Path(r) for r in a.roots]

    per_animal: dict[str, list[dict]] = {}
    for root in roots:
        for animal, mac, sdir in iter_raw_sessions(root, cfg.get("session_glob", "*"), cohort=a.cohort):
            meta = parse_session_name(sdir.name)
            if meta is None or (since is not None and meta["start"] < since):
                continue
            amp = sdir / "amplifier.dat"
            if not amp.exists():
                continue
            st = amp.stat()
            n = st.st_size // BYTES_PER_SAMPLE_AMP
            t_ok = (sdir / "time.dat").exists() and os.path.getsize(sdir / "time.dat") == 4 * n
            an_ok = (sdir / "analogin.dat").exists() and os.path.getsize(sdir / "analogin.dat") == 2 * n
            per_animal.setdefault(norm(animal), []).append({
                "animal": norm(animal), "root": str(root), "session": sdir.name, "start": meta["start"], "amp_bytes": st.st_size,
                "hours": n / fs / 3600.0,
                "predicted_card_bytes": st.st_size * BYTES_PER_SAMPLE_CARD / BYTES_PER_SAMPLE_AMP,
                "sidecars_ok": bool(st.st_size % BYTES_PER_SAMPLE_AMP == 0 and t_ok and an_ok),
                "growing": (time.time() - st.st_mtime) < GROWING_S,
            })

    rows, verdicts = [], {}
    window = f"sessions starting >= {since:%Y-%m-%d %H:%M}" if since else "window = the N newest folders per card (N = listed records)"
    print(f"offload size check, cohort {a.cohort}, {window}\n")
    for an in sorted(set(per_animal) | set(cards)):
        sess = sorted(per_animal.get(an, []), key=lambda r: r["start"])
        n_card, mb_card = cards.get(an, (None, None))
        skipped_older = 0
        if n_card and since is None:
            sess = sess[-n_card:]
            while len(sess) > 1 and sum(r["predicted_card_bytes"] for r in sess) > mb_card * 1e6:
                sess = sess[1:]
                skipped_older += 1      # the card's oldest record(s) were not downloaded: an older folder had crept into the window
        pred = sum(r["predicted_card_bytes"] for r in sess)
        span = f" (window {sess[0]['start']:%m-%d %H:%M} -> {sess[-1]['start']:%m-%d %H:%M})" if sess else ""
        listing = f", card lists {n_card} records / {mb_card:,.3f} MB" if n_card else ", no card listing given"
        print(f"== {an}: {len(sess)} folders on disk{span}{listing}")
        for r in sess:
            flag = ("GROWING " if r["growing"] else "") + ("" if r["sidecars_ok"] else "SIDECARS-INCONSISTENT ")
            print(f"   {r['session']:26} {r['amp_bytes'] / 1e6:12,.3f} MB  {r['hours']:6.2f} h  {flag}")
            rows.append({**{k: v for k, v in r.items() if k != "start"}, "card_records": n_card or "", "card_total_mb": mb_card or ""})
        if not n_card:
            verdicts[an] = "no listing"
            continue
        resid = mb_card * 1e6 - pred
        beyond = resid - OVERHEAD_PER_RECORD * n_card
        missing_s = max(beyond, 0.0) / (BYTES_PER_SAMPLE_CARD * fs)
        pct = pred / (mb_card * 1e6) * 100.0
        problems = [r["session"] for r in sess if r["growing"] or not r["sidecars_ok"]]
        if problems:
            v = f"WAIT - still writing or inconsistent: {', '.join(problems)}"
        elif len(sess) > n_card or resid < -OVERHEAD_PER_RECORD or skipped_older > 1:
            v = f"CHECK - disk holds MORE than the listing ({pct:.3f} %): card mix-up, or more than one record undownloaded"
        elif missing_s <= TEST_RECORD_MAX_S:
            v = f"SAFE TO FORMAT - {pct:.3f} % of the listing; residual {resid / 1e6:,.1f} MB = record overhead" + \
                (f" + ~{missing_s:.0f} s test record not copied" if missing_s > 2 else "")
        else:
            v = f"CHECK - {pct:.3f} %; an undownloaded record of ~{missing_s / 60:.1f} min remains on the card ({n_card - len(sess)} record(s) not on disk)"
        verdicts[an] = v
        print(f"   predicted card bytes {pred / 1e6:,.3f} MB -> {v}\n")

    tag = datetime.now().strftime("%Y-%m-%d")
    out = report_dir(a.cohort) / f"ephys_spikes_offload_sizes_{resolve_cohort(a.cohort)}_{tag}.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=(list(rows[0].keys()) + ["verdict"]) if rows else ["animal", "verdict"])
        w.writeheader()
        for r in rows:
            w.writerow({**r, "verdict": verdicts.get(r["animal"], "")})
    ar = analysis_root(a.cohort)
    if ar:
        (ar / "index").mkdir(parents=True, exist_ok=True)
        (ar / "index" / out.name).write_bytes(out.read_bytes())
    print("verdicts:")
    for an, v in verdicts.items():
        print(f"  {an}: {v}")
    print(f"\nwritten {out}")


if __name__ == "__main__":
    main()
