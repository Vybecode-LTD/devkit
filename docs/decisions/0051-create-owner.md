# 0051: The site's owner, made from the server: the reset's own link, and only an owner's address once there is one

- **Date:** 2026-11-20
- **Status:** Decided; applied in K5.5 (#95).
- **Context:** The K5 contract's `create-owner` (§2, §4 item 5) runs a site's `python -m app.owner <email>`. The owner answered its shape when the contract was approved (§8 answer 2): it prints a one-time link to set a password, so no password is typed into a terminal, and there's no setup token at first boot. Building it had to settle:
  - which link;
  - what a second run does once the site has an owner (the owner, 2026-11-20: "Owner's own address only");
  - what happens to an account someone made with the address first;
  - two runs at once on a site with no owner.
- **Decision:**
  1. **`kernel.auth.owners.create_owner(db, email) -> str`** answers the token of a password-reset link, `/auth/reset?token=…`: valid 30 minutes, single use, kept as a keyed hash, as every reset link is (14.12). The reset screen and its checks take it from there, and using it marks the address verified. Nothing is mailed: the command prints the link to whoever ran it, at the server.
  2. **With no active owner,** the address's account gets the owner role (and `member`, as every account has). With no account for it, one is made, with no password.
  3. **With an active owner,** only an owner's own address goes on: it gets a fresh link, which voids the last. That's how a locked-out owner gets back in from the server. Any other address is refused: an owner grants the role in Admin, People. A site whose owners are all suspended may be given one.
  4. **Whoever held the account holds nothing until the link is used:** its password is cleared, every session ends, and every live sign-in code, link, reset and second-factor challenge is voided. Someone who signed up with the owner's address first can't sign in as the owner with the password they chose. A second factor stays, as a reset leaves it. A suspended or deleted account isn't made an owner.
  5. **`owner`'s role row is locked first,** so two runs at once take turns, and the second finds the first's owner.
  6. **Every run is audited** as `auth.user.owner_link_issued`: `made`, `granted`, `renewed` or `refused`. A refusal is committed too, since a refused try from the server is worth seeing. No actor: the server ran it.
  7. **`app.owner` runs with the app's own settings:** the token's stored hash is keyed with SECRET_KEY, so it refuses the secrets the app would refuse (outside DEBUG). On Railway it runs in the service's shell (`railway ssh`), where the database and the secrets are.
  8. **`mechframe create-owner <email> [--site <dir>]`** checks the site's lock, then runs `app.owner` with the site's `.venv` Python and `backend` on the path, in the site's folder, and answers its exit code. A site with no `.venv` is refused.
- **Alternatives:**
  - *A setup token printed at first boot* (SPEC 14.1 had it, from VybeSite's `setup_admin.py`): the owner chose the command alone (§8 answer 2). A token in the deploy's logs would be readable by anyone who reads the logs.
  - *Refusing every address once there's an owner:* a locked-out owner would have only the reset email, which needs working mail.
  - *Making any address an owner:* whoever runs it holds the database anyway, but a mistyped address would make a stranger an owner.
  - *Keeping the password of an account already there:* someone who pre-claimed the address would sign in as the owner with it.
  - *A link of its own, longer than 30 minutes:* the person who ran the command is at the server, and running it again gives a new one.
- **Consequences:**
  - SPEC 14.1 drops the setup token at first boot.
  - The admin's Activity names the new action ("Gave … an owner's link from the server").
  - A run for an owner who is signed in signs them out everywhere until they use the link.
- **See:** SPEC 14.1, 14.7 and 14.12; decisions 0022 and 0047; the K5 contract's change 9; `kernel/backend/kernel/auth/owners.py`; `kernel/tests/auth/test_owners.py`; the template's `backend/app/owner.py`; `cli/mechframe/owner.py`
