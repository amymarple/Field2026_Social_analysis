# Ephys branch merged, ephys bulk moved off-repo, agent code map + `recording-inquiry` agent (2026-09-28)

Plan: [implementation_plan/2026-09-28-merge-ephys-bulk-offrepo-code-map.md](../implementation_plan/2026-09-28-merge-ephys-bulk-offrepo-code-map.md).
No analysis result, definition, exclusion rule or conclusion changed.

## What changed

1. **Merge** (`fcaa792`). `ephys-cohort3-pipeline` (86 commits, 2026-09-02 → 09-22: `ephys/`, `cohorts/2026c.yaml`,
   `results/2026c/ephys_spikes/`) merged into `main` next to the cv_field / thermal work. Conflicts in `CLAUDE.md` and
   the two index READMEs resolved as a union (newest first). Decision: ephys and CV preprocessing stay in this one repo
   as sibling subsystems (shared cohort registry, `common/`, ledgers, clock chain); keep branches short-lived.
2. **Ephys bulk off-repo** (`01099ba`). The 13 per-second coverage CSVs (~3.4 MB each, no reader) and the session-index
   JSON detail (7.5 MB, re-committed 17 times on the branch) moved from `results/2026c/ephys_spikes/reports/` to the
   new `ephys/_common.index_root()` = `<ephys.analysis_root>/index/` (fallback `<OUT_ROOT>/<cohort>/ephys_index/`).
   `coverage_tables.py` / `build_session_index.py` write there; `offload_qc_report.py` reads there, falls back to the
   legacy path, and prints the restore command when missing. `.gitignore` guards both patterns. `ephys/README.md`:
   output layout, and `analysis_root` is `D:` since 2026-09-10 (was still `E:`). History was not rewritten (the branch
   was already on `origin`), so the objects stay in the pack; future regenerations no longer add to it.
3. **Doc repair** (`39464fc`). Python-escape corruption (`\3 \a \b \t \r` written as control bytes, e.g.
   `E:\3rd_rat_spikes\analysis\tools` → `E:^Crd_rat_spikes^Gnalysis^Iools`) fixed in five files that came with the
   branch (`CLAUDE.md`, `change_log/2026-09-02-ephys-spike-sorting-pipeline.md`,
   `data_manifests/2026-09-02-wild-ephys-cohort3.yaml`, `data_manifests/README.md`, `ephys/README.md`). The manifest
   YAML parses again (two `E: …` plain scalars also broke it; rewritten as `E:\ …`).
4. **Agent orientation.** `CLAUDE.md` rewritten around a verified **code map** (per subsystem: pipeline order, entry
   points, in-repo vs off-repo outputs, env, self-tests, gotchas), a snapshot of the two sibling repos
   (`Field_2026_Social_Recording`: setup, sync/clocks, data flow, calibration, ledgers; `field2026-sync`: storage map,
   retention, where to look) and a **Known gaps** list. Built from six read-only mapping passes, with the high-impact
   claims spot-checked by hand. Corrections it carries vs the old text: file names/PTS are field-PC time and only the
   burned-in OSD is the NVR clock (≈ PC − 59½ min, drifting); cameras switch color/IR with the light (check the frame,
   not the channel); `cv_field` / `ephys_spikes` are directions; most WISER drivers do not take `--cohort`.
   `AGENTS.md` points to the map; `CONVENTIONS.md` lists `cv_field`.
5. **New subagent `recording-inquiry`** (`.claude/agents/recording-inquiry.md`): answers field-record questions
   (where a stream/day lives and which copy is original, recorder parameters on a date, clock alignment, gaps and clock
   steps, what the field PC reported) from the two sibling repos. It fast-forwards them first, reads only what the
   question needs, cites every fact and lists conflicts instead of resolving them; read-only otherwise. CLAUDE.md keeps
   the stable snapshot; the agent serves specific/current questions.
6. **`.gitattributes`**: `analysis_exchange/published/** -text`. Sealed bundles are hashed byte-for-byte; on a machine
   with `core.autocrlf=true` the LF manifest was checked out as CRLF and `test_bridge` failed ("Manifest hash does not
   match BUNDLE.SEALED"). Pre-existing on this PC, unrelated to the merge.

## Verification

- `python ephys/selftest.py` 20/20 PASS; `coverage_tables.py --cohort 2026c` regenerated all 13 per-second CSVs at the
  new location **byte-identical** to the removed tracked copies (in-repo hourly/raster outputs differed only in the
  generation timestamp and were restored).
- All self-tests listed in `CLAUDE.md` PASS on this PC, including `python -m analysis_exchange.tests.test_bridge`
  (21 tests, after the `.gitattributes` fix), the three cv_field self-tests, `dino_gate.py --selftest` (cv env) and
  both thermal self-tests.
- No inbound link to a removed file (the 2026-09-02 ledger mentions the CSV name as history, not as a link).

## Operator actions

- **Ephys PC, after pulling:** the session-index JSON has no off-repo copy there yet. Restore it once:
  `git show fcaa792:results/2026c/ephys_spikes/reports/ephys_spikes_session_index_2026c.json > D:/3rd_rat_spikes/analysis/index/ephys_spikes_session_index_2026c.json`
  (or rerun `build_session_index.py`). The per-second CSVs are already mirrored in `index/` there.
- **This PC:** `D:\3rd_rat_spikes\analysis\index\` was created to hold the relocated files; the rest of that
  `analysis_root` does not exist here (pc_time's master is on `Q:\…\3rd_rat\analysis\pc_time`) — see Known gaps in
  `CLAUDE.md` before relying on `ephys.analysis_root`.
