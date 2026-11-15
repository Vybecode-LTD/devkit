# 0025: A password change keeps its own session and gives way to a reset

- **Date:** 2026-11-14
- **Status:** Applied
- **Context:** The contract had `POST /api/auth/password/change {current_password, new_password}` (step-up; 200; every other session ends; 422 `auth.password_rejected`), and SPEC 14.5 says the session epoch goes up on a password change. They didn't say what a wrong current password answers or whether it is limited, what happens to the device cookie of the browser that stays signed in, or what a change does to the account's other live tokens.
- **Decision:**
  - **200 `{"status": "password_changed"}`.** The session the change came from carries on at the new epoch, and every other session ends (`sessions.end_all_but`).
  - **A fresh device cookie.** The device cookie is signed over the session epoch, so without a new one the browser that made the change would be a stranger over the failure limit, as the handoff warned.
  - **A wrong current password answers 401 `auth.invalid_credentials`** and counts as a failed step-up, so the fifth in 15 minutes ends the session (14.6), as at step-up. An account with no password (a passkey or a provider only) is refused the same way and sets one by reset.
  - **What a change ends:** every live sign-in code and link, reset link and second-factor challenge of the account. A pending email change dies by the epoch (decision 0024), and earlier undo links stay.
  - **It gives way to a reset.** No database connection is held through the breach lookup or the hash. The account row is then locked before any session or token row, as on every route, and looked at again: if this session has ended meanwhile (a reset, another change, an email undo, a suspension) the change answers 401 `kernel.not_signed_in` and the other one stands. Every route that changes a password raises the epoch, so checking the session is enough; a second check of the stored hash was dropped, since it only added a false refusal when a sign-in re-hashed the same password with newer parameters. A reset arriving after the second look waits for the lock, then finds its link voided by the change. The epoch seen when the current password was checked is compared too (Codex on #46): two changes at once from the same session keep that session alive, so only the moved epoch shows the second one that its current password is no longer current, and it answers 401 `auth.invalid_credentials`.
  - **Audit:** `auth.password_changed`; a wrong current password writes the step-up's failure row. A security mail follows the answer.
- **Alternatives:**
  - *A limit of its own for wrong current passwords.* The step-up budget already ends a session that keeps guessing; a second budget would only add a way to be confusing.
  - *A new session token at a password change.* 14.5 rotates the token at sign-in, step-up and role change; a password change ends every other session, and this one has just stepped up.
- **Consequences:**
  - SPEC.md 14.5 and 14.6 say so, with a change-log line; `docs/contracts/auth-api.md`'s row gives the answers.
  - The contract suite's password-change step-up cases and its every-other-session test now run, with three more tests.
  - `kernel/tests/auth/test_password_change.py` holds the kernel tests.
- **See:** SPEC.md 14.4, 14.5 and 14.6; decisions 0019, 0021, 0022 and 0024; `kernel/backend/kernel/auth/password_change.py`
