# Worked example — audit → summary → critique

**Illustrative only.** This shows the hand-off end-to-end on the real Direction-3 biological-day sleep
analysis (06-28→07-08, 5 rats). It is a teaching artifact, **not** the live `SCIENTIFIC_SUMMARY.md`.
Numbers trace to `change_log/2026-07-10-biological-day-sleep.md`.

---

## 1. Atomic claim audit (output of `scientific-report-promotion`)

| claim | measurement | scope | status | main_evidence | main_limitation | allowed_wording | forbidden_wording | required_validation | ledger_reference |
|---|---|---|---|---|---|---|---|---|---|
| Trunk-end marks locomotor site-departure, not true wake | first sustained afternoon movement above the ~7 in jitter floor | 5 rats, 06-28→07-08, daytime trunk, WISER only | **Established** (measurement) | emergence ~20.8 h; ρ(emergence,afternoon temp)=−0.02; sub-floor stirring unobservable by construction | in-nest arousal invisible → ~20:00 departure lags field ~18:00 wake | "locomotor emergence (site departure)" | "wake time", "arousal" | interior CV CH07/CH08 or ephys | CL 2026-07-10; report §A |
| Daytime rest is distributed across ≥6 mapped sites, not two houses | per-fix nearest-ROI classification over the full ROI set | classified ROI set, inch frame, 11 days | **Established** (descriptive, scoped) | dwell spreads house_1/house_2 + refuge/water/doorway/exposed; ~46% of transitions involve a non-house state | labels depend on ROI map + 15 in buffer; frame unverified | "across the mapped sites, rest is multi-site" | "rats prefer cooler microhabitats" (unmapped/physical) | ROI confirm + georeference | report §D |
| Within-trunk relocations are frequent (~3.1/rat-day) | count of confident state changes between ≥15-min segments | classified ROI set, 11 days | **Established** (descriptive, scoped) | mean 3.1, median 3, 170 total | segmentation depends on min-dwell/min-displacement thresholds | "rats relocate several times per rest period" | exact per-move destinations as physical sites | — | report §D |
| No clock-stereotyped ~10:00 relocation in the observed period | independent per-rat-day change-point (free location) | 11 days, this cohort | **Established** (scoped descriptive **negative**) | transition times spread (median 13.5 h), only ~11% within ±1 h of 10:00; robust to smoothing + dropout filter | absence of a **detected** cluster in 11 days ≠ proof no schedule exists | "no detectable 10:00 clustering in these 11 days" | "rats do not switch on a schedule" (evidence of absence) | more days / more animals | report §D; CP1 |
| On hotter days rats spend less time fully enclosed, more at doorway / near-water | within-rat Spearman of dwell fractions vs midday peak **ambient** temp | 11 days, within-rat, uncorrected | **Candidate** | any-shelter ρ=−0.44; doorway ρ=+0.58, water_2 +0.38, exposed −0.31 | n=11 days; ambient not shelter temp; uncorrected multi-comparison; doorway/exposed jitter-adjacent | "a **candidate** hot-day shift out of enclosed houses toward doorway/near-water" | "heat drives thermoregulatory site choice" | shelter thermistor + more days | report §E; E1 |
| Heat *causes* thermoregulatory doorway use | — (no manipulation; observational, ambient proxy) | — | **Unresolved** | — | no temperature manipulation; no shelter microclimate; site-coolness unverified | (do not state) | any causal phrasing | thermistor + within-site temp contrast, ideally manipulation | report §E |
| "Low movement" = sleep | low-speed occupancy proxy at the jitter ceiling | 11 days | **Unresolved** | rest window corroborated by the 21:00 circadian peak | proxy overcounts sleep; no physiology | "daytime rest / low-movement" | "sleep" (as validated state) | ephys or interior CV scoring | report caveats |
| Temperature-calibrated `sleep_end` (searched through the night) | crossing of an evening cooling threshold, hours-since-midnight | retired | **Rejected-Superseded** | ran past midnight (07-02 ≈02:20), conflating the active-night nap with trunk-end | — | (retired) | reporting it as the sleep-period end | — | CL 2026-07-10 (retired) |
| house_2-fraction measures sleep-site choice | fraction of trunk in house_2 (binary state space) | superseded | **Rejected-Superseded** | binary state space cannot represent refuge/water/doorway/exposed rest → its "no temperature effect" was uninformative | — | (superseded) | citing its null as evidence of no effect | — | CL 2026-07-10 (SUPERSEDED 07-11) |

