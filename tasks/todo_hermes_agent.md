# Hermes Agent Rewrite Todo

## Phase 0 — Contract and Safety

- [ ] 1. Prove the Hermes API contract with disposable integration tests.
- [ ] 2. Define and verify a hardened `loker-wfh` Hermes profile.

### Checkpoint A

- [ ] API contract, authentication, route aliases, health, and error behavior verified.
- [ ] Effective API-server toolsets contain no terminal, file-write, browser, cron, web, or delegation access.
- [ ] Hermes version and configuration contract documented.

## Phase 1 — Provider Foundation

- [ ] 3. Introduce a provider-neutral agent client interface.
- [ ] 4. Implement `HermesAgentClient` with bounded retry, timeout, validation, and safe errors.
- [ ] 5. Add Hermes configuration, secret masking, routing, and call observability.

### Checkpoint B

- [ ] Unit and Hermes contract tests pass.
- [ ] Template fallback and temporary 9Router path still pass regression tests.
- [ ] Full test suite passes.

## Phase 2 — Feature Migration

- [ ] 6. Migrate cover letters, proposals, revisions, comments, and bid terms.
- [ ] 7. Migrate form planning JSON and open-question answers.
- [ ] 8. Migrate Office Q&A, instinct, and dynamic meetings.

### Checkpoint C

- [ ] Every old LLM consumer has Hermes parity coverage.
- [ ] Invalid JSON and policy violations fall back safely.
- [ ] E2E dummy flow creates drafts without external submission.
- [ ] Full test suite passes.

## Phase 3 — Operations and UI

- [ ] 9. Replace 9Router Settings UI and test endpoint with Hermes health/readiness controls.
- [ ] 10. Add Hermes gateway lifecycle, startup order, healthcheck, and deployment wiring.

### Checkpoint D

- [ ] Wrong key, unavailable Hermes, restart, and cold-start behavior verified.
- [ ] Browser UI shows connected/degraded/error states without exposing secrets.
- [ ] Deployment smoke test passes.

## Phase 4 — Canary and Cutover

- [ ] 11. Run sanitized quality/safety canary against the same fixture corpus.
- [ ] 12. After owner approval, cut over to Hermes and remove 9Router runtime/config/UI.

### Final Checkpoint

- [ ] Hermes is the only production agent backend; template fallback remains.
- [ ] No dangerous Hermes tools are enabled.
- [ ] All regression, Hermes, browser, compile, CLI, and deployment checks pass.
- [ ] No real application, bid, or Telegram message was sent by verification.
- [ ] No 9Router runtime references remain.
- [ ] Canary report and cutover approved by owner.

