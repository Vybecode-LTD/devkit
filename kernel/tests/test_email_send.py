"""`email.send` and its templates (decision 0033).

A module declares its templates on `InstalledModule(emails=...)`, a site
rewords them through `create_app(emails=...)`, and both are checked when the
app is built. No database: building an app connects to nothing.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI

from kernel import email
from kernel.app import create_app
from kernel.email import CapturingMailer, Rendered, Template
from kernel.modules import InstalledModule

from .conftest import make_config, manifest

REPLY = Template(
    subject="$name replied on $site_name",
    text="$name wrote:\n\n$body\n\nSee it at $site_url/posts/$post.\n",
    html="<p><b>$name</b> wrote:</p><p>$body</p>",
)


def one(name: str, template: Template) -> InstalledModule:
    return InstalledModule(manifest(name.split(".")[0]), emails={name: template})


def blog(**emails: Template) -> InstalledModule:
    return InstalledModule(manifest("blog"), emails={"blog.comment_reply": REPLY, **emails})


def build(
    modules: list[InstalledModule] | None = None,
    emails: dict[str, Template] | None = None,
    **config: Any,
) -> tuple[FastAPI, CapturingMailer]:
    captured = CapturingMailer()
    app = create_app(
        modules=modules if modules is not None else [blog()],
        config=make_config(site_name="Vibe Site", site_url="https://vibe.test/", **config),
        mailer=captured,
        emails=emails,
    )
    return app, captured


CONTEXT = {"name": "Ana", "body": "Nice beat", "post": 7}


# --- rendering ---------------------------------------------------------------------


def test_a_template_renders_with_the_site_s_name_and_address() -> None:
    build()
    rendered = email.render("blog.comment_reply", CONTEXT)
    assert rendered == Rendered(
        subject="Ana replied on Vibe Site",
        text="Ana wrote:\n\nNice beat\n\nSee it at https://vibe.test/posts/7.\n",
        html="<p><b>Ana</b> wrote:</p><p>Nice beat</p>",
    )


def test_a_value_cannot_break_the_subject_or_the_html() -> None:
    build()
    rendered = email.render(
        "blog.comment_reply",
        {**CONTEXT, "name": "Ana\r\nBcc: x@evil.test" + chr(0x2028) + "<script>", "body": "<b>&"},
    )
    assert rendered.subject == "Ana Bcc: x@evil.test <script> replied on Vibe Site"
    assert rendered.html is not None
    assert "&lt;script&gt;" in rendered.html
    assert "&lt;b&gt;&amp;" in rendered.html
    assert "<script>" not in rendered.html
    assert "Ana\r\nBcc" in rendered.text  # the text body keeps what was written


def test_a_missing_value_is_named_and_nothing_else() -> None:
    build()
    with pytest.raises(ValueError, match=r"blog\.comment_reply needs \$post") as caught:
        email.render("blog.comment_reply", {"name": "Ana-secret-name", "body": "x"})
    assert "Ana-secret-name" not in str(caught.value)


def test_an_unknown_template_is_named() -> None:
    build()
    with pytest.raises(ValueError, match=r"No email template blog\.nope"):
        email.render("blog.nope", CONTEXT)


@pytest.mark.parametrize("key", ["site_name", "site_url"])
def test_the_context_cannot_set_the_site_s_own_values(key: str) -> None:
    build()
    with pytest.raises(ValueError, match=key):
        email.render("blog.comment_reply", {**CONTEXT, key: "spoof"})


def test_a_template_without_html_renders_none() -> None:
    build(
        modules=[
            InstalledModule(manifest("blog"), emails={"blog.plain": Template("Hi", "Hello $who")})
        ]
    )
    assert email.render("blog.plain", {"who": "you"}) == Rendered("Hi", "Hello you", None)


# --- declaring and rewording ---------------------------------------------------------


def test_a_site_rewords_a_module_s_template() -> None:
    build(emails={"blog.comment_reply": Template("New reply from $name", "$name: $body")})
    assert email.render("blog.comment_reply", CONTEXT) == Rendered(
        "New reply from Ana", "Ana: Nice beat", None
    )


@pytest.mark.parametrize(
    ("modules", "emails", "problem"),
    [
        (
            [InstalledModule(manifest("blog"), emails={"shop.receipt": REPLY})],
            None,
            "blog may only declare blog.*",
        ),
        (
            [InstalledModule(manifest("blog"), emails={"blog.Bad-Name": REPLY})],
            None,
            "blog.Bad-Name",
        ),
        (
            [InstalledModule(manifest("blog"), emails={"kernel.welcome": REPLY})],
            None,
            "kernel.welcome",
        ),
        ([blog()], {"blog.nope": REPLY}, "blog.nope, which no module declares"),
        ([blog()], {"blog.comment_reply": Template("$name $secret", "x")}, "$secret"),
        (
            [InstalledModule(manifest("blog"), emails={"blog.x": Template("a\nb", "x")})],
            None,
            "one line",
        ),
        (
            [InstalledModule(manifest("blog"), emails={"blog.x": Template("$", "x")})],
            None,
            "blog.x",
        ),
        (
            [InstalledModule(manifest("blog"), emails={"blog.x": Template("ok", "${broken")})],
            None,
            "blog.x",
        ),
        (
            [
                InstalledModule(
                    manifest("blog"), emails={"blog.x": Template("ok", "x", "<p>$ 1</p>")}
                )
            ],
            None,
            "blog.x",
        ),
        # Fixed wording no send could get past Checked (CodeRabbit on #59).
        ([one("blog.x", Template("", "Body"))], None, "blog.x's subject"),
        ([one("blog.x", Template("   ", "Body"))], None, "blog.x's subject"),
        ([one("blog.x", Template("S" * 256, "Body"))], None, "blog.x's subject"),
        ([one("blog.x", Template("Subject", ""))], None, "blog.x's text"),
        ([one("blog.x", Template("Subject", "a" + chr(0) + "b"))], None, "blog.x's text"),
        ([one("blog.x", Template("Subject", "x" * (256 * 1024 + 1)))], None, "blog.x's text"),
        ([one("blog.x", Template("Subject", "Body", " "))], None, "blog.x's html"),
        ([blog()], {"blog.comment_reply": Template("", "$name")}, "blog.comment_reply's subject"),
    ],
)
def test_a_bad_template_stops_the_start(
    modules: list[InstalledModule], emails: dict[str, Template] | None, problem: str
) -> None:
    with pytest.raises(RuntimeError, match="Refusing to start") as caught:
        build(modules=modules, emails=emails)
    assert problem in str(caught.value)


def test_a_switched_off_module_s_templates_still_render() -> None:
    # MODULES may leave a module out of this deploy; its code may still be
    # imported by a job, so its templates stay declared.
    build(MODULES="")
    assert email.render("blog.comment_reply", CONTEXT).subject == "Ana replied on Vibe Site"


# --- sending -----------------------------------------------------------------------


async def test_send_renders_and_hands_the_message_to_the_site_s_mailer() -> None:
    _, captured = build()
    await email.send("blog.comment_reply", "reader@vibe.test", CONTEXT)
    [message] = captured.to("reader@vibe.test")
    assert message.subject == "Ana replied on Vibe Site"
    assert message.text.startswith("Ana wrote:")
    assert message.html == "<p><b>Ana</b> wrote:</p><p>Nice beat</p>"


async def test_send_still_checks_the_address() -> None:
    _, captured = build()
    with pytest.raises(ValueError, match="to"):
        await email.send("blog.comment_reply", "a@b.test, c@d.test", CONTEXT)
    assert captured.to("a@b.test") == []


async def test_the_latest_app_s_mailer_and_templates_are_the_ones_used() -> None:
    _, first = build()
    _, second = build(emails={"blog.comment_reply": Template("Second $name", "x")})
    await email.send("blog.comment_reply", "reader@vibe.test", CONTEXT)
    assert first.to("reader@vibe.test") == []
    assert second.to("reader@vibe.test")[0].subject == "Second Ana"


def test_the_kernel_exports_email() -> None:
    import kernel

    assert kernel.email is email
    assert "email" in kernel.__all__


def test_mail_before_any_app_is_set_up_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(email, "_postbox", None)
    with pytest.raises(RuntimeError, match="create_app installs"):
        email.render("blog.comment_reply", CONTEXT)


async def test_a_worker_s_mailer_is_checked_too() -> None:
    # email.install puts any mailer behind Checked, not only create_app's
    # (CodeRabbit on #59): a bad address never reaches the adapter.
    captured = CapturingMailer()
    email.install(
        captured, {"blog.comment_reply": REPLY}, site_name="Vibe Site", site_url="https://vibe.test"
    )
    with pytest.raises(ValueError, match="to"):
        await email.send("blog.comment_reply", "a@b.test, c@d.test", CONTEXT)
    assert captured.to("a@b.test, c@d.test") == []
    await email.send("blog.comment_reply", "reader@vibe.test", CONTEXT)
    assert len(captured.to("reader@vibe.test")) == 1


def test_create_app_s_checked_mailer_is_not_wrapped_twice() -> None:
    app, _ = build()
    assert email._current().mailer is app.state.mailer
