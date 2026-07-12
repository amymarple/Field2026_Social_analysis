# CV measurement-context audit — 2026-07-02

*auditor:* cv-measurement-auditor · *mode:* **metadata** · *generated:* 2026-07-06T23:41:17Z · *git:* 6c703c5f5bdf

**Verdict.** AUDITABLE as a measurement record (metadata mode): provenance complete, per-row context populated, mc_run_id joins to the manifest, annotation is pure. No ground-truth labels for 2026-07-02, so detector/count accuracy is not evaluated here.

## Provenance & purity

- Sidecar `shelter_sleep_2026-07-02.measurement_context.json` → `mc_run_id=mc_88dc9f46d960`, detector `rat_feasibility-6`, frame units `cm`.
- Annotation purity: metric schema intact & 9 covariate columns appended-only = **PASS**.
- `CH05`: 294 rows; glass_regime/camera_model/shelter_id/mc_run_id filled = {'glass_regime': 1.0, 'camera_model': 1.0, 'shelter_id': 1.0, 'mc_run_id': 1.0}; mc_run_id↔manifest = **match**.
- `CH06`: 292 rows; glass_regime/camera_model/shelter_id/mc_run_id filled = {'glass_regime': 1.0, 'camera_model': 1.0, 'shelter_id': 1.0, 'mc_run_id': 1.0}; mc_run_id↔manifest = **match**.

## Regime / occupancy distributions (metadata mode — no error metrics)

### CH05
- state: {'empty': 180, 'occupied_low_motion': 112, 'occupied_high_motion': 2}
- view_quality_inside: {'clear': 259, 'degraded': 35}
- glass_regime: {'lift_1cm': 159, 'antifog_film': 135}
- usable_for_headline_summary: 88.1% of bins

### CH06
- state: {'empty': 177, 'occupied_low_motion': 107, 'occupied_high_motion': 8}
- view_quality_inside: {'degraded': 115, 'clear': 177}
- glass_regime: {'lift_1cm': 157, 'antifog_film': 135}
- usable_for_headline_summary: 60.6% of bins

## Failure modes / reliability

- CH05: 35 bins degraded/unusable inside-glass → occupancy there is lower-bound only
- CH06: 115 bins degraded/unusable inside-glass → occupancy there is lower-bound only

## Provenance gaps

- No labeled validation_2026-07-02.csv → detector/count error is NOT measurable for this date (metadata mode).
- glass_regime changes within the day at the 2026-07-02 13:00 lift_1cm→antifog_film boundary; do not pool view-quality across it.

## Smallest next action

Collect a small ground-truth set for 2026-07-02 stratified by glass_regime (esp. the post-13:00 antifog_film span) + view_quality to enable validation-mode error stratification; no retrain warranted on metadata alone.


## Sibling handoff

For occupancy under degraded glass / suspected huddles on 07-02, dispatch wiser-measurement-auditor (fog-immune cross-check via analyze_sleep_site_cv_crossval.py).
