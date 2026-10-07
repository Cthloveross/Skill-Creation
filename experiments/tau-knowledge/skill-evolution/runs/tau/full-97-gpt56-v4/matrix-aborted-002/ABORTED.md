# Aborted launch (2026-10-07 10:38-10:47 UTC)

Terminated after ~8 minutes with SIGTERM. Two defects surfaced under load that required source changes
(which change the run identity, so nothing here is reused):

1. GPT-5.6 Terra returned `status: completed` with an empty `output` list to the tau user simulator;
   `_assistant_response` raised `invalid_response`, the sealed RECEIVED_INVALID operation killed the bank
   worker (`bank_worker_exited`) and the cell permanently. Fix: bounded re-send of empty completed
   outputs, graceful empty assistant turn as the last resort.
2. Per-cell admission probes (tau `container_dependencies`, SkillsBench `verifier_dependencies`) failed
   transiently at load average >140 during the ramp, dropping ~40 tau cells and several SkillsBench cells
   before any model call. Fix: launcher re-queues failed stages (bounded), slower ramp.

No model result from this directory enters any report.
