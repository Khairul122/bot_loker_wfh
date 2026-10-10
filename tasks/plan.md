# Implementation Plan: Audit 001 fixes

## Overview
Fix audit findings 1-11 in small slices. Preserve staged user changes. Prioritize Settings correctness, endpoint method consistency, secret safety, input validation, XSS prevention, mobile/accessibility, then verification.

## Scope
- Touch only office Settings UI/server, related tests, and task tracking.
- No unrelated refactor.
- Secret values never return to browser.
- Read/test endpoints use GET; state-changing settings/skills actions remain POST.

## Task List

### Phase 1: Settings render and endpoint correctness
- [ ] Task 1: Fix Settings DOM construction and policy list rendering.
- [ ] Task 2: Align Settings read/test actions with GET routes and read live form engine value.

### Checkpoint: Phase 1
- [ ] Focused regression tests pass.
- [ ] Python compile and office JavaScript syntax checks pass.

### Phase 2: Security boundaries
- [ ] Task 3: Mask secrets in settings payload and preserve secrets on blank update.
- [ ] Task 4: Allowlist and validate settings writes.
- [ ] Task 5: Remove unsafe dynamic `innerHTML` from Settings data rendering.

### Checkpoint: Phase 2
- [ ] Server settings security tests pass.
- [ ] Browser-facing dynamic values render as text nodes.

### Phase 3: UI accessibility and responsive behavior
- [ ] Task 6: Add modal dialog semantics, Escape close, and focus return.
- [ ] Task 7: Fix mobile Settings width and restore zoom.

### Checkpoint: Phase 3
- [ ] Settings panel fits 375px viewport.
- [ ] Modal keyboard close and focus behavior verified.

### Phase 4: Long-running test routes and test environment
- [ ] Task 8: Bound BrowserMCP/LLM test operations and expose failure state safely.
- [ ] Task 9: Install/use project dev test dependency and run full suite.
- [ ] Task 10: Audit all fixes and update report verification.

## Risks and Mitigations
| Risk | Impact | Mitigation |
|---|---|---|
| Existing staged changes | High | Do not reset, format, or modify unrelated files. |
| Settings payload compatibility | High | Return masked metadata while keeping accepted stored values server-side. |
| UI data XSS | High | Build DOM nodes with `textContent`; no interpolated remote data in HTML. |
| Blocking external tests | Medium | Add bounded timeouts and explicit JSON errors; avoid broad refactor. |

## Open Questions
- None. Scope follows all numbered findings from `anti-slop/audit-001-2026-10-10.md`.
