# Derived-data root moved from E: to D: (2026-09-10)

**Why.** E: (18 TB) holds the raw offloads at ~1.1 TB/day for five loggers and had 3.99 TB free on 2026-09-09 with the cohort
planned to end Saturday 2026-09-12. The operator decided (2026-09-09) to move the derived-data tree off E: and leave the raw
sessions and the six `recovery.bin` images untouched.

**What moved.** `E:\3rd_rat_spikes\analysis\` → `D:\3rd_rat_spikes\analysis\` (index, pc_time, stage, sort, tools, open_phy.bat,
README.txt): 2857 files, 1.3327 TB. robocopy `/E /COPY:DAT /DCOPY:DAT /MT:8`, interrupted once for a card offload and resumed
(robocopy skips identical files), then a final incremental pass after the evening QC had rewritten `pc_time\` (298.5 GB re-copied).
Verification before deleting the E: copy: robocopy dry-run with nothing left to copy; file-by-file count and size identical
(2857 / 1.3327 TB, the only difference being the D: README that carries the move note); head/middle/tail SHA-256 of 20 files
(the twelve largest 45–91 GB `amplifier.dat` / `.dat` files, four mid-size, four small) and of 15 `pc_time.dat` files rewritten
that night all identical.

**What changed in the repo.** `cohorts/2026c.yaml` `ephys.analysis_root` → `D:/3rd_rat_spikes/analysis` (every consumer reads
it through `_common.analysis_root()`; nothing hard-codes the E: path). `E:\3rd_rat_spikes\CLAUDE.md` and the tree's own
README.txt carry the new location. `ephys/README.md` still names the E: path in two places (line 25 prose, line 205 example
`--cache-dir`) — left for the concurrent sorting session that has that file open.

**Consequences.** E: gains 1.33 TB (≈ 1.2 days of raw). The other session's Kilosort / Phy work continues from the D: copy
(`sort_runs` rows keep their historical `local_output_dir` on E: as a record). No raw session folder was written or read for
anything but the copy itself.
