# Data Manifests

Per-run field-data manifests (sources, clocks, units, excluded intervals, coordinate frame,
alignment notes). See `AGENTS.md` → "Data Manifest Requirements".

| Date | Run | Modalities |
|---|---|---|
| 2026-09-02 | [WILD ephys — 3rd rat cohort raw offloads](2026-09-02-wild-ephys-cohort3.yaml) | WILD CE64 neurologger sessions (64 ch @ 20 kHz) SF07–SF12 on E:rd_rat_spikes + recovery.bin images; firmware FM62/64/65 provenance + de-glitch rule; excluded windows; staged/sorted output roots |
| 2026-06-29 | [WISER pilot](2026-06-29-wiser-pilot.yaml) | WISER UWB (free-moving + stationary baseline) + AWN weather |
| 2026-06-29 | [Camera audio](2026-06-29-camera-audio.yaml) | CH01/CH02 ambient audio — relative camera-mic dBFS + soundscape indices (not SPL) |
| 2026-06-30 | [Episode Browser real slice v2](2026-06-30-episode-browser-route-slice.yaml) | Bounded real WISER route bouts + existing Phase B2 strict-following pair candidates, QC evidence, and unverified camera routing for selected-episode review |
| ongoing | [Field conditions](field_conditions.yaml) | Weather/visibility windows (fog, rain) to exclude/caveat in video + audio analysis |
| ongoing | [Glass treatments](glass_treatments.yaml) | CH05/CH06 shelter IR-glass optical regimes (equipment interventions: tape / lift / anti-fog film) — a covariate, not an exclusion rule |
