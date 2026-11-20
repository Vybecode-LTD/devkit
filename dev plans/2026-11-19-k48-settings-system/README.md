# K4.8: Settings beside its board

The admin's Settings tabs as Chromium draws them (`kernel/tests/e2e`, a throwaway spec, deleted after), at 1440 and 390 px in Machined Light and Vibrant Mindz, beside VM Website `design/site/AdminSettings.dc.html`. System shows three jobs that failed for good, one sealed (Discard only).

| Tab | Files |
| --- | --- |
| Site | `site-1440-*.png`, `site-390-*.png` |
| Features | `features-1440-*.png`, `features-390-*.png` (the harness's probe modules) |
| System | `system-1440-*.png`, `system-390-*.png` |

## What differs from the board, and why

- **Site:** no tagline, address, contact email or time zone, and no "Members must use a second factor": no settings section holds them (contract change 19). The fields `kernel.site` does hold are all here: description, kind, logo, share image, profiles, the summary for AI tools, the AI crawlers' switch. The name is SITE_NAME, read only. "Anyone can sign up" is the new section `kernel.auth`. Each section has its history at its foot.
- **Features:** grouped by the manifest's category (Content, Community, Shop and payments...), not the board's site-specific groups. A module waiting on one it needs says so under its switch.
- **System:** the section under the cards is "Jobs that failed for good", so it isn't a second heading named like the card. Email and storage say how the host set them up, not "Working" (there's no health check), and MechFrame has no "Up to date" (nothing checks). Tries are counted, not "8 of 8": a job's try limit isn't in the list.
- **One Save:** the board's, in the header; the kit's save bar isn't drawn as well.
- On a phone the failed-jobs table slides sideways in its card, as People's does.
