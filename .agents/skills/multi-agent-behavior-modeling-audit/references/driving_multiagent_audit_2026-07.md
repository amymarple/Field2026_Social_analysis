# Driving / robotics multi-agent behavior-modeling — SOTA audit snapshot

**Captured:** 2026-07-11. **Domain:** autonomous-vehicle / pedestrian / robot motion (trajectory
prediction, closed-loop simulation agents, learned ego policies). **Explicitly NOT** LLM-agent
orchestration. **This snapshot ages** — benchmark leaderboards turn over every few months; treat the
numbers as of the capture date and re-pull before quoting them as current.

This file is the durable reference behind the `multi-agent-behavior-modeling-audit` skill. The skill
body carries the *method discipline*; this file carries the *evidence* (numbers, URLs, conflicts).

---

## Metric glossary (so the numbers below are readable)

- **Realism Meta (WOSAC)** — Waymo Open Sim Agents Challenge composite realism score for *closed-loop*
  simulated agents; weighted blend of kinematic, interactive, and map-based sub-metrics. Higher = better.
- **minADE / minFDE** — minimum average / final displacement error (metres) between predicted and true
  trajectory over K samples. *Open-loop* prediction accuracy. Lower = better.
- **PDMS (NAVSIM)** — Predictive Driver Model Score; a *pseudo*-closed-loop planning score (non-reactive
  rollout scored on progress, collision, comfort, drivable area). Higher = better.
- **EPDMS (NAVSIM v2)** — Extended PDM Score; PDMS plus driving-direction / traffic-light / lane-keeping
  compliance and extended comfort, over reactive background traffic. Higher = better.
- **CLS / CLS-R / CLS-SR (nuPlan)** — Closed-Loop Score, non-reactive (CLS) or reactive with IDM agents
  (CLS-R) or with learned SMART agents (CLS-SR). Higher = better.
- **DS (CARLA / Bench2Drive)** — Driving Score, closed-loop route completion × infraction penalty.
- **ρ** — Spearman rank correlation.

---

## The three sub-problems (do NOT collapse them — different winners)

### (i) Predicting *other* agents (marginal / joint forecasting)
- Led by the same generative families, on *contested* metrics.
- Consistency-model predictive planner: **WOMD minADE 0.497 m, collision 0.8% at 4 sampling steps**
  (open-loop) — https://arxiv.org/abs/2502.08033
- The tokenized-autoregressive lineage (MotionLM → SMART) owns joint prediction.
- **Caveat that governs this whole sub-problem:** displacement error barely predicts driving —
  ADE/FDE vs closed-loop Driving Score **ρ = −0.36 (p = 0.43, not significant)**; the safety-aware
  composite PDMS does better (**ρ = 0.90**) but with ranking inversions.
  - **Provenance of the ρ ≈ −0.36 lesson (pinned):** *"Do Open-Loop Metrics Predict Closed-Loop
    Driving? A Cross-Benchmark Correlation Study of NAVSIM and Bench2Drive"*, arXiv preprint 2026
    (2605.00066) — https://arxiv.org/abs/2605.00066 (HTML: https://arxiv.org/html/2605.00066v1).
    **What was measured:** Spearman rank correlation between *open-loop* metrics and Bench2Drive
    *closed-loop* Driving Score across 8 paired SOTA end-to-end methods. Traditional displacement
    error (L2 / ADE-FDE) vs DS → **ρ ≈ −0.36, p = 0.43 (no significant correlation)**; NAVSIM PDMS vs
    DS → **ρ = 0.90, p = 0.002**; best single sub-metric Ego Progress **ρ = 0.83**. Small n = 8 and
    the −0.36 is not statistically distinguishable from zero. **Preprint, not peer-reviewed; the
    p = 0.43 / ρ = 0.90 values are independently corroborated by search, but re-verify the exact
    −0.36 against the paper's own table before any load-bearing reuse.**
- *Not re-pulled this round:* the live 2025 WOMD marginal-prediction (mAP) leaderboard.

