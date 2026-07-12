# 2026-07-12 — Is the group-social effect on leaving front-loaded/habituating? + a direct following test

**Status:** ⚠️ candidate. Responds to a reviewer's objection that the 8→11-night attenuation of
"crowding SUPPRESSES leaving" (pooled leave-one-night-out Δbits 0.012 → 0.003) might be an AVERAGING
ARTIFACT of a FRONT-LOADED effect that habituates (hypothesis: group-following is mainly for sampling a
novel environment). Two new analyses + an adversarial verification (5-agent workflow). The reviewer's
methodological point is correct — a pooled mean cannot test a non-stationary effect — and the answer is
**UNRESOLVED at n=11**, not the (overstated) "small and stationary" an earlier draft claimed.

## What was built

- `scripts/analyze_social_habituation.py` — non-stationarity of the leaving-social effect across the 11
  nights (held-out per-night increment, trend, 2-night fragility, pooled night-permuted social×novelty
  interaction, planted-decay power).
- `scripts/analyze_departure_contagion.py` — a DYNAMIC following feature (does a rat leave because
  group-mates just departed?) that the static-crowding features cannot encode, with a circular
  time-shift null and a front-loading test.

## Estimator correction (do not skip — an earlier draft was wrong)

The first version used an **in-sample** per-night Δbits and reported "06-28 (most novel) is the weakest;
peak at 07-04." A 5-agent adversarial workflow (each agent re-ran the numbers) showed **both reverse
under the leave-one-night-out HELD-OUT increment** — the estimator the pooled attenuation is actually
built from:

- 06-28 held-out social Δbits = **+0.0107 (2nd STRONGEST of 11)**, not weakest.
- 07-04 = **−0.0026** (the in-sample "peak" was an overfit blip; a social×fireworks interaction that only
  07-04 identifies HURTS held-out by −0.011).

The corrected script leads with the held-out estimator and shows in-sample only as a flagged secondary.

## Result 1 — non-stationarity of the STATIC crowding effect (UNRESOLVED)

- **Held-out per-night increment** (06-28..07-08): 0.0107, 0.0015, 0.0016, 0.0031, 0.0002, 0.0013,
  −0.0026, −0.0040, 0.0132, 0.0042, 0.0007 (pooled mean 0.0027).
- **Trend**: Spearman(held-out Δbits, night index) ρ = **−0.19, perm-p 0.57** (non-significant, and
  non-monotone — 07-06 is a late spike). But **early(0-2) mean 0.0046 > late(3-10) 0.0020** — a WEAK,
  non-significant whiff in the reviewer's front-loaded direction.
- **Pooled night-label-permuted social×novelty interaction** (more powerful than 11 per-night fits):
  held-out Δ(vary−const) night_index **+0.0015 (perm-p 0.17)**, is_early **−0.0061 (perm-p 0.95)** —
  **null** (both perm-p > 0.1; night_index leans positive but does not clear the night-permutation).
  No night-varying social structure survives the permutation. (The leave-one-night-out "wins k/11"
  statistic is itself a coin flip, null win-rate ≈ 0.58/0.44, so it is not evidence on its own.)
- **Power**: a planted decay of the reviewer's ~0.01-bit early magnitude is detected only ~**0.27–0.29**
  of the time (FPR ~0.21) — the null is **underpowered**, so it is NOT a stationarity result.
- **2-night fragility**: the pooled 0.0027 is carried by **06-28 (novelty) + 07-06 (wet+burrow)**; drop
  them and it collapses to **0.0007**. The two carriers share no single environmental regressor, so
  neither a calendar-habituation nor an environment-change story is identifiable at n=11 (an
  environment-change regressor sweep — burrow/wet/fireworks/refuge_4/perturbation — beat neither
  night_index nor a random-night-regressor permutation null, P(wins≥6)=0.51).

**Verdict:** the reviewer is **neither refuted nor confirmed**. The pooled attenuation is not shown to be
an averaging artifact; a real front-loaded decay of their magnitude also cannot be excluded at n=11.

## Result 2 — a direct FOLLOWING test (the reviewer's actual mechanism): NEGLIGIBLE + not front-loaded

Static crowding cannot encode following. `analyze_departure_contagion.py` builds
`n_others_departed_W` = # of OTHER tags whose module-3 bout ONSET falls in [t−W, t) before a leave
decision. Window sweep (held-out Δbits beyond static crowding): 30 s −0.0002, 60 s −0.0000, 120 s
+0.0001, **300 s +0.0010** (most favourable), from-rest-only −0.0003. At the most favourable 300 s
window: held-out Δbits **+0.0010** (below the 0.003 GO threshold), sign-test **p 0.23** (8/11). It DOES
beat a circular within-night time-shift null (**z 2.27**) — a whisper of genuine real-time coupling
beyond shared circadian timing — but the effect is far too small to matter. And it is **NOT front-loaded**:
early(0-2) held-out **−0.0004** vs late **+0.0015**, Spearman ρ +0.19 — if anything slightly stronger
LATE, the opposite of habituation.

## Result 3 — spacing dissociation downgraded to CANDIDATE

The earlier "the module-7 spacing effect dissociates by trending up across nights" is downgraded to a
**candidate directional observation**: the upward direction is robust (sign never flips across far
thresholds 100–250 in; jackknife ρ +0.47..+0.69) but significance is threshold-fragile (perm-p 0.05–0.20),
the night-bootstrap ρ CI includes 0 [−0.06, +0.89], claiming it *dissociates* from the (null) leaving
trend commits the significant-vs-non-significant fallacy at n=11, and the late-night rise is confounded
with the burrow (07-03) / refuge_4 removal (07-07).

## Definitions (formula + plain text)

- **Held-out per-night social Δbits** — leave-one-night-out $H_n(\text{base}) - H_n(\text{base+social})$;
  the estimator the pooled attenuation is built from (in-sample OVERFITS and reverses 06-28).
- **Pooled night-permuted interaction** — held-out Δbits of base+social+social×novelty vs base+social over
  all decisions, with a null that permutes the per-night novelty values across nights.
- **n_others_departed_W** — # of other tags with a module-3 bout onset in [t−W, t) before a leave decision
  (strictly pre-decision). **Circular time-shift null** — each other tag's onsets circularly shifted
  within its night (onset rate preserved, fine alignment destroyed): beating it (z>2) ⇒ real-time
  coupling, not shared circadian timing.
- **Front-loaded** — early(nights 0-2) held-out increment > late AND a negative trend vs night index.

## Verification

- 5-agent adversarial workflow (estimator-robustness, held-out-validity, environment-change,
  power+dissociation, synthesis); all four skeptics independently reproduced the load-bearing numbers.
  Disposition: **WEAKEN** — direction survives (no front-loaded *suppression*), but "small-and-stationary"
  overstated a low-power null and two in-sample evidence points were corrected.
- `analyze_social_habituation.py` and `analyze_departure_contagion.py` run; reports + JSON in
  `outputs/policy_identifiability_2026-06-28_to_2026-07-08/`.

## Scope / caveats

n = 11 nights is the resolution limit for these questions (all held-out per-night deltas sit within noise,
perm-p 0.2–0.9). Onset is a LOWER bound (sub-jitter in-nest stirring invisible), so following that
operates below the jitter floor is under-counted. Following is tested as temporal co-departure, NOT
spatial go-where-they-went (module 8). Group-level; association, not "sampling" motivation. Frame
UNVERIFIED. Definitive resolution needs more nights and/or CV co-presence validation, not more
re-estimation of these 11.
