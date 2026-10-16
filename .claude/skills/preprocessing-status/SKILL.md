---
name: preprocessing-status
description: >-
  Update the preprocessing tree (pipeline_map/) and its page: ask the active sessions what they are working on, hand
  their replies and the new repo record to the preprocessing-tracker agent (Opus), rebuild the interactive tree and
  republish it. Trigger phrases: "更新预处理进度", "preprocessing status", "/preprocessing-status", "预处理进度", "问下所有
  agent在干啥". For research results use the research-logic skill instead.
version: 0.1.0
---

# Preprocessing tree update

## Invocation

```text
更新预处理进度                       # ask the sessions, then update the tree
/preprocessing-status [ask|repo]     # ask = poll the sessions first (default); repo = from the repo record only
/preprocessing-status check          # validate + rebuild only: no polling, no agent, no publish
```

`check` runs only `python pipeline_map/pipeline_map.py check` and `build` and stops. If citations failed because a
cited file moved (CLAUDE.md), run `relocate` first.

The graph is `pipeline_map/graphs/preprocessing_2026c.yaml`. Its published page is
https://claude.ai/artifact/6YkHULY7zU691GaoJKG1rm (republish to that URL).

## Steps (the main session orchestrates; replies to cross-session messages reach the main session)

1. **Ask the sessions** (unless `repo` or `check`):
   - Run `ListAgents`.
   - Send each live session that may own a preprocessing stage one short status request. Skip other repos, and
     sessions that need the user's action.
   - The request asks for, in ≤ 12 lines:
     1. the stage(s) it owns;
     2. the status and current milestone;
     3. its outputs and how they were validated;
     4. what waits on the user;
     5. its next step;
     6. its key doc.
   - It also says to reply "n/a" if the session does no preprocessing.
   - Wait for the replies (they arrive as messages); do not poll. Offline sessions cannot be reached: use the repo
     record for their stages and say so.
2. **Dispatch** `subagent_type: preprocessing-tracker` with:
   - the replies verbatim, each with its session name;
   - the graph path;
   - the date of the last round (`meta.as_of`).

   It edits the YAML, runs `pipeline_map.py check` and `build`, and returns the changes, the waiting-on-you list and
   any contradictions.
3. **Republish:**
   - `python pipeline_map/pipeline_map.py figs` gives the `files` map;
   - publish `pipeline_map/maps/preprocessing_2026c.html` with the Artifact tool and that map as `files`, to the URL
     above.
   - If the publish is refused because a newer version exists, check that its data is contained in yours (the page is
     rebuilt from the shared YAML), then publish again.
4. **Report to the user in short Chinese:** the stages that changed status, the "waiting on you" list, who works on
   what, contradictions, the link.

## Guardrails

- A stage is `done` only with a cited output and validation in the repo record, never on a session's word alone.
- Nothing is deleted; a dropped route is `closed` with its reason.
- No pipeline is run and no code is changed by this skill.
