# Literature audit: is there a substate in which REM is more likely? (2026-10-07)

**Provenance.** A read-only literature audit by an Opus subagent, requested by the user on 2026-10-07 after Phase 2b of
[implementation_plan/2026-10-07-sleep-internal-schedule.md](../../implementation_plan/2026-10-07-sleep-internal-schedule.md).
It builds on [sleep_sequence_literature_audit_2026-10-07.md](sleep_sequence_literature_audit_2026-10-07.md). The text
below is unchanged.

Not re-checked by the main session:

- most sources were read as abstracts;
- Hao 2026, Jin 2026 and the Osorio-Forero 2025 preprint numbers are relayed as the agent reported them;
- any claim that a result comes to depend on is checked against the source first.

---

# Literature audit: is there a REM-permissive substate? (2026-10-07)

Scope: rodents first (rat preferred), humans briefly. Read-only; nothing computed. It builds on
`docs/methods/sleep_sequence_literature_audit_2026-10-07.md` (the "prior audit"). Topics it already covers are not
repeated: REM homeostasis, Park 2021 refractory/permissive, Bassi 2009, Benington & Heller 1994, Ginsberg 2024 /
Akhavan 2026 propensity curves, NE infraslow (Osorio-Forero 2021, Kjaerby 2022, Lecci 2017), orexin, arousal thresholds.

Labels: **[paper]** = what the cited paper states. **[inference]** = my reading. Most papers were read as
abstracts (Europe PMC). Full texts were read for Gervasoni 2004, Bandarabadi 2020, Hao 2026, Katsageorgiou 2018,
Park 2021, Ginsberg 2024, Akhavan 2026 and Stephenson 2013, and the Osorio-Forero 2025 preprint (bioRxiv v1, which may
differ from the published version). Numbers are quoted as reported. Conflicts are listed, not averaged.

---

## Executive summary

1. **There is a REM-entry *gate*, not a long REM-permissive NREM substate.** Across rats, mice and cats, every
   NREM→REM transition passes through a short transitional stage of ~5–30 s, called the intermediate stage (IS),
   transition sleep (TS) or pre-REM [paper: Gottesmann 1998; Glin 1991; Mandile 1996; Gervasoni 2004 — "Transitions
   from SWS to REM always course through the IS region", mode 26.7 s, Long-Evans rats]. Its signature is
   high-amplitude cortical spindles, low-frequency hippocampal theta and falling delta. **It often fails:** TS is
   followed "somewhat more frequently" by wake than by REM (Mandile 1996), and P(REM) given the best rat pre-REM index
   saturates at 50–60 % (Capitani 2005). It is the *attempt*, not a background state that raises the odds.
2. **On the ~50-s scale there is a causal gate, shown in mice only.** Every REM entry is preceded by a decline of
   locus-coeruleus (LC) activity. Closed-loop LC stimulation while sigma rises suppresses REM entries; LC inhibition
   while sigma falls increases them (Osorio-Forero 2025). Removing the infraslow fluctuation (DSP-4 or an α2 agonist)
   abolishes REM (Jin 2026). Spindle rate is up to 2.8× higher in the 25 s before REM than in NREM episodes that end in
   wake, and optogenetic TRN drive raises NREM→REM transitions (Bandarabadi 2020). Conflict: prolonged NE descents
   (spindle-rich) also precede awakenings (Kjaerby 2022).
3. **On the minutes scale the evidence is a slow ramp, not discrete substates.** In mice, heart rate falls steadily
   across the NREM of an inter-REM interval; wake raises it again. Heart rate plus sleep history predicts time to the
   next REM at R² 0.43, and raising heart rate pharmacologically reduces REM (Hao 2026). The same paper finds that
   heart rate beats EEG sigma or theta as a predictor. Park 2021's refractory phase (low δ/θ/σ, few spindles, more
   microarousals) is a "substage" defined by time since REM. Its causal test (REM-on stimulation should fail during
   the refractory phase) is proposed in that paper; I found no study that ran it.
4. **"Recent NREM depth helps REM" fits the literature only away from onset, and the sign depends on the timescale.**
   In the last ~30–60 s, delta/SWA *falls* and sigma rises (cat: Lancel 1992; mouse: Vyazovskiy 2004; human ascending
   branch: Terzano 2000). Over minutes, REM needs adequate delta and low sympathetic tone: a dark pulse fails to trigger
   REM when delta is low in the cold (Baracchi 2008), and delta is lowest in Park's refractory phase. Your lag window
   [t−150, t−30) s sits on the "depth helps" side. [inference]
5. **Slow states beyond the clock and accumulated NREM:** thermoregulatory gating of REM is robust and causal (cold
   suppresses REM, warmth within the thermoneutral zone raises it; rat: Cerri 2005, Baracchi 2008; mouse: Komagata
   2019, which also implicates MCH neurons). In an outdoor paddock it is probably the largest slow REM-permissive
   variable that you can measure (weather) [inference]. The rat rest–activity cycle (~1.5–2.7 h activity episodes,
   Ootsuka 2009, Blessing 2012) is a second candidate. I found no rodent "REM-rich period" beyond the clock and
   sequential cycles.
6. **The late hazard decline:** no sleep paper I found separates heterogeneity (frailty) from a within-stretch decline.
   Ginsberg 2024 shows that the decline is *forced* by their lognormal-mixture fit. The others stratify (REMpre,
   light/dark) or add animal random effects. Selection alone can make a population hazard fall (Vaupel & Yashin 1985).
   Testing this needs landmark comparisons of marker trajectories, not a univariate frailty fit (one event per
   stretch) [inference].
7. **Best non-circular markers for our data, ranked by evidence:**
   1. cortical spindle density / sigma;
   2. infraslow (~0.02 Hz) sigma phase;
   3. heart rate, *if* R-waves are recoverable from the LFP or the head accelerometer (feasibility unknown);
   4. cortical delta (minutes scale only).

   Weak or circular: SWR rate (no primary evidence for REM entry), hippocampal theta or the theta/delta ratio and IMU
   "EMG" (scorer inputs; hippocampal REM onset leads cortex by 17.2 s in 36.6 % of REM, Durán 2018), and IMU twitches
   (they peak 70–120 s *after* REM onset, Rukhadze 2011).