### (ii) Simulating agents closed-loop (WOSAC)
- **Winner: tokenized autoregressive (SMART lineage).** WOSAC 2025 top four are all SMART-lineage
  next-token models:
  - SMART-R1 — Realism Meta **0.7858** (kinematic 0.4944) — https://arxiv.org/abs/2509.23993
  - TrajTok — Realism Meta **0.7852**, map-based **0.9207** (SOTA) — https://arxiv.org/abs/2506.21618
  - unimotion — **0.7851** (leaderboard row, no paper pulled)
  - SMART-tiny-CLSFT — **0.7846** (leaderboard row, no paper pulled)
- Anchors: SMART (WOSAC 2024 Realism Meta **0.7614**, https://arxiv.org/abs/2405.15677);
  BehaviorGPT (WOSAC 2024 realism **0.7473**, 3M params, https://arxiv.org/abs/2405.17372).
- **Two asterisks:** (1) margins are razor-thin — top-4 span 0.0012; (2) **kinematic realism is the
  shared weakness (~0.49)** across the lineage — gains concentrate in map/interactive, not physics.
- The #1 entry (SMART-R1) wins *via R1-style RL fine-tuning* on top of the AR model.

### (iii) The ego (focal-agent) policy — planning
- **Genuinely contested; no single family dominates.**
  - Truncated-diffusion **DiffusionDrive: NAVSIM PDMS 88.1 at 2 denoising steps / 45 FPS** —
    https://arxiv.org/abs/2411.15139
  - Rule-based **PDM-Closed still leads classic nuPlan closed-loop (~92–93 CLS, Val14 reactive 92.12)**.
  - From-scratch RL **CaRL tops the hardest reactive split (~82–85 CLS-SR, Test14-Hard)** —
    https://arxiv.org/abs/2504.17838
  - NAVSIM v2 2025 champion (team "Simple") beats the PDM baseline only narrowly: **EPDMS 53.06 vs 51.3**
    (from search snippet; challenge PDF was unparseable — verify).

---

## Evidence table (number + URL per SOTA claim)

| Approach | System | Benchmark · metric · number | Loop | Source |
|---|---|---|---|---|
| Tokenized autoregressive | SMART-R1 | WOSAC 2025 · Realism Meta **0.7858** (kin. 0.4944) | Closed-loop sim | https://arxiv.org/abs/2509.23993 |
| Tokenized autoregressive | TrajTok | WOSAC 2025 · Realism Meta **0.7852**, map **0.9207** | Closed-loop sim | https://arxiv.org/abs/2506.21618 |
| Tokenized AR (anchor) | SMART | WOSAC 2024 · Realism Meta **0.7614** | Closed-loop sim | https://arxiv.org/abs/2405.15677 |
| Autoregressive next-patch | BehaviorGPT | WOSAC 2024 · realism **0.7473**, 3M params | Closed-loop sim | https://arxiv.org/abs/2405.17372 |
| Truncated diffusion (plan) | DiffusionDrive | NAVSIM · PDMS **88.1** · 2 steps, 45 FPS | Pseudo-closed | https://arxiv.org/abs/2411.15139 |
| Diffusion (plan + pred) | Diffusion-Planner | nuPlan Val14 R **82.80**; T14-Hard NR **75.99** · ~20 Hz | Closed-loop plan | https://arxiv.org/abs/2501.15564 |
| Consistency (prediction) | Consistency Pred. Planner | WOMD · minADE **0.497**, collision **0.8%** · 4 steps | Open-loop pred | https://arxiv.org/abs/2502.08033 |
| Rule-based | PDM-Closed | nuPlan Val14 CLS **~92–93** (R 92.12); NAVSIM v2 EPDMS **51.3** | Closed-loop plan | https://arxiv.org/html/2511.10403v1 |
| RL policy (from scratch) | CaRL | nuPlan Val14 **91.3** NR / **90.6** R; CARLA L6v2 **64 DS**; T14-Hard reactive **~82–85** | Closed-loop plan | https://arxiv.org/abs/2504.17838 |
| Metric critique | NAVSIM×Bench2Drive | ADE/FDE↔DS **ρ=−0.36 (p=0.43)**; PDMS↔DS **ρ=0.90** | Open vs closed | https://arxiv.org/html/2605.00066v1 |
| Reactive re-eval | "When Planners Meet Reality" | T14-Hard CLS-SR: CaRL **~82** > PDM **~74** > PLUTO **~69** > Diffusion **~63** | Closed-loop reactive | https://arxiv.org/html/2510.14677v1 |
| NAVSIM v2 champion | team "Simple" | NAVSIM v2 navhard · EPDMS **53.06** (vs PDM 51.3) | Pseudo-closed | https://huggingface.co/spaces/AGC2025/e2e-driving-navhard |

---

## The framing hypothesis, tested (not assumed)

> "The field moved from IRL/handcrafted opponent models to generative behavior models —
> (a) tokenized autoregressive, (b) diffusion/consistency policies, (c) world-model planning —
> with reward learning surviving only as an RL fine-tuning stage."

- ✅ **(a) SURVIVES strongly** for closed-loop *simulation agents* (SMART lineage sweeps WOSAC 2025).
- ✅ **(b) SURVIVES** for *ego planning* on NAVSIM (DiffusionDrive 88.1 PDMS); the latency weakness is
  being answered by truncated diffusion (2 steps / 45 FPS) and consistency models (4 steps).
- ❓ **(c) UNSUPPORTED by evidence pulled** — no benchmark found on which a world-model planner leads.
  Neither confirmed nor refuted; a coverage gap, and the weakest leg on current evidence.
- ❌ **"reward learning survives only as fine-tuning" is FALSIFIED** — CaRL is a from-scratch RL policy
  (500M samples) that tops the hardest reactive closed-loop split, beating both rule-based PDM-Closed
  and the generative Diffusion-Planner. Reward learning is a whole competitive model, not just polish.
  (And SMART-R1 *also* wins WOSAC via RL fine-tuning — reward learning is ascendant on both readings.)

**Strongest single counter-evidence:** open-loop displacement error ⟂ closed-loop driving
(ρ = −0.36) — much of the "generative models won" story rests on open-loop numbers that don't predict
driving. **Runner-up:** under realistic *learned* reactive agents, rule-based/hybrid beat *every*
imitation planner on absolute score and the generative Diffusion-Planner is the *worst* of the learned
set (~63); and "the field moved *from* rule-based" is undercut by PDM-Closed still being the reference
baseline new methods are measured against.

---

## Conflicts — report, do not resolve

1. **Reactive-nuPlan reversal is simulator-dependent.** Same Test14-Hard split:
   nuPlan-R (https://arxiv.org/html/2511.10403v1) → **Diffusion-Planner 75.70 > PDM-Closed 67.33**
   (generative wins); "When Planners Meet Reality" (https://arxiv.org/html/2510.14677v1) with SMART
   reactive agents → **PDM-Closed ~74 > Diffusion-Planner ~63** (rule-based wins). Opposite conclusions.
2. **Diffusion-Planner's own paper:** PDM-Closed ahead on *reactive* T14-Hard (75.19 vs 69.22) but
   Diffusion-Planner ahead *non-reactive* (75.99 vs 65.08).
3. **SMART-R1 Realism Meta:** paper table **0.7858** vs leaderboard summary **0.7855**.
4. **WOSAC 2024 "winner":** SMART and BehaviorGPT both claim 1st place (different tracks/leaderboards).

---

## Uncovered (caps hit — Phase 1 ≤3 sources, Phase 2 = 10 papers)

- **World-model planning** (hypothesis clause c) — no leaderboard evidence either way. Biggest gap.
- **Game-theoretic (Nash/Stackelberg/level-k)** and **IRL/MaxEnt** — candidate 2024–2026 papers exist
  (e.g. Stackelberg planning https://arxiv.org/abs/2507.22022, distributional IRL
  https://arxiv.org/abs/2510.03013) but none had a hard head-to-head benchmark number in-abstract.
- **2025 WOMD marginal motion-prediction (mAP) leaderboard** — not re-pulled; "predict others" answer
  is partly inferred.
- **unimotion / SMART-tiny-CLSFT** — WOSAC 2025 rows only, no paper fetched.
- **Gen-Drive, CarPlanner, diffusion traffic-sim** (Rolling Ahead Diffusion, EP-Diffuser) — not covered.
- **NAVSIM v2 champion approach** — challenge PDF unparseable; 53.06 from a search snippet only.
