# Aborted launch (2026-10-07 10:51-11:07 UTC)

Terminated because the Docker daemon was saturated: with ~170 concurrent cells, container create/start and
`docker rm` took longer than the 60 s helper limit, 521 containers were left in "created" state, per-cell
admission probes failed, SkillsBench NoSkill evaluations were sealed UNKNOWN (ContainerUnavailable), and the
tau chains that did finish stopped with infrastructure-caused `cleanup_failed` / verifier timeouts.
Nothing here enters any report; the matrix is relaunched at lower concurrency with the same source identity.
