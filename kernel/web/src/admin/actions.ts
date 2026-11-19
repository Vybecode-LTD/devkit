/**
 * The Activity page's words for the kernel's audit actions (`KERNEL_ACTIONS`
 * in `kernel/backend/kernel/audit.py`), as staff read them beside who did
 * each, and the kinds its filter stands for (VM Website `AdminActivity.dc.html`).
 *
 * A kind is a set of actions and prefixes, which the staff's log takes as
 * several `action`s at once. The board's Content and Money are modules'
 * actions, which have no kind until the modules declare theirs: they show
 * under All, their kind named after the module.
 */
import { DONE } from "../account/Activity";

/** What an action says, given the name of whom it concerns. */
type Words = string | ((subject: string) => string);

const STAFF: Readonly<Record<string, Words>> = {
  "auth.session_ended": "Signed a device out",
  "auth.second_factor_undone": "Removed a second factor from its email",
  "auth.user.removed_unverified": "Removed an unconfirmed account",
  "auth.user.suspended": (subject) => `Suspended ${subject}`,
  "auth.user.restored": (subject) => `Restored ${subject}`,
  "auth.user.roles_changed": (subject) => `Changed ${subject}'s roles`,
  "auth.role.created": "Created a role",
  "auth.role.changed": "Changed a role",
  "auth.role.deleted": "Deleted a role",
  "kernel.settings_saved": "Saved settings",
  "kernel.moderation.dismissed": "Dismissed a report",
  "kernel.moderation.hidden": "Hid something reported",
  "kernel.moderation.deleted": "Deleted something reported",
  "kernel.moderation.timed_out": (subject) => `Timed out ${subject}`,
  "kernel.moderation.time_out_lifted": (subject) => `Lifted ${subject}'s time-out`,
};

/** "Signed in", "Suspended Ann Example"; an action the kernel doesn't know, by its name. */
export function whatHappened(action: string, subject: string): string {
  const words = STAFF[action] ?? DONE[action];
  if (words === undefined) return action;
  return typeof words === "string" ? words : words(subject);
}

export type Kind = { label: string; actions: readonly string[] };

export const KINDS: readonly Kind[] = [
  {
    label: "Sign-in",
    actions: [
      "auth.sign_in",
      "auth.code_sent",
      "auth.second_factor",
      "auth.step_up",
      "auth.sign_out",
      "auth.session_ended",
      "auth.password_reset_requested",
      "auth.password_reset",
      "auth.password_changed",
      "auth.email_change_requested",
      "auth.email_changed",
      "auth.email_restored",
      "auth.totp_setup_started",
      "auth.totp_confirmed",
      "auth.totp_removed",
      "auth.recovery_codes_replaced",
      "auth.passkey_registration_started",
      "auth.passkey_added",
      "auth.passkey_renamed",
      "auth.passkey_removed",
      "auth.second_factor_undone",
    ],
  },
  { label: "Accounts and roles", actions: ["auth.sign_up", "auth.email_verified", "auth.verification_resent", "auth.user.", "auth.role."] },
  { label: "Moderation", actions: ["kernel.moderation."] },
  { label: "Settings", actions: ["kernel.settings_saved", "kernel.module.", "kernel.job."] },
];

function holds(kind: Kind, action: string): boolean {
  return kind.actions.some((each) => (each.endsWith(".") ? action.startsWith(each) : action === each));
}

/** An action's kind: the kernel's, else its module's name ("blog.post_published" → "Blog"). */
export function kindOf(action: string): string {
  const kind = KINDS.find((each) => holds(each, action));
  if (kind) return kind.label;
  const owner = action.split(".")[0] ?? action;
  return owner.charAt(0).toUpperCase() + owner.slice(1);
}
