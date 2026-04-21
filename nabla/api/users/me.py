"""Profile and identity for Alban Andrieu.

Used by ``get_me``, the ``/whoami/`` MCP resource and route, and ``/users/current``
(``current_user``). ``WHOAMI_HANDLE`` matches the login used in app logs; use
``runtime_whoami()`` for the shell ``whoami`` / OS username.
"""

from __future__ import annotations

import getpass
import os

from nabla.api.users.models import UserIn

DISPLAY_NAME = "Alban Andrieu"
EMAIL = os.environ.get("MAIL_FROM", "alban.andrieu@gmail.com")
PHONE = "+33 (0) 6 95 43 53 53"
ADDRESS = "11 terrasse de l'université"
CITY = "Paris"
STATE = "FR"
ZIPCODE = "92000"
COUNTRY = "France"

# Same handle as in ``get_user`` logging (``user="aandrieu"``).
WHOAMI_HANDLE = "aandrieu"


def runtime_whoami() -> str:
    """Return the current OS login name (equivalent to the ``whoami`` command)."""
    return os.environ.get("USER") or os.environ.get("USERNAME") or getpass.getuser()


def get_me() -> UserIn:
    """Return the canonical profile for Alban Andrieu (demo / MCP / ``whoami``)."""
    return UserIn(
        name=DISPLAY_NAME,
        email=EMAIL,
        phone=PHONE,
        address=ADDRESS,
        city=CITY,
        state=STATE,
        zipcode=ZIPCODE,
        country=COUNTRY,
    )
