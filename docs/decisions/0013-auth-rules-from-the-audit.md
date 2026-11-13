# 0013: Auth rules the audit found missing

- **Date:** 2026-11-12
- **Status:** Applied
- **Context:** The audit of 2026-11-12 ran the auth threat-model checklist over SPEC.md 14 before K2's sessions and routes. Built as written, the spec allowed:
  - an admin making itself owner, and a takeover through an address someone else signed up with first;
  - an unlimited stream of step-up guesses;
  - API keys that outlive their creator's rights.

  The next K2 step also brought in rules the spec didn't hold yet: VybeSite's known-device cookie, `role_version`, and the override precedence. And decision 0010 said every timeout reads `kernel.clock`, which the rate limiter doesn't.
- **Decision:** These rules join SPEC.md 14, and each gets a contract test:
  - **14.1, who can grant what.** A role is granted or removed only by someone holding every permission it carries. Only an owner grants, removes or suspends an owner. The last owner can't be removed, demoted or suspended. Built-in roles can't be deleted. Invites follow the same rules.
  - **14.3, no pre-claiming.** A provider link, a second factor or a passkey needs a verified email.
  - **14.4.** An unconfirmed TOTP isn't a second factor.
  - **14.5, `role_version`.** A role change raises it; the session's next request gets a new token and the old one stops working.
  - **14.5, known devices.** A signed, HttpOnly `__Host-dk_device` cookie lets the right password through over an account's failure limit, on a browser that signed in before. It survives sign-out and is never the session.
  - **14.6.** Step-up allows 5 failures per session in 15 minutes, then the session ends. A refusal is 429 `kernel.rate_limited` with `Retry-After`, identical whether or not the account exists. Email-keyed limits use the normalized address. Sign-up with an existing address sends that address a notice and answers as for a new one.
  - **14.6, clocks.** Rate-limit windows run on real time. Expiries, the 60-second resend wait and the growing delays read `kernel.clock`. Decision 0010 is narrowed to match.
  - **14.8.** A denial beats a grant, and a person's own override beats their role's.
  - **14.9.** An API key acts with its scopes and its creator's current permissions both. A suspended or deleted creator's keys stop working.
  - **`email.send`.** `email.send(template, to, context)` stays the public API (SPEC.md section 6). K2's `Mailer` protocol, `send(to, subject, text, html=None)`, is the adapter beneath it.
- **Alternatives:**
  - Leaving grant limits to each site: every site would get them wrong the same way.
  - Wiping factors at first verification instead of refusing them before it: harder to explain, and it races with the attacker.
  - Moving the rate limiter onto `kernel.clock`: possible later through a storage wrapper. Today no contract test needs to wait out a window.
- **Consequences:**
  - `docs/contracts/auth-api.md` gains a "Limits" section, the statuses the suite already relies on, and the device cookie.
  - The contract suite gains the tests (strict expected failures until K2).
  - The claude.ai design doc needs 14.1, 14.3 to 14.6, 14.8, 14.9 and the change log synced.
- **See:** SPEC.md 14; decisions 0003 and 0010; `docs/contracts/auth-api.md`
