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
"""

from kernel import email

EMAILS: dict[str, email.Template] = {}
