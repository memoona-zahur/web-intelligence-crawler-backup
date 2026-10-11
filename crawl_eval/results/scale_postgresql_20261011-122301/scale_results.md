# Local scale test on postgresql (2026-10-11 12:27)

Fake in-memory sites, no real website contacted; politeness spacing shortened (the spacing logic is unit-tested). Numbers describe this machine and this workload only.

| Concurrency per process | Processes | Wall s | Sites/hour (this run) | Pages saved | Overlaps | Peak MB per process | All checks |
|---|---:|---:|---:|---:|---:|---|---|
| 5 | 3 | 125.8 | 28622 | 4700 | 0 | [104.7, 104.8, 104.5] | PASS |
| 10 | 3 | 71.9 | 50059 | 4700 | 0 | [105.3, 105.6, 106.3] | PASS |
| 20 | 3 | 63.4 | 56758 | 4700 | 0 | [105.7, 105.5, 105.6] | PASS |