8. **The minimal decisive test:** add cortical spindle density/sigma, measured in [t−150, t−30) s, to the existing
   held-out competing-risks model. Pass requires three things:
   - (a) a held-out REM gain with the same sign in 6/6 rats;
   - (b) REM specificity: the REM coefficient larger than the wake coefficient;
   - (c) Park's interaction: no effect in the 1–3-min refractory phase.

   Main pitfall: sigma is collinear with SW depth, time since REM and phase, and a window closer than ~30 s to the
   scored onset measures the transition itself.

---

## Q1. Is there a REM-permissive NREM substate in rodents?

**Verdict.** Yes in the narrow sense: a transitional "gate" stage of seconds that precedes every REM, plus an ~50-s
infraslow gate that is causal in mice. No in the broad sense: I found no evidence that a discrete NREM substate lasting
minutes raises P(REM) beyond time since REM, NREM accumulated and circadian phase. The minutes-scale evidence is a
continuous ramp (Park's refractory→permissive; Hao's heart rate). It is a pressure variable, not a mode. [inference]

### 1a. Rat intermediate stage / transition sleep / pre-REM

| Item | Evidence |
|---|---|
| Definition | IS: "high-amplitude anterior cortex spindles and low-frequency hippocampal theta rhythm", precedes and "sometimes" follows paradoxical sleep (PS) in rat, cat and mouse [paper: Gottesmann 1998, abstract]; present before PS in 100 % of cases in 7 BALB/c mice [paper: Glin 1991]. TS: "abrupt appearance of theta and alpha waves within an ongoing period of slow-wave sleep", identified with 5-s epochs and 1-s spectra [paper: Mandile 1996]. Rat pre-REM scored from delta, theta, sigma and EMG; 88–92 % agreement with visual scoring of REM transitions; it "reveals brief REM episodes typically overlooked" [paper: Benington, Kodali & Heller 1994, abstract]. |
| State space (rat LFP, our species and strain) | Ratios 0.5–20/0.5–55 Hz and 0.5–4.5/0.5–9 Hz, 2-s windows, 20-s smoothing. "Transitions from SWS to REM always course through the IS region"; the SWS→IS→REM transition lasts 26.67 ± 0.36 s (mode ± SEM) vs QW→SWS 11.02 s and REM→QW 3.50 s; IS has high 7–22 Hz coherence peaking at 8–12 Hz; SWS→IS→QW also occurs. 5 Long-Evans rats [paper: Gervasoni 2004, full text]. No IS→REM vs IS→wake proportions are given. |
| How often it succeeds | TS episodes "were followed by paradoxical sleep (PS) or, somewhat more frequently, by a period of wakefulness" [paper: Mandile 1996]. In WAG/Rij rats IS is longer and "less frequently followed by paradoxical sleep and more frequently by slow wave sleep and especially by arousals" [paper: Gandolfo 1990]. With a 60-s window before a state change from consolidated NREM, both a modified Benington index (NIV60) and the hypothalamic temperature difference (ThyD) relate sigmoidally to P(REM onset), which "saturated at a probability level around 50–60 %"; such transitions "are often followed by an awakening" [paper: Capitani 2005, rat]. |
| Arousability | IS arousal threshold "slightly higher than during the slow wave sleep and much lower than in the paradoxical sleep" → "functionally nearer the slow wave sleep" [paper: Piallat & Gottesmann 1995]. |
| Causal / pharmacological | Barbiturates and benzodiazepines "extend the intermediate stage at the expense of paradoxical sleep"; with zolpidem and zopiclone "the intermediate stage never substitutes for paradoxical sleep" [paper: Gottesmann 1998; Gandolfo 1994]. After 48 h of PS deprivation, IS amount was unchanged *during* deprivation and rose during recovery together with PS; "the IS did not substitute for PS" [paper: Gandolfo 1996]. Brainstem transection abolishes IS and PS [paper: Gottesmann 1995, title/abstract line]. |
| Region | Rat REM starts in hippocampal LFP earlier than in parietal EEG in 36.6 % of REM epochs, by 17.2 ± 1.1 s, with a parallel drop in muscle tone; IS congruence across sites < 36.5 % [paper: Durán 2018]. The hippocampus progresses from transition-to-REM to REM before the neocortex in 38.7 ± 16.2 % vs synchronously in 15.8 ± 5.6 % [paper: Emrick 2016, 5 rats, 10-s epochs]. |

**Reading.** IS/TS is a necessary passage with a high failure rate. Prolonging it pharmacologically *blocks* REM, and
REM pressure does not make it more frequent during deprivation. So it is not a state whose presence makes REM more
likely; it is the attempt whose *success* depends on something else (REM pressure, thermoregulatory/autonomic state)
[inference from Gottesmann 1998, Gandolfo 1996, Capitani 2005, Franken 2002 in the prior audit].

**In our data [inference].** Your "theta rises and EMG falls over the last 30 s before REM" *is* this stage, together
with the hippocampus-led REM onset (17 s). With 1-s epochs, 15-s smoothing and 6-s minima, the IS is absorbed into
NREM or REM, and a failed attempt of ≤ 6 s is scored as NREM (prior audit, check 1). The 0.12 hazard in the first minute
after REM fits "IS sometimes follows PS" (Gottesmann 1998) and Park's sequential cycles, i.e. REM fragmentation. It is
not a permissive substate.

### 1b. Spindle-rich / sigma-high NREM

- Mice (C57BL/6, n = 7): spindles (~11 Hz) "increased before NREM-REM sleep transitions". Spindles and SWA rise
  together early in an NREM episode but "showed an opposite evolution prior to the transition to REM sleep". After 6-h
  SD, spindles immediately before REM "were enhanced during the first 2 h of recovery" [paper: Vyazovskiy 2004].
