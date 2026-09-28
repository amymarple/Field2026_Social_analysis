---
name: multi-agent-behavior-modeling-audit
description: >-
  This skill should be used when analyzing, comparing, reviewing, or citing SOTA for MULTI-AGENT
  BEHAVIOR MODELING or LEARNED / RL POLICIES for physically-moving agents — vehicles, pedestrians,
  robots, or animals (e.g. this project's rats): trajectory prediction, closed-loop simulation
  agents, learned ego/focal-agent policies, opponent models, reward/IRL modeling, world-model
  planning, generative vs game-theoretic vs rule-based behavior models. It enforces audit discipline:
  do NOT collapse "predict others" vs "simulate agents closed-loop" vs "the ego policy" (three
  different SOTA answers); benchmarks are ground truth and surveys are commentary; open-loop metrics
  (minADE/minFDE) do NOT stand in for closed-loop/real-world quality; every SOTA claim needs a number
  + benchmark + metric + URL; report conflicts, do not resolve them; state what is uncovered. It
  carries a captured driving/robotics SOTA snapshot (references/) and tests, rather than assumes, the
  "everything went generative" framing. Explicitly NOT for LLM-agent orchestration. Run it explicitly
  with /multi-agent-behavior-modeling-audit. Trigger phrases: "multi-agent modeling", "behavior
  model", "trajectory prediction", "closed-loop", "sim agents", "WOSAC", "nuPlan", "NAVSIM", "RL
  policy", "learned policy", "IRL", "inverse RL", "reward learning", "world model", "generative
  behavior model", "opponent model", "game-theoretic", "MotionLM", "SMART", "diffusion policy",
  "diffusion planner", "motion planning", "trajectory planning", "ego policy", "planner",
  "agent-policy identifiability", "choice model", "is this SOTA", "which model family wins",
  "compare model families".
version: 0.1.0
---

# Multi-agent behavior-modeling audit

## Core principle

**"SOTA in multi-agent behavior modeling" is not one answer — it is three, and they diverge.** An
analyzing agent that reports a single "best model family" has almost certainly collapsed sub-problems
that different families win. Keep them separate at all times:

1. **Predicting OTHER agents** — marginal/joint forecasting, scored open-loop (minADE/minFDE/mAP).
2. **Simulating agents closed-loop** — rolling agents forward interactively, scored on distributional
   realism (WOSAC Realism Meta).
3. **The ego / focal-agent policy** — the decision-maker's own plan, scored closed-loop
   (nuPlan CLS, NAVSIM PDMS/EPDMS, CARLA DS).

As of the captured snapshot: (ii) is won by **tokenized autoregressive** models; (iii) is **contested**
between diffusion, rule-based, and from-scratch RL; (i) rests on metrics whose closed-loop validity is
under active attack. Full numbers, URLs, and conflicts: `references/driving_multiagent_audit_2026-07.md`.

## When to invoke

Invoke before any of: claiming what the SOTA / leading model family is for behavior modeling or
policy learning; comparing generative (autoregressive/diffusion/world-model) vs game-theoretic vs
rule-based vs IRL approaches; reading a trajectory-prediction / sim-agents / planning leaderboard;
deciding whether to *build* a generative behavior model, an IRL/reward model, or an RL policy for a
new dataset (including the rats); or writing up any "the field moved to X" narrative.

## Required discipline (carry before any SOTA claim)

- **Staleness firewall (hard rule — same tier as the open-loop/closed-loop firewall below).** The
  reference table is a dated snapshot (2026-07). Treat its numbers as a **PRIOR, not current SOTA**.
  Before citing any entry as state of the art, check its date: if older than ~6 months, re-verify
  against current leaderboards (Waymo Open Motion / Sim Agents, nuPlan / NAVSIM) or label the claim
  **"as of 2026-07, unverified since."** The reference file is true as of 2026-07-11, not evergreen.
- **Benchmarks are ground truth; surveys and abstracts are commentary.** Anchor on current
  leaderboards (WOSAC, nuPlan, NAVSIM, WOMD) before trusting any paper's self-description of "SOTA."
- **Every SOTA claim = number + benchmark + exact metric + URL.** No bare "X beats Y." No number,
  no claim.
- **Open-loop ≠ closed-loop ≠ reactive.** Never present minADE/minFDE (or any displacement error) as
  evidence of closed-loop or real-world driving/behavior quality — the measured correlation is
  ρ ≈ −0.36 (not significant). Always tag each number: open-loop vs closed-loop, reactive vs
  non-reactive, marginal vs interactive. A method's rank can *flip* across these.
- **Test the "everything went generative" framing; don't assume it.** Actively look for
  counter-evidence and report it: rule-based baselines (PDM-Closed) that still lead classic closed-loop;
  from-scratch RL (CaRL) that beats generative models on the hardest reactive split; results that
  reverse depending on which reactive-agent simulator is used.
- **Reward learning is not merely a fine-tuning stage** — it appears as a whole competitive policy.
  But before proposing to learn a reward/policy at all, ask the identifiability question first
  (below).
- **Report conflicts; do not resolve them.** When two sources disagree on the same split, cite both
  and name the methodological difference. Resolving a genuine conflict from abstracts is a fabrication.
- **State the caps and what is uncovered.** A snapshot with gaps flagged is trustworthy; one that
  implies full coverage is not. This snapshot's known gaps: world-model planning, game-theoretic/IRL
  quantification, 2025 WOMD marginal-prediction leaderboard (see reference file).

## Project hook — Field_2026_Social (rats), read before building anything

This project already ran the identifiability analysis for the rats' movement decisions and reached a
**NO-GO** (see the `agent-policy-identifiability-nogo` memory): WISER leaving/destination decisions are
governed by shared layout + dwell; individual and social policy are **not identifiable beyond it**,
reward-feasibility is NO-GO, so the modeling **stops at a semi-Markov choice model — do NOT build IRL**
here. Use this driving/robotics audit as **prior-art and method context** (what the field's generative,
IRL, game-theoretic, and RL branches actually buy you, and where they fail), **not** as a mandate to
port those models onto WISER data. The audit's own lessons *reinforce* the NO-GO: open-loop fit ≠
recoverable policy, and generative realism ≠ identifiable reward. If new data ever reopens
identifiability, this skill's three-sub-problem split and metric discipline are the checklist to apply.

## Reference

- `references/driving_multiagent_audit_2026-07.md` — captured SOTA snapshot: metric glossary, the
  three-sub-problem breakdown, the evidence table (system · benchmark · metric · number · URL), the
  framing-hypothesis verdict, the reported conflicts, and the uncovered gaps.
