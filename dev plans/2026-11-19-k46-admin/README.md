# K4.6's admin screens beside their boards

The K4 contract's §7 "by eye" check for the admin's frame, Dashboard and Activity (#84): each beside VM Website's `design/site/AdminDashboard.dc.html` and `AdminActivity.dc.html`, at 1440 and 390 px, in Vibrant Mindz and in Machined Light. Taken on 2026-11-19 with headless Chromium against `python -m harness.e2e`, signed in as a fresh admin after a member signed in and out and a wrong password was tried, so the log has rows.

Files are `<screen>-<theme>-<width>.png` for the built screens (`dashboard`, `activity`) and `<screen>-board-<width>.png` for the boards as drawn.

## Where they match the boards

- **The frame:** the rail at 256px with the site's name and the Admin badge, the sections with their icons, the current one filled with its accent edge, the person's card at the bottom with View site; the top bar with the breadcrumb, Search or jump to with its Ctrl K key, the bell and View site; the page at 1180px at most, padded as drawn.
- **Dashboard:** the greeting and the day, "Needs you" with its count, each item with its tone's edge and icon, what and why, and its action at the right.
- **Activity:** the title and lead, the kinds as chips, the table (When, Who with their role, What happened, Details, Kind as a pill), the entry's fields in an open section beneath it, and the keep.
- **At 390:** the sidebar folds behind Menu in the bar; the search and View site go; the breadcrumb and bell stay; the table slides sideways inside its card, as the board's does.

## Where they differ, and why

- **Fewer sections:** the board's Homepage, Music, Beats, Marketplace, Collective, Community and Content are Vibrant Mindz's modules, which the harness doesn't have. A section's pages show under it while one is open (`AdminBlog.dc.html`'s drawing), so on Activity "People and access" shows People, Roles and Activity, the last current, where `AdminActivity.dc.html` fills the section itself (decision 0044).
- **No name:** "Good afternoon", not "Good evening, Big Haas", and the email in the person's card: the session has no name and nothing sets one yet. The role line comes from the role ids.
- **The Dashboard's cards and checklist** are a site's modules' (`admin.dashboard.widget`); the harness has none. `StatCard` draws them on the kit's tokens, tested in Vitest.
- **The board's three items** are Vibrant Mindz's modules' (Stripe, comments, the spotlight). The kernel's own item here is the card picture (info); the e2e site has a description, so that warning doesn't show.
- **Activity:** no search box or Export CSV (no route behind either), no Content or Money chips (modules' kinds), and "What happened" is underlined, since picking it shows that entry beneath. The All chip carries the kit's check while pressed (contract change 15).
- **The display face** falls back to the system's: the harness loads no web fonts. The site's name truncates with an ellipsis where it's longer than the board's.

## Contrast

Measured as rendered by axe in both themes on the Dashboard and Activity, with the notices open and Jump to open (`kernel/tests/e2e/admin.spec.ts`): no serious or critical finding. The new info tone's words are 4.5:1 or more on every ground and on its tint in both themes (`tests/test_themes.py`).
