# Storage health baseline for the raw-data drive E: (2026-09-12)

**Why.** Since the cohort-3 offloads finished, `E:\3rd_rat_spikes` (raw neurologger data, ~11.5 TB) is the **only copy**: the
SanDisk Extreme that held the F: backup has been dead since 2026-08-24, its replacement (Seagate IronWolf Pro 28 TB in an Oyen
Novus enclosure) does not enumerate yet, and the five SD cards hold only the records since the last format. This entry records the
drive's condition on the day the field phase ended, so any later check is a diff against it.

## Drive

| | |
|---|---|
| Disk | 1 (`\\.\PhysicalDrive1`, smartctl `/dev/pd1`) |
| Model | WDC WD202KFGX-68CKWN0 (Western Digital Red Pro 20 TB, helium) |
| Firmware | 83.00A83 |
| Serial | T0GK24DH |
| Volume | E:, NTFS, 18.19 TB, 2.27 TB free at the time of the check |
| Bus | SATA |

## SMART, 2026-09-12 22:5x ET — `smartctl -H -A -l error /dev/pd1` (smartmontools 7.5)

```
SMART overall-health self-assessment test result: PASSED

ID# ATTRIBUTE_NAME          FLAG     VALUE WORST THRESH TYPE      UPDATED  WHEN_FAILED RAW_VALUE
  1 Raw_Read_Error_Rate     0x000b   100   100   001    Pre-fail  Always       -       0
  2 Throughput_Performance  0x0004   147   147   054    Old_age   Offline      -       51
  3 Spin_Up_Time            0x0007   083   083   001    Pre-fail  Always       -       352 (Average 352)
  4 Start_Stop_Count        0x0012   097   097   000    Old_age   Always       -       1259
  5 Reallocated_Sector_Ct   0x0033   100   100   001    Pre-fail  Always       -       0
  7 Seek_Error_Rate         0x000a   100   100   001    Old_age   Always       -       0
  8 Seek_Time_Performance   0x0004   140   140   020    Old_age   Offline      -       15
  9 Power_On_Hours          0x0012   100   100   000    Old_age   Always       -       1400
 10 Spin_Retry_Count        0x0012   100   100   001    Old_age   Always       -       0
 12 Power_Cycle_Count       0x0032   100   100   000    Old_age   Always       -       23
 22 Helium_Level            0x0023   100   100   025    Pre-fail  Always       -       6553700
192 Power-Off_Retract_Count 0x0032   100   100   000    Old_age   Always       -       2914
193 Load_Cycle_Count        0x0012   100   100   000    Old_age   Always       -       2914
194 Temperature_Celsius     0x0002   063   063   000    Old_age   Always       -       32 (Min/Max 22/41)
196 Reallocated_Event_Count 0x0032   100   100   000    Old_age   Always       -       0
197 Current_Pending_Sector  0x0022   100   100   000    Old_age   Always       -       0
198 Offline_Uncorrectable   0x0008   100   100   000    Old_age   Offline      -       0
199 UDMA_CRC_Error_Count    0x000a   100   100   000    Old_age   Always       -       0

SMART Error Log Version: 1
No Errors Logged
```

**Reading.** Every failure-relevant counter is zero: reallocated sectors (5), pending sectors (197), offline-uncorrectable (198),
reallocated events (196), interface CRC errors (199), raw read / seek / spin-retry errors (1, 7, 10). Helium normalised value 100
against a threshold of 25 (the seal is intact). Temperature 32 °C with a lifetime maximum of 41 °C. 1,400 power-on hours over 23
power cycles: the drive is new and past infant mortality. Load-cycle count 2,914 against a 600,000 rating.

**Caveat.** A pending sector only appears once a read of that sector fails, so these zeros certify the parts of the surface that
have been read, not the whole platter. The full-surface check will come for free when the raw tree is copied to the replacement
backup drive: that copy reads all 11.5 TB. A separate `badblocks`-style pass, and especially `smartctl -t long`, is NOT run —
both add read load to the only copy for no extra information.

## OS-side evidence, same day

- `Get-PhysicalDisk`: HealthStatus **Healthy**, OperationalStatus **OK**.
- System event log since 2026-08-30: **no** `disk`, `Ntfs`, `storahci`, `partmgr` or `volmgr` error/warning naming Disk 1. The 52
  × `disk` id 153 (IO retried) and 12 × id 158 (duplicate disk identifiers) events in that window all belong to the USB card
  readers and the failing external enclosure (Disks 3, 4, 5, 7, 8, 10).
- NTFS self-check 2026-09-09: `Volume E: (\Device\HarddiskVolume4) is healthy. No action is needed.`
- `Get-StorageReliabilityCounter` (elevated): temperature 31 °C, power-on 1,399 h, read errors total 0, uncorrected 0, start/stop
  1,259.

## Power settings changed the same day (operator, elevated `powercfg`)

The 1,259 start/stop cycles in 1,400 hours (~21 spin-ups per day) came from the power plan parking the disks after 20 minutes
idle; spin-up is the most stressful routine event for an HDD and this drive holds the only copy. Now, on the High performance
scheme: **hard-disk idle timeout AC/DC = 0 (never spin down)** and **USB selective suspend AC = 0 (disabled**, which also removes
one cause of card-reader dropouts during offloads; DC left at 1, irrelevant on a desktop).

## How to re-check (read-only, no platter I/O)

```powershell
& 'C:\Program Files\smartmontools\bin\smartctl.exe' -H -A -l error /dev/pd1
```

Compare attributes 5, 196, 197, 198 and 199 against the table above. **Any of them moving off zero means the drive has started to
fail: stop writing to it and copy the data off first.** Do not run `smartctl -t long` / `-t short` on the single copy. Re-check
after the raw tree has been copied to the replacement backup drive.

## Re-checks

- **2026-09-19 09:39**, after robocopy had read the whole tree (18.2 TB) for the copy to L:: PASSED, attributes 1/5/7/10/196/197/198/199
  all 0, 32 °C.
- **2026-09-20 09:5x**, after the full SHA-256 pass had read it a second time: PASSED, same attributes all 0, 1,578 power-on hours,
  35 °C (lifetime max 41 °C). The full-surface read this entry deferred is therefore done, twice, with no read error. E: is no longer
  the single copy — `change_log/2026-09-20-raw-tree-backup-verified.md`.
