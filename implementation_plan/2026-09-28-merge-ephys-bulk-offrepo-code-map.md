# Merge the ephys branch, move ephys bulk off-repo, write the agent code map (2026-09-28)

**Status.** In progress 2026-09-28.

**Why.** Two workstreams — ephys preprocessing (`ephys/`, branch `ephys-cohort3-pipeline`, 86 commits since
2026-09-02) and CV preprocessing (`cv/cv_field/`, `thermal/`, on `main`) — diverged for four weeks and collided in the
shared files (`CLAUDE.md`, the two index READMEs). Decision: keep both in this one repo as sibling subsystems (they share
the cohort registry, `common/output_paths.py`, the ledger discipline and the cross-modal clock chain); the fix is to merge
back to `main` often, not to split the repo. Separately, the ephys branch committed ~55 MB of regenerable bulk into
`results/2026c/ephys_spikes/reports/`, against the "bulk goes off-repo" rule, and re-committed it on every regeneration.

**Scope.**
1. Merge `ephys-cohort3-pipeline` into `main` (conflicts: `CLAUDE.md`, `change_log/README.md`,
   `implementation_plan/README.md`). No history rewrite — everything is already on `origin`.
2. Move two regenerable bulk outputs from `results/<cohort>/ephys_spikes/reports/` to the ephys index root
   (`<analysis_root>/index/` when the cohort declares `ephys.analysis_root`, else `<OUT_ROOT>/<cohort>/ephys_index/`):
   - `ephys_spikes_coverage_1s_<cohort>_<date>.csv` (14 × ~3.4 MB, 86,401 rows/day; no code reads them),
   - `ephys_spikes_session_index_<cohort>.json` (7.5 MB, per-channel probe detail; read only by
     `offload_qc_report.py`, re-committed 17 times).
   The session-index CSV + MD, hourly coverage, raster figure and every QC report stay in-repo.
   Code: new `index_root()` in `ephys/_common.py`; `coverage_tables.py` and `build_session_index.py` write there;
   `offload_qc_report.py` reads there, falls back to the legacy in-repo path, and warns loudly (with the restore
   command) when the JSON is missing. `.gitignore` guards both patterns.
3. Rewrite `CLAUDE.md` with a verified per-subsystem **code map** (pipeline order, entry points, in-repo vs off-repo
   outputs, envs, self-tests, gotchas) so an agent does not need to read the code to orient; point `AGENTS.md` at it;
   add `cv_field` to the CONVENTIONS.md direction list.

**Verification.** `python ephys/selftest.py` PASS; `coverage_tables.py --cohort 2026c` regenerates the 1-s CSVs at the
new location byte-identical to the removed tracked copies; no inbound link to a removed file left (link-integrity rule);
the other self-tests listed in `CLAUDE.md` still PASS.

**Operator action on the ephys PC after pulling.** The JSON has no off-repo copy there yet; restore it once with
`git show fcaa792:results/2026c/ephys_spikes/reports/ephys_spikes_session_index_2026c.json > D:/3rd_rat_spikes/analysis/index/ephys_spikes_session_index_2026c.json`
(or rerun `build_session_index.py`). The 1-s CSVs are already mirrored there by `coverage_tables.py`.
