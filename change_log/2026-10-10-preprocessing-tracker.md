# Preprocessing tracker: the preprocessing tree and its progress page (2026-10-10)

Plan: [implementation_plan/2026-10-10-preprocessing-tracker.md](../implementation_plan/2026-10-10-preprocessing-tracker.md).
Page (private): https://claude.ai/artifact/6YkHULY7zU691GaoJKG1rm.

## What changed

| file | what |
|---|---|
| `pipeline_map/pipeline_map.py` | `check`, `build`, `show`, `index`, `figs`, `--selftest` (8 checks); citations and figures verified through `research_logic/logic_map.py`; the template may be written in Unicode, the build escapes it to ASCII |
| `pipeline_map/map_template.html` | the tree page: progress, waiting on you, who works on what, levels × branches grid with dependency arrows, drawer, update log, stage list; light / dark |
| `pipeline_map/graphs/preprocessing_2026c.yaml` | the first tree: 36 stages, 78 edges |
| `pipeline_map/maps/preprocessing_2026c.{html,json}` | generated |
| `pipeline_map/README.md` | schema, statuses, rules |
| `.claude/agents/preprocessing-tracker.md` | agent (Opus): records only; never marks done without a cited output and validation |
| `.claude/skills/preprocessing-status/SKILL.md` | "更新预处理进度": poll the sessions → agent → rebuild → republish |
| `.codex/agents/preprocessing-tracker.toml`, `.agents/skills/preprocessing-status/SKILL.md` | thin mirrors |

## The first tree (as of 2026-10-10)

**Ephys** (19 stages):
- **Done (11):** offload QC, field-PC time, FM64 rule, LFP, head IMU, LFP-EMG, sleep scores, EMG-ICA, SWR, delta,
  electrode drift.
- **In progress:** Kilosort1 per block.
- **Waiting on the user:** phasic / tonic REM (review page).
- **Blocked:** theta subtypes (waits for video behaviour labels).
- **Planned:** curation, cross-block units.
- **Not started:** place cells, replay.
- **Closed:** Kilosort4 per session (superseded by K1).

**Behaviour** (17 stages):
- **Done (5):** camera calibration rev g, WISER tracks, WISER ↔ IMU, head attitude, mics.
- **In progress:** cross-day motion, USV, in-box identity, panorama detector.
- **Waiting on the user:** CH05–CH08 mapping (floor labels), behaviour labels (ethogram).
- **Blocked:**
  - WISER georeference (anchor layout);
  - head direction (the IMU route is closed; it needs a video pose).
- **Planned:** video ↔ ephys clock, identity strategy.
- **Not started:** tracking with identity, syllables.

**Session poll (10-10, 9 sessions asked):**
- **Replied:** SWRdetection, IMU-video校准, Calibration restart path, social_label.
- **Replied, not a preprocessing owner:** the sleep-schedule research session (it consumes these outputs); KTH
  (another repo).
- **Unreachable:** Mic (offline) — its USV state was read from the repo (headless DeepSqueak; a whitened detector;
  the user's 260-strip labels: sensitivity 0.58 / specificity 0.80, MIC01 0.86–0.90 / 0.66–0.72, MIC02 0.67 / 0.86).
- **No reply at the time of writing:** others (Kilosort, deltawave, Yolo offline).

## Verification

- `python pipeline_map/pipeline_map.py --selftest`: 8 checks pass:
  - valid tree;
  - dangling `requires`;
  - done without validation;
  - waiting without what;
  - unknown layer;
  - cycle;
  - anchor not at the line;
  - done downstream of a planned input (warning).
- `check`: 0 errors, 0 warnings. Every stage's citation was resolved (file, lines, anchor), including one into the
  recording repo.
- Page script: `node --check` passes. One headless screenshot checked the overview, the tree, the colours and the
  arrows.

## Not done

- **Owner names change** when a session restarts; the page says so.
- **Unconfirmed stages.** Stages owned by offline sessions (Kilosort, deltawave, Yolo, Mic) rest on the repo record
  until they reply.

## astra text review (Codex session 01a128fb, 2026-10-10) and what changed

astra's four points, all adopted:
1. **Separate stages for finished parts and blocked parts.**
   - Theta: a finished per-second cache (`e.theta_cache`, done) is now split from the blocked Type I / II
     interpretation (`e.theta_types`).
   - Head direction needs a video pose: new stage `b.pose` (not started), required by `b.head_direction`.
2. **"In progress" needs evidence of current work, not only a next step.**
   - New `evidence` field, required for in_progress.
   - `check` mode in the skill skips polling, the agent and publishing.
3. **Questionable statuses:**
   - USV -> blocked: the owner (Mic) is offline and no next step is recorded.
   - In-box identity stays in progress, with its evidence: the SAM 3 / DINOv3 test plan has amendments 1-3 and a
     computed grouping table, so it is running and not waiting on an audit.
   - WISER tracks: their "done" covers the production tracks; the blind video verdicts validate the QC-event reading.
4. **Every stage states what "done" covers and its acceptance gate** (`done_when`, required); the status refers to
   that scope only. The rule is in the agent definition and the README.

**Also new:** `pipeline_map.py relocate`. CLAUDE.md shifted by 5-8 lines under this session's own map edit and broke
31 citations; `relocate` re-finds each anchor and rewrites its line, keyed on file + line + anchor so shifts cannot
chain.

**After the review:**
- 38 stages: 17 done, 4 in progress, 3 waiting on the user, 4 blocked, 4 planned, 5 not started, 1 closed.
- `check`: 0 errors, 0 warnings. Selftest: 10 checks pass.
- Republished (version 2).

