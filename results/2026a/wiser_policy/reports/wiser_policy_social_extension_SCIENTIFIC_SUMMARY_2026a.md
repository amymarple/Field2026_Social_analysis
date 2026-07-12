# Scientific summary — What structures rats' movement decisions, and does the group matter?

*Standalone, current-state summary (regenerated 2026-07-12) of the behavioral-policy program: the
locomotor decision hierarchy built on WISER UWB tracking, now over **eleven nights**. ~5 min read; the
quantitative appendix is read on demand. **Nothing here is Established as a biological result** — all
findings are Candidate, gated by the pilot's frame/hardware limits. Links down to the technical ledger.*

## Biological picture

Over eleven nights (2026-06-28→07-08, every night the five UWB tags were present, up to Hypnos's removal;
active window 21:00–05:00) we asked which low-level movement decisions of an outdoor rat group are
structured, and by what. Working only with what the sensor resolves — coarse locomotion above a ~7 in
position-jitter floor, in an **unverified** coordinate frame that supports topology and coarse distance
but no direction or route — one picture holds: the animals' resolvable movement decisions follow a
**single shared rule** set by the physical layout and by how long a rat has already stayed somewhere,
with **no detectable individual signature** and **no recoverable reward**. The group matters, but chiefly
as **inter-individual spacing during movement**; the once-headline "crowding keeps residents home" effect
**shrinks to a small, borderline signal** on the fuller dataset. Every quantity is a coarse proxy
(low-speed "rest" is not validated sleep; a bout "onset" is a lower bound that misses in-nest stirring),
so all findings are candidate and stated as associations, not causes.

## Finding 1 — One shared, time-invariant environment-and-dwell rule; no individual policy, no reward

When a rat leaves a named site is predictable from an explicit-layout + elapsed-dwell baseline (held-out
**skill 0.13–0.26** across a preregistered parameter grid, n = 11,675 leave epochs), and that rule is
**constant**: letting it vary by hour-of-night or by night yields no held-out gain, and knowing *which*
individual adds essentially nothing (personalization ≈ 0.001 bits). Apparent hour/night differences are
shifts in *where the animals are*, not in the rule. We therefore stop at an interpretable shared choice
model; a reward function is **not identifiable** in a multi-agent, non-stationary, partially observed,
measurement-degraded system, so no utility or goal is claimed. This is the backbone result and the most
robust one — it held under adversarial review and is unchanged by the extension to eleven nights.

## Finding 2 — The group acts as movement spacing, not attraction; crowding-on-leaving is real but small

Within active movement bouts, animals maintain a **preferred inter-individual spacing**: against a
mismatched-night (layout) control they *close* distance on **far** group-mates (>3.8 m: e_day **+0.12,
positive on 11/11 nights**) and *open* distance from **near** ones (1–2 m: −0.26, 0/11 nights; 2–3.8 m:
−0.10, ~0–1/11), a distance-dependent pattern significant night-by-night (sign-test p ≤ 0.012). Extending
the data **strengthened** this signal, and a nap/circadian cross-check shows it is **not an artifact of
when the group rests**: it holds in both the active and the deep-nap population-rest phases, so it is a
property of active movement whenever it occurs. This is now the clearest social result.

