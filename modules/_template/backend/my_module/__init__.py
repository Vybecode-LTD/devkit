"""my-module: the backend package. The id's hyphens become underscores here.

`CSP` lists the hosts this module adds to the site's Content-Security-Policy
while it's on, as (directive, https origin) pairs, such as
("frame-src", "https://player.vimeo.com"). Leave it empty when the module
loads nothing from elsewhere (decision 0009).
"""

CSP: list[tuple[str, str]] = []
