# AGENT-GUIDE: building a site with AI DevKit

You are an AI agent asked to build a website with DevKit. This page is your front door. It follows `SPEC.md` section 17; if they ever differ, the spec wins. The `devkit-site-picker` skill (in `skills/`) holds the same flow in more detail.

**Status (2026-11-12):** the catalog is empty and the CLI isn't built yet. Until they exist, use this guide to plan, and build by hand as `SPEC.md` section 12 describes.

## Rules

- Read `catalog.json` and `recipes/` to pick. Open a module's `MODULE.md` only for finalists. Never read module source code to decide.
- Ask at most 3 questions, and only ones whose answer changes the module list.
- Nothing is copied into the site until the owner confirms the module list.
- Report the exact commands you ran and their results. Never claim tests pass unless they ran.

## The flow

1. **Read the brief.** Fill the brief card: purpose, visitors, content, accounts, money, interaction, integrations, sensitive areas, launch vs later. If the site replaces an existing one, read that site; its pages are requirements too.
2. **Ask, if needed** (at most 3): do visitors get accounts? does money change hands, and for what? do visitors talk to each other or under content?
3. **Match a recipe** whose `fits` lines describe the site. If none is close, start from `minimal`.
4. **Pick modules.** Test each catalog entry's `use_when` and `avoid_when` against the card. Add every `requires`, check `conflicts`, prefer fewer modules, and mark each `launch` or `later`.
5. **Name the gaps:** needs no module covers. Each is either site code (in `site/` folders) or a module candidate.
6. **Present the plan** and wait for a yes:

   | Module | Why (from the brief) | Phase | Status |
   | --- | --- | --- | --- |

   Then list the modules considered and dropped (with the `avoid_when` reason), the gaps, and the settings to decide.
7. **Build:** `devkit new <site> --recipe <recipe>`, then `devkit add` or `devkit remove` for each change to the recipe. Set the theme, each module's settings and the env vars the CLI prints. Write the site's `CLAUDE.md` with the brief card and the confirmed list.
8. **Check:** `devkit check` and the tests. Report what ran and what it returned.

## Picking: distinctions agents get wrong

| If the brief says | Pick | Not |
| --- | --- | --- |
| Media hosted on YouTube, SoundCloud, Spotify, Bandcamp | `embeds` | `audio-player` |
| Selling or previewing the site's own audio files | `audio-player` | `embeds` |
| Discussion under posts or items | `comments` | `community` |
| Real-time chat, channels, a Discord-like space | `community` | `comments` |
| Selling usage rights to files (beats, samples, compositions) | `licensing` with `shop`, `payments`, `downloads` | `shop` alone |
| Customers designing their own printed products | `print-on-demand` | `shop` alone |
| Any money at all | `payments` | |
| Visual work by discipline | `portfolio` | `blog` |
| A profile per member or artist | `roster` | `pages` |

Accounts are a cost: add member sign-up only when a picked module needs it.
