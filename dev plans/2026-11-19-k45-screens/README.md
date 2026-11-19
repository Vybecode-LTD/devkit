# K4.5's screens beside their boards

The K4 contract's §7 "by eye" check for the sign-in and account screens (#83): each beside VM Website's `design/site/Auth.dc.html` and `Account.dc.html`, at 1440 and 390 px, in Vibrant Mindz and in Machined Light. Taken on 2026-11-19 with headless Chromium against `python -m harness.e2e`, the account page signed in as a fresh account.

Files are `<screen>-<theme>-<width>.png`: `sign-in`, `sign-up`, `forgot-password`, `link` (the sign-in link's landing), `reset` (choosing a new password) and `account`.

## Where they match the boards

- **Sign-in:** the frame (the site's name, "Back to the site", the year and name below), the display title, the lead, the strong passkey button, the "or" rule, the 54px fields with "Forgot password?" beside the label, the primary Sign in, the outlined "Email me a code instead", and "New here? Create an account". Every button 54px and round; the fields 54px at 14px.
- **Account:** "Signed in as", the account's pages as pills (the current one filled), the display title and lead, cards two to a row from 540px, each with its display title, its line and its action beside it, rows split by the card's edge, the Now pill, buttons 44px and round.

## Where they differ, and why

- **No art column.** The board's art is the site's own mark. The kernel draws the site's `logo` there when it has one; the harness's test site has none, so the form stands alone, as the board draws it below 980px.
- **The display face** falls back to the system's: the harness loads no web fonts (the theme names Big Shoulders and Geist; a site loads them).
- **Plain words, not the board's:** "Create an account" for "Join the vibe", and no "Vibrify ya mind". Sign-up has no name field or news box, the password no "Last changed", and there's no "Delete account": none has a home in the kernel yet (decision 0043).
- **Field edges** are `color.border-control`, 3:1, not the board's 1.5:1 (the owner's choice, contract change 15).
- **Pill dots:** "On" is the success tone and "Now" the neutral one, where the board draws them blue and orange.

## Contrast

Measured as rendered by axe in both themes on every sign-in page (`parity.spec.ts`) and on the account's three pages, a dialog open, the second step and a sign-in's refusal (`sign-in.spec.ts`): no serious or critical finding. The new strong and large controls' boundaries are measured on the kit's page (`kit.spec.ts`).
