"""The kernel's own mails, as templates a site can reword (decision 0033).

`create_app` declares `TEMPLATES` under the owner `kernel`, as it declares a
module's `EMAILS`, so `create_app(emails={"kernel.sign_in_code": ...})`
rewords one, using only the placeholders it has here. The wording is what
K2's routes said before it moved here (`kernel/tests/auth/test_mail_wording.py`
holds it to that). A link that carries a token arrives whole, as `$link` or
`$undo_link`, so a rewording can't break it; `$site_url/sign-in` is the
sign-in page. Dates stay English (`when`), as does the name a new device
gets when its browser can't be named.

Each route keeps its own builder (`codes._message` and the rest), which
calls `rendered` with its values and hands the subject and text to the mailer
as before.
"""

from __future__ import annotations

from datetime import datetime

from kernel.email import Template, render


def when(at: datetime) -> str:
    """`5 March 2026 at 09:07 UTC`."""
    return f"{at.day} {at:%B %Y} at {at:%H:%M} UTC"


def rendered(name: str, **context: str | int) -> tuple[str, str]:
    """The subject and text of the kernel's template `name` with `context`."""
    message = render(name, context)
    return message.subject, message.text


def _undo(what: str) -> str:
    """The lines an "added" mail ends with: the undo link, and the reset."""
    return (
        f"If it wasn't, someone else has your password. Open this link within "
        f"$days days to remove the {what} and sign every device out:\n\n"
        "$undo_link\n\n"
        "Then reset your password at $site_url/sign-in.\n"
    )


def _undone(what: str) -> Template:
    return Template(
        f"A {what} was removed from your $site_name account",
        f"The link in our email was used: the {what} it was sent for is no longer on your "
        "$site_name account, and every device was signed out.\n\n"
        "Whoever added it knows your password. If you haven't yet, reset your password now "
        "at $site_url/sign-in.\n",
    )


