# Submission Service

`src/bot_loker_wfh/submission.py` is the guarded orchestration layer for Task 29. It does not contain a Greenhouse/Lever production adapter and does not submit a real application by itself.

## Guard sequence

1. Load the application and require status `APPROVED`.
2. Claim it with an atomic `UPDATE ... WHERE status = 'APPROVED'`.
3. Write a `started` row to `submission_attempts` and a `SUBMITTING` history entry.
4. Call the injected submitter with application data.
5. Convert the result to one of `success`, `failed`, `timeout`, or `ambiguous`.
6. Store the result, sanitized error code, confirmation URL/reference, and final status.

## Safety rules

- An application that is not `APPROVED` cannot be claimed.
- `SUBMISSION_AMBIGUOUS` is never retried automatically.
- A timeout is treated as ambiguous because the remote outcome is unknown.
- The submitter must return `SubmissionOutcome`; it cannot directly mutate application state.
- Logs contain only application ID and result status, never cover letter, CV summary, credentials, or provider messages.
- `confirmation_url` and `confirmation_reference` are optional and are stored only when returned by a verified adapter.

## Current production status

Production submission remains disabled. Task 27's decision is still **NO-GO** until a reviewed non-empty target allowlist, target-specific policy approval, secure upload handling, and a manually approved production test exist. The tests use fake submitters only.
