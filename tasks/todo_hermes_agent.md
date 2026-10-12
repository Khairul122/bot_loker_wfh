# Hermes Agent Rewrite Status

## Implemented in repository

- [x] Replace 9Router/direct provider routing with Hermes API Server adapter and offline template fallback.
- [x] Record task calls with model, latency, usage, and error status.
- [x] Route draft, form, answer, bid-term, cover-letter, and office tasks through Hermes task personas and employee sessions.
- [x] Package all 20 current employee personas as on-demand Hermes `SKILL.md` skills.
- [x] Keep bid approval, Telegram allowlist, and CAPTCHA protections in application flows.
- [x] Add `check-llm` health, model-alias, toolset/capability, and employee-skill checks without making inference calls.
- [x] Disable Hermes `skill_manage` in the dedicated profile template; only read-only skill lookup is needed by the app.
- [x] Pass the full pytest suite locally (latest recorded run: 347 passed, 10 subtests).

## Remaining before live cutover

- [ ] Create/configure a dedicated Hermes profile with a valid upstream provider/model route and a separate API server key.
- [ ] Start the local Hermes API Server and confirm authenticated `check-llm` succeeds against that profile.
- [ ] Run a sanitized live inference canary and review generated drafts for quality and policy compliance.
- [ ] Verify effective runtime tool permissions from the running profile; `/v1/toolsets` reports static toolset expansion and does not reflect per-tool suppression.
- [ ] Approve live cutover after the canary. No bid, application, CAPTCHA action, or Telegram message may be sent during verification.

## Provisioning notes

Use `deploy/hermes/loker-wfh/config.example.yaml` as the dedicated profile template. Do not clone the personal Hermes profile: profiles are configuration/state isolation, not a security boundary, and cloning may carry credentials and identity. Keep the API server bound to loopback and protect its API key. See [HERMES_INTEGRATION.md](../docs/HERMES_INTEGRATION.md).
