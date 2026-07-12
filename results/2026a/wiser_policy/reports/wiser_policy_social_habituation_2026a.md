# Is the group-social effect on leaving front-loaded / habituating? (11 nights)

**Status:** ⚠️ candidate. Tests a reviewer's objection that the 8→11-night attenuation of crowding-suppresses-leaving is a POOLED-MEAN artifact of a front-loaded (habituating) effect. Whole-night blocks (11 = the only replicates). **Corrected 2026-07-12 after adversarial review**: leads with the HELD-OUT per-night estimator (an earlier in-sample version reversed the 06-28 example). Generated 2026-07-12T17:13:29.884370.

## Definitions (formula + plain text)

- **Held-out per-night social Δbits** (PRIMARY) — leave-one-night-out: train base(+social) on the other
  10 nights, score the held-out night; $\Delta\text{bits}_n = H_n(\text{base}) - H_n(\text{base+social})$.
  This is the estimator the pooled attenuation is built from. **In-sample** per-night Δbits is shown only
  as a secondary — it OVERFITS and reverses the 06-28 example (an artifact).
- **Trend** — Spearman $\rho$ of the held-out increment vs night index (night-label permutation p, n=11);
  early = pre-burrow novel nights (06-28..30), late = the rest. **2-night fragility** — the pooled mean
  with the two largest-increment nights removed.
- **Pooled night-permuted interaction (HEADLINE)** — held-out Δbits of adding social×novelty to
  base+social over ALL decisions, with a NIGHT-LABEL permutation null (shuffle the per-night novelty
  values). More powerful than 11 per-night fits. A positive, night-perm-significant Δ ⇒ the social effect
  genuinely varies with novelty.
- **Power** — simulated detection rate for a planted decay of the reviewer's ~0.01-bit early magnitude,
  so the null is interpretable (an underpowered null is not a stationarity result).

## T1 — per-night effect (held-out primary; in-sample reverses 06-28)

| night | index | n_leave | HELD-OUT social Δbits | in-sample (secondary) |
|---|---|---|---|---|
| 2026-06-28 | 0 | 1151 | +0.0107 | +0.0001 |
| 2026-06-29 | 1 | 1426 | +0.0015 | +0.0020 |
| 2026-06-30 | 2 | 1112 | +0.0016 | +0.0043 |
| 2026-07-01 | 3 | 1207 | +0.0031 | +0.0020 |
| 2026-07-02 | 4 | 1416 | +0.0002 | +0.0021 |
| 2026-07-03 | 5 | 1227 | +0.0013 | +0.0011 |
| 2026-07-04 | 6 | 945 | -0.0026 | +0.0065 |
| 2026-07-05 | 7 | 947 | -0.0040 | +0.0017 |
| 2026-07-06 | 8 | 653 | +0.0132 | +0.0011 |
| 2026-07-07 | 9 | 674 | +0.0042 | +0.0023 |
| 2026-07-08 | 10 | 917 | +0.0007 | +0.0014 |

## T2 — trend + fragility

- Spearman(held-out Δbits, night index) **ρ = -0.191** (perm-p 0.5709, non-significant).
- early (novel, 0-2) mean **0.0046** vs late (3-10) **0.002** — a WEAK, non-significant
  whiff in the reviewer's front-loaded direction (driven by 06-28; non-monotone because 07-06 is a late spike).
- Pooled held-out **0.0027** is **2-night fragile**: carried by ['2026-07-06', '2026-06-28'];
  drop them → **0.0007** (neither shares a single environmental regressor).

## T3 — pooled night-permuted social×novelty interaction (headline stationarity read)

| novelty | held-out Δ(vary−const) | night-perm p | wins | null win-rate |
|---|---|---|---|---|
| night_index | +0.00149 | 0.1653 | 5/11 | 0.583 |
| is_early | -0.00607 | 0.9504 | 2/11 | 0.442 |

Both null (perm-p ≫ 0.1) — no night-varying social structure survives a night-label permutation. Note
the leave-one-night-out "wins k/11" statistic is itself a coin flip (null win-rate ≈ 0.5), so it is not
evidence on its own.

## Power

run with --power; prior review measured ~0.27-0.29 detection at the reviewer's ~0.01-bit early magnitude (FPR ~0.21) -> the null is UNDERPOWERED.

## Spacing dissociation — CANDIDATE only

Far-approach toward-ness trend vs night index: >120in: ρ=0.418 (p0.2018) · >150in: ρ=0.573 (p0.0704) · >200in: ρ=0.5 (p0.1204) · >250in: ρ=0.618 (p0.0483).

direction robust across thresholds but significance threshold-fragile (perm-p 0.05-0.20); night-bootstrap rho CI includes 0; claiming it DISSOCIATES from the leaving trend is a significant-vs-nonsignificant fallacy at n=11; late-night rise confounded with burrow onset 07-03 / refuge_4 removal 07-07. CANDIDATE only.

## Verdict

UNRESOLVED at n=11 (the reviewer is neither refuted nor confirmed). The pooled attenuation is NOT shown to be a front-loaded-decay averaging artifact: on the correct HELD-OUT estimator the trend vs night index is ρ=-0.191 (perm-p 0.5709, non-significant) and the pooled night-permuted social×novelty interaction is null (night_index perm-p 0.1653, is_early perm-p 0.9504). BUT there is a WEAK, non-significant whiff in the reviewer's DIRECTION — early(0-2) held-out Δbits 0.0046 > late 0.002 — and the test is UNDERPOWERED (~0.27-0.29 detection at the reviewer's ~0.01-bit magnitude, FPR ~0.21), so a real decay cannot be excluded. The pooled 0.0027 is 2-NIGHT FRAGILE (carried by ['2026-07-06', '2026-06-28']; drops to 0.0007 without them). Static crowding features cannot see FOLLOWING — that mechanism is tested separately (analyze_departure_contagion.py) and is negligible + not front-loaded. Resolution needs more nights / a co-departure feature / CV.

## Scope

Group-level; association, not the "sampling" MOTIVATION the hypothesis names. n = 11 nights is low power
for a trend or interaction; a null is NOT proof of stationarity. In-sample per-night Δbits is biased and
shown only as a flagged secondary. Frame UNVERIFIED. The FOLLOWING mechanism the reviewer proposes is not
encoded by these static-crowding features — see analyze_departure_contagion.py.
