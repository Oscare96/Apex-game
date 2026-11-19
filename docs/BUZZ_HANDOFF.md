# Buzz — APEX implementation and deployment handoff

## Scope delivered
Synthetic autonomous driving prototype + character commentary + protected research API + tests + Docker + Cloud Run runbook. This is an engineering **foundation**, not the full APEX product.

## Mandatory acceptance gates
1. `ruff check app tests` and `pytest -q` pass.
2. Docker image builds and runs as non-root.
3. Unauthorized `/episodes` request returns 401.
4. Same seed yields identical metrics; episode terminates within 150 steps.
5. `/identity` explicitly identifies APEX as AI.
6. Google Cloud deployment uses a dedicated project, private Cloud Run, dedicated runtime identity and Secret Manager.
7. Capture Cloud Run revision, smoke-test results, cost/budget configuration, and rollback instructions.
8. No production deployment or billing changes without owner approval.

## Next engineering batches (not delivered)
- B1: richer 2D simulator, obstacles, replay format, benchmark suite with success thresholds.
- B2: adapter protocol for **permitted** environments, event bus, deterministic trace capture.
- B3: vision model evaluation and latency benchmarks in simulator.
- B4: trainable policy, offline evaluation, experiment tracking, safety supervisor.
- B5: real-time voice, persistent character memory, moderation, disclosure.
- B6: OBS capture/streaming, fail-safe standby, media pipeline, clip QA.
- B7: OwnerEasy media adapter, explicitly versioned and isolated; no shared production credentials.
- B8: official social APIs, consent, rate limits, publishing review and audit trail.
- B9: security hardening, observability, chaos tests, load tests and release gates.

## Open decisions
- Google project ID, region, budget, repository name, access model, GPU availability, supported game integration permissions, creator character design, and paid API provider selections.
- Do not assert GTA 6 automation compatibility or monetize prohibited gameplay.

## Required feedback to owner
Provide exact commands, test outputs, commit SHA, deployment URL (if deployed), revision ID, costs observed, blocked permissions, and next recommended batch. Never claim a service is deployed merely because a build succeeded.