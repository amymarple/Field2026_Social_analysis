# Literature audit: history dependence and sequence structure of sleep stages (2026-10-07)

**Provenance.**
- A read-only literature and methods audit by a Fable 5.1 subagent, commissioned on 2026-10-07 for the plan
  [implementation_plan/2026-10-07-sleep-internal-schedule.md](../../implementation_plan/2026-10-07-sleep-internal-schedule.md).
- Questions 1–5 were asked first. Questions 6 (scheduled vs permissive REM) and 7 (what survives a wake) were added
  mid-run, with a steering note (one hypothesis: an internal, long-range schedule that survives interruptions).
- The audit's text below is unchanged. The main session's checks come first; where a check disagrees with the text, the
  check wins.

## Checks by the main session (2026-10-07)

**1. Our scorer's minimum-duration rules: checked in the code, one correction.**
- Code: PreprocessPipeline `src/preprocess/state_scoring.py` `_apply_minimum_state_durations`, lines 1663–1729,
  `min_state_length` = 6 s (`ephys/score_sleep.py` `MIN_REM_S`).
- The order:
  1. NREM ≤ 6 s → WAKE;
  2. WAKE ≤ 6 s next to REM → REM;
  3. REM ≤ 6 s between WAKE on both sides → WAKE;
  4. any remaining REM ≤ 6 s → WAKE;
  5. **WAKE ≤ 6 s next to NREM → NREM**;
  6. NREM ≤ 6 s → WAKE.
- The audit (§5) lists steps 1–4 only. Because of step 5, a REM attempt of ≤ 6 s inside NREM ends as **NREM**, not as a
  brief wake, and every wake of ≤ 6 s next to NREM is already NREM in our scores.
- The general point stands: brief REM attempts are deleted, at ≤ 6 s by the scorer and by the `imu_remclean` rules
  after it.

**2. Park et al. 2021 and wake inside the cycle: checked in the full text (PLoS), one correction.**
- The sentence the audit relies on concerns REM *duration*: "the dependence of REMpost on the CDF value was not
  affected by the presence of wake episodes".
- For the NREM content, the paper says: "both |W| and the number of wake episodes within an inter-REM interval
  contribute to longer |N|". More wake in an interval goes with more NREM before the next REM.
- So Park 2021 does **not** support a pure "pause during wake" for REM timing. It points the same way as our v2 term
  "wake since the last REM lowers the REM odds".
- The pause reading in §7(c) rests on Benington & Heller 1994 and on the neural marker in Weber 2018.
- Also confirmed verbatim: MA = "wake bouts ≤ 20 s", counted in |N|; "19.3% of all cycles were sequential"; "the
  refractory period is approximately twice the duration of REMpre".

**3. "REM duration is unpredictable from history": overgeneralised (user review, 2026-10-07; checked).**
- The near-zero R² (Park 2021) is for one relation: the preceding NREM content → the next REM duration.
- REM propensity at REM onset does predict REM duration: "REMS propensity at REMS onset was positively correlated with
  REMS bout duration".
  - Source: Akhavan et al. 2026, *Frontiers in Neuroscience*, doi 10.3389/fnins.2026.1844209 — the published version of
    the arXiv 2604.01252 preprint cited below; the same authors.
- Executive summary item 1 and §1.1 should be read with this restriction. REM duration stays a research object.

**4. "Own history survives → internal; swapped history predicts as well → weather / house" (§7(e)): a leap (user
review).**
- Internal rhythms can synchronise animals, and a shared environment can affect animals differently.
- The comparison can say only how much of an animal's own-history information the other animals' sleep does *not*
  explain.

**5. Not re-checked by the main session; relayed as the audit reported them.**
- Every other citation and number.
- In particular: Weber 2018 (vlPAG R values), Franken 2002, Ocampo-Garcés 2020, Amici 2008, Stephenson 2013/2025 (the
  audit had abstracts only), Yetton 2018 and Akhavan 2026 (an arXiv preprint).
- Any of these that a result or a claim comes to depend on is checked against the source first.

---

Date: 2026-10-07. Scope: literature and methods audit for the planned bout-level sequence analysis (S0 Markov baseline, S1 context-length sweep, S2 bout-level latent-state model) and for the two reframed questions (Q6 scheduled vs permissive; Q7 survival of an internal schedule across interruptions). Judgement only; nothing was computed. Read-only; no repository file was changed.

How to read the evidence labels: **[paper]** = what the cited paper states (abstract or full text as fetched); **[inference]** = my own reading or extrapolation. Where only an abstract was reachable (PMC and PubMed pages were blocked by reCAPTCHA / cookie walls during this session; Europe PMC, PLoS, arXiv, bioRxiv API and publisher pages were used instead) the entry says "abstract". Numbers are quoted as reported; nothing is averaged across papers.

---

## Executive summary

