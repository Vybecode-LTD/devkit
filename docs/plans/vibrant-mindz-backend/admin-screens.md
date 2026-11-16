# Admin screens

Designed on the working canvas, **Admin** page: https://claude.ai/artifact/W7EZQumtcK36K3xczG8mNH. Board sources are in `VM Website/design/site/Admin*.dc.html` (generator `VM Website/design/generators/build_admin.py`). They use the site's tokens and the VybeSite admin shell patterns (sidebar, accordions, scannable cards, tables, save bar, SaveConflict). Sample data only.

| Board | Module | Route | Permission |
| --- | --- | --- | --- |
| Admin: Dashboard | kernel + `admin.dashboard.widget` from featured, discography, audio-player, comments, shop | `/admin` | staff |
| Admin: Homepage players | `featured` | `/admin/featured` (sidebar label "Homepage › Players") | `featured.placement.manage` |
| Admin: Album editor | `discography` | `/admin/discography` | `discography.release.manage` |
| Admin: Marketplace products | `shop` (with `licensing`, `downloads`, `print-on-demand`) | `/admin/shop` | `shop.product.manage` |
| Admin: Member profile | `roster` | `/admin/roster` | `roster.profile.manage` (artists: their own) |
| Admin: Roles and permissions | kernel | `/admin/people/roles` | `auth.role.assign` |

**Patterns every screen shares** (build them once in the kernel UI kit if they're missing):

- **Needs-you item:** icon, what's wrong (bold), why it matters (muted), one action button. Warning, error and info tones.
- **Status card:** label, a status pill, one big value, one line of context, and a link to the detail.
- **Placement row:** grip, thumbnail, title and subtitle, a schedule chip, a status pill, and remove.
- **Save bar:** sticky, with the count of unsaved changes, Discard, and Save and go live. It sends `version` and shows SaveConflict on a clash.
- **Pills:** Live (ok), Up next (volt), Queued (muted), Processing (volt), Can't play (bad), Draft (muted), Needs X (warn).
