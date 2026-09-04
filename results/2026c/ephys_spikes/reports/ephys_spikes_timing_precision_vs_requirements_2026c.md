# Cross-modal timing: what the neurologger chain delivers vs what the analyses need — cohort 2026c

Written 2026-09-04 (hand-written assessment; the numbers come from the regenerated reports named below, re-derive from
those rather than editing here). Status of every claim: **MEASURED** unless marked ESTIMATE.

**Question.** Spike times live on the logger's 20 kHz sample clock; position lives on the field PC (video at 20 Hz via
the 1 Hz LED sync, WISER UWB at ~3.8 Hz). How well are the two aligned now, and how well do place-cell and social
analyses actually need them aligned?

**Answer.** The ephys → field-PC-time chain is at 8–22 ms typical and ≤ 60 ms worst case (excluding the 08-31
troubleshooting block, which has no PC time and is excluded anyway). Place-field analysis tolerates 100–300 ms before
timing error reaches the position sensors' own noise; behaviour-event alignment tolerates one video frame (50 ms). The
ephys chain is therefore not the bottleneck by a factor of 5–10; the bottleneck is the position side (WISER 0.26 s fix
interval and 10–18 cm jitter, then the 50 ms video frame). The one thing the chain cannot support is millisecond spike
synchrony **between** animals.

## 1. Precision budget, link by link

| Link | Precision | Evidence | Status |
|---|---|---|---|
| spike ↔ LFP, same logger | 50 µs (one sample; shared clock) | by construction | MEASURED |
| spike → field-PC ms, natively fitted sessions (58 / 311.2 h) | anchor residual rms 8–22 ms; line systematic ≤ 13 ms (§2 linearity) | `ephys_spikes_pc_time_chain_2026c.csv` `native_residual_ms`; §2 | MEASURED |
| … sessions spanning a field-PC clock step (9 / 59.4 h) | + up to 40 ms after the step (step size ±0.04 s) | `cohorts/2026c.yaml` `field_pc_clock_steps`; change_log 2026-09-04 | MEASURED |
| … tail-extrapolated sessions (3) | 1–50 ms on the extrapolated tail | `tail_extrap_unc_ms` (formal; SF10 `2_20260901_125856` realistically ~50 ms) | MEASURED |
| … assumed-drift sessions (10 / 25.0 h, each 1–4 h) | ≤ 60 ms worst at the session end | $\delta_{\text{end}}$ with $\sigma_{\Delta b}$ = 2.0 ppm, $T$ = 4 h (§4) | MEASURED |
| … corrupt sync lanes (5 / 16.7 h, 08-31 daytime FM62) | no PC time | `ephys_spikes_offload_qc_2026c.md` | MEASURED (excluded block) |
| BLE transport latency, constant | ≤ 50 ms, common to every logger and session | BLE connection-interval class; NOT measurable from internal consistency | ESTIMATE |
| video frame → field-PC ms (LED 1 Hz) | LED-on = PC second to < 1 ms; frame → PC < 1 frame (50 ms at 20 fps); frame → sample ≈ 22 ms in the field selftest (25 fps) | field2026-sync `from-field/2026-09-03_led-sync-pipeline.md` | MEASURED (synthetic selftest) |
| WISER UWB position | fix interval ≈ 0.26 s per tag (3.7–3.9 Hz); radial jitter 4–7 in (10–18 cm) | `wiser/README.md` | MEASURED (earlier cohorts) |

## 2. Is the logger drift linear? (this is what makes any of the above hold over 13 h)

Eight long, well-anchored sessions (6–11 h), robust line vs parabola:

| session | h | drift ppm | anchor rms ms | parabolic bow $\beta$ ms | hourly mean residual after the line |
|---|---|---|---|---|---|
| SF08 17_20260902_190241 | 10.96 | −20.7 | 10.3 | 6 | within ±13 |
| SF11 17_20260902_190852 | 10.75 | −26.7 | 13.4 | 6 | within ±4 |
| SF12 11_20260902_083748 | 9.72 | −19.2 | 9.6 | 1 | within ±3 |
| SF11 12_20260902_083534 | 8.48 | −26.1 | 13.2 | 13 | within ±8 |
| SF10 9_20260902_083247 | 8.47 | −22.6 | 12.5 | 12 | within ±8 |
| SF09 10_20260902_083015 | 8.47 | −26.0 | 12.5 | 12 | within ±14 |
| SF10 6_20260901_233920 | 7.79 | −23.2 | 8.2 | 1 | within ±1 |
| SF12 15_20260903_002228 | 6.49 | −20.6 | 11.7 | 6 | within ±0 |

