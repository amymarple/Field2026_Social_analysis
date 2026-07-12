# Destination-choice — GATED fit (Module 6, Phase 2)

**Status:** ⚠️ candidate / EXPLORATORY. Fit ONLY because the representation validated (`validation_report.md`, gate PASS). 55 clean relocation events (settlement -> different settlement); generated 2026-07-12T04:02:37.476901.

## Definitions (formula + plain text)

- **Relocation** — a departure from a sustained settlement that ends in a *different* sustained
  settlement (the only destination-choice event; same-site returns / pass-throughs / open-field
  terminations / censored are excluded).
- **Held-out categorical bits** $H=-\frac1N\sum\log_2 p(\text{chosen dest})$ (leave-one-night-out).
  **M0 global** = $P(\text{dest})$ from training; **M1 origin-conditioned** = $P(\text{dest}\mid
  \text{origin})$ (Laplace $\alpha{=}0.5$ over the origin's training choice set); **uniform** =
  $1/|C(o)|$. **skill** $=1-H/H_{\text{uniform}}$.
- **Matched-choice house preference** — per animal, cross-night consistency of the fraction settling
  in house_1 vs house_2 (LONO transfer error $<0.15$ AND $|pref-0.5|>0.15$).

## Results

**Held-out choice bits (robust result):** global 4.553 → origin-conditioned
**3.919** bits → **origin-over-global Δbits = 0.6345
(skill 0.139)**. Knowing the ORIGIN improves destination prediction beyond
the global hub rate — this comparison is baseline-independent (both models share the EPS out-of-support
floor, so unpredictable held destinations cancel). The uniform-over-supported-set reference
(9.099, skill-vs-uniform 0.569) is **baseline-SENSITIVE at
n=55** (dominated by held destinations outside the training support) — reported for completeness, not
as the headline.

**Structure (descriptive counts, not a directional claim):** top destinations by count
{'house_1': 21, 'house_2': 12, 'refuge_1': 6, 'tunnel_1': 6, 'refuge_3': 4}; **house↔house switches = 19** of 55
relocations. (Endpoints only — the frame is UNVERIFIED, so no route/direction/"feeds into" is claimed.)

**Individual house preference:** stable cross-night preference in
**0/2** animals.

## Power & scope

~55 relocations over 8 nights (~7/held-night); per-origin support is thin (only house_1/house_2 have >10). Held-out skill is an effect-size estimate, NOT a powered test. Most departures are open-field terminations, not relocations. Endpoints only (frame UNVERIFIED — no route/path/direction). Not "route choice", not
"goal-directed navigation". The headline of Module 6 is the **validated representation** (most shelter
departures terminate in the open, not at a named site); this choice fit is a thin, gated add-on.