---

## 2. Scientific summary (generated from the audit — ~900 words)

# Direction 3 — daytime sleep-site — scientific summary

_Current-state, illustrative. Methods & history: see Technical references._

## Biological picture
These are day-sleeping rats whose daytime rest is not a single fixed nest but a distributed, frequently
shifting use of several shelter sites. Over 11 days in 5 animals, WISER UWB position shows each rat
settling into a daytime rest period from about 05:00 and only leaving its rest site around dusk. During
that rest period the animals move among the two houses, secondary refuges, the water-tower surrounds,
shelter doorways, and occasionally open ground — several moves per day rather than one commitment.
Because WISER registers only body movement above a ~7-inch localization-noise floor, it tells us **where
an animal is, not whether it is asleep**, and it cannot see an animal stirring inside a nest. Every
statement below is therefore about rest-site *location*, in an unverified coordinate frame — not about
sleep depth or the moment of true waking.

## Main findings
1. **Daytime rest is multi-site, not a choice between two houses.** When each position fix is classified
   independently against the full mapped site set, dwell spreads beyond the two houses (mean fractions
   house_1 0.52, house_2 0.40, then refuge/near-water/doorway ≈0.05 each, exposed ≈0.02), and **≈46% of
   site-to-site moves involve a non-house site**; animals relocate **≈3.1 times per rest period** (median
   3, range 0–8; 170 moves over 55 rat-days). *Caveat:* labels depend on the mapped regions and a 15-inch
   jitter tolerance, and the frame is unverified — this describes the mapped state set, not physical
   microhabitat. (Appendix A1–A2.)

2. **The daily "get-up" WISER sees is a locomotor site-departure around dusk that is clock-fixed, and it
   is not true waking.** Departure clusters at **≈20.8 h (median; range 16.0–21.0)** with essentially no
   relationship to that day's afternoon temperature (**Spearman ρ = −0.02, n = 11**), and the dusk activity
   rhythm is locked from the first night. *Caveat:* field observation places in-nest waking ~2 h earlier,
   below WISER's ~7-inch movement floor — so this marks when the animals *leave*, lagging true arousal.
   (Appendix A3.)

3. **Relocations are frequent but not on a clock; there is no mid-morning "switch."** An independent
   change-point per rat-day — free to land anywhere — puts transition times across the whole period
   (**median 13.5 h, IQR [6.8, 18.2]**), with **only ≈11% within ±1 h of 10:00** (16% within ±2 h);
   44/55 rat-days show a supported move (median confidence 0.96, median displacement ≈203 in), and the
   spread holds across smoothing settings and after dropping high-dropout days (median 13.4 vs 13.5 h).
   *Caveat:* this is the absence of a *detected* clustering in 11 days, not proof that no schedule exists.
   (Appendix A4.)

## Candidate interpretation
**[Candidate] On hotter days the animals spend less of the rest period fully enclosed and more time at
doorways and near the water tower.** Within each rat, time fully inside a shelter falls as midday heat
rises (**within-rat Spearman ρ = −0.44**), while doorway and near-water time rise (**ρ = +0.58 and +0.38**;
exposed −0.31; **n = 11 days × 5 rats = 55 rat-days**). This is the one result that would change *why* we
think the rats move, so it is worth stating — but it remains candidate: 11 days only, driven by **ambient**
air temperature rather than any measured shelter microclimate, uncorrected across several sites, and the
doorway/exposed positions sit close to the localization-noise floor. It is an association, not a cause, and
no site has yet been shown to be cooler. (Appendix A5.)