Median bow 6 ms, worst 13 ms, no systematic curvature. Between sessions of the same logger the rate deviates from
that logger's median by 0.8 ppm (median) / 2.0 ppm (sd); day- vs night-session medians differ by ≤ 1.5 ppm per logger.

## 3. What each analysis needs

Timing error becomes position error through the animal's speed, $e_x = v\,\delta t$ (§4). Rats in the paddock move at
~10–30 cm/s when locomoting and 50–100 cm/s in bursts (ESTIMATE, typical open-field values; the cohort's own speed
distribution is a WISER quantity and carries that pipeline's caveats).

| timing error $\delta t$ | $e_x$ at 30 cm/s | $e_x$ at 100 cm/s | where this sits |
|---|---|---|---|
| 20 ms | 0.6 cm | 2 cm | current typical |
| 60 ms | 1.8 cm | 6 cm | current worst |
| 190 ms | 5.7 cm | 19 cm | the pre-2026-09-04 worst case (removed) |
| 500 ms | 15 cm | 50 cm | matches WISER's own jitter |

Position-side noise for comparison: one WISER fix interval (0.26 s) smears a 30 cm/s animal by 8 cm and its jitter is
10–18 cm; one video frame (50 ms) is 1.5 cm at 30 cm/s plus a few cm of tracking noise.

| analysis | needs (cross-device) | current | verdict |
|---|---|---|---|
| place fields / spatial rate maps (bins ≥ 20 cm in a 6 × 12 m paddock) | 100–300 ms before $e_x$ reaches sensor noise | 20–60 ms | margin ≥ 5× |
| theta phase precession, ripples, sleep staging | none across devices (same logger) / seconds | 50 µs / n.a. | not limited by this chain |
| cross-animal behaviour events (approach, contact, follow) | one video frame, 50 ms | two chains, 15–30 ms combined | inside one frame |
| cross-animal spike synchrony at ms scale | ≤ 5 ms | 15–30 ms + unknown constant (§1) | **not supported**; needs a shared hardware TTL, not more anchors |
| absolute response latency to a PC-timed event | ≤ 20 ms | bounded by the ≤ 50 ms constant BLE latency | would need one calibration experiment; not needed for the goals above |

## 4. Definitions

Symbols: $t$ = logger sample time (s) from session start; $y(t)$ = field-PC time (ms) carried by a BLE anchor at $t$;
$T$ = session duration (s); $b$ = fitted rate ratio (dimensionless); drift in ppm $= (b-1)\times10^6$; $v$ = animal
speed (cm/s). Units: ms for time errors, cm for position errors, ppm for rates.

### Anchor residual ($r_i$, `native_residual_ms`)
$$ r_i = y_i - (a + b\,t_i\cdot 1000), \qquad \text{rms} = \sqrt{\tfrac{1}{n}\textstyle\sum_i r_i^2} $$
over the anchors kept by the robust fit (MAD gate, 150 ms floor). **Text:** scatter of a single BLE anchor around the
fitted line. Units: ms. Range $[0,\infty)$; 8–22 ms on this cohort = the BLE precision class.

### Parabolic bow ($\beta$)
With $\tau = (t-\bar t)/T \in [-\tfrac12,\tfrac12]$ and a least-squares parabola $y = c_2\tau^2 + c_1\tau + c_0$ through
the kept anchors,
$$ \beta = |c_2| / 4 $$
**Text:** the largest departure of the best-fitting parabola from its own chord over the session, i.e. the maximum
error a straight line makes if the true drift changes linearly with time. Units: ms. Range $[0,\infty)$; 6 ms median /
13 ms worst here = linear to within the anchor scatter.

### Between-session drift deviation ($\Delta b$)
$$ \Delta b_s = \text{drift}_s - \operatorname{median}_{s' \in L(s)}\,\text{drift}_{s'} $$
where $L(s)$ = the natively fitted sessions > 1 h of the same logger with no clock step inside. **Text:** how far one
session's rate sits from its logger's typical rate; $\operatorname{median}|\Delta b|$ = 0.8 ppm, $\sigma_{\Delta b}$ = 2.0 ppm.
Units: ppm.

### End error of an assumed-drift session ($\delta_{\text{end}}$)
$$ \delta_{\text{end}}(T) = |\Delta b|\times10^{-6}\times T \times 1000 $$
**Text:** the PC-time error at the end of a session anchored only at its start, when its drift is taken from the
logger's median. Units: ms. Typical (0.8 ppm) 22 ms at 8 h / 37 ms at 13 h; worst (2 sd = 4.0 ppm) 117 ms / 187 ms; for
the 1–4 h sessions that remain in this class, ≤ 60 ms.

### Drift error from one extra touch ($\sigma_b$) and the tail it leaves
$$ \sigma_b = \frac{\sqrt{2}\,\sigma_c}{t_1}, \qquad \sigma_c = \frac{\sigma_r}{\sqrt{n_c}}, \qquad
   \delta_{\text{tail}} = \sigma_b \,(T - t_1) $$
where $t_1$ = time of the touch (s), $n_c$ = anchors in the touch (~25 for one minute), $\sigma_r$ ≈ 15 ms.
**Text:** a touch at $t_1$ measures the rate to $\sigma_b$ and the remaining tail is extrapolated at $\delta_{\text{tail}}$.
Units: ppm and ms. At $t_1$ = 6 h of a 13 h session: 0.20 ppm and 4.9 ms.

### Timing error as position error ($e_x$)
$$ e_x = v\,\delta t $$
**Text:** the displacement an animal covers during the timing error, i.e. how far a spike is mis-placed on the map.
Units: cm (with $v$ in cm/s, $\delta t$ in s). Compare with the position sensor's own noise to decide whether timing
matters.

### Requirement thresholds
Values **100–300 ms** (place fields) $= e_x$ equal to the WISER jitter (10–18 cm) at 30–100 cm/s; **50 ms**
(behaviour events) $=$ one video frame at 20 fps; **≤ 5 ms** (spike synchrony) $=$ the usual coincidence window.
**Text:** the point at which cross-device timing error would become visible in each analysis.

### Field-PC clock-step size (registered)
Measured as described in change_log 2026-09-04: drift-log line difference at the reboot ($1.263$ s) and free-step anchor
fits ($1.265/1.281/1.319$ s); adopted $1.28 \pm 0.04$ s. The ±0.04 s is the "+ up to 40 ms" term in §1.

## 5. Consequences

- No further anchor work is needed for place-cell or social-behaviour analyses; the remaining protocol suggestions
  (a 1-minute touch at 13:00–14:00; no midnight Stop→Start now that FM65 is verified power-cut-safe) are conveniences
  — a bounded worst case and one continuous epoch per night for sorting — not precision requirements.
- Any millisecond cross-animal synchrony question needs a shared hardware sync line; state that in the design rather
  than expecting the BLE chain to deliver it.
- Every session's `pc_time.dat` + `pc_time_fit.json` under `E:/3rd_rat_spikes/analysis/pc_time/` already carries the
  join schema the LED pipeline consumes (`model.slope`, `model.intercept_ms`, `recording_start_ms`, `sample_rate_hz`,
  `common_start_master_sample`), so frame ↔ sample tables need no manual alignment step.

Sources: `results/2026c/ephys_spikes/reports/ephys_spikes_pc_time_chain_2026c.{csv,md}`,
`ephys_spikes_offload_qc_2026c.md`, `cohorts/2026c.yaml`, `change_log/2026-09-02-ephys-spike-sorting-pipeline.md`
(addenda 2026-09-04), field2026-sync `from-field/2026-09-03_led-sync-pipeline.md`, `wiser/README.md`.
