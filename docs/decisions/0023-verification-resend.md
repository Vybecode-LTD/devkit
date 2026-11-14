# 0023: A signed-in account can ask for a new verification link

- **Date:** 2026-11-14
- **Status:** Applied
- **Context:** A verification link lasts 24 hours (decision 0020), and a sign-up for an address that has an account sends a notice, not a link. So a member who misses the first link had no way to get another, and an unverified account is removed after 7 days (14.7). The contract had no route for it.
- **Decision** (the shape the owner approved, 2026-11-14):
  - **`POST /api/auth/verify-email/resend`**, for a signed-in account, with no body. It answers 202 `{"status": "check_email"}` and mails a new 24-hour link to the address the account has now. The last link stops working, so one is live at a time.
  - **409 `auth.already_verified`** once the address is verified. The account is the caller's own, so there is nothing to hide, and a client can say so plainly. This check comes before the limit, so a verified account's requests spend no budget. It is made again under the account's row lock, so a verification landing while a request waits wins.
  - **Limited as codes are, per account:** 3 in 15 minutes, and a request within 60 seconds of the last link (by `kernel.clock`) answers the same and sends nothing. The account row is locked while that is decided, so requests at once, from any number of browsers, send one link.
  - **Audit:** `auth.verification_resent`, `success` or `waiting`, with the account as actor and subject.
- **Alternatives:**
  - *A public route taking an address.* It would need the same answer for every address and the answer floor, and its mail could be aimed at anyone's inbox. An unverified account can sign in, so a signed-in route is enough.
  - *A silent 202 for a verified address.* It hides nothing worth hiding from the account's own owner, and leaves the client guessing.
  - *Sharing sign-up's per-address mail budget.* Then sign-ups aimed at the address could spend the budget and block the owner's own request.
- **Consequences:**
  - SPEC.md 14.6 gains a limits row and 14.7 the new link, with a change-log line.
  - `docs/contracts/auth-api.md` gains the route, its limit and its mail; the contract suite has three tests for it.
  - `kernel/tests/auth/test_sign_up.py` holds the kernel tests.
- **See:** SPEC.md 14.6 and 14.7; decisions 0020 and 0021; `kernel/backend/kernel/auth/sign_up.py`
