# cv_field compute routing — local GPU vs Cornell BioHPC

Small batches run on the **local GPU**; large batches dispatch to the Cornell **BioHPC** box
(`cbsuruiz01.biohpc.cornell.edu`, user `hc997`) via the **`gpu-cv` skill** at
`D:\FastenPC\.claude\skills\gpu-cv`. The drivers here are compute-location-agnostic — they read
`FIELD2026_ANALYSIS_OUT_ROOT` from the environment and pass `--device` to YOLO — so the *same* code runs
either place. Nothing in Phase 0 (code + self-tests) depends on the server.

## Which step runs where

| Step | Tool | Where |
|---|---|---|
| Harvest a candidate pool | `cv/scan_for_rats.py --no-detector` (CPU video decode) | local for a session; **BioHPC** for many camera-hours |
| Embed the pool | `select_frames.py` (YOLO backbone / gray) | local for a few thousand frames; **BioHPC** for tens of thousands |
| **Select frames** | `select_frames.py` (numpy/sklearn) | **always local** (light CPU) |
| **Label** | `cv/label_frames.py` (Tkinter GUI) | **always local** (human in the loop) |
| Train the detector | `cv/train_detector.py --data-root dataset/rat_field --name rat_field` | local for a quick fine-tune; **BioHPC** for a full multi-night retrain at imgsz 1280 |
| Whole-field inference | `run_field.py` | local for a clip; **BioHPC** for long video |
| Self-test | `selftest_field_select.py` | **always local** (synthetic, numpy-only) |

Rule of thumb: a single-session round-0 pool / a few-thousand-frame fine-tune = local; embedding the full
pool, a full-cohort retrain, or long-video inference = BioHPC. Always check contention first with
`D:\FastenPC\gpu-job.ps1 status` (shared machine).

## BioHPC sequence (via the `gpu-cv` skill)

The golden rule: **compute from `/workdir`, never from network storage**; `/workdir` is purged daily at
3 AM, so archive anything worth keeping.

1. **Preconditions (once).** `ssh gpu true` must succeed (2FA is cached ~1 week/IP; if it prompts, enter the
   code once). The box has **2× RTX PRO 6000 Blackwell (96 GB, sm_120)** and — per `D:\FastenPC\BioHPC-server.md`
   — **no conda and no CUDA module**; build a venv once:
   ```bash
   module load python/3.12.7
   python -m venv /home/hc997/envs/cv        # /home survives the daily /workdir purge
   source /home/hc997/envs/cv/bin/activate && pip install --upgrade pip
   pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128   # Blackwell needs cu128
   pip install ultralytics opencv-python-headless numpy pandas scikit-learn shapely av tqdm matplotlib
   ```
   The `<activate>` prefix for every job is then
   `module load python/3.12.7 && source /home/hc997/envs/cv/bin/activate`.
2. **Upload code.** `sync-project.ps1 -Path <repo>\cv -Name cv_field` → `/workdir/hc997/projects/cv_field`
   (code only; data/weights excluded by design).
3. **Stage data server-side.** `stage-data.ps1 -Source hc997/<...>/dataset/rat_field -Dest rat_field` (and the
   raw whole-field video) storage → `/workdir/hc997/data/...`. Mirror the off-repo `cv_field` assets to Cornell
   storage (`Q:\hc997`, see `assets_manifest.json`) first so `stage-data` can reach them.
4. **Launch** (env-driven paths point the output root into `/workdir`):
   ```
   D:\FastenPC\gpu-job.ps1 run "conda activate <env> && cd /workdir/hc997/projects/cv_field && \
       FIELD2026_ANALYSIS_OUT_ROOT=/workdir/hc997/data/out \
       python train_detector.py --data-root /workdir/hc997/data/rat_field --name rat_field --device 0"
   ```
5. **Monitor.** `gpu-job.ps1 tail` / `jobs` / `status`.
6. **Fetch + archive.** `fetch-results.ps1 -Name cv_field -Archive` → `D:\FastenPC\results\cv_field` **and** a
   server-side copy to permanent storage. Then register the fetched weights in `assets_manifest.json` and
   commit the canonical report/figures under `results/<cohort>/cv_field/`, exactly as for a local run.

> The skill's own doc link is still under construction; treat this runbook as the interim contract and defer
> to `D:\FastenPC\.claude\skills\gpu-cv\SKILL.md` + `references/biohpc-notes.md` for the authoritative steps.