- Cat (thalamic and cortical EEG, 8 cats): "SWA declined sharply prior to REMS"; sigma "initially increased and then
  decreased rapidly" during the transition [paper: Lancel 1992].
- Mice (n = 6 + 12, thalamus and cortex):
  - spindle rate "within a 25 s window prior to REM sleep onset" was "up to 2.8 ± 0.1 times higher" than in NREM
    episodes that end in wake (N2W);
  - no change before wake ("5–40 s before wake onset vs. N2W: P > 0.99");
  - optogenetic TRN or TRN→AD activation "significantly increased the probability of NREM-to-REM transitions without
    affecting REM sleep latency" (stimulated n = 6 TRN, 3 AD; 4 controls; no percentages reported);
  - no correlation between spindle rate and REM bout duration;
  - time since the last REM was not controlled [paper: Bandarabadi 2020, full text].
- Mice: "prolonged descent of NE promotes spindle-enriched intermediate state and REM sleep but also associates with
  awakenings" [paper: Kjaerby 2022, abstract].
- Mice: across the inter-REM interval, σ and θ power and spindle rate are low in the refractory phase and rise through
  the permissive phase [paper: Park 2021].
- Rat CA1: spindles are detectable in the hippocampus, with the same current generators as theta; firing during them
  does not differ between NREM and NREM→REM transitions [paper: Sullivan 2014].

**Reading.** Spindle-rich NREM is the best-supported REM-favouring substate. In mice it has causal support for
*transitions* (not latency), and it is at least partly REM-specific in Bandarabadi. But it is short (≤ 25–60 s), it
overlaps the IS, and its REM specificity is contested (Kjaerby; Mandile; Capitani) [inference].

### 1c. Low-delta / "light" NREM and depth fluctuations

- Immediately before REM, SWA falls (cat, mouse; above). In humans, the ascending branch before REM is dominated by
  CAP A2/A3 phases (faster, arousal-like): 64.3 % of A phases there vs > 90 % A1 in the descending branch and trough
  [paper: Terzano 2000, 25 humans].
- On the minutes scale the opposite holds. In albino rats a dark pulse during NREM triggers REM "with a high
  probability and a short latency". The efficiency fell in the cold, and the failure was "associated with low Delta
  activity and high sympathetic tone" [paper: Baracchi 2008]. Delta is lowest in Park's refractory phase (Park 2021).
- Within an NREM episode, rat SWA rises to a plateau with τ ≈ 40 s [paper: Trachsel 1988].

**Reading.** "Light NREM" helps REM only as the last-seconds transition. Over minutes, deeper NREM is permissive.
Your positive lagged-SW effect at [t−150, t−30) s agrees with Baracchi and Park; a window that reaches into the last
30 s would flip the sign [inference].

### 1d. Infraslow (~0.02 Hz) sigma / NE / LC gate

- Mice: LC activity fluctuates with side peaks at 48.3 ± 2.2 s. "Every REMS onset remained invariably preceded by a
  decline of LC activity" (stated for REM restriction; the abstract generalises it).
  - Closed-loop 1-Hz LC stimulation "once σ power was rising" reduced REM time and REM entries.
  - LC inhibition while sigma was declining "increased REMS time and the frequency of REMS entries, leaving both
    NREMS and wake time unaffected".
  - Under REM restriction, entries are limited to at most one per ~50-s period: "a non-reducible time interval of
    30–50 s in between attempts".
  - The transition shows "a continued increase in spindle density and σ power levels while LC activity declined",
    then θ rises and EMG tone is lost ("intermediate sleep").
  - The fraction of LC troughs that end in REM is not reported [paper: Osorio-Forero 2025, abstract + bioRxiv v1].
- Mice (17, intracerebral electrodes): 5–30 Hz power fluctuates at 0.005–0.02 Hz, and "the sequence of sleep stages
  followed reliably this fluctuation". DSP-4 (LC axon lesion) or medetomidine abolished the fluctuation: "the brain
  got locked in a continuous N3-like state and no REM was present" [paper: Jin 2026].

**Reading.** This is the strongest causal evidence for a REM gate: necessary (LC low) and bidirectionally manipulable.
It sets *windows of opportunity* every ~50 s. It is not a minutes-long substate. All of it is in mice [inference].

### 1e. Substates from unsupervised clustering

- Rats: Gervasoni 2004, above. The IS is a distinct region of the state space that every SWS→REM transition crosses.
- Mice: an mcRBM on 4-s epochs (60 mice) found "approximately 190" latent states, including "transitional" states
  linked with roughly equal probability to NREM and REM. No transition probabilities into REM are reported
  [paper: Katsageorgiou 2018, full text].
- Mice: N2s (with spindles) and N2n stages ordered along the infraslow cycle [paper: Jin 2026].

**Reading.** Purely correlational. These papers report no effect sizes on REM entry [inference].

### 1f. Park 2021 permissive phase and the autonomic ramp

- Park's refractory phase lasts ≈ 2 × REMpre and has lower θ, σ and spindle rate and more microarousals. The authors
  call it a "substage of NREM sleep" and propose testing "whether activation of known REM sleep-promoting neurons
  specifically during the refractory period is indeed ineffective". They report no hazard values [paper: Park 2021,
  full text]. My searches found no study that ran this test [inference].
- Mice (Hao 2026, full text; 10 24-h recordings for the main model; heart rate from R-waves in a leg EMG):
  - "heart rate exhibited a progressive decline throughout inter-REM", specific to NREM; "across wake bouts the
    heart rate initially increased before plateauing";
  - heart rate at NREM→REM transitions is lower than at NREM→wake transitions;
  - heart rate plus sleep history predicts time to REM at R² = 0.43 (n = 2335 30-s windows, 10 mice); a full
    EMG/REMpre/elapsed-time model reaches 0.52;
  - the EMG plus sleep-history model "outperformed models that received the EEG bandpass filtered in the theta or
    sigma band";
  - under REM restriction, heart rate fell more steeply and reached lower values at transitions;
  - methylatropine 10 mg/kg (which raises heart rate) "reduced REM sleep throughout the 6-h post-injection interval"
    (P = 0.0028).