## What is no longer supported
- ~~A temperature-calibrated "sleep-end" time~~ — it searched through the night and ran past midnight on
  warm days, mistaking the active-night nap for the end of daytime sleep.
- ~~"house_2 fraction" as a measure of sleep-site choice~~ — a two-house description cannot represent the
  refuge, near-water, doorway, and exposed rest that actually occurs, so its earlier "no temperature
  effect" was uninformative, not a real negative.

## Unresolved
1. **When do the rats actually wake?** True in-nest waking is below WISER's movement floor; resolving it
   redefines the whole day/night boundary. Needs the glass-free interior house cameras or ephys.
2. **Is any preferred site actually cooler?** Without a shelter thermistor the hot-day shift stays an
   association to outside air, not to microclimate.
3. **Is low movement sleep at all?** The rest measure is a low-speed proxy, never checked against
   physiology.

## Next decision
1. **Bring the interior house cameras online for the rest window** — glass-free, they can time true waking
   and check occupancy against WISER, addressing unresolved (1) and (3) together. Highest value.
2. **Install a shelter thermistor and add days** — the single step most likely to move the hot-day doorway
   shift from candidate toward established.
3. **Run the pole-dwell georeference survey** — so site labels and any "cooler site" claim rest on a
   verified frame rather than the current offset.

## Technical references
Full report (methods, full transition matrix, per-state correlations, sensitivity grids, figures):
`outputs/direction3_biological_day_sleep/…report.md`. Claim audit: this document, §1. Change log:
`change_log/2026-07-10-biological-day-sleep.md`. Status: `ANALYSIS_STATUS.md`.

## Appendix — how each finding was quantified
_Read on demand; not counted in the reading budget. Units: WISER inches (unverified offset frame), hours
are local-clock hours-since-midnight. Trunk = daytime rest period `[05:00, emergence)`._

### A1. Site composition — dwell fraction per state
- **Quantity** ($d_s$): fraction of trunk time a rat spends in mapped state $s$. Units: dimensionless.
  Range $[0,1]$; $\sum_s d_s = 1$.
- **Formula:** $$ d_s = \frac{1}{N}\sum_{t=1}^{N}\mathbb{1}\!\left[\operatorname{state}(t)=s\right],\qquad
  \operatorname{state}(t)=\text{nearest ROI within footprint}+15\text{ in, else doorway}/\text{exposed} $$
  where $N$ = trunk 5-min bins, $t$ indexes bins.
- **Value:** mean over 55 rat-days — house_1 0.52, house_2 0.40, refuge_1/water_2/doorway ≈0.05 each,
  exposed ≈0.02. (`refuge_4` 0.14 is the 07-03→07-07 **burrow** window — date-gated out of the sleep
  denominator, not counted as rest.)
- **Decision rule:** "multi-site" iff non-house dwell and the non-house transition share are non-negligible;
  here house_1+house_2 = 0.92 but transitions tell the real story (A2).
- **Sensitivity:** 15-inch jitter buffer on ROI membership; food ROIs folded into their enclosing house.
- **Inference:** dwell is not concentrated in a single site and the two houses do not exhaust it ⇒ rest is
  distributed across the mapped set.

### A2. Relocation rate and non-house transition share
- **Quantity** ($R$, $\pi_{\text{nonhouse}}$): $R$ = confident state changes per rat-day;
  $\pi_{\text{nonhouse}}$ = share of transitions with ≥1 endpoint ∉ {house_1, house_2}. Units: moves/day;
  fraction $[0,1]$.
