# Housekeeping log

Add one row per change immediately before its first push for review. Use local
dates and include the time zone with the active intervals. Split intervals at
pauses. Sum recorded minutes to calculate the daily total. See the
[housekeeping guide](housekeeping.md) for the timing and completion rules.

| Date | Job | Active work intervals (with zone) | Recorded minutes | Verified outcome |
| --- | --- | --- | ---: | --- |
| 2026-11-22 | Document how to read a skipped PR gate | 02:01:34–02:05:08 MYT (UTC+08:00) | 4 | CI policy suite, 168 native matrix mutation controls, 66 PR gate controls, and documentation links checked; workflow unchanged. |
| 2026-11-22 | Run historical candidate-batch controls independently of live source setup | 08:44:45–08:45:08; 08:45:13–08:48:10 MYT (UTC+08:00) | 3 | Eight independent and historical controls pass in both Python modes; live mismatches still fail, and an already approved live source passes all eleven. |
| 2026-11-23 | Fix README compiler source links | 08:43:32–08:43:45, 08:43:53–08:45:09, 08:45:18–08:46:10, 08:46:28–08:47:36 MYT (UTC+8) | 3 | Verified compiler and Prelude paths against manifests, rendered links, and GHC-hosted build help. |
| 2026-11-23 | Repair release profiling references | 08:48:42–08:49:09, 08:49:15–08:49:53, 08:51:23–08:51:49, 08:51:55–08:52:15, 08:52:44–08:53:08 MYT (UTC+8) | 2 | Rendered retained profiling anchors and verified release commands and recorded figures are unchanged. |
| 2026-11-24 | Restore the historical bootstrap memory reader path | 08:57:14–09:00:03 MYT (UTC+08:00) | 3 | Rendered the build guide and retained summary; the new link resolves, the three removed evidence links are gone, and measurements and commands are unchanged. |
| 2026-11-24 | Fix the regex-redux source link | 09:02:15–09:03:06 MYT (UTC+08:00) | 1 | Rendered the benchmark guide and verified the href resolves to the tracked, manifest-registered Bootstrap.Regex source; all other text is unchanged. |
| 2026-11-24 | Restore the October 18 native benchmark reader path | 09:09:35–09:11:18 MYT (UTC+08:00) | 2 | Rendered and verified the October 18 summary anchor, removed the stale raw link, and preserved sample counts, commands and later sections. |
| 2026-11-25 | Restore the October 13 native build driver link | 08:20:13–08:22:37, 08:22:46–08:22:56 MYT (UTC+08:00) | 3 | Rendered the Stage 2 link and verified the historical driver bytes against all three reports; only the href changed. |
| 2026-11-25 | Correct the package guide’s executable source map | 08:25:59–08:26:57 MYT (UTC+08:00) | 1 | Rendered the guide and verified all three entry points and the manager’s direct dependencies against the root manifest; command blocks are unchanged. |
| 2026-11-25 | Clarify which October 16 benchmark evidence is retained | 08:29:30–08:30:09 MYT (UTC+08:00) | 1 | Verified both missing diagnostic files, the rendered October 16 heading, and the retained final archive’s 189 compilation and 189 runtime samples. |