- Rats: hypothalamic temperature shows a "strictly controlled decrease, during NREMS episodes leading to REMS
  occurrence" [paper: Parmeggiani 1975, cited in the Cerri 2017 review — secondary]; ThyD predicts REM success,
  saturating at 50–60 % (Capitani 2005).

**Expected gain for us (Q1).** It tells us what a "permissive substate" can look like in our data:
- a ≤ 30-s gate, which in our data is scoring-defined;
- an ~50-s infraslow window, measurable from cortical sigma;
- a minutes-scale ramp, measurable only if heart rate or a scorer-independent EEG feature can be recovered.

It also sets a realistic ceiling: even the best rat index gives P(REM | attempt) ≈ 50–60 %.

**Cost.** None (literature).

---

## Q2. Slow states vs substates

**Verdict.** Beyond circadian phase and accumulated NREM, the only slow REM-permissive variable with causal evidence
in rodents is **thermoregulatory state / ambient temperature**. A slow within-interval ramp is documented in mice
(heart rate, latent EEG/EMG) but tracks accumulated NREM, and it is reset by wake. Rodent ultradian rhythms longer than
one cycle shape *rest vs activity*, not REM specifically. No paper I found separated a heterogeneity-driven hazard
decline from a within-stretch decline.

**Evidence.**

- **Thermoregulatory gate (minutes–hours, causal).**
  - Rats, 10 °C to −10 °C for 24 h: REM "greatly depressed by cold exposure", dependent on temperature, with an
    increase in recovery [paper: Cerri 2005, 24 rats].
  - Dark-pulse REM induction fails in the cold with low delta and high sympathetic tone; the authors conclude that
    "suspension of the central control of body temperature is a prerequisite for REMS occurrence" [paper: Baracchi
    2008].
  - Mice: warm pulses within the thermoneutral zone raise REM specifically; MCHR1-KO abolishes the effect and
    optogenetic MCH silencing blocks it [paper: Komagata 2019].
  - Rat REM onset raises hypothalamic temperature by tenths of a degree [paper: Kawamura & Sawyer 1965 via the
    Cerri 2017 review — secondary].
  - Relevance [inference]: the paddock has outdoor nights and days; ambient temperature is a slow, shared,
    REM-specific gate that is confounded with phase. It is also the shared-condition control the prior audit asked
    for.
- **Rest–activity cycles (hours).**
  - Rats alternate active and inactive episodes every 1–2 h: brown-fat temperature peaks every 94 ± 43 min (dark)
    [paper: Ootsuka 2009] and every 96 ± 7 / 162 ± 16 min in dark / light [paper: Blessing 2012, 14 rats]. Each episode
    begins with a rise in hippocampal theta and heart rate.
  - Stephenson 2013 (rats) defines an ultradian phase of ~3–6 h from cumulative wake. REM maintenance (Prr) was "not
    statistically different between w+ and w−" and was "only slightly affected by ultradian phase" (3 of 8 dark
    windows). "Residual second-order dependence" suggested heterogeneity still unaccounted for [paper, full text].
  - [inference] The wake hazard rising after 20–30 min of NREM fits an approaching active episode of this cycle.
- **Entry vs maintenance.**
  - Cholinergic PPT/LDT activation during NREM "increased the number of REM sleep episodes and did not change REM
    sleep episode duration" [paper: Van Dort 2015, mice].
  - TRN drive raised transitions without changing latency (Bandarabadi 2020).
  - The diurnal REM rhythm mainly reflects maintenance (Benington & Heller 1994, prior audit), and REM success rate
    triples after 24-h sleep deprivation (Franken 2002, prior audit).
  - [inference] Permissive variables act on the *success* of attempts. Our REM ≥ 7 s and `imu_remclean` rules hide
    failed attempts, so "entry" and "success" are confounded in the current outcome.
- **Within-interval slow ramp (minutes).** In Hao 2026, latent principal component 2 shows "a gradual decay in its
  activity over several minutes", traced up to ~1250 s before REM; heart rate declines across the NREM of the interval
  (above). It is measured *within* intervals (time-normalised trajectories), so it is not a heterogeneity artefact
  [paper]. It is reset by wake, matching the "pause/reset" picture in the prior audit §7 [inference].
- **Rat cycle length.** The REM–NREM cycle has its mode at 10–13 min, and the mean depends on the minimum REM duration
  and the interruption rules [paper: Trachsel 1991]. That matches your hazard plateau at 8–20 min [inference].

**Population vs within-stretch decline: how the literature handled it.**

| Paper | Treatment | Statement |
|---|---|---|
| Ginsberg 2024 (mice) | Conditional propensity p = [F(N+Δ) − F(N)] / [1 − F(N)] from a Gaussian mixture on log N, pooled across mice, stratified by REMpre bin and light/dark | "any propensity defined as in Equation 1 for which the CDF of the log … is a GMM must have at least one local maximum and must eventually decay to zero" — the decline is **forced by the model** [paper, full text] |
| Akhavan 2026 (5 rats, mice, humans) | Same, pooled, per REMpre bin | Late decline attributed to "circadian phase, arousal/wake intrusions, or other regulatory processes"; no heterogeneity analysis [paper, full text] |
| Park 2021 | Two-lognormal mixture (sequential vs single cycles = explicit heterogeneity) | No discussion of the hazard implications [paper] |
| Hao 2026 | Linear mixed effects, mouse as random effect | No variance decomposition [paper] |
| Stephenson 2013 | Conditioning on circadian × ultradian phase | Residual heterogeneity remains [paper] |
| General survival | Selection makes the population hazard diverge from the individual hazard | [paper: Vaupel & Yashin 1985]; frailty survival models for behavioural sequences [paper: Gygax 2021] |

[inference] Two reasons a univariate frailty model will not settle this here:
- with one REM event per stretch, the frailty variance is identified only through the shape of the baseline;
- a lognormal hazard is itself hump-shaped without any frailty.

