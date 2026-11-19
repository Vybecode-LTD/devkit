# The UI kit

Every part a kernel screen or a module's page is built from (K4 contract §4 item 4, change 15). `@/kernel` exports all of it. Use a part before writing a component of your own (SPEC 16).

The behavior is ported from VybeSite; the look is drawn from the Vibrant Mindz admin boards (VM Website `design/generators/admin_kit.py`, `design/theme/vibrant-mindz/shell-slots.md`) on the theme's tokens alone, so Machined Light draws the same parts in its own values. The styles are `kit.css`, in the `mf.kit` cascade layer after the frames' `mf.base`.

| Part | What it's for |
| --- | --- |
| `Button`, `LinkButton` | Secondary (outlined) by default, `primary` for the page's own action, `small` for the top bar and a Needs-you item. A `Button` is `type="button"` unless it says otherwise |
| `Field` with `Input`, `TextArea`, `Select` | A labelled control with its hint and its error, wired to it (`aria-describedby`, `aria-invalid`); the field's `id` is the control's |
| `Switch` | A setting that's on or off at once (`role="switch"`) |
| `Card` | A panel with an optional heading row and actions; `flush` for a table that fills it |
| `Pill`, `Chip` | A state in words over its tint; a filter that's pressed or not, with a check while pressed |
| `Attention` | One "Needs you" item: what's wrong, why, and the action that fixes it |
| `Accordion` | A collapsible section on `<details>`, remembering the reader's own choice, opening for a problem |
| `Tabs` | WAI-ARIA tabs: one tab stop, arrows, Home and End; every panel stays drawn |
| `Table` | Records in a sideways scroller that keeps the focused control in view, a tab stop named by its caption while it slides; empty, its caption over the empty state |
| `Dialog` | A modal `<dialog>` named by its heading, focus in and back |
| `UnsavedDialog`, `useUnsavedGuard`, `useLeaveGuard` | Asking before a move away loses changes |
| `SaveBar` | A form's Save while it has changes, with room kept below what scrolls |
| `SaveConflict`, `settingsConflict`, `resolveConflict` | A settings save someone else got to first (`kernel.settings_conflict`) |
| `SectionHistory` | A settings section's saved versions, one click deeper |
| `ToastProvider`, `useToast` | Short notes after an action, in live regions (the provider is in every page's tree) |
| `EmptyState`, `LoadError` | Nothing there yet; a load that failed, said as a failure |
| `ErrorBoundary` | A part that fails to draw, kept from taking the page with it |
| `RouteFocus`, `ScrollMemory`, `landOn`, `reveal` | Focus and scroll on a move between pages, and landing on a `#place` |
| `Icon`, `ICON_NAMES` | The kit's icon set; `IconName` is one of its names |

## Focus, two ways

The site, sign-in and account screens keep the base outline: 2px of `color.focus`, 3px off (`frames.css`). Inside the admin (`.mf-admin-look`, on the admin frame), focus is the accent ring (`shadow.focus-ring`), as the owner set it on 2026-11-18:

- a 2px page-colour gap first on a filled or pressed control: the primary button, a switch that's on, anything `aria-pressed="true"` (`shadow.focus-ring-gap`);
- drawn inside on a table's scroller and on a row of a clipped list, class `mf-pick` (`shadow.focus-ring-inset`);
- over the 2px edge the current nav item and the selected tab keep (`shadow.nav-current-focus`, `shadow.tab-current-focus`).

The outline turns transparent rather than off, so forced colours still draw it.

## Checked

- Vitest: the parts' tests in `src/ui/`; `RouteFocus` through `app/routes.test.tsx`, `ErrorBoundary` through `slots/slots.test.tsx`, `ScrollMemory` through `place.test.tsx`.
- Playwright on the kit's page, `harness/web/kit.html` at `/kit.html` (`kernel/tests/e2e/kit.spec.ts`): axe in both themes, the dialog open and shut; the boundary as drawn of each field, select, switch, pressed chip and filled button, 3:1 against what's behind it, and a switch's knob against its track (a secondary button or a chip that's not pressed keeps `border-strong`: its words name it, contract change 15); the focus rings, reached with real Tab presses; a half-hidden button in a table's scroller brought fully into view; and the save bar keeping the focus clear of itself.
