"""audio-player: backend package. `CSP` lists hosts this module adds while it's on (decision 0009)."""

CSP: list[tuple[str, str]] = [
    ("frame-src", "https://w.soundcloud.com"),
    ("script-src", "https://w.soundcloud.com"),
]
