# Auto-Submit Risk Assessment

**Task:** 27 — Riset legal dan teknis auto-submit
**Date:** 2026-09-19
**Decision:** **NO-GO for production auto-submit; GO for non-production dry-run only.**

## Scope and Decision

The system may prototype browser form filling without clicking a final submit control. Production submission is not approved yet because target forms are not uniform, official ATS submission APIs require authenticated access, and CAPTCHA, consent, custom questions, file uploads, and terms remain target-specific concerns.

Every real submission requires explicit user approval, an idempotency guard, and a verifiable outcome. A crash or timeout after the final action must become `SUBMISSION_AMBIGUOUS` and must never be retried automatically.

## Allowed Target Registry

The registry is empty by default. A target may be added only after manual review records the employer, ATS, URL pattern, form version/date, supported fields, CAPTCHA result, consent behavior, and fallback plan.

| ATS | Target pattern | Mode allowed now | Production status |
|---|---|---|---|
| Greenhouse | None configured | Dry-run only | Not approved |
| Lever | None configured | Dry-run only | Not approved |

Unknown fields, CAPTCHA, unexpected consent notices, new custom questions, or changed DOM structure must stop automation and trigger manual fallback.

## Technical Findings

### Greenhouse

- Public Job Board GET endpoints do not require authentication; the documented application submission POST requires Basic Auth with a board API key.
- Application fields are dynamic and can include required questions, location questions, compliance/demographic questions, multi-value fields, and file inputs.
- Resume and cover-letter attachments have multiple documented upload formats, so upload handling requires separate verification.
- Credentials and personal data must never appear in browser logs, screenshots, URLs, or command-line arguments.

### Lever

- The official API exposes posting-specific application questions and a dedicated Apply to a posting operation.
- API authentication uses API keys for internal workflows and OAuth for integrations; credentials remain server-side.
- The application surface must not be assumed identical across employers; questions and posting-specific fields require per-target review.

### Playwright

- Playwright recommends user-facing role and label locators and documents auto-waiting/retry behavior.
- Locators do not guarantee submission safety. Dry-run must verify current DOM, required fields, uploads, validation messages, and the final-submit boundary.
- Selector mismatch or timeout is a manual fallback, not proof that submission failed; if final action may have happened, record `SUBMISSION_AMBIGUOUS`.

## Risk Register

| Risk | Required control | Decision |
|---|---|---|
| CAPTCHA or bot challenge | Never solve or bypass; stop for manual completion | Block target |
| Resume/CV upload | Explicit approved file, validate type/size, hide local path, verify attachment | Dry-run until verified |
| Custom questions | Reviewed mappings; unknown questions require user input | Manual fallback |
| Consent, demographic, GDPR, or AI notices | Show notice and require explicit user decision | Manual fallback |
| DOM change | Versioned allowlist and preflight checks; no final click in dry-run | Re-verify target |
| Duplicate submission | Atomic `APPROVED -> SUBMITTING`, idempotency key, one attempt record | Required |
| Crash after final click | Set `SUBMISSION_AMBIGUOUS`, notify user, manually verify | Required |
| Credentials | Server-side storage, least privilege, rotation, redacted logs | Required |
| Terms/policy | Target-specific policy and legal review | No production go-ahead |

## Legal Position

This is a technical risk assessment, not legal advice. Public job data or documented APIs do not automatically authorize third-party automated candidate submission. Employer-specific terms, ATS customer agreements, privacy notices, consent requirements, and anti-bot controls may apply.

The Lever terms reviewed contain restrictions on access and use, but no blanket authorization for this project. Greenhouse documentation describes authenticated application submission, but is not legal permission for browser automation. Production use requires target-specific review and user authorization.

## Go/No-Go Outcome

- **GO:** Task 28 dry-run on test pages or explicitly approved safe targets; inspect/fill supported fields and stop before final submission.
- **NO-GO:** Real production submission through Playwright for Greenhouse or Lever at this stage.
- **Prerequisites:** reviewed non-empty allowlist, target policy approval, stable mapping, CAPTCHA-free target, explicit consent handling, secure upload handling, atomic idempotency, ambiguous-outcome recovery, and limited manual production testing.

## Primary Sources

- Greenhouse Job Board API: https://developers.greenhouse.io/job-board.html
- Lever Developer Documentation: https://hire.lever.co/developer/documentation
- Playwright Locators: https://playwright.dev/docs/locators
- Lever Terms of Service: https://www.lever.co/terms-of-service

Sources accessed 2026-09-19; recheck terms and employer policy before production launch.

## Update: Semi-Automatic Form Assist (Option B)

**Decision (2026-09-19, owner):** production auto-submit stays **NO-GO**. Instead the project adopts a semi-automatic assistant (`src/bot_loker_wfh/form_assist.py`).

- It opens the real Greenhouse/Lever form in a visible browser on the owner's computer, fills only mapped fields, and stops. It has no code path that clicks Submit.
- CAPTCHA is never solved or bypassed; the report tells the owner it is present.
- Required fields it cannot fill from reviewed data (dropdowns, work authorization, salary, custom questions) are listed for the owner. Reviewed text answers live in `data/answers.json` and are applied only when exactly one text field matches the label.
- Targets are limited to the exact hosts `job-boards.greenhouse.io`, `boards.greenhouse.io`, `jobs.lever.co`, `jobs.eu.lever.co` over HTTPS. Any other site is opened manually.
- Every form still requires explicit owner approval in Telegram before it is opened, and the owner performs the final submission and marks it with `/dilamar`.
- Personal data (`data/applicant.json`) is local-only, is gitignored with `data/`, and is never logged.