1. **The one robust, cross-species, cross-scoring fact is an asymmetric forward dependence:** the length of a REM episode predicts the NREM content of the *following* inter-REM interval, not the preceding one (rats: Vivaldi 1994, Benington & Heller 1994, Vivaldi 2005, Stephenson 2025; mice: Park 2021 with the vlPAG neural correlate in Weber 2018, r = 0.50–0.63; humans only under extended sleep and in 3 of 8 cycles, Barbato & Wehr 1998). REM *duration* itself is essentially unpredictable from prior history (Benington & Heller 1994; Park 2021: R² ≈ 0.001). Our v1/v2 "previous REM length" term being the weakest history term is the expected result, not a failure.
2. **A post-REM refractory period is robust; its length scales with the preceding REM** (mice ≈ 2 × REMpre, Park 2021; rats: hazard nadir ≈ 2.5 min, Bassi 2009; duration-dependent dip, Ocampo-Garcés 2020). Our "REM in the last 10 min lowers REM odds" is this refractory period.
3. **Two cycle types (sequential / single) exist in rats, mice and humans** (Park 2021: 19.3 % sequential in mice; Akhavan 2026: present in all three species). The split threshold depends on how brief wakes are handled (Park: wakes ≤ 20 s counted as NREM); our 48 % light-phase sequential fraction at 135 s is not directly comparable to the mouse 19.3 %.
4. **Whether the forward dependence is "homeostasis / scheduling" or merely carried-over transition probability is unresolved in the literature** (Stephenson 2025: a 2nd-order semi-Markov "transition momentum" reproduces it; Le Bon 2021: REM sets only a refractory period, the rest is indeterminate). Correlational natural data cannot settle this; interventions (REM deprivation) do show compensation (Franken 2002; Ocampo-Garcés 2002, 2020; Amici 2008).
5. **Bout-duration laws are partly scoring artefacts:** sleep bouts ≈ exponential everywhere; wake is heavy-tailed, but power law (Lo 2004, α ≈ 2.2) vs biexponential (Stephenson 2013) vs multi-exponential mimicking a power law (Chu-Shore 2010) is decided by sample size and epoch rules. The robust, usable part: *wake has at least two time scales (brief vs long); sleep bouts are close to memoryless given state.* Split wake before modelling.
6. **Memory beyond one or two steps has never been measured in rodent sleep.** Humans: a 2nd-order Markov is optimal (Yetton 2018: +1.2 % accuracy from the second-previous stage, nothing from the third); rat bout durations show no serial correlation in one analysis (Stephenson 2013, r −0.08…+0.10) and positive contiguous-state correlations in another from the same lab (Stephenson 2025). Nobody has used context trees or mutual-information decay on hypnograms. Our memory curve would be new.
7. **S1-vs-S2 is a valid model comparison but not a test of "latent mode vs scheduling":** a K-state latent model is itself a finite-memory process (Lin & Tegmark 2017), and a slow continuous REM-pressure variable *is* a latent state. The informative comparison is between three ways of summarizing the past: discrete bout context (S1), continuous accumulated quantities in NREM-time (REM pressure, as in Park/Ginsberg/Akhavan), and discrete latent states (S2). Use held-out block likelihood as Ashwood 2022 did (GLM-HMM vs GLM-with-history vs drift model).
8. **The field's standard, and the right choice for us, is to measure memory in time (minutes–hours) and in REM-cycles, not in bouts**, with brief wakes (≤ 20 s) merged into NREM and the clock run in NREM-time. The decisive experiment the data allow is the *post-interruption* test: after a spontaneous long wake (≥ 10 min) or a battery round, does the first REM arrive sooner when more NREM-since-REM had accumulated before the interruption (pause-and-resume), sooner after a longer wake (pressure keeps growing), or neither (reset)? Literature predicts "pause" on the cycle scale (Benington & Heller; Park; Weber) and "keeps growing" only on the long-term scale (Franken 2002; Ocampo-Garcés 2020).
9. **Time of day is not an optional control; it is part of the generative model.** Without it a Markov chain cannot even simulate hypnograms (Kemp & Kamphuisen 1986) and HMMs invent extra states (Pohle 2017). Keep the 2-harmonic phase term in every version. The only *additional* control worth adding is a cross-animal "shared conditions" term (other animals' concurrent REM, or a swapped-history surrogate), because weather (Komagata 2019; Szymusiak & Satinoff 1981; Amici 2008) and co-sleeping (Drews 2020) create slowly varying shared REM fluctuations that look exactly like a 3-h "persistence" memory.
10. **Report scoring rules as part of the result**: 1-s epochs, 15-s smoothing, 6-s minima, REM ≥ 7 s, no REM after > 10 s wake, no REM while moving. The Buzsáki code converts short REM inside NREM to WAKE and merges short wake next to REM into REM; Benington & Heller showed that the brief (< 30 s) REM attempts these rules delete are the carrier of the within-interval propensity signal. Give every key coefficient at MA thresholds 10 / 20 / 60 s and on the pre-rule states.

---

## 1. What the literature concludes about history dependence in sleep-stage sequences

**Verdict.** Robust: (i) forward REM → next-interval dependence; (ii) post-REM refractory period scaling with REM length; (iii) sequential vs single cycles; (iv) REM duration not predictable from history; (v) within-interval rise of REM propensity (brief REM attempts, θ/σ/spindles); (vi) long-term REM compensation under deprivation. Not robust / scoring- or model-dependent: the power-law-vs-exponential form of wake bouts, the size of the sequential fraction, any claim of memory beyond two steps, and the mechanistic reading of (i) as homeostasis.

### 1.1 REM timing and short-term REM homeostasis (rodents)

- Vivaldi et al. 1994 (16 rats, 3 days, 15-s epochs, episodes/intervals ≥ 2 epochs) [abstract]: "highly significant correlations between the length of AS episodes and the length of the non-AS intervals that followed", none with preceding intervals; "a forward regulatory mechanism that, given the duration of an AS episode, permissively controls the interval that the animal may abstain from AS". https://doi.org/10.1152/jn.1994.72.4.1745
- Benington & Heller 1994 (rats, REM onset scored from pre-REM EEG phenomena, independent of REM duration) [abstract]: (1) NREM episode duration positively correlated with prior REM duration; (2) mean NREM duration decreases after repeated brief REM (< 30 s); (3) "REM-sleep episode duration is independent of prior sleep history"; (4) brief REM episodes become progressively more frequent across the NREM interval between sustained REM (> 30 s) → propensity rises within NREM; (5) the diurnal REM cycle mainly reflects REM *maintenance* efficiency. https://doi.org/10.1152/ajpregu.1994.266.6.R1992
- Vivaldi, Ocampo-Garcés & Villegas 2005 (16 rats, 15-s epochs, LD 12:12) [abstract]: interval and NREM content rise with REM episode length following a Gompertz sigmoid; the relation is modulated over 24 h, "highest amplitude and earliest rise in hours 1 to 4 after lights on and the lowest amplitude at the start of lights off"; holds in intervals with < 3 min wake. https://doi.org/10.1093/sleep/28.8.931
- Bassi, Vivaldi & Ocampo-Garcés 2009 (16 rats, 15-s epochs) [abstract + repository summary]: inhomogeneous-Poisson model with *Propensity* (into-REM hazard), *Volatility* (out-of-REM hazard) and *Opportunity* (P(NREM)); highest propensity and volatility at the very beginning of intervals/episodes, then rapid stabilization; nadirs at 2.50 min (propensity) and 1.25 min (volatility) per the repository record. https://doi.org/10.1093/sleep/32.5.655 ; https://repositorio.uchile.cl/handle/2250/164760
- Park et al. 2021 (mice; 125 light-phase recordings of 72 mice, 55 dark of 35; 2.5-s epochs; wakes ≤ 20 s scored as microarousals and counted in the NREM content |N|) [full text]: ln|N| given REMpre is a 2-Gaussian (lognormal) mixture; 19.3 % of cycles sequential; the refractory period ≈ 2 × REMpre (1st percentile of the long Gaussian); for the long cycles μ_long rises *and σ_long falls* with REMpre; preceding |N| does not predict REMpost (slope 0.0041, R² 9.8e-4, p 0.052); in short cycles REMpost vs REMpre is negative (slope −0.22, R² 0.010, p 0.002); "the presence or absence of wakefulness during the sleep cycle does not affect the correlation"; during the refractory phase δ, θ, σ power and spindle rate are lower and MAs more frequent, then θ/σ/spindles rise through the permissive phase. https://doi.org/10.1371/journal.pcbi.1009316
- Weber et al. 2018 (mice, n = 11 optrode, 3 imaging) [full text]: vlPAG GABAergic "REM-off" activity correlates with the preceding REM duration (r = 0.50, P = 0.001) and with the inter-REM interval (r = 0.63); it declines across NREM (R = −0.48) "but not for wake states" (R = 0.21); post-REM elevation scales with REM duration (P = 0.03). https://doi.org/10.1038/s41467-017-02765-w
- Ginsberg et al. 2024 (mice) [full text]: a propensity measure in NREM-time since the last REM "increases, attains a local maximum, and then decreases to zero"; propensity at REM onset correlates with REM duration and with the chance of a sequential cycle — light phase only, "statistically significant but small"; sequential cycles contain 31.57 % REM vs 11.73 % in single cycles. https://doi.org/10.3389/fnins.2024.1431407
- Akhavan et al. 2026 (arXiv; mice, rats, humans) [abstract/summary]: the same non-monotonic propensity-in-NREM-time curve in all three species; propensity at onset correlates with REM duration; sequential and single cycles in all three species. https://arxiv.org/abs/2604.01252

**Conflict to carry, not resolve:** Benington & Heller 1994 and Park 2021 find REM duration unpredictable from the preceding interval; Ginsberg 2024 / Akhavan 2026 find small but significant correlations between propensity at onset and REM duration. [inference] The difference is partly the covariate (NREM-time-based propensity vs raw interval length) and partly light-phase restriction; the effect, where present, is small.

### 1.2 Sequential vs single cycles; the refractory period

- Two populations of inter-REM intervals, rats and mice: Benington & Heller 1994 (brief REM clusters), Park 2021 (19.3 % sequential; refractory ≈ 2 × REMpre), Ginsberg 2024 (sequential cycles are REM-rich), Akhavan 2026 (all species). Ocampo-Garcés et al. 2020 (15 rats) [abstract]: REM "activates a short-term REM sleep refractory period that modulates the ultradian organization of sleep states" — "a transient and duration-dependent diminution of REM sleep transitions" inside permission windows. https://repositorio.uchile.cl/handle/2250/179846
- Le Bon 2021 (review; humans/rodents) [full text]: the "asymmetrical hypothesis": a REM episode determines only a Post-REM Refractory Period proportional to its duration; the remainder of the interval (λ) is indeterminate; no oscillator is presupposed. https://doi.org/10.3389/fnins.2021.627193

### 1.3 Long-term REM homeostasis (compensation under deprivation)

- Franken 2002 (rats) [abstract]: REM lost during sleep deprivation predicts the rebound (cats, rats, mice); two processes — a long-term one for daily amount and a short-term one for the NREM–REM cycle; after 24-h SD a "threefold increase in the success-rate to enter REMS", fewer unsuccessful pre-REM episodes. https://doi.org/10.1046/j.1365-2869.2002.00275.x
- Ocampo-Garcés & Vivaldi 2002 (7 rats; 3 h of 10-min permission / 20-min deprivation windows) [abstract]: REM in permission windows rose until hour-3 REM equalled baseline; attempted transitions increased already in the 2nd deprivation window and were more frequent in the second half of each 20-min window. https://repositorio.uchile.cl/handle/2250/163481
- Ocampo-Garcés et al. 2020 (15 rats) [abstract]: a REM debt of 9.0–10.8 min "was fully compensated regardless of cumulated NREM sleep or wakefulness". (same URL as above)
- Amici et al. 2008 (24 rats, cold) [abstract]: REM fell with cold; "a fast compensatory REMS rebound occurred during the first day of recovery when the previous loss went beyond a 'fast rebound' threshold corresponding to 22 % of the daily REMS need", slow rebound over 3 further days. https://doi.org/10.1093/sleep/31.5.708
- Franken et al. 1991 (rats, 24-h SD) [abstract]: REM enhanced only on the first recovery day; SWA elevated then below baseline. https://doi.org/10.1152/ajpregu.1991.261.1.R198
- Endo et al. 1997 (rats) [search snippet]: during REM deprivation the number of interventions increased over the first 2 h and then stayed constant. https://pubmed.ncbi.nlm.nih.gov/9075274

[inference] Compensation is a deprivation result. No paper found shows a *budget* operating in undisturbed rodent data at the scale of hours; Vivaldi 2005 shows only that the strength of the short-term relation varies with time of day.

### 1.4 Bout-duration distributions

- Lo et al. 2004 (mice, rats, cats, humans) [abstract]: wake bouts "scale-free power-law behavior with an exponent alpha … approximately equal to 2.2" for all species; sleep bouts exponential with species-dependent time constants. https://doi.org/10.1073/pnas.0408242101
- Blumberg et al. 2005 (developing rats) [search summary]: sleep bouts exponential at all ages; the wake power law emerges only at older ages. https://pmc.ncbi.nlm.nih.gov/articles/PMC1253573
- Stephenson et al. 2013 (10 rats, 5-s epochs, 7 days) [full text]: WAKE biexponential beats power law; NREM biexponential in light, monoexponential in dark; REM monoexponential; brief WAKE = 88 % (L) / 75 % (D) of wake bouts, "rarely lasted longer than 4 min"; transition probabilities depend on circadian *and* ultradian phase; "an absence of serial correlation within the bout duration data series" (r −0.08 to +0.1). https://academic.oup.com/sleep/article/36/9/1377/2453890
- Chu-Shore, Westover & Bianchi 2010 (human PSG simulations, 30-s epochs) [full text]: multi-exponential data pass as power law at n = 40 bouts, are rejected at n = 640; human wake needs τ ≈ 0.6, 3, 14 epochs and NREM ≈ 2, 8, 44 epochs; log-log OLS R² is "not an appropriate measure of goodness-of-fit"; epoch truncation and scoring rules shape the histogram. https://doi.org/10.1371/journal.pone.0014204
- Perez-Atencio et al. 2018 (10 mice, 5-s epochs) [full text]: wake bimodal with a 150-s breakpoint; NREM and REM ≈ exponential; 4-state Markov (brief W, long W, NREM, REM); only long-wake duration changes light/dark; the Markov property was *not* tested ("we did not perform specific tests"). https://doi.org/10.1371/journal.pone.0189931
- McShane et al. 2010 (4 mouse strains, 4-s and 10-s epochs) [abstract]: "spike-and-slab" (short vs long bouts) for W, NREM and REM; strains differ in sustaining long bouts. https://doi.org/10.1016/j.jneumeth.2010.08.024
- Simasko & Mukherjee 2009 (rats) [abstract]: brief wake < 300 s vs long wake > 300 s; "vigilance cycling" episodes within which SWS pressure decreases and REM duration increases. https://doi.org/10.1016/j.bbr.2008.09.003
- Kishi et al. 2008 (humans) [abstract]: deep-sleep durations power-law, stage 2 stretched exponential, stage 1 and REM exponential; REM→NREM transitions common in humans but "reported to be virtually nonexistent in rats". https://doi.org/10.1152/ajpregu.00925.2007

### 1.5 Memory and long-range structure in stage sequences

- Kemp & Kamphuisen 1986 (95 human hypnograms) [abstract]: a Markov chain "simulates both probabilistic and the … predictable dynamics of sleep, but only if these time-varying, individual rates are applied" (time since sleep onset, REM–NREM periodicity). https://europepmc.org/abstract/MED/3764288
- Yetton et al. 2018 (3,202 nights, 30-s epochs, bouts broken by ≤ 1 min merged) [full text]: optimal model is 2nd-order (current stage from the previous two stage identities and the previous duration; duration from current and previous stage); stage accuracy 62.6 % (chance 20 %), duration 50.9 %; the second-previous stage adds ≈ 1.2 % and t−3 adds nothing. https://doi.org/10.1371/journal.pone.0194604
- Stephenson 2025 (bioRxiv; 10 rats, 7 days) [abstract]: "positive serial correlations between durations of contiguous states, and between state bouts and inter-bout intervals"; "no correlation between wake bout duration and subsequent sleep episode duration"; confirms REM-duration → inter-REM-interval correlation but concludes "the REM homeostat hypothesis is underdetermined" — an "inter-state transition momentum" (2nd-order 3-state semi-Markov) reproduces it. https://doi.org/10.1101/2025.03.13.643124
- Kishi et al. 2011 (10 humans, risperidone) [abstract]: lengthening the REM-onset interval went with increased N2→N3 transition probability; NREM stage-transition mechanisms "play an important role in determining ultradian REM sleep rhythms". https://doi.org/10.5665/sleep.1292
- Le Bon et al. 2002 (26 humans × 4 nights) [abstract]: REM/NREM ratio tracks the number of cycles; REM is associated with cycle count, NREM is not; the within-cycle REM–NREM relationship is "rather weak". https://doi.org/10.1152/japplphysiol.00917.2001

**Conflict:** Stephenson 2013 (no serial correlation in bout-duration series) vs Stephenson 2025 (positive serial correlations of contiguous states). [inference] The 2025 analysis conditions on joint circadian–ultradian phase and looks at specific state pairs; the 2013 analysis tested the pooled series. Which is the right summary for our question depends on conditioning — exactly the issue our phase term addresses.

### 1.6 "Scheduling" / trade-offs

- Benington & Heller 1994 points (1)–(2) are the closest to "REM permits NREM": NREM episodes shorten after repeated brief REM.
- Kharchenko & Zhdanova 2023 (humans) [search summary]: an invariant product of NREM-episode duration and REM-episode intensity across cycles, read as a common regulator. https://pmc.ncbi.nlm.nih.gov/articles/PMC10660848
- Against: Stephenson 2025 (momentum suffices), Le Bon 2021 (only a refractory period is determined), Le Bon 2002 (weak within-cycle coupling in humans).

[inference] A job-scheduler reading ("if one is longer, another is shorter") is supported in one direction only (REM length → following NREM content), with the opposite direction (NREM → REM length) repeatedly null in rodents. The literature has no test of influence beyond one cycle.

**Expected gain for us:** these facts fix the sign and shape priors for the first-cycle terms and tell us which terms are *not* worth modelling (previous REM length as a predictor of the *next REM length*). **Cost:** none.

---

## 2. Methods for the two unknowns, and what fits our data

### 2(a) Memory length / influence range

What SOTA rodent sleep papers actually use: time-varying hazards in 15-s epochs (Bassi 2009), brief-REM frequency across the interval (Benington & Heller 1994), lognormal mixtures of ln|N| (Park 2021), propensity as a discrete hazard in NREM-time (Ginsberg 2024; Akhavan 2026), first-order Markov chains with split wake (Perez-Atencio 2018; Dunmyre 2014), survival/mixture fits of bout durations (Stephenson 2013; McShane 2010), serial correlations and a 2nd-order semi-Markov simulation (Stephenson 2025). Humans add 2nd-order Bayesian networks (Yetton 2018), mixed-effects multinomial-logit Markov chains with time-of-night covariates (Bizzotto 2010, https://doi.org/10.1007/s10928-009-9148-2), and Weibull semi-Markov chains (Wang et al. 2013, https://www.scitepress.org/Papers/2013/42528/42528.pdf). No sleep paper found uses variable-order Markov / context trees, mutual-information decay, DFA or transfer entropy on hypnograms.

Recommended, in order of information per unit effort:

1. **k-cycle-ahead partial regressions (cycle units).** Regress ln|N|_k (NREM content of the k-th interval ahead) on REM_0 duration, partialling the intervening REM and intervals, k = 1…5. This is the direct answer to "does a REM affect REMs several cycles later" in the same units as Vivaldi/Park. With 4,488 cycles it is well powered for k ≤ 5. Define cycles with brief wakes ≤ 20 s merged into NREM (Park convention) so that brief wakes do not inflate counts.
2. **Time-lag history kernel (time units).** The v2 rolling 10/60/180-min windows are a 3-step kernel; refine to log-spaced lags (1–3, 3–10, 10–30, 30–90, 90–270, 270–720 min) in the same discrete-time competing-risks logit, with phase kept. Read the memory range off where the kernel becomes indistinguishable from zero across held-out blocks. Use three clocks for the same kernel — wall time, NREM-time, cycle count — and compare held-out gain: the clock that wins says what the memory is counted in (NREM-time per Park/Ginsberg/Weber; wall-clock per an oscillator). [inference] This is the self-exciting/inhibiting point-process view (Hawkes 1971, https://doi.org/10.1093/biomet/58.1.83) written as a hazard model; no new machinery.
3. **S1 context sweep on bouts**, but with a variable-length context tree (Bühlmann & Wyner 1999, https://projecteuclid.org/euclid.aos/1018031204) or lag features in a logit rather than raw n-grams: a 4-symbol alphabet at L = 10 has 4^10 ≈ 10^6 contexts against ≈ 30 k bouts. Expect the gain to saturate at L = 2 (Yetton 2018; Stephenson 2025's 2nd-order model). Treat S1 as a descriptive check, not the main memory estimate — brief wakes make bout count a poor clock.
4. **Mutual information vs lag** (Berman et al. 2016: fly behaviour kept predictive information over ≥ 10^3 transitions ≈ 20 min, where a Markov fit predicted ≈ 29 transitions; https://pmc.ncbi.nlm.nih.gov/articles/PMC5081631) is a cheap descriptive curve, but it **cannot separate S1 from S2**: any finite-order Markov chain *and any finite-state HMM* has exponentially decaying MI (Lin & Tegmark 2017, https://doi.org/10.3390/e19070299). Use it only to bound the range.

Not recommended: DFA/Hurst on hypnograms (confounds the light/dark trend with memory), transfer entropy within one sequence (it is conditional MI, nothing more), cross-animal Granger/TE (6 animals, shared conditions).

### 2(b) Cycle composition

- **Mixture split of ln|N|** (Park 2021) — already done (135 s, 48 %). Add the MA-merge sensitivity (0 / 10 / 20 / 60 s), because Park's 19.3 % was obtained with ≤ 20-s wakes inside NREM.
- **Episodes as the composition unit**: "vigilance cycling" bounded by long wake > 300 s (Simasko & Mukherjee 2009); the Buzsáki code's `StatesToEpisodes.m` uses NREM episodes with microarousals ≤ 100 s and 20-s minimum episodes (https://raw.githubusercontent.com/buzsakilab/buzcode/master/detectors/detectStates/SleepScoreMaster/StatesToEpisodes.m). Counting N/R bouts per episode and REM per episode-position (Simasko: REM rises as the episode progresses) answers "what a cycle consists of" without a latent model.
- **S2 (explicit-duration HMM / HSMM on bouts)**: HSMMs are standard in sequence modelling (Yu 2010, https://doi.org/10.1016/j.artint.2009.11.011) and HMMs are used for rodent sleep *staging* (Yaghouby et al. 2016, > 90 % accuracy, https://uknowledge.uky.edu/cbme_facpub/12), but no rodent paper uses a bout-level HSMM to discover cycle types. Keep it, with the safeguards in §3. Data size (≈ 30 k bouts, 129 sequences) comfortably supports K ≤ 6 with lognormal or Weibull durations per state.
- Changepoint and motif mining: not used in this field and not needed; the lognormal split plus episodes cover composition.

**Expected gain:** items 1–2 give the two numbers the PI asked for (range in cycles, range in minutes/hours, and the clock) for the cost of extending v2's feature set. **Cost:** low for 1–2 and 4; medium for 3 and S2.

---

## 3. Latent mode vs explicit history

**How others separated them.** Ashwood et al. 2022 compared a 3-state GLM-HMM against a 1-state GLM *with history regressors* (previous choice, win-stay/lose-switch), the classic lapse model and a continuous drifting-weight model (PsyTrack), by 5-fold cross-validation over sessions in bits/trial: example mouse +0.13 bits/trial vs the GLM, +0.09 vs lapse; across 37 mice +4.2 % accuracy vs GLM; K chosen where held-out likelihood "approximately levels off at 3"; MAP with priors (σ = 2, α = 2), state dwell times 24/13/12 trials; GLM-HMM beat PsyTrack in all 37 mice (https://www.biorxiv.org/content/10.1101/2020.10.19.346353v4.full ; https://doi.org/10.1038/s41593-021-01007-z). Calhoun et al. 2019 used the same GLM-HMM logic for fly courtship (https://pmc.ncbi.nlm.nih.gov/articles/PMC7819718). In sleep, Stephenson 2025 is the only explicit contrast (homeostat vs 2nd-order semi-Markov) and calls it underdetermined.

**Is S1-vs-S2 a valid test?** As a *model comparison*, yes, if both are scored on the same held-out blocks with the same loss. As a test of "latent mode vs scheduling", no, for three reasons [inference]:
1. A K-state HMM/HSMM is a finite-memory process (Lin & Tegmark 2017); if a small K matches long-context S1, that says the past is compressible into a few bits — not that there is no scheduling.
2. The hourglass view *is* a latent-state model with a continuous state (REM pressure). S2 with K levels approximates it. "S2 wins" is therefore compatible with homeostatic scheduling.
3. S1 on bouts uses the wrong clock (bout count), so "long-context S1" can be beaten by any model that counts time.

The comparison that is informative: **(A) history as accumulated quantities** — NREM-since-REM, wake-since-REM, REM deficit vs expectation, in NREM-time; **(B) history as discrete context** — previous L bout types/durations; **(C) latent K states** with the same emissions. If A ≈ C ≫ B, the memory is a slow drive; if C ≫ A, there are discrete modes not captured by accumulation; if B ≈ A ≈ C at L = 2, the system is effectively 2nd-order (Yetton; Stephenson 2025).

**Pitfalls (with sources).**
- *Identifiability of durations vs states*: a bimodal wake-duration distribution can be fit as two wake states or one wake state with a mixture emission; decide the alphabet first (Pohle et al. 2017: within-state heterogeneity and misspecified emissions inflate K; https://doi.org/10.1007/s13253-017-0283-8).
- *Non-stationarity*: light/dark (NREM 60 % vs 17 %), across-day REM decline (−0.18 pp/day) and the 09-11 population change will be absorbed as extra states (Pohle 2017; Kemp & Kamphuisen 1986). Put phase on the transition probabilities or stratify light/dark.
- *K selection*: do not use AIC/BIC (they over-select; Pohle: BIC chose 3 states where 2 were defensible); use held-out block likelihood and the plateau (Ashwood 2022), plus pseudo-residuals and interpretability (Pohle 2017; McClintock et al. 2020, https://doi.org/10.1111/ele.13610).
- *Label switching*: many restarts; order states by their REM-emission probability; check dwell times are longer than one bout (Ashwood's dwell-time check).
- *Over-flexible emissions*: with lognormal durations × 4 types, each state has ≥ 11 free emission parameters; cap K ≤ 6 and fix duration variances across states first.
- *Animals*: 6 animals; a pooled HMM can create "animal states". Use animal-specific initial distributions, shared transitions; check 6/6 sign consistency as v2 did.

**Expected gain:** a defensible statement of whether the history is compressible into a slow drive. **Cost:** S2 is the expensive item; limit to one well-specified fit per alphabet choice.

---

## 4. Is the plan sound? Concrete design choices

**Verdict.** Sound as a first look; change the order (cycle- and time-domain memory first, bout-level S1 last), fix the alphabet and the clock before S2, keep phase, add one shared-condition control.

1. **Bout alphabet.** Four symbols: N, R, W_brief, W_long. Pre-register the brief/long cut from our own wake-survival biexponential fit per phase (Stephenson 2013), expected in the 1–5-min range (literature cuts: 20 s MA, Park 2021; 100 s MA, buzcode episodes; 150 s, Perez-Atencio 2018; 300 s, Simasko 2009; "< 4 min", Stephenson 2013). For cycle-level analyses, merge wakes ≤ 20 s into N (Park) and also report ≤ 10 s (our rule boundary). Do not let S2 discover the split.
2. **Duration model.** Discrete-time hazard with a spline in ln(elapsed) (as v2) for the competing-risks models; for S2, lognormal (Park) or Weibull (Wang 2013) per state, not geometric; test the exponential baseline for N and R first (Stephenson 2013: REM monoexponential). Censor bouts cut by record ends; never impute gap states.
3. **Time of day.** In the first version. It is a generative ingredient (Kemp & Kamphuisen 1986; Vivaldi 2005; Stephenson 2013), not a control; omitting it produces spurious states (Pohle 2017) and spurious memory. 2-harmonic phase on transitions, as in v2.
4. **Held-out scheme.** Keep the 22 day-half blocks (natural, respects dependence); report per-block gains (22/22 is the strongest form of evidence we have). Forward chaining as the secondary. Do not hold out individual bouts or cycles.
5. **Per-animal vs pooled.** Pooled with animal intercepts; replication = sign in 6/6 animals; per-animal fits only as a check for the two or three headline terms.
6. **Remove:** raw n-gram sweep to L = 10; "previous REM length → next REM length" as a headline (expected null: Benington & Heller 1994; Park 2021). **Add:** the across-interruption test (§7) and a cross-animal shared-condition term (§7).
7. **Report** the Park-convention sequential fraction next to ours, the three-clock comparison, and the kernel sign by lag.

---

## 5. Pitfalls of automatic scoring for sequence statistics

- **Epoch, smoothing and minima set the bout histogram.** Lo 2004, Stephenson 2013 (5 s), Park 2021 (2.5 s), Vivaldi/Bassi (15 s), humans (30 s), McShane 2010 (4 s vs 10 s) all differ; Chu-Shore 2010 shows truncation of brief bouts and scoring rules shape the apparent law. Our 1-s epochs with 15-s smoothing and 6-s minima put the effective resolution near 6–15 s; the 10-s hazard grid therefore carries ≈ 1 bin of onset jitter.
- **The Buzsáki rules impose transitions.** `ClusterStates_DetermineStates.m` applies 6-s minima in a fixed order: short NREM → WAKE; short WAKE next to REM → REM; short REM in WAKE → WAKE; remaining short REM in NREM → WAKE (https://raw.githubusercontent.com/buzsakilab/buzcode/master/detectors/detectStates/SleepScoreMaster/ClusterStates_DetermineStates.m ; windows [2 15] s in `SleepScoreMaster.m`). So a failed REM attempt inside NREM becomes a brief *wake* — a rule-made W bout. Benington & Heller 1994 showed brief REM (< 30 s) attempts are the carrier of the within-interval propensity signal; Benington, Kodali & Heller 1994 showed pre-REM scoring "reveals a significant population of brief REM sleep episodes that are ignored by most sleep cycle analyses" (https://europepmc.org/abstract/MED/8191200). Our REM ≥ 7 s rule removes them again.
- **The transitional stage is scored inconsistently.** Rat intermediate stage 1–5 s (Gottesmann, via https://frontiersin.org/articles/10.3389/fnins.2019.00748/full); pre-REM in mice is scored with F1 ≈ 0.5 vs 0.95 for the classical stages (Grieger et al. 2021, https://pmc.ncbi.nlm.nih.gov/articles/PMC8192905). REM "onset" is therefore uncertain by ~5–10 s and REM→NREM transitions are "virtually nonexistent in rats" partly by convention (Kishi 2008).
- **Our no-REM-after->10-s-wake rule makes P(W_long → R) = 0 by construction**, and the 14.6 % of REM entries from ≤ 10-s wake are an artefact of where the rule draws the line. Any S0/S1/S2 must encode W_long → R as impossible, and the ≤ 10-s wakes before REM should be merged into N for sequence statistics (Park ≤ 20 s; Yetton merged ≤ 1 min; buzcode MAs ≤ 100 s inside episodes).
- **How the literature handled it:** duration-independent REM-onset scoring (Benington & Heller), ≥ 2-epoch episodes (Vivaldi 1994), MA merging (Park; Yetton), survival fits with explicit truncation (Stephenson 2013; Chu-Shore 2010), and the pre-rule comparison (our v1: slope −0.12 pre-rule vs +0.07 post-rule — a documented rule sensitivity).
- **What to report:** epoch, smoothing, minimum durations, the full rule list, the fraction of REM entries and of bouts touched by each rule, key coefficients at MA thresholds 0/10/20/60 s and on pre-rule states, and κ once any manual scoring exists (none yet).

---

## 6. Is the next REM scheduled in time, or only made possible?

### 6(a) Views, their statistical signatures, and where they coincide

| View | Representative models | Hazard after the last REM | Spread of time-to-REM given history | History sharpens timing or shifts probability? | Compensation after a missed REM |
|---|---|---|---|---|---|
| Hourglass in NREM-time (permissive) | Benington & Heller 1994; Vivaldi 1994/2005; Park 2021; Ginsberg 2024; Akhavan 2026; Le Bon 2021 (PRRP) | ≈ 0 for ≈ 2 × REMpre, then rising (Benington: brief-REM frequency rises; Bassi 2009: nadir ≈ 2.5 min then rise); Ginsberg/Akhavan: rises, peaks, decays with more NREM | Park: σ_long *falls* as REMpre grows (sharpens) | Both: shifts the refractory boundary and narrows the long component | Only via the long-term process (Franken 2002), not within a cycle |
| Oscillator / limit cycle | McCarley & Massaquoi 1986 (via Le Bon 2021); Schulz et al. 1975 (first REM predictable from sleep onset; 5–10 min/24 h phase drift across nights, https://epub.uni-regensburg.de/20058/) | Phase-locked peak at a fixed delay; low CV | Sharp, independent of REMpre | Shifts phase, not probability | Skipped REM → next at the following phase |
| Stochastic hazard / transition momentum | Bassi 2009 (inhomogeneous Poisson); Stephenson 2025; Lo 2004 | Smoothly varying hazard; the REM→interval correlation is carried-over probability | Wide | Shifts probability only | None |
| Budget / long-term homeostasis | Franken 2002; Ocampo-Garcés 2002, 2020; Amici 2008; Endo 1997 | Rises with accumulated deficit regardless of NREM/wake content | — | Shifts probability and REM maintenance ("success rate" ×3 after 24-h SD) | Yes; thresholded (fast rebound only beyond 22 % of daily need, Amici 2008) |
| Circadian gating (humans) | Carskadon & Dement 1980 (74 % of REM on the rising temperature phase; REM on alternate 30-min naps; "neither the sleep-independent nor the sleep-dependent models … supported", https://doi.org/10.1093/sleep/2.3.309); Dijk & Czeisler 1995 (robust circadian REM rhythm plus a sleep-dependent rise, https://doi.org/10.1523/JNEUROSCI.15-05-03526.1995) | Set by circadian phase | — | Shifts probability | — |

**Same predictions (natural data cannot separate):** all views predict a dip right after REM (discharged pressure, phase, or carried-over low probability) and clustering in a permissive window; the hourglass and the momentum model predict the same REM→interval correlation (Stephenson 2025). Separation needs either interventions (deprivation → compensation; only the budget/hourglass predict it) or physiological markers of pressure (θ/σ/spindle ramp, Park 2021; vlPAG activity, Weber 2018). In natural data the only lever is the *clock*: hourglass = NREM-time, oscillator = wall time, momentum = neither (bout-local). [inference]

### 6(b) Splitting the competing-risks gain into opportunity and timing

Our discrete-time model gives per-10-s hazards h_R(t), h_W(t) with survival S(t) = ∏(1 − h_R − h_W). From these alone:
- **Opportunity**: P(REM before wake | stretch start, history) = Σ_t S(t−1) h_R(t) — the cumulative incidence (Putter et al. 2007, https://doi.org/10.1002/sim.2712).
- **Timing**: f(t | REM) = S(t−1) h_R(t) / P(REM) — the conditional time-to-REM distribution; its spread (CV, entropy, interval width) is the "sharpness".
- The log-score of the joint model factorizes exactly as log P(type) + log f(t | type) (the Larson & Dinse 1985 mixture factorization, https://ideas.repec.org/a/bla/jorssc/v34y1985i3p201-211.html; the alternative P(t)·P(type | t) is "vertical modelling", Nicolaie et al. 2010, https://scholarlypublications.universiteitleiden.nl/access/item%3A2920020/view). So **both parts are derivable from the current model; no second model is needed** — one computes the two terms on held-out blocks and reports the gain of history in each. Proper scores for the two parts: Brier for the cumulative incidence at fixed horizons (Schoop et al. 2011, https://www.fdm.uni-freiburg.de/publications-preprints/papers/pre102), CRPS or interval score for f(t | REM) (Gneiting & Raftery 2007, https://doi.org/10.1198/016214506000001437).
- Caveat [inference]: with time-varying history covariates the per-stretch cumulative incidence must be integrated forward along the stretch (NREM-since-REM and the rolling windows evolve deterministically inside an NREM stretch; wake-since-REM is constant), which is a loop over steps, not a new fit.

**Pitfalls.**
- *Conditioning on success*: analysing REM latency only in stretches that reached REM selects long stretches; the mixture factorization avoids it because f(t | REM) is model-based.
- *Wake as competing risk, not censoring*: censoring assumes wake is independent of REM propensity; Park 2021 shows MAs are *more* frequent in the refractory phase, so the risks are dependent.
- *The > 10-s rule* makes long wake absorbing for REM and chops NREM into stretches at every > 10-s wake; define stretch starts with ≤ 20-s wakes merged (Park) and show the 10/20/60-s sensitivity.
- *"NREM start" when fragmented*: Park counted MAs ≤ 20 s as NREM; our stretch definition should match or be reported alongside.

### 6(c) Observational substitutes for interventions

- *Spontaneous brief wake inside REM*: after REM deprivation rats show REM–wake–REM with 10–30-s wakes (Dunmyre et al. 2014, https://doi.org/10.1371/journal.pone.0094481); our rule cannot score a REM resumption after > 10 s, so it is visible only as REM–(≤ 10 s W)–REM. Caveat: scoring-defined.
- *Spontaneous long wake* (> 300 s, Simasko 2009; "long wake", Stephenson 2013): hundreds of events at all clock times, no stress — the best natural interruption (see §7).
- *Handling / cage change*: cage exchange in rats raises sleep latency, lowers NREM and REM and fragments sleep (Cano et al. 2008, https://toyama-kaken.devel.elsevierpure.com/en/publications/neural-circuitry-of-stress-induced-insomnia-in-rats); cage change in mice suppresses REM and NREM immediately with strain-dependent recovery (Tang et al. 2005, https://doi.org/10.1016/j.physbeh.2005.05.008) and disrupts sleep ≈ 3 h (Febinger et al. 2014, https://pmc.ncbi.nlm.nih.gov/articles/PMC3894645). Our battery rounds are this kind of event: usable, with the stress level confound (§7d).
- *Social change*: social defeat raises SWS/SWA for ≈ 9 h in rats (Meerlo et al. 1997, https://pubmed.ncbi.nlm.nih.gov/9143013); co-sleeping raises REM ≈ 10 % and synchronizes stages within ± 5 min in humans (Drews et al. 2020, https://doi.org/10.3389/fpsyt.2020.00583). The 09-11 19:40 release is one night, population 5 → 10: descriptive only, exclude from inference.

---

## 7. How does sleep stay organized while interruptible — what is carried across a wake?

### 7(a) Amount and timing dissociate from state stability

- Mochizuki et al. 2004 (orexin-KO mice) [abstract]: "normal sleep-wake amounts" with "very brief" bouts and "many more transitions between all behavioral states"; abnormal homeostasis, circadian disruption and defective arousal were ruled out → "behavioral state instability, with apparently low thresholds to transition between states". https://doi.org/10.1523/JNEUROSCI.0586-04.2004
- Diniz Behn et al. 2010 (orexin-KO) [abstract]: "less distinct and more labile states". https://doi.org/10.1093/sleep/33.3.297
- Rats: orexin/ataxin-3 rats show "fragmented vigilance states", decreased REM latency, more dark-phase REM and direct W→REM transitions (Beuckmann et al. 2004, https://pmc.ncbi.nlm.nih.gov/articles/PMC384801) — in rats the dissociation is partial (amounts shift too). Undisturbed rats separate "long-duration wake events" from "vigilance cycling" within sleep episodes (Simasko & Mukherjee 2009).

### 7(b) Dynamics of arousability within NREM

- Neckelmann & Ursin 1993 (rats) [abstract]: acoustic arousal threshold higher in SWS-2 than SWS-1, REM and transition sleep; "epochs with high delta power had increased arousal threshold"; a time-of-day effect (lower in the 9th–10th hour of light). https://europepmc.org/abstract/MED/8378687
- Hayat et al. 2020 (rats) [abstract]: LC-NE activity determines whether a sound wakes the animal; lowering NE signalling reduces sound-evoked awakenings. https://doi.org/10.1126/sciadv.aaz4232 — the same stimulus does or does not wake depending on internal state.
- Osorio-Forero et al. 2021 (mice) [abstract]: ≈ 50-s noradrenaline fluctuations in thalamus during NREM, coinciding with spindle clustering and heart-rate variations; LC "renders mammalian NREMS vulnerable to disruption on the close-to-minute timescale". https://doi.org/10.1016/j.cub.2021.09.041
- Lecci et al. 2017 (mice, humans): 0.02-Hz sigma infraslow oscillation; microarousals phase-locked to it (https://pmc.ncbi.nlm.nih.gov/articles/PMC5298853). Kjaerby et al. 2022 (mice): MAs ride on NE peaks every ≈ 30 s; prolonged NE descents promote the spindle-rich intermediate state and REM (https://pmc.ncbi.nlm.nih.gov/articles/PMC9817483).
- Time since REM: MAs are more frequent in the refractory phase than in the permissive phase (Park 2021).
[inference] Fragility is periodic (≈ 30–50 s), depth-dependent (delta power) and phase-dependent (time since REM, time of day). Brief wakes are therefore a property of NREM, not interruptions of a programme — one more reason to merge MAs into N.

### 7(c) REM progress across awakenings: reset vs pause vs keeps evolving

| Finding | Source | Reading |
|---|---|---|
| REM propensity accumulates during NREM, not wake; brief REM attempts rise across the NREM interval | Benington & Heller 1994 (abstract); Benington & Heller 1994 Prog Neurobiol (https://doi.org/10.1016/0301-0082(94)90005-1) | **Pause** during wake |
| Wake inside the inter-REM interval does not change the CDF→REM relation; propensity accumulates "primarily during NREM" | Park 2021 (full text) | **Pause** |
| REM-off vlPAG activity declines in NREM (R = −0.48) "but not for wake states" (R = 0.21) | Weber 2018 (full text) | **Pause** (neural) |
| Propensity defined on an NREM-time clock, wake ignored | Ginsberg 2024; Akhavan 2026 | Pause by construction |
| Model: REM drive H_R "decreases during wake to a reset value" | Dunmyre 2014 (model assumption) | Partial **reset** |
| REM debt after total SD (= wake) is repaid; REM debt compensated "regardless of cumulated NREM sleep or wakefulness"; ×3 success rate after 24-h SD | Franken 1991, 2002; Ocampo-Garcés 2020 | **Keeps evolving** on the long-term scale |
| Humans: REM recurs in alternate 30-min naps across 60-min wakes but is set by circadian phase; "REM cycle is a sleep-dependent rhythm" | Carskadon & Dement 1980; Moses et al. 1977 (title; https://doi.org/10.1038/265360a0) | Circadian drive + reset at sleep onset |
| Humans: first REM predictable from sleep onset within a night; phase drifts 5–10 min/24 h across nights | Schulz et al. 1975 | Reset at sleep onset |
| Rats: no correlation between wake-bout duration and the following sleep-episode duration | Stephenson 2025 (abstract) | Wake length carries little into the next sleep |

**Conflict to carry:** short-term pause (Benington & Heller; Park; Weber) vs long-term accumulation across wake (Franken; Ocampo-Garcés). [inference] Both can hold if the long-term variable is slow (hours) and the cycle-level variable is NREM-timed; this is Franken 2002's two-process proposal. Effect sizes: cycle-level r ≈ 0.5–0.6 on the neural variable (Weber), R² ≈ 0.001 for interval → REM length (Park); long-term: 3× success rate after 24-h SD (Franken).

### 7(d) Program-like vs drive-like control; what interruptions can separate

| Model | Memory carried across a wake | Prediction for the first REM after a wake |
|---|---|---|
| Two-process (S + C; Dijk & Czeisler 1995) | None REM-specific; S rises in wake | Latency set by circadian phase and S; longer wake → longer latency (more NREM pressure); no resumption |
| Hourglass in NREM-time (Benington & Heller; Park) | REM pressure frozen | Latency in NREM-time shorter when more NREM-since-REM had accumulated before the wake; independent of wake length |
| Flip-flop with slow REM drive (Dunmyre 2014) | Decays toward a reset | Weak dependence on pre-wake state, fading with wake length |
| Limit-cycle oscillator (McCarley & Massaquoi; Le Bon 2021 review) | Phase | Latency depends on *wall-clock* time since the last REM, not on NREM-time |
| Stochastic hazard / momentum (Bassi 2009; Stephenson 2025) | Only the current transition probability | No dependence on the pre-wake cycle state beyond the last bout |
| Long-term budget (Franken 2002) | Deficit | REM in the first hour after the wake exceeds the phase expectation when the pre-wake hours were REM-poor; scales with gap length |

**Which single contrast is most decisive.** Regress, for every spontaneous long wake (≥ 10 min, inside a record), the NREM-time latency to the first REM after the wake on (i) NREM-since-last-REM accumulated *before* the wake, (ii) wake duration, (iii) phase — and the same with wall-clock-since-last-REM in place of (i). Sign pattern: pause → (i) negative, (ii) ≈ 0; reset → both ≈ 0; keeps evolving → (ii) negative; oscillator → the wall-clock version fits better. Hundreds of events, all clock times, no handling. [inference]

**The battery rounds** (operator-timed; all rats caught; 1–2 h handling; ≈ 50-min recording gap). Usable as the *imposed* replication of the same regression, comparing slopes, not levels: the level is confounded by handling stress (REM and NREM suppressed 1–3 h: Cano 2008; Tang 2005; Febinger 2014), by fixed clock times (collinear with phase), and by the unobserved gap state (whether the rat slept in the box is unknown; nothing is to be assumed about gap states). Its unique value is for the *budget* prediction: the gap is long and non-state-dependent, so REM in the first post-gap hour vs the pre-gap 3-h REM, conditioned on phase and animal, tests compensation at a 2–3-h horizon that v2 (history cut at > 60 s) never saw. ≈ 2 rounds × 12 days × 6 rats ≈ 140 events.

### 7(e) The merged hypothesis: an internal schedule that survives interruptions — how to test range, form and origin

- **Range in time and in cycles, not bouts.** §2(a) items 1–2 with log-spaced lags out to ≥ 12 h and k ≤ 5 cycles; cycles defined on REM onsets with MAs merged, so brief wakes do not inflate counts. Report the clock that wins (wall / NREM-time / cycle).
- **Across interruptions.** Instead of cutting history at every > 60-s gap, carry it across with three rules fit side by side — frozen (pause), exponentially decaying with the gap length (reset-like), and growing with the gap length (evolving) — and let held-out blocks choose; gap duration enters as a covariate. The battery gaps are included as gaps with known duration and unknown state.
- **Form.** Read the kernel sign by lag, conditioned on phase: negative at < 15 min = refractoriness (Park; Bassi; our 10-min term); positive with slow decay = persistence/mode; negative at long lags after REM-poor hours = compensation (test it specifically as "REM deficit vs animal-phase expectation over the past 3–12 h", the natural analogue of Amici's thresholded rebound). v2's positive 3-h term is clustering, which the hourglass + Franken interaction also predicts (high long-term pressure → more successful entries), so it does not yet refute a budget at longer lags. [inference]
- **Internal memory vs shared slow conditions.** Ambient temperature changes REM amount (Komagata et al. 2019, https://doi.org/10.1016/j.cub.2019.05.009; Szymusiak & Satinoff 1981, https://doi.org/10.1016/0031-9384(81)90145-1; Amici 2008) and co-sleeping synchronizes stages (Drews 2020; group housing shortens light-phase REM bouts, Febinger 2014). Single control: add the other five animals' concurrent REM fraction (last 3 h) — or a swapped-history surrogate in which an animal's own 3-h history is replaced by a co-housed animal's — to the same model. If the own-history gain survives, the memory is internal; if the swapped history predicts as well, it is weather/house. Weather covariates directly (console temperature, rain) are the second cheapest check.

---

## Do not do

1. Do not run raw n-gram contexts to L = 10 on ≈ 30 k bouts; use lag features or a pruned context tree, and expect saturation at L = 2.
2. Do not choose K by AIC/BIC; use held-out block likelihood plus pseudo-residuals and interpretability.
3. Do not fit S2 without phase; non-stationarity becomes states.
4. Do not let the HSMM discover the brief/long wake split; fix the alphabet from the wake-survival fit first.
5. Do not treat wake as censoring in the REM hazard; it is a dependent competing risk.
6. Do not analyse REM latency only in stretches that reached REM (conditioning on success); use the mixture factorization.
7. Do not read "previous REM length → next REM length" as the memory test; the carrier is the interval.
8. Do not interpret the positive 3-h term as an internal mode before the cross-animal / weather check.
9. Do not keep cutting history at every > 60-s gap if the question is memory across interruptions.
10. Do not infer mechanism from power-law vs exponential fits of wake bouts at our epoch/rule settings (Chu-Shore 2010).
11. Do not use the 09-11 social night for inference; one night, population change.
12. Do not use MI decay, DFA or transfer entropy to separate S1 from S2; finite-state models all decay exponentially.
13. Do not compare our 48 % sequential fraction with Park's 19.3 % without matching the MA convention.
14. Do not average conflicting papers (Stephenson 2013 vs 2025; Benington/Park vs Ginsberg on REM-duration prediction; pause vs long-term accumulation); report both and state which conditioning each used.

---

## References — primary sleep literature (core, 35)

| # | Citation | Year | Species | Method | Key number / finding | URL / DOI |
|---|---|---|---|---|---|---|
| 1 | Vivaldi EA, Ocampo A, Wyneken U, Roncagliolo M, Zapata AM. J Neurophysiol 72:1745 | 1994 | rat (16) | 15-s epochs, episode–interval correlations | REM length ↔ following interval only; "forward regulatory mechanism" | https://doi.org/10.1152/jn.1994.72.4.1745 |
| 2 | Benington JH, Heller HC. Am J Physiol 266:R1992 | 1994 | rat | duration-independent REM-onset scoring | NREM duration ∝ prior REM; REM duration independent of history; brief REM (< 30 s) frequency rises across the interval | https://doi.org/10.1152/ajpregu.1994.266.6.R1992 |
| 3 | Benington JH, Kodali SK, Heller HC. Sleep 17:28 | 1994 | rat | pre-REM (NRT) scoring | 88–92 % agreement; brief REM "ignored by most sleep cycle analyses" | https://europepmc.org/abstract/MED/8191200 |
| 4 | Vivaldi EA, Ocampo-Garcés A, Villegas R. Sleep 28:931 | 2005 | rat (16) | Gompertz fit of interval vs REM length by hour | strongest hours 1–4 after lights-on; holds with < 3 min wake | https://doi.org/10.1093/sleep/28.8.931 |
| 5 | Bassi A, Vivaldi EA, Ocampo-Garcés A. Sleep 32:655 | 2009 | rat (16) | inhomogeneous Poisson hazards (Propensity, Volatility, Opportunity) | nadirs 2.50 min (into-REM), 1.25 min (out-of-REM) | https://doi.org/10.1093/sleep/32.5.655 |
| 6 | Ocampo-Garcés A, Vivaldi EA. J Sleep Res 11 | 2002 | rat (7) | intermittent REM deprivation | attempted REM transitions rise within 20-min windows; hour-3 REM reaches baseline | https://repositorio.uchile.cl/handle/2250/163481 |
| 7 | Ocampo-Garcés A, Bassi A, Brunetti E, Estrada J, Vivaldi EA. Sleep 43(8) | 2020 | rat (15) | selective/total deprivation + permission windows | REM debt 9.0–10.8 min fully compensated regardless of NREM/wake; duration-dependent refractory dip | https://repositorio.uchile.cl/handle/2250/179846 |
| 8 | Franken P. J Sleep Res 11:17 | 2002 | rat | baseline vs 24-h SD | two processes (long-term amount, short-term cycle); ×3 success rate to enter REM after SD | https://doi.org/10.1046/j.1365-2869.2002.00275.x |
| 9 | Franken P, Dijk DJ, Tobler I, Borbély AA. Am J Physiol 261:R198 | 1991 | rat | 24-h SD | REM enhanced only on recovery day 1; SWA overshoot then undershoot | https://doi.org/10.1152/ajpregu.1991.261.1.R198 |
| 10 | Amici R et al. Sleep 31:708 | 2008 | rat (24) | cold exposure + recovery | fast rebound only when loss > 22 % of daily REM need | https://doi.org/10.1093/sleep/31.5.708 |
| 11 | Park SH, Baik J, Hong J, Antila H, Kurland B, Chung S, Weber F. PLoS Comput Biol 17:e1009316 | 2021 | mouse (72 + 35) | lognormal mixture, MAs ≤ 20 s as NREM | 19.3 % sequential; refractory ≈ 2 × REMpre; σ_long falls with REMpre; preceding |N| → REM R² ≈ 0.001; wake does not alter the relation | https://doi.org/10.1371/journal.pcbi.1009316 |
| 12 | Weber F et al. Nat Commun 9:354 | 2018 | mouse (11) | vlPAG GABA recordings, optogenetics | r = 0.50 with REMpre, 0.63 with interval; decline in NREM (R −0.48) not wake | https://doi.org/10.1038/s41467-017-02765-w |
| 13 | Ginsberg AG, Cruz MEC, Weber F, Booth V, Diniz Behn C. Front Neurosci 18:1431407 | 2024 | mouse | propensity in NREM-time | rises, peaks, decays; sequential cycles 31.57 % vs 11.73 % REM | https://doi.org/10.3389/fnins.2024.1431407 |
| 14 | Akhavan N, Ginsberg AG, Cruz MEC et al. arXiv 2604.01252 | 2026 | mouse, rat, human | propensity in NREM-time | same non-monotonic curve in all three species | https://arxiv.org/abs/2604.01252 |
| 15 | Le Bon O. Front Neurosci 15:627193 | 2021 | review | asymmetrical hypothesis | REM sets only a refractory period (PRRP); no oscillator | https://doi.org/10.3389/fnins.2021.627193 |
| 16 | Le Bon O et al. J Appl Physiol 93:141 | 2002 | human (26 × 4 nights) | ratio vs cycle count | REM tied to cycle number, NREM not; weak within-cycle coupling | https://doi.org/10.1152/japplphysiol.00917.2001 |
| 17 | Barbato G, Wehr TA. Sleep 21:267 | 1998 | human (11; 308 nights) | extended 14-h sleep | REM → following NREM correlated in 3 of 8 cycles | https://doi.org/10.1093/sleep/21.3.267 |
| 18 | Lo CC et al. PNAS 101:17545 | 2004 | mouse, rat, cat, human | bout-duration fits | wake power law α ≈ 2.2; sleep exponential | https://doi.org/10.1073/pnas.0408242101 |
| 19 | Blumberg MS, Seelke AMH, Lowen SB, Karlsson KÆ. PNAS 102:14860 | 2005 | rat pups→adult | bout-duration fits | sleep exponential at all ages; wake power law emerges with age | https://pmc.ncbi.nlm.nih.gov/articles/PMC1253573 |
| 20 | Stephenson R, Famina S, Caron AM, Lim J. Sleep 36:1377 | 2013 | rat (10), 5-s | survival fits, phase | wake biexponential; brief wake 88/75 %, < 4 min; no serial correlation (r −0.08…0.10) | https://academic.oup.com/sleep/article/36/9/1377/2453890 |
| 21 | Stephenson R. bioRxiv 2025.03.13.643124 | 2025 | rat (10) | serial correlations; 2nd-order semi-Markov | positive contiguous-state correlations; homeostat "underdetermined" | https://doi.org/10.1101/2025.03.13.643124 |
| 22 | Chu-Shore J, Westover MB, Bianchi MT. PLoS ONE 5:e14204 | 2010 | human / simulation | ML + KS fits | multi-exponential mimics power law at n = 40, detected at n = 640 | https://doi.org/10.1371/journal.pone.0014204 |
| 23 | Perez-Atencio L et al. PLoS ONE 13:e0189931 | 2018 | mouse (10), 5-s | 4-state Markov | wake break at 150 s; Markov property untested | https://doi.org/10.1371/journal.pone.0189931 |
| 24 | McShane BB et al. J Neurosci Methods 193:321 | 2010 | mouse (4 strains) | spike-and-slab | two bout components in W, NREM, REM | https://doi.org/10.1016/j.jneumeth.2010.08.024 |
| 25 | Simasko SM, Mukherjee S. Behav Brain Res 196:228 | 2009 | rat | episode definition | brief < 300 s vs long wake; REM rises within episodes | https://doi.org/10.1016/j.bbr.2008.09.003 |
| 26 | Dunmyre JR, Mashour GA, Booth V. PLoS ONE 9:e94481 | 2014 | rat (5) + model | coupled flip-flop | H_R rises in NREM, falls in REM, decays to a reset in wake (model) | https://doi.org/10.1371/journal.pone.0094481 |
| 27 | Kemp B, Kamphuisen HAC. Sleep 9:405 | 1986 | human (95 nights) | Markov chain | fits only with time-varying individual rates | https://europepmc.org/abstract/MED/3764288 |
| 28 | Yetton BD, McDevitt EA, Cellini N, Shelton C, Mednick SC. PLoS ONE 13:e0194604 | 2018 | human (3,202 nights) | dynamic Bayesian network | 2nd-order optimal; 62.6 % stage accuracy; t−2 adds ≈ 1.2 %, t−3 nothing | https://doi.org/10.1371/journal.pone.0194604 |
| 29 | Kishi A et al. Am J Physiol 294:R1980 | 2008 | human (44) | duration/transition statistics | REM exponential; REM→NREM "virtually nonexistent in rats" | https://doi.org/10.1152/ajpregu.00925.2007 |
| 30 | Kishi A et al. Sleep 34:1423 | 2011 | human (10) | risperidone, transitions | N2→N3 probability controls REM-onset interval | https://doi.org/10.5665/sleep.1292 |
| 31 | Carskadon MA, Dement WC. Sleep 2:309 | 1980 | human (10) | 90-min schedule | 74 % of REM on rising temperature phase; neither sleep-dependent nor -independent model supported | https://doi.org/10.1093/sleep/2.3.309 |
| 32 | Dijk DJ, Czeisler CA. J Neurosci 15:3526 | 1995 | human (8) | forced desynchrony | robust circadian REM rhythm + sleep-dependent rise | https://doi.org/10.1523/JNEUROSCI.15-05-03526.1995 |
| 33 | Mochizuki T et al. J Neurosci 24:6291 | 2004 | mouse (orexin-KO) | bout statistics, SD, circadian | normal amounts, very brief bouts; "behavioral state instability" | https://doi.org/10.1523/JNEUROSCI.0586-04.2004 |
| 34 | Neckelmann D, Ursin R. Sleep 16:467 | 1993 | rat | acoustic arousal threshold | threshold higher in SWS-2 and with high delta; time-of-day effect | https://europepmc.org/abstract/MED/8378687 |
| 35 | Osorio-Forero A et al. Curr Biol 31:5009 | 2021 | mouse | NA fluctuations, closed-loop LC | ≈ 50-s NA cycles; NREM vulnerable on the close-to-minute scale | https://doi.org/10.1016/j.cub.2021.09.041 |

## Supporting citations (used for single points)

Hayat H et al. 2020 Sci Adv (LC-NE gates sound-evoked awakenings, rat) https://doi.org/10.1126/sciadv.aaz4232 · Lecci S et al. 2017 Sci Adv (0.02-Hz sigma ISO; MAs phase-locked) https://pmc.ncbi.nlm.nih.gov/articles/PMC5298853 · Kjaerby C et al. 2022 Nat Neurosci (NE peaks every ≈ 30 s carry MAs) https://pmc.ncbi.nlm.nih.gov/articles/PMC9817483 · Diniz Behn CG et al. 2010 Sleep https://doi.org/10.1093/sleep/33.3.297 · Beuckmann CT et al. 2004 J Neurosci (orexin/ataxin-3 rats) https://pmc.ncbi.nlm.nih.gov/articles/PMC384801 · Benington & Heller 1994 Prog Neurobiol https://doi.org/10.1016/0301-0082(94)90005-1 · Schulz H, Dirlich G, Zulley J. 1975 Pflügers Arch 358:203 https://epub.uni-regensburg.de/20058/ · Moses J et al. 1977 Nature 265:360 https://doi.org/10.1038/265360a0 · Endo T et al. 1997 Psychiatry Res 66:97 https://pubmed.ncbi.nlm.nih.gov/9075274 · Kharchenko V, Zhdanova IV. 2023 Clocks & Sleep https://pmc.ncbi.nlm.nih.gov/articles/PMC10660848 · Cano G, Mochizuki T, Saper CB. 2008 J Neurosci https://toyama-kaken.devel.elsevierpure.com/en/publications/neural-circuitry-of-stress-induced-insomnia-in-rats · Tang X et al. 2005 Physiol Behav https://doi.org/10.1016/j.physbeh.2005.05.008 · Febinger HY et al. 2014 JAALAS https://pmc.ncbi.nlm.nih.gov/articles/PMC3894645 · Meerlo P et al. 1997 (social defeat, rat) https://pubmed.ncbi.nlm.nih.gov/9143013 · Drews HJ et al. 2020 Front Psychiatry https://doi.org/10.3389/fpsyt.2020.00583 · Komagata N et al. 2019 Curr Biol https://doi.org/10.1016/j.cub.2019.05.009 · Szymusiak R, Satinoff E. 1981 Physiol Behav https://doi.org/10.1016/0031-9384(81)90145-1 · Grieger N et al. 2021 Sci Rep (pre-REM F1 0.5) https://pmc.ncbi.nlm.nih.gov/articles/PMC8192905 · Gottesmann (intermediate stage 1–5 s), via https://frontiersin.org/articles/10.3389/fnins.2019.00748/full · Katsageorgiou VM et al. 2018 PLoS Biol (sleep substages) https://pmc.ncbi.nlm.nih.gov/articles/PMC5993302 · Yaghouby F, O'Hara BF, Sunderam S. 2016 Int J Neural Syst https://uknowledge.uky.edu/cbme_facpub/12 · Wang, Alvarez, Ruiz, Moonis 2013 HEALTHINF (Weibull semi-Markov, human) https://www.scitepress.org/Papers/2013/42528/42528.pdf · Bizzotto R et al. 2010 J Pharmacokinet Pharmacodyn https://doi.org/10.1007/s10928-009-9148-2 · Buzsáki-lab SleepScoreMaster code: https://raw.githubusercontent.com/buzsakilab/buzcode/master/detectors/detectStates/SleepScoreMaster/ClusterStates_DetermineStates.m , .../StatesToEpisodes.m , .../SleepScoreMaster.m

## Method references (statistics / sequence modelling, not sleep)

Ashwood ZC et al. 2022 Nat Neurosci (GLM-HMM vs GLM-with-history, lapse, PsyTrack; 5-fold over sessions; bits/trial) https://doi.org/10.1038/s41593-021-01007-z and https://www.biorxiv.org/content/10.1101/2020.10.19.346353v4.full · Calhoun AJ, Pillow JW, Murthy M. 2019 Nat Neurosci https://pmc.ncbi.nlm.nih.gov/articles/PMC7819718 · Pohle J, Langrock R, van Beest FM, Schmidt NM. 2017 JABES (K-selection pitfalls) https://doi.org/10.1007/s13253-017-0283-8 · McClintock BT et al. 2020 Ecol Lett (HMM practice) https://doi.org/10.1111/ele.13610 · Yu S-Z. 2010 Artif Intell (HSMM) https://doi.org/10.1016/j.artint.2009.11.011 · Berman GJ, Bialek W, Shaevitz JW. 2016 PNAS (MI decay; predictive information) https://pmc.ncbi.nlm.nih.gov/articles/PMC5081631 · Lin HW, Tegmark M. 2017 Entropy 19:299 (exponential MI decay for any finite-state process) https://doi.org/10.3390/e19070299 · Bühlmann P, Wyner AJ. 1999 Ann Stat 27:480 (VLMC) https://projecteuclid.org/euclid.aos/1018031204 · Hawkes AG. 1971 Biometrika (self-exciting point processes) https://doi.org/10.1093/biomet/58.1.83 · Larson MG, Dinse GE. 1985 Appl Stat 34:201 (P(type)·P(time | type) mixture) https://ideas.repec.org/a/bla/jorssc/v34y1985i3p201-211.html · Nicolaie MA, van Houwelingen HC, Putter H. 2010 Stat Med (vertical modelling) https://scholarlypublications.universiteitleiden.nl/access/item%3A2920020/view · Putter H, Fiocco M, Geskus RB. 2007 Stat Med (competing risks tutorial) https://doi.org/10.1002/sim.2712 · Schoop R, Beyersmann J, Schumacher M, Binder H. 2011 Biom J (Brier score under competing risks) https://www.fdm.uni-freiburg.de/publications-preprints/papers/pre102 · Gneiting T, Raftery AE. 2007 JASA (proper scoring rules, CRPS) https://doi.org/10.1198/016214506000001437

## Coverage note

Not reached in this session (would strengthen but not change the verdicts): full text of Stephenson 2013/2025 (abstract/summary only), Lo 2004 per-species time constants (abstract only), Kishi 2008/2011 full text, Watson et al. 2016 methods text (the scoring rules were read from the buzcode source instead), Weber & Dan 2017 review, McCarley & Massaquoi 1986 (cited via Le Bon 2021). No rodent paper was found that measures sequence memory beyond two steps, uses context trees or MI decay on hypnograms, or tests REM-pressure persistence across spontaneous long wakes in undisturbed animals — those would be new results.
