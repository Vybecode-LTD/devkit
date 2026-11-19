/**
 * The question an editor asks before a move away would lose what isn't saved
 * (ported from VybeSite's `components/UnsavedDialog.tsx`): what's lost, then
 * keeping it in one click. Save and leave saves and goes on where the person
 * was going; a save that fails says why here and stays, so nothing is lost
 * unseen. `what` names the thing being edited ("This role"), or `several`
 * things on a page of forms. Drawn only while a move waits (`useUnsavedGuard`).
 */
import { Button } from "./Button";
import { Dialog } from "./Dialog";
import type { UnsavedGuard } from "./unsaved";

export type UnsavedDialogProps = { guard: UnsavedGuard; what: string; several?: boolean };

export function UnsavedDialog({ guard, what, several = false }: UnsavedDialogProps) {
  if (!guard.asking) return null;
  return (
    <Dialog title="You have changes that aren't saved" onClose={guard.stay}>
      <p className="mf-dialog-lead">
        {what} {several ? "have" : "has"} changes that aren't saved. If you leave now, they're lost.
      </p>
      {guard.error ? (
        <p role="alert" className="mf-dialog-error">
          {guard.error}
        </p>
      ) : null}
      <div className="mf-dialog-actions">
        <Button variant="primary" onClick={guard.saveAndLeave} disabled={guard.saving}>
          {guard.saving ? "Saving…" : "Save and leave"}
        </Button>
        <Button onClick={guard.leave} disabled={guard.saving}>
          Leave without saving
        </Button>
        <Button onClick={guard.stay}>Stay</Button>
      </div>
    </Dialog>
  );
}
