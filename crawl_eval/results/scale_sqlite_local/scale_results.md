# Local scale test on sqlite (2026-10-11 08:46)

Fake in-memory sites, no real website contacted; politeness spacing shortened (the spacing logic is unit-tested). Numbers describe this machine and this workload only.

| Concurrency per process | Processes | Wall s | Sites/hour (this run) | Pages saved | Overlaps | Peak MB per process | All checks |
|---|---:|---:|---:|---:|---:|---|---|
| 5 | 3 | 120.6 | 29858 | 4700 | 0 | [97.5, 97.5, 97.4] | PASS |
| 10 | 3 | 70.3 | 51215 | 4700 | 0 | [98.2, 97.4, 98.7] | PASS |
| 20 | 3 | 90.5 | 39798 | 4700 | 0 | [98.7, 98.2, 98.7] | PASS |
