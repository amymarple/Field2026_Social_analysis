# 2026-10-03 — Head-IMU speed reference independent of the WISER smoother (step B): proxy not valid; R1 re-scores the smoothers

**Plan:** [`implementation_plan/2026-10-03-imu-speed-proxy.md`](../implementation_plan/2026-10-03-imu-speed-proxy.md) (step B of
A → B → C, approved by the user 2026-10-03, "干吧"). Amendment 1 (operational details) was written before any number; the
models were frozen on the tuning night (12:11) before any test-night or rain-night number (12:12); Note 2 (after the
results) added a reading-aid section and figure-layout fixes only.
**Report:** [`results/2026c/wiser_baseline/reports/wiser_baseline_imu_speed_proxy_2026c.md`](../results/2026c/wiser_baseline/reports/wiser_baseline_imu_speed_proxy_2026c.md)
(verdict, clean-second counts, noise floor, models, validity, R1 tables, reading, reading aid, checks, full Definitions;
3 figures `wiser_baseline_imu_speed_proxy_{floor,test,r1}_2026c.png`).
**Driver / config:** `wiser/scripts/analyze_imu_speed_proxy.py` (new; `--stage compute|fit|evaluate`, `--report-only`,
`--selftest` all pass) / `wiser/configs/imu_speed_proxy_2026c.json` (new; `fitted` and `result` blocks written by the run).
**Bulk:** `D:\Field2026_analysis_out\2026c\imu_speed_proxy_20261003_1210\` (`seconds/` per animal-period references, clean
flags and track speeds; `tables/`; `models/` pickled dicts + `features.json`; `summary.json`; `input_provenance.json`);
pointer `results/2026c/wiser_baseline/reports/run_manifest_imu_speed_proxy_2026c.json`.
**New cache:** `D:\Field2026_analysis_out\2026c\imu_speed_features\<SFxx>\night_<date>.csv.gz` + `README.md` (per-second head-IMU
features, 1-s and 3-s windows, six audit nights × five animals; later models never re-read the npz).
**Not written:** the ephys deliverable `D:\Field2026_analysis_out\2026c\imu_speed_proxy\` (the proxy is not valid).

## Results

**Clean seconds** (six audit nights, SF07/08/09/10/12): 82,041 for $u_3$ (75,639 for $u_1$) of 792,000; train 34,043, tune
10,149, test 17,460, rain 20,389. Most seconds fail on an anchor count < 8 in the 4-s span or a fix rate < 3 Hz.
**Noise floor** (certified still, ≥ 8 anchors, all ten audit periods, 55,258 s): $u_3$ p50 0.59 / p95 1.64 / p99 2.48 in/s;
$u_1$ p50 1.90 / p95 5.26 / p99 7.83 in/s (nights slightly higher, rain highest).

**Models** (tuning night 09-07, median absolute error): 3 s M1 1.095 vs **M2 0.754 in/s**; 1 s M1 2.009 vs **M2 1.680 in/s**;
M2 grid point lr 0.1 / depth 5 / min leaf 200 at both scales.

**Validity (test night 09-08, pre-registered, point estimates decide):**

| scale | MdARE (u ≥ 5) | Spearman ρ | IMU-locomoting p50 / p95 Δ | verdict |
|---|---|---|---|---|
| 3 s | **0.262** [0.249, 0.279] (≤ 0.25: fail) | 0.816 (pass) | −2.9 % / −7.8 % (pass) | **not valid** |
| 1 s | 0.406 (fail) | 0.576 (fail) | −17.2 % / −7.3 % (fail) | **not valid** |

Rain nights (reported): 3-s MdARE 0.35–0.36, locomoting p50 −15 % / −26 %. → No R2, no ephys deliverable.

**R1 (each track vs the clean reference, same median estimator, all six nights, 3 s; paired 10-min block bootstrap):**

| track | p50 Δ | p95 Δ | > 15 in/s band p95 Δ | MAE (in/s) |
|---|---|---|---|---|
| B1 | −11.5 % | −1.2 % | −0.7 % | 0.23 |
| B2 = V1b | −26.6 % | −5.2 % | −8.0 % | 0.50 |
| B2′ ≈ V1 | −38.2 % | −12.2 % | −18.5 % | 0.68 |
| V2 | −45.0 % | −5.9 % | −4.3 % | 0.65 |
| V2b | −32.1 % | −2.5 % | −1.4 % | 0.50 |

Pre-registered reading: **least biased in speed = B1** (smallest max(|Δp50|, |Δp95|), 11.5 %); **biased** (95 % CI of p50 or
p95 entirely beyond ± 10 %): **all seven smoothed tracks** (every CI is narrow; the p50 decides). Same order and labels at 1 s.
No default changed (plan); B1 as "least biased" is a proposal by the rule only.

**Reading aid (after the results):** the primary cell is decided by p50, but the reference p50 (1.68 in/s) sits at the noise
floor's p95 (1.64 in/s) — 49 % of clean seconds are at or below it, 85 % below 5 in/s — so a negative p50 Δ mostly measures
noise removal. Where the reference is above its floor (p95, > 15 in/s band), B1 and V2b are within ≈ 1–2.5 %, B2 / V1b run
≈ 5–8 % slow (26 % at the 1-s p50 above 15 in/s, partly selection regression) — consistent with the stiff constant-velocity q
under-following fast bursts (NIS 8–10 in runs) — and B2′ / V1 12–19 % slow. B1 is closest partly by construction (a running
median of raw fixes, like the reference; it was eliminated earlier for jumps and ≈ 107 in/min fake still path).

**Checks:** the audit's per-second IMU QC / still / state reproduced from the npz on all 30 animal-nights (100 % agreement,
max |ΔVeDBA| 4e-15); float64 fix-cache reference vs the audit's float32 raw ≤ 7.5e-5 in/s; all track files matched the fix
cache fix by fix.

## Definitions (headline quantities; full set in the report)

- **Window median** $\mathbf m_h(g)$ = coordinate-wise median of the aligned raw fixes in $[g-h, g+h)$, ≥ 3 fixes. in.
- **Clean WISER speed** $u_3(s) = \lVert\mathbf m_{0.5}(c+1.5)-\mathbf m_{0.5}(c-1.5)\rVert/3$, $u_1(s) = \lVert\mathbf m_{0.375}(c+0.5)-\mathbf m_{0.375}(c-0.5)\rVert/1$,
  $c = s + 0.5$ for the second $[s, s+1)$. in/s; nearly model-free head speed, the target on clean seconds.
- **Clean second:** span $[c-2, c+2]$: every fix ≥ 8 anchors, valid, unmasked; no jump (> 30 in in ≤ 0.35 s); ≥ 12 fixes;
  both $u_3$ medians outside the houses + 14 in; the audit's per-second `ok`.
- **Noise floor** $F_k$ = $u_k$ on certified still segments (≥ 30 s, trimmed 1 s) under the same fix conditions; true speed 0.
- **MdARE** $= \operatorname{median}_{u\ge5}\lvert\hat u-u\rvert/u$ (≤ 0.25); **Spearman** $\rho_S(\hat u, u)|_{u\ge5}$ (≥ 0.7); locomoting
  $\lvert Q_q(\hat u)/Q_q(u)-1\rvert \le 0.10$ for $q = 50, 95$ (state 3). All three → valid at that scale.
- **R1 bias** $d_q = Q_q\{v\}/Q_q\{u\} - 1$ over clean seconds ($v$ = the track's speed by the same medians); **MAE** $= \operatorname{median}\lvert v-u\rvert$;
  **closest** = smallest $\max(\lvert d_{50}\rvert,\lvert d_{95}\rvert)$; **biased** = CI of $d_{50}$ or $d_{95}$ entirely beyond ± 10 %.
- **Block bootstrap:** (animal, night, 10-min block) resampled with replacement, 1000 replicates, paired across tracks.

## Files

- new `wiser/scripts/analyze_imu_speed_proxy.py`, `wiser/configs/imu_speed_proxy_2026c.json`
- new `results/2026c/wiser_baseline/reports/wiser_baseline_imu_speed_proxy_2026c.md`, `run_manifest_imu_speed_proxy_2026c.json`,
  `results/2026c/wiser_baseline/figures/wiser_baseline_imu_speed_proxy_{floor,test,r1}_2026c.png`
- edited `implementation_plan/2026-10-03-imu-speed-proxy.md` (Amendment 1, Note 2)
- **For the main session:** add the driver to the `wiser_baseline` row of CLAUDE.md's WISER code map (+ its selftest, the
  feature cache `imu_speed_features/`, the pointer name) and list the plan / change_log / report in both index READMEs
  (`implementation_plan/README.md`, `change_log/README.md`). Not done here (boundary of this step).
