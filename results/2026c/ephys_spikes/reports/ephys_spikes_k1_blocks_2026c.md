# K1 sorting blocks, cohort 2026c

Made by `ephys/plan_blocks.py` (plan `implementation_plan/2026-10-09-k1-block-sorting.md`).

- Trim: first 0 min of every block (user 2026-10-10: keep everything; the block start is the release into the field; `post_release_until` flags the first 20 min). Blocks shorter than 30 min are dropped. Clipped at the paddock end 2026-09-12 10:10:00 and at `valid_until`.
- **135 blocks**, 1358 h (1243 h FM65 in 122 blocks, 115 h FM64 in 13 blocks), 12.5 TB.
- Hours per block: median 11.1, maximum 14.9. 34 blocks join several files.
- Tier 2 (SF11 out of CA1): 12 blocks; tier 3 (SF12 connector regime): 7. Blocks with disconnected shanks: 8; settle windows: 9.

| animal | blocks | hours | chains | FM64 blocks | max h |
|---|---|---|---|---|---|
| SF07 | 26 | 250.1 | 4 | 2 | 14.9 |
| SF08 | 24 | 247.7 | 3 | 3 | 14.9 |
| SF09 | 23 | 248.4 | 1 | 2 | 14.8 |
| SF10 | 24 | 244.7 | 1 | 2 | 14.6 |
| SF11 | 16 | 137.4 | 5 | 2 | 13.8 |
| SF12 | 22 | 229.4 | 5 | 2 | 12.9 |

Dropped pieces (before a group's first long recording, or in groups without one): 180 recordings, 2.46 h; 157 of them <= 60 s (`ephys_spikes_k1_blocks_dropped_2026c.csv`).