A second social effect is real but modest. Real-time crowding is associated with a resident **staying
put**, but on eleven nights the effect **attenuates to ≈0.003 bits (jitter-safe 0.0027)** — down from
≈0.012 on the first eight nights. It still beats every null (time-shift z 3.4, day-shuffle z 3.0,
jitter-safe day-shuffle z 2.5) and **survives a rest-need control** (67 % retained after adding the
circadian rest rhythm and the focal's own rest-state), so it is a genuine real-time group effect and
*not* merely a huddle/rest confound — but its **magnitude now falls below our 0.003-bit promotion
threshold**, and it is **2-night fragile** (the pooled 0.0027 is carried by 06-28 and 07-06; drop them and
it collapses to 0.0007). Crucially, whether this attenuation means the effect is *genuinely small* or is a
*front-loaded effect averaged flat* (strong on novel early nights, habituating later — a group-sampling
hypothesis) **cannot be resolved at eleven nights**: the per-night held-out increment shows a weak,
non-significant lean in the front-loaded direction (early nights 0.0046 > late 0.0020) but a night-permuted
test is null and the design has only ~0.27 power to detect a decay of the relevant size, so the hypothesis
is **neither refuted nor confirmed**. A *direct* test of the proposed mechanism — group *following*
("a neighbour just left, so I leave"), which the static-crowding features cannot encode — finds it
**negligible** (held-out Δbits ≤ 0.001 even at the most favourable 5-minute window) and, if anything,
slightly *stronger* late, not front-loaded. Meanwhile the *same* group-social state does **not** predict
when a resting animal *starts* a bout (Δbits ≈ 0.0002). So the group governs *spacing while moving*
strongly, *when a resident leaves* weakly, and *when movement begins* not at all — a process-specific
pattern, all **group-level** (herd, not pairs) and **associative**, not attraction.

## Finding 3 — Movement mostly ends in the open, and where it lands is set by layout, not a search preference

Counting a "destination" **only after sustained stable residence**, most departures do not go anywhere in
particular: **≈61 % of departures end with the animal stopping in the open** (open-field termination),
only ≈18 % relocate to another named site, and ≈12 % return to the same site (n = 410 departures, stable
across the settlement-threshold grid). Among the 123 excursions that *do* end at a named site, there is
**no return-vs-explore preference beyond the layout base rate**: the 76 % raw return rate is exactly what
site popularity alone predicts (night-block sign-test p = 0.55), so "goes back to a familiar site" is not
a demonstrated tendency here — a few sites are simply popular. Coarse path geometry is uniformly tortuous
(bout straightness ≈ 0.2) with only a modest radius gradient, and fine search structure is
jitter-unresolvable — so no area-restricted-vs-global "search strategy" is claimed. Where a rat does
relocate, origin still conditions destination (Δbits ≈ 0.56 / ~15 % skill over the hub base rate) with
house-to-house switching dominant, but on ~75 events this stays exploratory.

## Candidate interpretation to watch

**Distance-dependent spacing (Finding 2) as active maintenance of a characteristic distance** rather than
passive aggregation. It is the freshest and most biologically interesting result, now robust across
eleven nights and circadian phase — but still coarse (net proximity change over a bout, ≥1 m, no
orientation), group-level, and we **cannot yet separate active steering from passive co-location** in
shared space. That separation needs orientation/contact from video.

## No longer supported

- **The 8-night crowding-on-leaving magnitude (≈0.012 bits, ~4 % skill).** The fuller eleven-night data
  put it near ≈0.003 — still real and rest-independent, but small; do not cite the larger figure.
- **"Rats travel purposefully between named sites."** Most departures end in the open; relocation is the
  minority outcome, and named destinations track site popularity, not a return/explore choice.
- **Fine-movement structure** (heading, turn angles, "decision legs", search mode): not separable from
  position jitter at this resolution — no route or search-strategy claim.

## What remains unresolved (ranked by impact)

1. **Is the crowding-on-leaving effect genuinely small, or a front-loaded effect averaged flat?** At
   eleven nights this is unresolvable (weak non-significant lean toward front-loaded; ~0.27 power; a direct
   following test is negligible). Needs more nights and/or a CV co-presence check — not more re-analysis of
   these eleven.
2. Is the spacing **active steering or passive co-location**? Needs orientation/contact from video.
3. All spatial claims remain gated by the **unverified coordinate frame** (the georeference survey).
4. Does settling at a site track **other rats at the destination** (a social pull we did not test), given
   that it does *not* track the circadian rest rhythm?

## Next decision (ordered by expected value)

1. **Georeference survey** — it gates every spatial claim (route, direction, metric distance).
2. **Shelter/interior cameras** for the spacing/steering, contact, and true-sleep questions WISER cannot
   resolve.
3. **Destination-side social test** — whether relocation/settlement is drawn to conspecifics already
   present (the untested arm of Finding 3).

## Technical references

Change logs: [module 3 initiation](../../../../change_log/2026-07-11-locomotor-bout-initiation.md) ·
[module 5 leaving](../../../../change_log/2026-07-10-decision-unit-hysteretic-social.md) ·
[module 6 destination/settlement](../../../../change_log/2026-07-11-destination-settlement-rebuild.md) ·
[module 7 approach/avoid](../../../../change_log/2026-07-12-approach-avoid.md) ·
[Phase 4 search excursions](../../../../change_log/2026-07-12-phase4-search-excursions.md) ·
[11-night extension + rest/circadian/social](../../../../change_log/2026-07-12-11night-rest-social-circadian.md) ·
[DBV resolution limit](../../../../change_log/2026-07-11-dbv-crosscheck-locomotor.md). Index:
[`ANALYSIS_STATUS.md`](../../../../wiser/ANALYSIS_STATUS.md). Full tables/reports in `outputs/locomotor_initiation_*`,
`outputs/destination_settlement_*`, `outputs/approach_avoid_*`, `outputs/search_excursions_*`.

---

## Quantitative appendix — how each finding was quantified

Primary loss throughout: **held-out cross-entropy in bits/decision**, leave-one-night-out (whole nights =
the 11 outer blocks). `Δbits = H_baseline − H_model` (>0 = better); `skill = 1 − H_model/H_baseline`.
Promotion threshold for a social/added increment: Δbits > 0.003 AND survives its nulls.

**F1 — shared, time-invariant leaving rule; individual negligible; reward not identifiable.** *Quantity:*
held-out skill of the layout+dwell hazard; incremental bits from time-variation and individual identity.
*Values (n = 11,675 leave epochs, 11 nights):* environment+dwell **skill 0.13–0.26**; hour-varying and
night-varying held-out gain ≤ 0; personalization ≈ **0.001 bits**. *Rule:* held-out gain ≤ 0 or ≪ 0.003
⇒ no added structure; ~11 blocks under-power a <0.003-bit effect ⇒ NO-GO is an upper bound, not exact
zero. *Inference:* one shared rule, constant in time, no individual policy; reward preconditions fail ⇒
not identifiable.

**F2a — distance-dependent social spacing.** *Quantity:* per-night geometry-adjusted effect `e_dir` and
real-time social increment `e_day` of toward-ness (dimensionless, [−1,1]). *Formula:*
$\text{toward}=(d_0-\lVert p_{\text{end}}-p_{\text{partner,0}}\rVert)/\lVert\Delta\rVert$;
$e_{\text{day}}(n)=\overline{\text{toward}}_{\text{valid}}(n)-\mu_{\text{day}}(n)$ (same partner, same
hour, different night = layout null). *Value (n = 5,717 pairs, 11 nights):* e_day far (>3.8 m) **+0.12,
11/11 nights**; near (1–2 m) **−0.26, 0/11**; 2–3.8 m −0.10, ~1/11; e_dir positive in every bin, 11/11.
*Null/rule:* **night-level two-sided binomial sign test p ≤ 0.012** (NOT the pseudoreplicated per-pair z).
*Sensitivity:* holds in both active and nap population-rest phases (circadian-robust). *Inference:* e_day
sign flips with distance and is night-consistent ⇒ preferred-spacing tendency, beyond layout and nap
timing.

**F2b — crowding suppresses leaving (attenuated, rest-independent, stationarity unresolved).** *Quantity:*
jitter-safe group-social increment on the per-epoch leaving hazard. *Value (11 nights):* Δbits mean
**0.0030**, jitter-safe **0.0027**; nulls time-shift z 3.4, day-shuffle z 3.0, jitter-safe day-shuffle z
2.5. *Rest control:* 0.0027 → **0.0018 (67 % retained)**, day-shuffle z 2.3; rest itself predicts leaving
(Δbits 0.0048). *Fragility:* pooled 0.0027 → **0.0007** dropping nights 06-28 + 07-06 (the two carriers).
*Non-stationarity (reviewer's front-loaded/habituation hypothesis):* on the correct **held-out** per-night
increment, early(0-2) **0.0046** > late(3-10) **0.0020** (weak, non-significant; Spearman ρ = −0.19, perm-p
0.57), pooled night-permuted social×novelty interaction **null** (perm-p 0.17 / 0.95), planted-decay
detection power only **~0.27–0.29** (FPR ~0.21) ⇒ **UNRESOLVED, neither refuted nor confirmed**. *Following
mechanism (F2d):* `n_others_departed_W` (other tags' bout onsets in [t−W,t)) beyond static crowding: held-out
Δbits ≤ **0.0010** (best at W=300 s; sign-test p 0.23), beats a circular time-shift null (z 2.27, a whisper
of real-time coupling) but ≪ threshold, and early(0-2) −0.0004 < late 0.0015 ⇒ **negligible + not
front-loaded**. *Rule:* GO requires Δbits > 0.003 ⇒ **magnitude NO-GO**; direction survives all nulls + rest
control. *Inference:* a genuine but small real-time group effect on leaving, not a rest/huddle artifact; the
8-night 0.012 is superseded; whether the small size reflects habituation-averaging is not resolvable at
n=11. (Ref: `change_log/2026-07-12-social-nonstationarity-and-following.md`, adversarially verified.)

**F2c — social does not drive initiation.** *Value:* social increment on the bout-**initiation** hazard
Δbits ≈ **0.0002** ⇒ NO-GO on magnitude. *Inference:* social predicts leaving, not initiation.

**F3a — destinations are the minority; no return-vs-explore preference beyond layout.** *Values (n = 410
departures):* open-field termination **251 (0.61)**, relocation **75 (0.18)**, same-site return **48
(0.12)**, censored 19, pass-through 17; stable across the settlement grid. Return-vs-explore (n = 123
named-dest excursions): raw return rate **0.76** but night-block effect vs the site-popularity null p =
**0.55** ⇒ not distinguishable from layout. Origin-conditioned relocation held-out **Δbits ≈ 0.56 / ~15 %
skill** over the hub base rate (n ≈ 75, exploratory). *Inference:* most departures terminate in the open;
where a rat relocates, origin predicts destination, but there is no demonstrated return/explore tendency
beyond site popularity.

**F3b — coarse search geometry (DBV-capped).** *Values (n = 1,541 bouts):* 99.7 % clear 3 jitter floors;
median straightness ≈ 0.17–0.21 across in_place/relocating/open; median radius in_place 100 < relocating
124 < open 142 in. *Rule:* fine turn/ARS structure is not resolvable at the ~7 in jitter floor ⇒ coarse
geometry only. *Inference:* uniformly tortuous movement with a modest radius gradient; no ARS-vs-global
strategy claim.

*All values are code-verified (offline selftests PASS) — code verification is not biological validation.
Frame UNVERIFIED; rest/onset are coarse proxies; single 11-night pilot; whole nights are the outer
inference blocks.*
