# K1 sorting blocks, cohort 2026c

Made by `ephys/plan_blocks.py` (plan `implementation_plan/2026-10-09-k1-block-sorting.md`).

- Trim: first 20 min of every block (handling). Blocks shorter than 30 min after trimming are dropped. Clipped at the paddock end 2026-09-12 10:10:00 and at `valid_until`.
- **135 blocks**, 1312 h (1202 h FM65 in 122 blocks, 110 h FM64 in 13 blocks), 12.1 TB.
- Hours per block: median 10.7, maximum 14.6. 31 blocks join several files.
- Tier 2 (SF11 out of CA1): 12 blocks; tier 3 (SF12 connector regime): 7. Blocks with disconnected shanks: 8; settle windows: 9.

| animal | blocks | hours | chains | FM64 blocks | max h |
|---|---|---|---|---|---|
| SF07 | 26 | 241.4 | 4 | 2 | 14.6 |
| SF08 | 24 | 239.3 | 3 | 3 | 14.5 |
| SF09 | 23 | 240.7 | 1 | 2 | 14.5 |
| SF10 | 24 | 236.7 | 1 | 2 | 14.2 |
| SF11 | 16 | 132.1 | 5 | 2 | 13.5 |
| SF12 | 22 | 222.1 | 5 | 2 | 12.6 |