- **Formula:** $$ R_{r,d}=\sum_i \mathbb{1}\!\left[g_i\neq g_{i+1}\right],\qquad
  \pi_{\text{nonhouse}}=\frac{\#\{i: g_i\notin H \ \lor\ g_{i+1}\notin H\}}{\#\{\text{transitions}\}} $$
  over merged segments $g_i$ (each ≥15-min, centroid shift ≥24 in), $H=\{$house_1,house_2$\}$.
- **Value:** $R$ mean 3.1, median 3, range 0–8 (170 moves / 55 rat-days); $\pi_{\text{nonhouse}}\approx0.46$.
- **Decision rule:** binary "house_1↔house_2" would give $\pi_{\text{nonhouse}}\approx0$; observed 0.46 ≫ 0.
- **Sensitivity:** min-segment 15 min and min-displacement 24 in guard against jitter-flicker moves.
- **Inference:** frequent moves, nearly half touching non-house states ⇒ the binary relocation label was
  wrong; sleep-site behavior is genuinely multi-site.

### A3. Locomotor emergence vs afternoon temperature
- **Quantity** ($E$, $\rho_E$): $E$ = first afternoon locomotion onset (site departure), h;
  $\rho_E$ = Spearman(E, afternoon peak temp). Range $E\in[16,21]$ (clamped); $\rho_E\in[-1,1]$.
- **Formula:** $$ E=\min\{h\ge15{:}00:\ a(h)\ge a_{\text{base}}+\max(0.03,\,0.20\,(a_{\text{dusk}}-
  a_{\text{base}}))\ \text{for}\ \ge 3\ \text{bins}\} $$ with $a$ = active fraction per 5-min bin,
  $a_{\text{base}}$ = midday baseline, $a_{\text{dusk}}$ = dusk peak.
- **Value:** $E$ median 20.8 h (range 16.0–21.0; the 07-03 16.0 is a fog-day afternoon blip);
  $\rho_E=-0.02$, n = 11 days.
- **Decision rule:** $|\rho|<0.2\Rightarrow$ no detectable association.
- **Sensitivity:** relative dusk-ramp threshold (not an absolute cut); clamp $[16,21]$ prevents past-midnight
  runaway (the failure of the retired `sleep_end`).
- **Inference:** departure clusters near dusk and is flat vs temperature ⇒ circadian-fixed *departure*.
  Because sub-floor stirring is unobservable, $E$ ≠ true wake (measurement limit, not a null result).

### A4. Change-point timing — no 10:00 cluster
- **Quantity** ($\tau$, confidence $c$): $\tau$ = within-trunk change-point time (h); $c$ =
  displacement / (displacement + within-segment scatter). $c\in[0,1]$.
- **Formula:** $$ \tau=\arg\max_{k}\ \lVert \operatorname{med}(P_{<k})-\operatorname{med}(P_{\ge k})\rVert_2,
  \quad\text{supported iff disp}\ge100\text{ in with}\ge3\text{ bins/side} $$ over the 3-bin-smoothed 5-min
  median-position series $P$.
- **Value:** 44/55 rat-days supported (median $c$ = 0.96, median displacement ≈203 in ≈ house separation);
  $\tau$ median 13.5 h, IQR [6.8, 18.2]; **P(|τ − 10:00| ≤ 1 h) ≈ 0.11**, ≤ 2 h ≈ 0.16.
- **Decision rule:** a 10:00-stereotyped switch would concentrate $\tau$ near 10:00; a ±1 h window is ~1/8
  of the ~16 h trunk, so ~0.11 ≈ chance — no clustering.
- **Sensitivity:** 36/44 stable across smooth_bins ∈ {1,3,5}; median 13.4 vs 13.5 h after the >25%-dropout
  filter.
- **Inference:** $\tau$ spread and no 10:00 excess ⇒ *no detected* clock cluster (absence of detected
  evidence, not evidence of absence).

### A5. Candidate temperature association (multi-site, within-rat)
- **Quantity** ($\rho_s$): within-rat Spearman between per-day dwell fraction in state $s$ and that day's
  midday peak **ambient** temperature, computed per rat then pooled (rat-centered to remove identity).
- **Formula:** $$ \rho_s=\operatorname{Spearman}\big(\,d_{s,r,d}-\bar d_{s,r}\,,\ T_d-\bar T\,\big)
  \ \text{pooled over}\ (r,d) $$ with $T_d$ = day-$d$ midday peak temp.
- **Value:** any-shelter $\rho=-0.44$; doorway $+0.58$; water_2 $+0.38$; exposed $-0.31$; n = 55 rat-days
  (11 days × 5 rats), **uncorrected** across sites.
- **Decision rule / bands:** $|\rho|<0.2$ none; $0.2$–$0.4$ weak; $>0.4$ moderate. No multiple-comparison
  correction ⇒ candidate, not confirmed.
- **Sensitivity:** ambient (not shelter) temperature; doorway/exposed states sit near the ~7-inch jitter
  floor; day-level temperature is shared across the 5 rats (not 55 independent exposures).
- **Inference:** enclosed-house time falls and doorway/near-water rise with heat ⇒ a **candidate**
  thermoregulatory shift the binary house_2-fraction test could not see; not causal, no site verified cooler.

---

## 3. Critique — is it genuinely readable?

**Reads in one pass.** One sentence captures it: *daytime rest is multi-site and frequently shifts (~3.1
moves/day, ~46% non-house), the dusk "get-up" is a clock-fixed departure (~20.8 h, ρ = −0.02) that lags
true waking, and a hot-day shift toward doorways (ρ = −0.44 enclosed) is a candidate.* The dominant result
lands within ~30 seconds, candidate work is separated with its dependency named, and the two superseded
claims are struck. Narrative ≈ 810 words (plus a short technical-reference link list), inside the
700–1,200 budget; the quantitative appendix adds drill-down depth on demand, not counted in the read.

**Numbers are now load-bearing and in the narrative.** Every headline and candidate finding carries its
effect size + n + the null it is judged against (≈3.1 moves/day; ≈46% non-house; E ≈ 20.8 h with
ρ = −0.02, n = 11; τ median 13.5 h, 11% near 10:00; any-shelter ρ = −0.44, doorway +0.58, n = 55). A reader
gets the magnitude without opening the code — the earlier draft's vague "several moves per day" is gone.

**The appendix shows how each conclusion was reached.** Each finding has a definition (formula + plain text,
units, range), the computed value with n and dispersion, the explicit decision rule/null (e.g.
$\sum_s d_s = 1$; $|\rho|<0.2\Rightarrow$ none; the ±1 h-of-10:00 chance calculation), a sensitivity line,
and a one-line inference. That is enough to reproduce the *logic* of the claim without the raw tables.

**Preserved audit distinctions:** measured-vs-construct (departure ≠ wake; "rest" not "sleep"), descriptive
Established vs Candidate association vs Unresolved cause, absence-of-detected-clustering vs evidence-of-
absence (finding 3), conditional-on-use vs composition, and scope confined to the mapped state set. No
sentence exceeds an `allowed_wording`.

**Still kept out entirely** (linked in Technical references, not even in the appendix): the full transition
matrix cell-by-cell, all per-day rows, the complete sensitivity grid, every function name / figure ID, and
"self-test PASS." The appendix gives the *inference-critical* numbers (one value + rule per finding), not
every cell — the line between appendix and technical report.

**Honest weaknesses.** (a) The one-sentence picture is three clauses — acceptable, at the edge. (b) Findings
1 and 3 both touch relocations; kept separate because one is *composition* (where) and the other *timing*
(when), which the reader must not conflate. (c) The appendix uses LaTeX — it renders in a Markdown viewer
but is denser in a raw terminal; that is the intended narrative/appendix split (narrative for the one read,
appendix for the scientist who wants the math). Net: passes the final readability test, including the two
new quantitative checks; the one-sentence-picture check remains the closest call.
