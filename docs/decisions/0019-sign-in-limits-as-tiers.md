# 0019: Sign-in waits are rate-limit tiers, and second factors are limited per account

- **Date:** 2026-11-13
- **Status:** Applied
- **Context:** K2's sign-in routes put two of SPEC.md 14.6's rules into code, and the auth threat-model checklist turned up two problems with them.
  - **Growing delays.** 14.6 asked for "growing delays" after 5 failed passwords on one account in 15 minutes, and decision 0013 said those delays read `kernel.clock`. Running them on the clock needs a place to keep a wait per address, and it has to work the same for addresses that have no account. The only store that does that today is the rate limiter's, and its windows run on real time (decision 0013).
  - **Second-factor guesses.** "5 failures per sign-in" doesn't bound guesses from someone who has the password. A new sign-in is a new challenge with 5 new tries, so at 10 sign-ins a minute that is 50 TOTP guesses a minute, a real chance of a hit within a day.
- **Decision:**
  - **The growing waits are rate-limit tiers** on failed passwords per normalized address: 5 in 15 minutes, 10 in an hour, 20 in a day. Past any tier, every password is refused with 429 and the longest wait, the right one too, except on a browser holding the account's device cookie (14.5). Like every window, the tiers run on real time. `kernel.clock` keeps expiries and the resend wait.
  - **Second-factor failures are also limited per account:** past 10 in an hour, the account's challenges answer 429 until the hour has passed. The limit of 5 per sign-in stays.
- **Alternatives:**
  - *A table of waits on `kernel.clock`.* It would let the contract suite wait one out, but it needs a migration and a row per address typed, account or not. No test needs that, and the tiers give the same protection.
  - *Ending the challenge but not limiting the account.* This leaves the guessing rate above set by the sign-in limit alone.
  - *Locking the account after second-factor failures.* This would let anyone who has the password lock the owner out, which 14.6 forbids.
- **Consequences:**
  - SPEC.md 14.6's table and its clocks line change, with a change-log line.
  - `docs/contracts/auth-api.md`'s limits gain the tiers and the per-account second-factor limit, and its step-up row gains the failure answers.
  - `kernel/tests/auth/test_sign_in.py` holds the tests: the hour's wait is longer than the quarter's, and 10 failures across sign-ins stop the account taking codes.
- **See:** SPEC.md 14.5 and 14.6; decisions 0010 and 0013; `kernel/backend/kernel/auth/routes.py`
