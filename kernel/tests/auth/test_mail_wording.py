"""K2's mails say what they said before they moved onto `kernel.*` templates.

`mail_wording.json` was recorded from the code before the move
(`dev plans/contracts/kernel-auth-templates.md`): every builder, given the
same fixed inputs, must still give exactly that subject and text. A site
rewords them through `create_app(emails=...)`, as it does a module's.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from kernel.app import create_app
from kernel.auth import (
    codes,
    email_change,
    factor_undo,
    passkeys,
    password_change,
    resets,
    routes,
    sign_up,
    totp,
)
from kernel.config import KernelConfig
from kernel.email import CapturingMailer, Template

from ..conftest import make_config

SNAPSHOT = json.loads((Path(__file__).parent / "mail_wording.json").read_text(encoding="utf-8"))
AT = datetime(2026, 3, 5, 9, 7, tzinfo=UTC)

BUILDERS: dict[str, Callable[[KernelConfig], tuple[str, str]]] = {
    "codes._message": lambda c: codes._message(c, "123456", "LINKTOKEN"),
    "email_change._confirm_mail": lambda c: email_change._confirm_mail(c, "CONFIRMTOKEN"),
    "email_change._taken_notice": email_change._taken_notice,
    "email_change._undo_mail": lambda c: email_change._undo_mail(c, "UNDOTOKEN"),
    "email_change._restored_notice": email_change._restored_notice,
    "factor_undo._undone/passkey": lambda c: factor_undo._undone(c, "passkey"),
    "factor_undo._undone/totp": lambda c: factor_undo._undone(c, "totp"),
    "passkeys._added": lambda c: passkeys._added(c, AT, "UNDOTOKEN"),
    "passkeys._removed": lambda c: passkeys._removed(c, AT),
    "password_change._notice": lambda c: password_change._notice(c, AT),
    "resets._reset_mail": lambda c: resets._reset_mail(c, "RESETTOKEN"),
    "resets._notice": lambda c: resets._notice(c, AT),
    "sign_up._verify_mail": lambda c: sign_up._verify_mail(c, "VERIFYTOKEN"),
    "sign_up._notice": sign_up._notice,
    "sign_up._resend_mail": lambda c: sign_up._resend_mail(c, "VERIFYTOKEN"),
    "totp._added": lambda c: totp._added(c, AT, "UNDOTOKEN"),
    "totp._removed": lambda c: totp._removed(c, AT),
    "totp._replaced": lambda c: totp._replaced(c, AT),
}
DEVICES = {
    "routes._mail_new_device/Firefox on Windows": "Firefox on Windows",
    "routes._mail_new_device/unnamed": "",
}


def _site(**emails: Template) -> KernelConfig:
    config = make_config(site_name="Vibe Site", site_url="https://vibe.test")
    create_app(config=config, mailer=CapturingMailer(), emails=emails or None)
    return config


def test_the_snapshot_covers_every_builder() -> None:
    assert set(SNAPSHOT) == set(BUILDERS) | set(DEVICES)


@pytest.mark.parametrize("name", sorted(BUILDERS))
def test_each_mail_says_what_it_said(name: str) -> None:
    config = _site()
    subject, text, html = BUILDERS[name](config)
    assert [subject, text] == SNAPSHOT[name]
    assert html is None


@pytest.mark.parametrize("name", sorted(DEVICES))
def test_the_new_device_mail_says_what_it_said(name: str) -> None:
    _site()
    subject, text, html = routes.new_device_mail(DEVICES[name], AT)
    assert [subject, text] == SNAPSHOT[name]
    assert html is None


def test_a_site_rewords_a_kernel_mail() -> None:
    config = _site(
        **{
            "kernel.sign_in_code": Template(
                "Your code for $site_name", "Code: $code\nLink: $link\n($minutes min)\n"
            )
        }
    )
    assert codes._message(config, "123456", "LINKTOKEN") == (
        "Your code for Vibe Site",
        "Code: 123456\nLink: https://vibe.test/auth/link?token=LINKTOKEN\n(10 min)\n",
        None,
    )


def test_a_kernel_mail_rewording_gets_only_its_own_values() -> None:
    with pytest.raises(RuntimeError, match=r"kernel\.password_changed uses \$link"):
        _site(**{"kernel.password_changed": Template("Changed", "See $link")})


# --- a site's HTML wording is sent (Codex on #60) ------------------------------------------


def test_a_site_s_html_for_a_kernel_mail_comes_out_of_its_builder() -> None:
    config = _site(
        **{"kernel.sign_in_code": Template("Code", "Code: $code", "<p>Code: <b>$code</b></p>")}
    )
    assert codes._message(config, "123456", "LINKTOKEN") == (
        "Code",
        "Code: 123456",
        "<p>Code: <b>123456</b></p>",
    )


def test_the_new_device_mail_carries_a_site_s_html() -> None:
    _site(**{"kernel.new_sign_in": Template("New sign-in", "From $device", "<p>From $device</p>")})
    _, _, html = routes.new_device_mail("Firefox", AT)
    assert html == "<p>From Firefox</p>"
