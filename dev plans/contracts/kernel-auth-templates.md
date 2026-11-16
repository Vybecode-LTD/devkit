---
feature: K2's auth mails on kernel.* templates
status: approved
approved: 2026-11-16 (the owner, as the follow-up in the K3 email plan, contracts/k3-email.md §6)
plan: docs/HANDOFF.md, Next 1
pr: 60
---

# Contract: K2's auth mails on `kernel.*` templates

## 1. Goal

A site can reword any of the kernel's own mails (sign-in codes, verification, resets, security notices) through `create_app(emails=...)`, the way it rewords a module's, with no change to what any mail says today.

## 2. Interfaces

`kernel/backend/kernel/auth/mails.py`: `TEMPLATES: dict[str, email.Template]`, declared to `build_templates` by `create_app` as the owner `kernel`, and `rendered(name, **context) -> tuple[str, str]`, the subject and text that each route's existing builder returns. Every template also gets `$site_name` and `$site_url`; links that carry a token arrive whole, as `$link` or `$undo_link`, so a rewording can't break them.

| Template | Sent | Its own placeholders |
|---|---|---|
| `kernel.sign_in_code` | A sign-in code and magic link | `code`, `link`, `minutes` |
| `kernel.verify_email` | After sign-up | `link`, `hours` |
| `kernel.verify_email_again` | A new verification link | `link`, `hours` |
| `kernel.sign_up_exists` | Sign-up with an address that has an account | — |
| `kernel.password_reset` | A reset link | `link`, `minutes` |
| `kernel.password_was_reset` | After a reset | `when` |
| `kernel.password_changed` | After a password change | `when` |
| `kernel.new_sign_in` | A sign-in from a new device | `device`, `when` |
| `kernel.email_change_confirm` | To the new address | `link` |
| `kernel.email_change_taken` | To a new address that has an account | — |
| `kernel.email_change_undo` | To the old address | `link`, `days` |
| `kernel.email_restored` | After an undo | — |
| `kernel.passkey_added` | A passkey added | `when`, `undo_link`, `days` |
| `kernel.passkey_removed` | A passkey removed | `when` |
| `kernel.passkey_undone` | A passkey removed by its undo link | — |
| `kernel.totp_added` | An authenticator app added | `when`, `undo_link`, `days` |
| `kernel.totp_removed` | An authenticator app removed | `when` |
| `kernel.totp_undone` | An authenticator app removed by its undo link | — |
| `kernel.recovery_codes_replaced` | New recovery codes | `when` |

`factor_undo`'s one "second factor undone" message becomes two templates, so a rewording never has to splice in the kernel's word for the factor. The builders keep their names and signatures; only their bodies change.

## 3. Data

None.

## 4. Files

New: `kernel/backend/kernel/auth/mails.py`, `kernel/tests/auth/test_mail_wording.py` and its snapshot `kernel/tests/auth/mail_wording.json`. Changed: `kernel/backend/kernel/app.py` and the nine route files (`codes`, `email_change`, `factor_undo`, `passkeys`, `password_change`, `resets`, `routes`, `sign_up`, `totp`); `SPEC.md` 6; `docs/HANDOFF.md`.

## 5. Conventions this follows

`dev plans/contracts/k3-email.md` and decision 0033: names `<owner>.<name>`, `string.Template` syntax, a site's rewording limited to the original's placeholders.

## 6. Non-goals

- No change to any mail's words: the snapshot test proves it.
- The dates (`5 March 2026 at 09:07 UTC`) and the new-device fallback name stay English and in code.
- Mail still goes out through each route's background task and `get_mailer`; moving it onto K3's jobs comes with the jobs.

## 7. Acceptance

- `kernel/tests/auth/test_mail_wording.py`: every builder's subject and text, for fixed inputs, equal a snapshot taken from the code before the move (it passes before the move and after); a site's rewording of `kernel.sign_in_code` is what the code mail says; a rewording that adds a placeholder is refused.
- The auth suites and the contract suite stay green unchanged; the full suite and coverage hold.

## 8. Open questions

None.

## Changes after approval
