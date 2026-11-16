# dev plans

Session prompts and working plans, the owner's convention across `C:\DEV`. Each session ends with a starting prompt for the next one saved here as `<date>-next-session-<topic>.md`. When a prompt's session is done, it moves to `done/`, so the one left here is the job. Durable decisions go in `docs/decisions/`, not here.

`contracts/` holds the one-page contract each feature that touches a seam gets before its code (`C:\DEV\knowledge\decisions\0008-feature-contracts.md`):

| File | What |
| --- | --- |
| `contracts/k3-storage.md` | K3's storage service, `kernel.storage` (PR #58) |
| `contracts/k3-email.md` | K3's email service: `email.send`, templates, SMTP and Resend (PR #59) |
| `contracts/kernel-auth-templates.md` | K2's auth mails on `kernel.*` templates (PR #60) |
