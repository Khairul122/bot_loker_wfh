# Hermes Agent integration

The application routes draft, form, and answer tasks to a Hermes Agent API
Server using Hermes' OpenAI-compatible endpoint. Hermes is the only agent engine;
`template` remains the deterministic offline fallback.

## Application settings

Set these values in the application's private `.env`:

```dotenv
LLM_PROVIDER=hermes
HERMES_BASE_URL=http://127.0.0.1:8642/v1
HERMES_API_KEY=<dedicated API_SERVER_KEY>
HERMES_MODEL_DRAFT=loker-draft
HERMES_MODEL_FORM=loker-form
HERMES_MODEL_ANSWER=loker-answer
```

The route names are sent as the API `model` field and must be configured in the
dedicated profile's `model_routes`. The profile template is
`deploy/hermes/loker-wfh/config.example.yaml`; copy it into a separately created
Hermes profile, replace each upstream model placeholder with a model already
configured in that profile, and set a unique `API_SERVER_KEY` in that profile's
`.env`. Keep the API server key separate from the upstream model credential.

Point `LOKER_WFH_HERMES_SKILLS_DIR` at the packaged `hermes_skills` directory.
Hermes scans the 20 per-employee `SKILL.md` files on demand. The profile's
allowlisted `skills`, `memory`, and `delegation` toolsets let the runtime load a
persona, recall/store employee context, and hand work to bounded subagents. The
delegation cap is 2 children, 24 iterations, and one level; children inherit the
same restricted toolsets.

## Hermes server safety

Use a separate Hermes profile for this application; profiles isolate settings
and state but are not a security sandbox. Bind the API server to loopback, require
a strong `API_SERVER_KEY`, and verify the effective toolsets through the
authenticated `/v1/toolsets` endpoint before connecting the application. The
profile explicitly enables only `skills`, `memory`, and `delegation`; terminal,
file, browser, web, cron, and code-execution tools stay disabled. Protect the
external skill directory from writes by the Hermes service account where the
host supports separate service permissions.

The application's `check-llm` command checks authenticated Hermes readiness,
required toolsets and capabilities, all employee skills, and all three model
aliases. Hermes' `/v1/toolsets` inventory advertises the full static expansion
of each enabled toolset; it does not report per-tool suppression. Because the
`skills` toolset includes `skill_manage`, the dedicated profile must disable
that tool with `agent.disabled_toolsets: [skill_manage]`. Keep the profile
restricted to the documented allowlist and inspect its configuration during
provisioning. The readiness check makes no inference request and incurs no
model cost. Template mode remains available when Hermes is offline.

## Current migration status

Hermes routing, task personas, employee sessions, sequential meeting handoff,
and authenticated readiness checks are implemented. The local Hermes gateway has not yet been enabled as this
application's API server, so no live canary has run. The remaining acceptance
gate is to configure the dedicated profile, verify its effective toolsets and
route aliases, then run mocked and sanitized end-to-end checks before enabling
real inference.

References: [Hermes API Server](https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server),
[toolsets](https://hermes-agent.nousresearch.com/docs/reference/toolsets-reference),
[profiles](https://hermes-agent.nousresearch.com/docs/user-guide/profiles/).
