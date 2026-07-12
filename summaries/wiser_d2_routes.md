# Direction 2 — route structure

Direction key: `wiser_d2_routes`. Regenerated from `analyses/registry.yaml` — **do not hand-edit**; a
new cohort appends coverage, it does not rewrite prose. Each finding: one sentence + evidence + source
+ status (ACTIVE / SUPERSEDED / CONTESTED).

## Cohort coverage

| Question | `2026a` |
|---|---|
| Do the animals reuse spatial corridors, and are the corridors shared or individual? | ✓ |
| Does each animal have an individually stereotyped trajectory, or is stereotypy shared? | ✓ |
| Are there stable leader-follower dyads, or is following a promiscuous herd effect? | ✓ |
| Do route bouts recur as a small set of reused motifs, and does the repertoire develop over time? | ✓ |
| Is there a discrete, shared route 'vocabulary' the animals draw from? | ✓ |
| How frequent is strict trailing, and who leads (incident-level)? | ✓ |
| Is the ~4 s / ~100 in 'bout capacity' a real behavioral unit? | ✓ |
| Can decision-to-decision legs (a 'reorientation-punctuated' structure) be resolved from WISER? | ✓ |

## Findings

### Do the animals reuse spatial corridors, and are the corridors shared or individual?
- **Claim:** Corridors are robust to QC and shared/environment-driven: cross-rat edge similarity 0.90 >> within-rat 0.35.
- **Evidence:** 11 nights; night-to-night IoU only ~27%.
- **Source:** [`change_log/2026-06-29-route-structure-analysis.md`](../change_log/2026-06-29-route-structure-analysis.md)
- **Status:** ACTIVE (candidate).

- **Card:** [`analyses/wiser_d2_routes/route_corridor_structure.md`](../analyses/wiser_d2_routes/route_corridor_structure.md)

### Does each animal have an individually stereotyped trajectory, or is stereotypy shared?
- **Claim:** Space-use stabilizes (0.15->0.89 over 11 nights) but is mostly SHARED/road-driven — residual individual correlation ~ -0.01, label-perm 0/10 above null.
- **Evidence:** 11 nights (Phase A re-run); only Dormi shows any individual residual.
- **Source:** [`results/2026a/wiser_d2_routes/reports/wiser_d2_routes_trajectory_stereotypy_2026a.md`](../results/2026a/wiser_d2_routes/reports/wiser_d2_routes_trajectory_stereotypy_2026a.md)
- **Status:** ACTIVE (candidate).

- **Card:** [`analyses/wiser_d2_routes/trajectory_stereotypy.md`](../analyses/wiser_d2_routes/trajectory_stereotypy.md)

### Are there stable leader-follower dyads, or is following a promiscuous herd effect?
- **Claim:** Following is HERD/promiscuous, not stable dyads: 7-10/10 pairs beat the circular-shift null nightly but the top pair reshuffles (Spearman 0.11); Sen is the dominant leader.
- **Evidence:** 10 nights (07-04 excluded); movement ~1.25% co-moving; Sen top leader 5/7 nights.
- **Source:** [`results/2026a/wiser_d2_routes/reports/wiser_d2_routes_following_structure_2026a.md`](../results/2026a/wiser_d2_routes/reports/wiser_d2_routes_following_structure_2026a.md)
- **Status:** ACTIVE (candidate).

- **Card:** [`analyses/wiser_d2_routes/following_structure.md`](../analyses/wiser_d2_routes/following_structure.md)

### Do route bouts recur as a small set of reused motifs, and does the repertoire develop over time?
- **Claim:** Trajectories are strongly stereotyped: 97% of route bouts recur (<=3x jitter), broad repertoire (top-motif share only 3-10%/night), present from night 1 (not developing).
- **Evidence:** 13 nights (06-28..07-10); recurrence 92-99%/night; activity concentrates at 21:00.
- **Source:** [`results/2026a/wiser_d2_routes/reports/wiser_d2_routes_route_motifs_2026a.md`](../results/2026a/wiser_d2_routes/reports/wiser_d2_routes_route_motifs_2026a.md)
- **Status:** ACTIVE (candidate).

- **Card:** [`analyses/wiser_d2_routes/route_motifs.md`](../analyses/wiser_d2_routes/route_motifs.md)