What separates the two readings:
- **(i) Landmark comparison.** Among stretches still in NREM at, e.g., 20 min, compare scorer-independent markers
  (sigma, spindle density, delta and, if feasible, heart rate) at minutes 4–8 between stretches that end in REM at
  10–20 min and stretches that survive past 25 min. If the long stretches already differ at minutes 4–8, that is
  selection or heterogeneity. If they diverge only after ~15–20 min, that is a within-stretch change.
- **(ii) Stretch-start covariates.** Add phase, ambient temperature, time since the last long wake (a BRAC proxy) and
  REMpre, and check whether the late decline flattens.
- **(iii) Repeated-event clustering.** Use a shared frailty per animal × day-half block, which has many stretches,
  rather than per stretch.

**Expected gain.** Decides whether the post-20-min decline is a biological change (worth modelling as a state) or a
mixture artefact (handled with covariates). Ambient temperature is cheap and directly REM-relevant.
**Cost.** Low: the weather CSVs exist in field2026-sync, and (i)–(iii) reuse the existing competing-risks dataset.

---

## Q3. Markers computable from our LFP/IMU, ranked by evidence

The scorer uses SW (IRASA slope) and theta ratio with 15-s smoothing, plus the IMU "EMG". A marker is non-circular only
if it comes from a different signal or channel, and from a window that ends well before the scored onset.

