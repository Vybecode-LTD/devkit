# K4.7's admin screens beside their boards

The K4 contract's §7 "by eye" check for People and Roles (#85): each beside VM Website's `design/site/AdminPeople.dc.html` and `AdminRoles.dc.html`, at 1440 and 390 px, in Vibrant Mindz and in Machined Light, with the person's roles dialog and the role editor open. Taken on 2026-11-19 with headless Chromium against `python -m harness.e2e`, signed in as a fresh owner, with three editors with a second factor, one without, three members, one unconfirmed address and a site role, Artist.

Files are `<screen>-<theme>-<width>.png` for the built screens (`people`, `roles`), `<screen>-board-<width>.png` for the boards as drawn, and `person-roles-` and `role-editor-vibrant-mindz-1440.png` for the dialogs.

## Where they match the boards

- **People:** the title and its line; the table (Person, Roles as pills, Second factor as On or Not set up, Last seen, Status as Active, Email not confirmed or Suspended) and Open at the right of each row. A member's role is left out beside a staff role, as the board draws one role a row.
- **Roles:** "Roles and permissions" and New role; a card per role with how many hold it and its line ("Everything, always" for the owner); the permissions with their words and keys in groups, a check per role that holds each.
- **At 390:** the table slides sideways inside its card; the page doesn't.

## Where they differ, and why

- **Left off, not faked:** Invite someone, the Invites tab and the invite form (K2 step 10); Export; the All, Staff, Artists and Members chips (the list has no filter by role); the second-factor and unconfirmed-email notices with Send a reminder and See who (no route sends one); the board's "own" checks (per-resource grants, a K4 non-goal).
- **Names:** the board's "Big Haas" is an address here: nothing sets a name yet (the owner's open question).
- **The lead** says "Open someone to change their roles", not "or help them back in": suspending and restoring aren't on People yet.
- **The matrix** is a table per group, each with its own column heads, where the board draws one table with group rows: each group is a captioned table a screen reader can move through.
- **Groups:** the kernel's permissions as People and access, Site and system, and Moderation; a module's under its id. The board's Community, Music and the rest are Vibrant Mindz's modules, which the harness doesn't have.
- **Role cards:** a site's own role carries Edit beneath its card; built-in roles have none, since they stay as the manifests declare them. Role pills are all the info tone but Member's neutral; the board colours Owner and Editor orange.
- **Search** is by email only ("Search by email"), since names aren't set.

## Contrast

Measured as rendered by axe in both themes on People and Roles, with New role and a person's roles dialog open (`kernel/tests/e2e/admin.spec.ts`): no serious or critical finding.