### Is there a discrete, shared route 'vocabulary' the animals draw from?
- **Claim:** FALSIFIED (conditional on 3s-bout segmentation): verdict C = continuous route manifold, NOT a discrete vocabulary; endpoints dominate and the shared structure is the endpoint GRAPH, not a path vocabulary.
- **Evidence:** 1692 units, 13 nights; endpoint chord 7.88 in ~ jitter beats the K=176 route dict 15.72; robust to bouts<->pause-merged episodes.
- **Source:** [`results/2026a/wiser_d2_routes/reports/wiser_d2_routes_route_vocabulary_SCIENTIFIC_SUMMARY_2026a.md`](../results/2026a/wiser_d2_routes/reports/wiser_d2_routes_route_vocabulary_SCIENTIFIC_SUMMARY_2026a.md)
- **Status:** SUPERSEDED (retracted).
- **Superseded:** the 'discrete shared route vocabulary' reading; also corrected a Phase-B 'z>2' individual-residual claim (z was 1.84)
- **Card:** [`analyses/wiser_d2_routes/route_vocabulary.md`](../analyses/wiser_d2_routes/route_vocabulary.md)

### How frequent is strict trailing, and who leads (incident-level)?
- **Claim:** Trailing is frequent but brief: 2046 strict-following episodes (median 3 s) over 11 nights; all 4 top ordered pairs are Sen->X (Sen the dominant lead).
- **Evidence:** 11 nights; Sen->Siesta 1.82/hr, ->Hypnos 1.70, ->Dormi 1.47, ->Nox 1.41; 2046/2046 routed to a camera queue.
- **Source:** [`results/2026a/wiser_d2_routes/reports/wiser_d2_routes_following_incidents_2026a.md`](../results/2026a/wiser_d2_routes/reports/wiser_d2_routes_following_incidents_2026a.md)
- **Status:** ACTIVE (candidate).

- **Card:** [`analyses/wiser_d2_routes/following_incidents.md`](../analyses/wiser_d2_routes/following_incidents.md)

### Is the ~4 s / ~100 in 'bout capacity' a real behavioral unit?
- **Claim:** RETRACTED: the '~4 s bout capacity' is a SEGMENTATION ARTIFACT (scale moves 1:1 with the 3 s min-bout filter); the un-truncated median run is sub-second at the jitter floor; hazard is non-monotone lognormal with no 4 s breakpoint ('memoryless' retracted).
- **Evidence:** 0.54 s no-filter median; 99% of bouts sit inside longer pause-merged episodes.
- **Source:** [`results/2026a/wiser_d2_routes/reports/wiser_d2_routes_bout_segmentation_validation_2026a.md`](../results/2026a/wiser_d2_routes/reports/wiser_d2_routes_bout_segmentation_validation_2026a.md)
- **Status:** SUPERSEDED (retracted).
- **Superseded:** the '~4 s / ~100 in bout capacity' and 'memoryless' claims
- **Card:** [`analyses/wiser_d2_routes/bout_segmentation_validation.md`](../analyses/wiser_d2_routes/bout_segmentation_validation.md)

### Can decision-to-decision legs (a 'reorientation-punctuated' structure) be resolved from WISER?
- **Claim:** NO reliable boundary class at WISER resolution: pause heading-change is not separable from jitter (matched +18 deg vs jitter-null +20 deg); decision legs are NOT validatable without CV pose/keypoints.
- **Evidence:** changepoint detector 30-77% false-positive, 4-24% sensitivity.
- **Source:** [`results/2026a/wiser_d2_routes/reports/wiser_d2_routes_decision_boundary_validation_2026a.md`](../results/2026a/wiser_d2_routes/reports/wiser_d2_routes_decision_boundary_validation_2026a.md)
- **Status:** CONTESTED (blocked).
- **Superseded:** the 'reorientation-punctuated' / discrete-legs reading
- **Card:** [`analyses/wiser_d2_routes/decision_boundary_validation.md`](../analyses/wiser_d2_routes/decision_boundary_validation.md)

---
*Generated by `summaries/_generate_summaries.py`. Verdict marks trace to `wiser/ANALYSIS_STATUS.md` and the linked change logs.*