| Rank | Marker | Evidence for REM entry | Causal evidence | Circularity with the scorer | Cost / risk |
|---|---|---|---|---|---|
| 1 | **Cortical spindle density / sigma (10–16 Hz)** on a cortical channel the scorer did not use | Rat IS spindles (Gottesmann); mice 2.8× in last 25 s, not before wake (Bandarabadi 2020); rise before REM, opposite to SWA (Vyazovskiy 2004); low in refractory, rising in permissive (Park 2021) | Mice: TRN optogenetics ↑ transitions (Bandarabadi) | Low if measured off the scorer channels and ≥ 30 s before onset. Spindle energy perturbs the 4–90 Hz slope fit, so partial collinearity with SW remains [inference] | Low; a spindle detector is needed. Confounded by time since REM and phase: the rat 10–25 Hz band rises toward the end of the light phase (Trachsel 1988) |
| 2 | **Infraslow sigma (0.01–0.04 Hz envelope): phase, trough duration** | Every REM entry follows an LC decline, i.e. a sigma rise (Osorio-Forero 2025); stage sequence follows the 0.005–0.02 Hz fluctuation (Jin 2026) | Mice: closed-loop LC stimulation/inhibition; DSP-4 | Low | Low–medium; needs ≥ 3–5 min of continuous NREM per estimate. Mice only |
| 3 | **Heart rate** (R-waves as ECG artefact in the LFP or reference, or ballistocardiogram in the 1250-Hz accelerometer during stillness) | Best single predictor in mice, R² 0.43 with history; declines within the interval; lower before REM than before wake (Hao 2026) | Methylatropine ↑ HR → ↓ REM (pharmacological) | None (autonomic) | **Feasibility unknown** [inference]: check whether R-peaks are visible in still NREM. If yes, highest expected gain |
| 4 | **Cortical delta / SWA** (not the scorer's SW channel) | Minutes: low delta goes with failed REM induction (Baracchi 2008) and with the refractory phase (Park 2021). Last 30–60 s: SWA falls (Lancel 1992; Vyazovskiy 2004) | Indirect (cold) | **High:** SW defines NREM, so delta near the threshold is partly the NREM/REM boundary | Low; sign depends on timescale (Q1c) |
| 5 | Hippocampal SWR rate | No primary paper found that links SWR rate to REM entry. SPW/ripples reflect sleep need (Findlay 2026, rats); spindles and SWRs predict firing changes in the next REM (Miyawaki & Diba 2016) | None | Medium: the ripple channel is near the scorer's theta channel, and ripple detection drops as theta rises before hippocampal REM onset (17 s lead, Durán 2018) [inference] | Medium; exploratory only |
| 6 | Theta/delta ratio, hippocampal theta | Defines REM; rises 17–27 s before the scored onset (Durán 2018; Gervasoni 2004) | — | **Circular** | Do not use as a permissive marker |
| 7 | IMU twitches | Twitches grow *after* REM onset and peak 70–120 s in (tongue EMG, 8 rats; Rukhadze 2011) | — | The IMU EMG is a scorer input | Useful to validate REM, not to predict entry |
| — | Ambient temperature (weather), not LFP/IMU | Strong, rat and mouse (Cerri 2005; Baracchi 2008; Komagata 2019) | Yes (temperature, MCH) | None | Very low; slow covariate and shared-condition control |

**Best test of "a REM-permissive substate exists" without circularity [inference]:** ranks 1 + 2 on a cortical channel,
in a window ending ≥ 30 s before the scored onset, with cause-specific (REM vs wake) effects. Add heart rate if R-waves
are recoverable. The scorer cannot have built these markers into the outcome.

---

## Q4. The minimal decisive test in our data

**Design (one model, pre-registered) [inference].**
- **Frame.** The existing discrete-time competing-risks model on 10-s NREM steps (REM vs wake), held out over the
  22 day-half blocks. M0 = time since REM (spline) + NREM since REM + 2-harmonic phase + animal + lagged SW
  [t−150, t−30).
- **Marker.** Cortical spindle density and sigma power, as a z-score against the animal's own NREM in the same
  day-half, in [t−150, t−30) s. Use a channel that is neither the scorer's SW channel nor its theta channel (check the
  scorer's channel record). Secondary marker: infraslow sigma phase at t−30.
- **M1** = M0 + marker, with separate REM and wake coefficients.

**Pass criteria (all three).**
- **(a) Held-out gain.** The REM log-likelihood gain is positive in ≥ 18/22 blocks, and the REM coefficient has the
  same sign in 6/6 rats.
- **(b) REM specificity.** The REM coefficient exceeds the wake coefficient, with a CI on the ratio of cause-specific
  hazard ratios excluding 1. Without (b), the marker means "NREM about to end", not "REM-permissive" (Mandile;
  Capitani; Kjaerby).
- **(c) Gate interaction.** The marker effect is ≈ 0 when time since REM is 1–3 min (Park's refractory phase) and
  positive at ≥ 4 min. If (a)+(b) hold without (c), the marker acts as additive pressure rather than a gate.

**Controls.**
- **Negative controls:** the same marker shifted by +1 h, and the marker of another animal at the same clock time
  (shared environment). Both should give no gain.
- **Leak control:** the marker in [t−30, t). Expected to be strong; it is not evidence, because it is the transition
  stage.
- **Sensitivity:** repeat on the pre-rule states, so that ≤ 6-s REM attempts become events. Optionally treat
  "attempt" and "success" as separate outcomes (Franken 2002; Capitani 2005).

**Power [inference].** About 2,300 REM events give a pooled SE of log HR per SD of the marker of ≈ 0.02, and ≈ 0.05
per rat (~380 events each). A per-SD hazard ratio ≥ 1.15 should show in all six rats if the effect is uniform. The
mouse effects (2.8× spindle rate; R² 0.43 for heart rate) suggest the true effect may be larger, but in a ≤ 25-s window
that this design deliberately excludes.

**Main pitfall.** Collinearity and leakage:
- sigma/spindles co-vary with SW depth (the scorer's NREM axis), with time since REM (Park) and with phase
  (Trachsel 1988);
- 15-s smoothing and the 17-s hippocampal lead mean that any feature within ~30 s of the scored onset partly measures
  REM itself.

A positive result is meaningful only if it survives M0's time-since-REM, phase and lagged-SW terms, comes from a
window ending ≥ 30 s before onset, and passes (b). A secondary pitfall: the ≥ 7-s REM and `imu_remclean` rules turn
failed attempts into NREM or wake. That dilutes (b), so run the pre-rule sensitivity before calling a null.

**Expected gain.** A yes/no on a scorer-independent permissive state, and its timescale (gate vs pressure), for one
spindle detector and one model refit. **Cost.** Low–medium: a cortical spindle and sigma pipeline on the existing LFP,
plus the existing model code.

---

## Conflicts between papers (not averaged)

1. **Is the spindle-rich pre-REM state REM-specific?** Bandarabadi 2020: spindle rate rises before REM, not before
   wake (mice). Against: Kjaerby 2022, where prolonged NE descents → spindle-rich IS and REM "but also … awakenings"
   (mice); Mandile 1996, TS → wake "more frequently" than → PS (rats); Capitani 2005, transitions "often followed by an
   awakening", P(REM) ≤ 50–60 % (rats). Conditioning differs: Bandarabadi compares the 25 s before REM with whole NREM
   episodes that end in wake.
2. **What is the IS?** Gervasoni 2004 describes a distinct, highly coherent state that every SWS→REM transition
   crosses. Piallat & Gottesmann 1995 find it "functionally nearer the slow wave sleep" by arousal threshold.
3. **Does the transitional state facilitate or block REM?** Optogenetic TRN drive ↑ transitions (Bandarabadi 2020,
   mice). Barbiturates and benzodiazepines prolong IS "at the expense of PS" (Gottesmann 1998; Gandolfo 1994, rats).
4. **Delta before REM.** SWA declines just before REM (Lancel 1992; Vyazovskiy 2004; Terzano 2000). Low delta goes with
   failed REM induction (Baracchi 2008) and with the refractory phase (Park 2021). The difference is timescale (seconds
   vs minutes).
5. **Which marker is best?** Heart rate plus history outperforms EEG sigma or theta (Hao 2026). Sigma/LC is the causal
   gate (Osorio-Forero 2025). They measure different levels (autonomic ramp vs ~50-s gate); both can hold.
6. **Ultradian modulation.** Stephenson 2013: REM maintenance barely depends on a 3–6-h ultradian phase. Blessing and
   Ootsuka: robust ~1.5–2.7-h activity episodes in rats. The variables differ (REM maintenance vs activity/temperature
   episodes).
7. **Why the propensity declines.** Ginsberg 2024: forced by the lognormal-mixture model. Akhavan 2026: other factors
   (circadian, wake intrusions).

## Do not do

1. Do not use hippocampal theta, the theta/delta ratio or IMU "EMG" in the pre-onset window as evidence for a
   permissive state. They are scorer inputs, and hippocampal REM leads cortical REM by ~17 s (Durán 2018).
2. Do not measure any candidate marker in the last 30 s before the scored onset and call it a substate. That is the
   IS/transition, and the 15-s smoothing leaks it.
3. Do not read the 0.12 first-minute post-REM hazard as a permissive substate. It is REM fragmentation or sequential
   cycles ("IS sometimes follows PS"). Check it under a rule that merges ≤ 30–60-s NREM between REMs.
4. Do not call spindle-rich NREM "REM-permissive" without the cause-specific wake comparison.
5. Do not fit lognormal or Gaussian-mixture propensities to argue that the hazard declines after 20–30 min. The
   decline is built into that model (Ginsberg 2024).
6. Do not use a per-stretch univariate frailty model to decide heterogeneity vs within-stretch decline. Use landmark
   marker trajectories and stretch-start covariates.
7. Do not use IMU twitches as pre-REM markers. They peak 70–120 s after REM onset.
8. Do not make SWR rate a primary REM-gate marker. There is no primary evidence, and detection drops as theta rises.
9. Do not interpret sigma without time-since-REM and phase in the model (Park 2021; Trachsel 1988).
10. Do not cite the mouse causal results (LC, TRN, methylatropine, MCH) as established in rats. The rat causal
    evidence is pharmacological (hypnotics) and thermal.
11. Do not use unsupervised substate discovery (HMM, mcRBM) as the test. It yields many states without effect sizes
    (Katsageorgiou 2018: ~190).
12. Do not ignore ambient temperature in a field dataset. It gates REM causally and varies slowly with phase and
    weather.

---

## References (primary unless marked)

| # | Citation | Year | Species | Method | Key number / finding | URL / DOI |
|---|---|---|---|---|---|---|
| 1 | Gottesmann C, Gandolfo G, Arnaud C, Gauthier P. Eur J Neurosci 10 | 1998 | rat (review of own data) | IS scoring, hypnotics | IS = high-amplitude cortical spindles + low-frequency hippocampal theta; barbiturates/BZDs extend IS "at the expense of" PS | https://doi.org/10.1046/j.1460-9568.1998.00069.x |
| 2 | Gandolfo G, Gauthier P, Arnaud C, Gottesmann C. Neurosci Res | 1996 | rat (6 + 6) | 48-h PS deprivation | IS unchanged during deprivation, ↑ in recovery; "did not substitute for PS" | https://doi.org/10.1016/0168-0102(96)01040-1 |
| 3 | Gandolfo G, Scherschlicht R, Gottesmann C. Pharmacol Biochem Behav | 1994 | rat | benzodiazepines | IS extended at the expense of PS (diazepam, triazolam) | https://doi.org/10.1016/0091-3057(94)90244-5 |
| 4 | Gandolfo G et al. Physiol Behav | 1990 | rat (WAG/Rij vs Wistar) | IS scoring | longer IS, less often → PS, more often → SWS/arousal | https://doi.org/10.1016/0031-9384(90)90063-a |
| 5 | Glin L et al. Physiol Behav | 1991 | mouse (7) | IS scoring | IS before PS in 100 % of cases | https://doi.org/10.1016/0031-9384(91)90420-s |
| 6 | Piallat B, Gottesmann C. Physiol Behav | 1995 | rat | reticular arousal threshold | IS threshold slightly > SWS, ≪ PS | https://doi.org/10.1016/0031-9384(94)00351-5 |
| 7 | Mandile P, Vescia S, Montagnese P, Romano F, Giuditta A. Physiol Behav 60:1435 | 1996 | rat | 5-s epochs, 1-s spectra | TS → wake "somewhat more frequently" than → PS | https://doi.org/10.1016/s0031-9384(96)00301-0 |
| 8 | Benington JH, Kodali SK, Heller HC. Sleep 17:28 | 1994 | rat | pre-REM transition index (δ, θ, σ, EMG) | 88–92 % agreement on REM transitions; reveals brief REM | https://doi.org/10.1093/sleep/17.1.28 |
| 9 | Capitani P et al. Neurosci Lett | 2005 | rat | NIV60 + hypothalamic temperature, 60 s before state change | sigmoid P(REM), saturating at 50–60 % | https://doi.org/10.1016/j.neulet.2005.04.009 |
| 10 | Gervasoni D et al. J Neurosci 24:11137 | 2004 | rat (5 Long-Evans) | multi-site LFP state space | all SWS→REM via IS; transition 26.67 ± 0.36 s; 8–12 Hz coherence | https://doi.org/10.1523/JNEUROSCI.3524-04.2004 |
| 11 | Durán E, Oyanedel CN, Niethard N, Inostroza M, Born J. Sleep 41 | 2018 | rat | EEG + mPFC/hippocampal LFP | hippocampal REM earlier in 36.6 %, by 17.2 ± 1.1 s; IS congruence < 36.5 % | https://doi.org/10.1093/sleep/zsy060 |
| 12 | Emrick JJ, Gross BA, Riley BT, Poe GR. Sleep 39 | 2016 | rat (5) | hippocampal vs neocortical scoring | hippocampus TR→REM first 38.7 % vs synchronous 15.8 % | https://doi.org/10.5665/sleep.6326 |
| 13 | Bandarabadi M et al. Nat Commun 11 | 2020 | mouse (6 + 12; opto 6/3 vs 4) | thalamocortical LFP, SSFO optogenetics | spindle rate ≤ 2.8× in 25 s before REM vs N2W; no change before wake; TRN drive ↑ NREM→REM transitions, latency unchanged | https://doi.org/10.1038/s41467-020-19076-2 |
| 14 | Vyazovskiy VV, Achermann P, Borbély AA, Tobler I. Arch Ital Biol 142 | 2004 | mouse (7) | spindle detection, SD | spindles ↑ and SWA ↓ before REM; pre-REM spindles ↑ after SD | https://europepmc.org/abstract/MED/15493552 |
| 15 | Lancel M, van Riezen H, Glatt A. Brain Res | 1992 | cat (8) | cortical/thalamic SWA, sigma | SWA declines sharply before REM; sigma rises, then falls | https://doi.org/10.1016/0006-8993(92)91559-w |
| 16 | Trachsel L, Tobler I, Borbély AA. Am J Physiol 255 | 1988 | rat | 4-s spectra, 24 h | SWA rises with τ ≈ 40 s within NREM episodes; 10–25 Hz ↑ at the end of the light phase | https://doi.org/10.1152/ajpregu.1988.255.1.R27 |
| 17 | Trachsel L, Tobler I, Achermann P, Borbély AA. Physiol Behav | 1991 | rat | 4-s epochs, SD | REM–NREM cycle mode 10–13 min; depends on REM minimum/interruption rules | https://doi.org/10.1016/0031-9384(91)90283-t |
| 18 | Osorio-Forero A et al. Nat Neurosci | 2025 | mouse (7–9 per experiment) | LC photometry, closed-loop optogenetics | LC fluctuation 48.3 ± 2.2 s; REM always after an LC decline; stimulation ↓ / inhibition ↑ REM entries; ≤ 1 entry per ~50 s under restriction | https://doi.org/10.1038/s41593-024-01822-0 ; preprint https://doi.org/10.1101/2023.05.20.541586 |
| 19 | Kjaerby C et al. Nat Neurosci 25 | 2022 | mouse | NE photometry | prolonged NE descent → spindle-rich IS and REM, but also awakenings | https://doi.org/10.1038/s41593-022-01102-9 |
| 20 | Jin N et al. J Sleep Res | 2026 | mouse (17) | deep electrodes, DSP-4, medetomidine | 0.005–0.02 Hz fluctuation orders stages; its abolition → N3-like lock, no REM | https://doi.org/10.1111/jsr.70262 |
| 21 | Hao L et al. (Weber lab). Curr Biol | 2026 | mouse (10 main; 12 restriction; 8 pharmacology) | BiLSTM latent EEG/EMG, HR from leg-EMG R-waves | HR declines through inter-REM NREM; HR + history R² 0.43, full model 0.52; methylatropine ↓ REM (P = 0.0028) | https://doi.org/10.1016/j.cub.2026.02.034 |
| 22 | Katsageorgiou VM et al. PLoS Biol 16 | 2018 | mouse (60) | mcRBM, 4-s epochs | ~190 latent states incl. NREM/REM transitional states; no REM-entry effect sizes | https://doi.org/10.1371/journal.pbio.2003663 |
| 23 | Baracchi F et al. J Sleep Res 17 | 2008 | rat (albino) | dark pulses at several ambient temperatures, ECG, Thy | dark-pulse REM induction ↓ in cold with low delta + high sympathetic tone | https://doi.org/10.1111/j.1365-2869.2008.00658.x |
| 24 | Cerri M et al. Sleep 28:694 | 2005 | rat (24) | 24-h cold, 10 to −10 °C | REM "greatly depressed", temperature-dependent; rebound in recovery | https://doi.org/10.1093/sleep/28.6.694 |
| 25 | Komagata N et al. Curr Biol 29 | 2019 | mouse | ambient-temperature pulses, MCHR1-KO, optogenetics | warm pulses within the thermoneutral zone ↑ REM; MCH needed | https://doi.org/10.1016/j.cub.2019.05.009 |
| 26 | Ootsuka Y et al. Neuroscience 164 | 2009 | rat | BAT/brain/body temperature, HR, hippocampal theta | episodes every 94 ± 43 min; theta and HR rise first | https://doi.org/10.1016/j.neuroscience.2009.08.013 |
| 27 | Blessing W, Mohammed M, Ootsuka Y. Physiol Behav | 2012 | rat (14) | BAT temperature, eating | peaks every 96 ± 7 (dark) / 162 ± 16 (light) min | https://doi.org/10.1016/j.physbeh.2011.11.009 |
| 28 | Rukhadze I, Kamani H, Kubin L. Arch Ital Biol 149 | 2011 | rat (8) | tongue/nuchal EMG, 10-s epochs | twitches peak 70–120 s after REM onset | https://doi.org/10.4449/aib.v149i4.1385 |
| 29 | Sullivan D, Mizuseki K, Sorgi A, Buzsáki G. J Neurosci 34 | 2014 | rat | CA1/EC laminar LFP + units | hippocampal spindles share theta generators; also occur at NREM→REM transitions | https://doi.org/10.1523/JNEUROSCI.0552-13.2014 |
| 30 | Findlay G et al. Nat Neurosci | 2026 | rat | 48-h Neuropixels | SPW (and partly ripples, DS) track sleep need; "hippocampal sharp wave sleep" | https://doi.org/10.1038/s41593-025-02141-8 |
| 31 | Van Dort CJ et al. PNAS 112 | 2015 | mouse | PPT/LDT cholinergic optogenetics | ↑ REM episode number, not duration (entry ≠ maintenance) | https://doi.org/10.1073/pnas.1423136112 |
| 32 | Terzano MG et al. Clin Neurophysiol 111 | 2000 | human (25) | CAP in sleep cycles | ascending branch before REM: A2/A3 = 64.3 % of A phases vs > 90 % A1 earlier | https://doi.org/10.1016/s1388-2457(99)00245-x |
| 33 | Ginsberg AG et al. Front Neurosci 18 | 2024 | mouse | conditional propensity from GMM on log NREM | a GMM-based propensity "must eventually decay to zero" | https://doi.org/10.3389/fnins.2024.1431407 |
| 34 | Akhavan N et al. Front Neurosci | 2026 | rat (5), mouse, human | same, pooled | late decline attributed to circadian / wake intrusions / other factors | https://doi.org/10.3389/fnins.2026.1844209 |
| 35 | Park SH et al. PLoS Comput Biol 17 | 2021 | mouse | lognormal mixture | refractory "substage" with low θ/σ/spindles; the causal test proposed, not run | https://doi.org/10.1371/journal.pcbi.1009316 |
| 36 | Stephenson R et al. Sleep 36:1377 | 2013 | rat (10) | circadian × ultradian (3–6 h) transition probabilities | REM maintenance barely modulated by ultradian phase; residual heterogeneity | https://academic.oup.com/sleep/article/36/9/1377/2453890 |

Supporting (method or secondary):
- Vaupel JW, Yashin AI 1985, Am Stat 39:176, "Heterogeneity's ruses" (selection distorts population hazards):
  https://pure.iiasa.ac.at/2582
- Gygax L, Zeeland YRA, Rufener C 2021, Ethology (frailty survival models for behavioural sequences):
  https://doi.org/10.1111/eth.13225
- Miyawaki H, Diba K 2016, Curr Biol (spindles/SWRs in NREM predict firing changes in the following REM; rat):
  https://doi.org/10.1016/j.cub.2016.02.024
- Cerri M et al. 2017, Front Physiol (review; source for Parmeggiani 1975 and Kawamura & Sawyer 1965 on hypothalamic
  temperature around REM): https://doi.org/10.3389/fphys.2017.00624
- Prior audit for Franken 2002, Benington & Heller 1994, Bassi 2009, Weber 2018, Lecci 2017, Szymusiak & Satinoff
  1981: `docs/methods/sleep_sequence_literature_audit_2026-10-07.md`.

## Coverage note

Not found or not reached:
- any rodent study that tests REM-on stimulation during vs after the refractory phase;
- any paper linking SWR rate to REM entry;
- IS → REM vs IS → wake proportions in Gervasoni 2004;
- per-trough REM success rates in Osorio-Forero 2025;
- full texts of Kjaerby 2022 (PMC was blocked by reCAPTCHA) and Benington & Heller 1994.

Rat causal evidence for a gate is pharmacological (hypnotics) and thermal. Optogenetic and neuromodulator evidence is
from mice only.