TEMPLATES: dict[str, Template] = {
    "kernel.sign_in_code": Template(
        "Your $site_name sign-in code",
        "Your code to sign in to $site_name is $code\n\n"
        "Or open this link to sign in on this device:\n\n"
        "$link\n\n"
        "The code and the link work once, within $minutes minutes.\n\n"
        "If you didn't ask to sign in, ignore this message: nobody can use it "
        "without reading your email.\n",
    ),
    "kernel.verify_email": Template(
        "Confirm your email for $site_name",
        "Welcome to $site_name. Confirm this is your address by opening this link "
        "within $hours hours:\n\n"
        "$link\n\n"
        "If you didn't make an account, ignore this message: nothing more will be sent.\n",
    ),
    "kernel.verify_email_again": Template(
        "Confirm your email for $site_name",
        "Here is a new link to confirm this is your $site_name address. "
        "Open it within $hours hours:\n\n"
        "$link\n\n"
        "Any earlier link no longer works.\n",
    ),
    "kernel.sign_up_exists": Template(
        "Sign-up attempt on $site_name",
        "Someone tried to make a $site_name account with this address, which "
        "already has one, so no new account was made.\n\n"
        "If it was you, sign in at $site_url/sign-in instead, where you can also "
        "reset your password if you've forgotten it.\n\n"
        "If it wasn't you, there's nothing to do.\n",
    ),
    "kernel.password_reset": Template(
        "Reset your $site_name password",
        "Someone asked to reset the password of your $site_name account. "
        "To choose a new one, open this link within $minutes minutes:\n\n"
        "$link\n\n"
        "The link works once. Resetting signs out every device.\n\n"
        "If you didn't ask, ignore this message: your password stays as it is.\n",
    ),
    "kernel.password_was_reset": Template(
        "Your $site_name password was reset",
        "The password of your $site_name account was reset on $when, "
        "and every device was signed out.\n\n"
        "If that was you, there's nothing to do.\n\n"
        "If it wasn't, someone can read your email: secure your mailbox first, "
        "then reset your password again at $site_url/sign-in.\n",
    ),
    "kernel.password_changed": Template(
        "Your $site_name password was changed",
        "The password of your $site_name account was changed on $when, and "
        "every other device was signed out.\n\n"
        "If that was you, there's nothing to do.\n\n"
        "If it wasn't, reset your password now at $site_url/sign-in: that signs every "
        "device out, this one too.\n",
    ),
    "kernel.new_sign_in": Template(
        "New sign-in to $site_name",
        "Someone signed in to your $site_name account from a new device "
        "($device) on $when.\n\n"
        "If that was you, there's nothing to do.\n\n"
        "If it wasn't, reset your password from the sign-in page, "
        "$site_url/sign-in: that signs every device out.\n",
    ),
    "kernel.email_change_confirm": Template(
        "Confirm your new email for $site_name",
        "Someone asked to move a $site_name account to this address. "
        "To confirm it's yours, open this link within 24 hours:\n\n"
        "$link\n\n"
        "Until then the account keeps its old address. "
        "If you didn't ask, ignore this message: nothing changes.\n",
    ),
    "kernel.email_change_taken": Template(
        "Email change attempt on $site_name",
        "Someone asked to move another $site_name account to this address, "
        "which already has an account, so nothing was changed.\n\n"
        "If it wasn't you, there's nothing to do.\n",
    ),
    "kernel.email_change_undo": Template(
        "Your $site_name email was changed",
        "The email address of your $site_name account was changed to another "
        "one. If that was you, there's nothing to do.\n\n"
        "If it wasn't, open this link within $days days to put this address back "
        "and sign every device out:\n\n"
        "$link\n\n"
        "Then reset your password at $site_url/sign-in.\n",
    ),
    "kernel.email_restored": Template(
        "Your $site_name email was restored",
        "The email of your $site_name account is this address again, and "
        "every device was signed out.\n\n"
        "If someone else had changed it, reset your password now at $site_url/sign-in.\n",
    ),
    "kernel.passkey_added": Template(
        "A passkey was added to your $site_name account",
        "A passkey was added to your $site_name account on $when. It can sign "
        "in on its own.\n\n"
        "If that was you, there's nothing to do.\n\n" + _undo("passkey"),
    ),
    "kernel.passkey_removed": Template(
        "A passkey was removed from your $site_name account",
        "A passkey was removed from your $site_name account on $when, and "
        "every other device was signed out.\n\n"
        "If that was you, there's nothing to do.\n\n"
        "If it wasn't, reset your password now at $site_url/sign-in: that signs every device "
        "out, this one too.\n",
    ),
    "kernel.passkey_undone": _undone("passkey"),
    "kernel.totp_added": Template(
        "Two-step sign-in is on for your $site_name account",
        "An authenticator app was added to your $site_name account on $when, "
        "so signing in now asks for one of its codes too.\n\n"
        "If that was you, there's nothing to do. Keep your recovery codes somewhere safe.\n\n"
        + _undo("authenticator app"),
    ),
    "kernel.totp_removed": Template(
        "Two-step sign-in is off for your $site_name account",
        "The authenticator app was removed from your $site_name account on "
        "$when, and every other device was signed out. Signing in now needs only "
        "your password.\n\n"
        "If that was you, there's nothing to do.\n\n"
        "If it wasn't, reset your password now at $site_url/sign-in: that signs every "
        "device out, this one too. Then turn two-step sign-in on again.\n",
    ),
    "kernel.totp_undone": _undone("authenticator app"),
    "kernel.recovery_codes_replaced": Template(
        "New recovery codes for your $site_name account",
        "New recovery codes were made for your $site_name account on $when, "
        "and the old ones no longer work.\n\n"
        "If that was you, keep the new ones somewhere safe.\n\n"
        "If it wasn't, someone is signed in to your account: reset your password now at "
        "$site_url/sign-in, which signs every device out, then make new codes.\n",
    ),
}
