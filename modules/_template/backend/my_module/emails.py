"""my-module: its email templates (kernel.email, decision 0033).

`EMAILS` maps each template's name, `my-module.<name>` (letters, digits and
underscores after the dot), to its wording. A template is `string.Template`
text: `$name` or `${name}` for a value the sender passes, `$$` for a dollar
sign. Every template also gets `$site_name` and `$site_url`. The HTML body is
optional; values in it are escaped, and in the subject they're folded onto
one line. Send one with:

    await email.send("my-module.welcome", address, {"name": user.name})

A site rewords any template through `create_app(emails=...)`, using only the
placeholders this one uses. For example:

    EMAILS = {
        "my-module.welcome": email.Template(
            subject="Welcome to $site_name, $name",
            text="Hi $name,\n\nYou're in. Start at $site_url.\n",
        ),
    }

A notification key in module.json's `notifications` needs a template of the
same name (kernel.notifications): its subject is the notice's title in the
site, its text and HTML the email. Send one with:

    await notifications.notify(db, user.id, "my-module.something_happened",
                               {"thing": thing.name}, link=f"/my-module/{thing.id}")
"""

from kernel import email

EMAILS: dict[str, email.Template] = {
    "my-module.something_happened": email.Template(
        subject="Something happened to $thing",
        text="Something happened to $thing on $site_name.\n\nSee it: $link\n",
        html='<p>Something happened to <a href="$link">$thing</a> on $site_name.</p>',
    ),
}
