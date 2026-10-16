# Preprocessing tracker: the preprocessing tree and its progress page (2026-10-10)

**Status:** DONE (minimal version) 2026-10-10 —
[change log](../change_log/2026-10-10-preprocessing-tracker.md); page https://claude.ai/artifact/6YkHULY7zU691GaoJKG1rm.

**The user (2026-10-10):** write a preprocessing agent with a tree like the research-logic map, to track preprocessing
progress. Finished stages get their own colour. Before writing it, ask every agent (session) what it is doing. Once
written, have the Codex session astra review it.

The tree has two parts:
- **Ephys.**
  - Kilosort → spikes, with place cells and then replay after them.
  - On the LFP branch: SWR, delta and theta.
- **Behaviour.**
  - Camera calibration (cross-day motion, multi-camera mapping) feeds WISER, and WISER feeds the IMU.
  - YOLO tracking, behaviour syllable labelling and head direction form the behaviour layer.
  - To reach that layer, WISER helps animal identity and tracking: an intermediate level.

## Design

- **Its own small tool (`pipeline_map/`) beside `research_logic/`**, reusing the research-logic citation and figure
  checks. Research hypotheses stay in `research_logic/`.
- **One YAML per cohort.** Stages sit in trunks (ephys, behaviour) × lanes (branches) × layers (levels). Each stage
  carries:
  - status, owner session;
  - outputs, validation, tools;
  - what waits on the user, blocker / next step / reason;
  - `requires` / `aids` edges;
  - cited sources (file + line + anchor);
  - figures, history.
- **Statuses:** done, in_progress, waiting_user, blocked, planned, not_started, closed (a dropped route stays in the
  tree).
- **Page:**
  - progress per trunk;
  - the waiting-on-you list;
  - who works on what;
  - the tree as a levels × branches grid with dependency arrows (cross-trunk links in pink) and coloured stages;
  - a drawer per stage; the update log; a filterable stage list.
- **Agent `preprocessing-tracker`** (Opus) with skill `preprocessing-status`. The main session polls the sessions; the
  agent records and never runs pipelines. A stage is done only with a cited output and validation.

## Order

1. Poll the sessions.
2. Build the tool + selftest.
3. Write the first tree from the replies and the repo record.
4. Check, build, publish.
5. Agent, skill, mirrors, README, docs.
6. astra text review; fold its points in.
