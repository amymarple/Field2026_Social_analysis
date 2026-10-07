# Claim audit v2 — NREM → REM transitions and recent sleep history, cohort 2026c (2026-10-07)

`/scientific-report-promotion` on v2 ([report](ephys_spikes_sleep_cycles_v2_final_2026c.md),
[change log](../../../../change_log/2026-10-07-sleep-rem-cycle-history-v2.md)). **It supersedes the v1 audit
([ephys_spikes_sleep_cycles_claim_audit_2026c.md](ephys_spikes_sleep_cycles_claim_audit_2026c.md)) wherever the two
differ.** The v1 audit stays as the ledger.

**Common.**
- **Measurement.** Automatic scores: the user-reviewed per-session `imu_remclean` + SF07 09-05 from `pass2med_remclean`.
  No epoch-level manual scoring (κ) exists.
- **Units of replication.** 6 rats; 22 day-half blocks.
- **Outcome space.** NREM → REM / Wake from every NREM bout. REM entered directly from wake ≤ 10 s (allowed by the
  post-rules) is outside the model; wake → REM > 10 s is excluded by construction.

| # | claim | status (v1 → v2) | main_evidence | allowed_wording | forbidden_wording |
|---|---|---|---|---|---|
| 1 | Recent sleep history adds out-of-sample predictive information about the next NREM transition. | Established → **Established** (scope widened to 24 h) | ΔLL M1 − M0 = −1.99 % [−2.35, −1.58] % of M0, **22/22** held-out day-halves; forward chaining −1.85 % (15/16); light only −2.08 %. | "Over the full day, recent sleep history improved held-out prediction of NREM-to-REM / Wake transitions by about 2 %, in every held-out day-half and forward in time." | "History determines / schedules REM"; any mechanism. |
| 2 | Wake since the last REM is the strongest single history term (more wake → REM less likely). | Candidate → **Candidate** | Alone −1.15 % (22/22); coefficient −0.65 per SD, negative in **6/6**. | "Wake accumulated since the last REM was the strongest predictor: the more wake, the less likely REM." | "Wake resets a REM clock". |
| 3 | REM is unlikely shortly after REM (short-term refractoriness) and clusters over hours. | new → **Candidate** | Window terms (compositional): REM in the last 10 min ↓ REM odds, REM in the last 3 h ↑ REM odds; windows add −1.00 % held out (19/22). | "REM was less likely within ~10 min of a previous REM, and more likely in REM-rich hours." | Quantitative refractory durations; "REM pressure". |
| 4 | Previous REM length adds predictive information. | Candidate (null) → **Candidate (small positive)** | v2 alone −0.31 % [−0.67, −0.08] % (18/22); coefficient +0.13 per SD conditional on the windows, 6/6 positive. In v1 (anchor-only history, light only) it was null. | "Previous REM length added a small amount of predictive information in the 24-h model; its sign depends on the other history terms." | "Longer REM delays / hastens the next REM" stated as a general rule. |
| 5 | The history dependence does not detectably change with time of day. | Candidate → **Candidate (scoped negative, now 24 h)** | M2 − M1 +0.07 % [−0.14, +0.38] % (13/22). In-sample interaction terms (p < 0.05) do not replicate held out. | "Time-of-day interactions with history did not improve held-out prediction over the full day." | "The history effect is constant over the day"; citing the in-sample interaction p-values as evidence. |
| 6 | History predicts night-time (dark-phase) transitions on its own. | Unresolved → **Unresolved** | Night-only fit −0.49 % [−1.36, +0.58] % (9/13); 231 dark REM entries. | "Cannot be established with the night data alone." | "History matters less at night". |
| 7 | REM rarely starts a sleep bout that follows a long wake. | new → **Candidate** | `has_anchor` +0.62 per SD on the REM odds (steps before a record's first REM vs after). | "Before the first REM of a record, NREM bouts were less likely to end in REM." | "Rats enter sleep through NREM" as a demonstrated rule (scoring rules forbid wake → REM > 10 s). |
| 8 | The descriptive "previous REM → following NREM" relation. | Unresolved → **Unresolved** (unchanged; v2 did not re-test it) | v1: null overall, positive in single cycles, negative on pre-post-rule states. | as v1 | as v1 |
| 9 | The PI's scheduling mechanism. | Unresolved → **Unresolved** | Design. | "These data test predictive dependence on history, not a scheduling mechanism." | Any mechanistic wording. |

**Stop conditions.**
- #4 changed sign of evidence between v1 and v2 (null → small positive) with the model specification; it stays a
  Candidate, with its dependence on the other history terms stated.
- #5's in-sample interactions must not be cited without the held-out result.
- The v2 joining across file splits (28 joins, 670 s unknown) still lacks a no-join sensitivity run.
