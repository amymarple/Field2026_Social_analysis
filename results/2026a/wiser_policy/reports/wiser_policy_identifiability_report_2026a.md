# Policy-identifiability report — WISER agent-policy (Phase 1)

**Provenance:** decision unit = `hysteretic_buf14_exit30_ep15` (hysteretic_roi_state); 43273 leave epochs, 2511 departures; generated 2026-07-11T21:16:52.367850; n_perm=20. **All metrics below are from THIS single run.**

**Status:** ⚠️ candidate. Hierarchical semi-Markov identifiability ladder; whole nights are the outer blocks (~8); primary loss = held-out cross-entropy in **bits/decision**. Inch frame UNVERIFIED (topology + coarse distances only); gaps are 'unknown', never departures. FORWARD-prediction / identifiability study — NOT reward inference (see verdict).

## Definitions

- **Leaving hazard** $h_i(t)=P(\text{leave ROI }r\text{ in }[t,t{+}\Delta)\mid\text{resident at }t,z_t)$,
  $\operatorname{logit}h_i(t)=\beta\cdot z_t+f_r(\tau)$; $\tau$=elapsed dwell (mandatory), $\Delta$=epoch (s).
  Plain: per fixed time-slice while in an ROI, the probability of leaving given dwell + covariates.
- **Destination choice** $P(\text{next ROI}=j\mid o, C(o), z_t)$ over the origin-specific supported
  choice set $C(o)$. Plain: given a departure from $o$, which supported ROI is entered next.
- **Held-out bits** $H=-\frac1N\sum \log_2 p(\text{observed}\mid z)$ (bits/decision). **Dbits**
  $=H_{\text{base}}-H_{\text{model}}$ (>0 = model better). **skill** $=1-H_{\text{model}}/H_{\text{base}}$.
- **Personalization gain** $\Delta\text{bits}(i,\text{night})=H_{\text{holdout}}(\text{pooled})-H_{\text{holdout}}(\text{personalized})$;
  personalized = pooled + animal FE + animal x resource interactions, the identity part fit only on
  animal $i$'s TRAINING nights (whole held-out night excluded). Plain: does knowing WHICH animal
  improve prediction on a night it was not trained on.
- **Env-matched conditional permutation**: shuffle identity WITHIN (roi) strata, recompute the
  median gain; $z=(\text{obs}-\mu_\text{null})/\sigma_\text{null}$ (holds marginal state-visitation
  fixed). **Time-shift null**: circularly shift the pre-decision social features within night.
- **Shared-use hazard** (leave-focal-out pooled $P(\text{left}\mid \text{roi,dwell-tercile})$): an
  animal-derived behavioral feature; its Dbits over M2 (explicit layout+weather) = emergent shared use.
- **Matched-choice stability**: for a symmetric resource group, an animal's cross-night preference
  transfers (LONO error < 0.15) AND departs indifference $1/|\text{group}|$ by > 0.15.

## Stage results

**A0 support:** 43273 leave epochs, 2511 departures;
multi-animal comparable strata = 76 → individual arm
**SUPPORTED (state coverage; see power note)**.

**A1 registration:** UNVERIFIED (physical transform absent);
allowed predictors: topology + coarse distances (>= min_resolvable_distance_in); NO fine metric distance, NO absolute direction.

**A2 measurement process:** valid_frac [0.4889434889434889, 1.0], gap_frac
[0.0, 0.0520152091254752] (a gap stays 'unknown', never a departure).

**M1→M3 (held-out bits):** marginal 0.322 → M1 layout
0.263 (skill 0.184) → M2 +weather
0.269 (weather Δbits -0.0064)
→ M3 +shared-use 0.265 (shared-use Δbits
0.0042).

**Memory:** history Δbits over M2 = -0.00012203839172597597 →
observed-state Markov-sufficient.

**M4 individual:** weather-adjusted personalization Δbits median = 0.0005302236797264936
(frac+ nights 0.75); without-weather median
4.066471522448656e-05; conditional-permutation z = 2.3216728386570065.
**Verdict: NO-GO — no identifiable individual policy beyond the shared baseline.**

**M5 social:** pre-decision social Δbits mean = 0.0117 (frac+ nights
1.00); time-shift null z = 15.137552934802937;
**day-shuffle null z = 30.357129571180945**; jitter-safe (drop sub-floor
nn_dist) Δbits = 0.011795465211014749, day-shuffle z = 25.646970640222982.
**Verdict: GO — real-time group-social predictive increment (survives time-shift + day-shuffle + jitter-safe).**

**Matched-choice:** stable cross-night symmetric-resource preferences =
1/14.

## Reward-feasibility verdict

Gates: {"policy_stationary_transfer": true, "state_coverage_ok": true, "observed_state_markov": true, "action_space_adequate": true} → **GO**.
Forward predictability != reward identifiability; unobserved odor/temperature/food/habituation/social -> observationally equivalent rewards. Preferred endpoint = interpretable semi-Markov choice model.

## Classification

Each result is behavioral / measurement-artifact / mixed / lower-bound; individual and social
verdicts rest on **cross-night transfer**, not coefficients. Permutations: 20. Artifacts:
`A0_support_per_animal_night.csv`, `M4_personalization_gain.csv`, `M5_social_increment.csv`,
`matched_choice.csv`, `transfer_audit.csv`, `policy_identifiability_results.json`.
