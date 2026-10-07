# Aborted launch 001 (2026-10-07 10:23-10:28 UTC)

Launched 291 cells (stagger 4 s) plus smoke task_019. Every cell that reached evolution crashed in
`bank.py` `BankEvolutionSession.__enter__`: `canonical_json_sha256` raised
`TypeError: Object of type mappingproxy is not JSON serializable` (v4 code path never exercised with a
real model). ~30 cells had started; acquisition and S0 creation for those were sealed here and are NOT
reused (the fix changes the source identity). Launcher terminated with SIGTERM; no model results from
this directory enter any report.
