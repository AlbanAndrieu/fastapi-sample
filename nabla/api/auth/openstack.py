"""
OVH API smoke test / consumer-key helper.

Run from repo root (recommended) so stdlib modules are not shadowed:

    uv run python -m nabla.api.auth.openstack

Or:

    uv run python3 nabla/api/auth/openstack.py

Credentials: same OVH *application* (create at https://eu.api.ovh.com/createApp/ or your
region's equivalent). ``consumer_key`` must be issued for that application_key.

``Invalid signature`` almost always means: wrong ``application_secret``, key/secret from
different apps, ``consumer_key`` from another app, or wrong ``OVH_ENDPOINT`` for your
account (ovh-eu / ovh-ca / ovh-us).
"""

from __future__ import annotations

import os
import sys

import ovh
from ovh.exceptions import APIError, BadParametersError

# See https://help.ovhcloud.com/csm/en-api-getting-started-ovhcloud-api?id=kb_article_view&sysparm_article=KB0042777


def _env_str(name: str) -> str | None:
    raw = os.getenv(name)
    if raw is None:
        return None
    stripped = raw.strip()
    return stripped or None


def _build_client() -> ovh.Client:
    endpoint = _env_str("OVH_ENDPOINT") or "ovh-eu"
    application_key = _env_str("OVH_APPLICATION_KEY")
    application_secret = _env_str("OVH_APPLICATION_SECRET")
    consumer_key = _env_str("OVH_CONSUMER_KEY")

    missing = [
        n
        for n, v in (
            ("OVH_APPLICATION_KEY", application_key),
            ("OVH_APPLICATION_SECRET", application_secret),
            ("OVH_CONSUMER_KEY", consumer_key),
        )
        if v is None
    ]
    if missing:
        print(
            "Set non-empty environment variables (no extra quotes/newlines in .env): "
            + ", ".join(missing),
            file=sys.stderr,
        )
        sys.exit(1)

    # Pass all three explicitly so missing env does not silently fall back to ~/.ovh.cfg
    return ovh.Client(
        endpoint=endpoint,
        application_key=application_key,
        application_secret=application_secret,
        consumer_key=consumer_key,
    )


def main() -> None:
    client = _build_client()

    try:
        me = client.get("/me")
    except BadParametersError as exc:
        if "signature" in str(exc).lower():
            print(
                "OVH rejected the request signature. Check, in order:\n"
                "  1. OVH_APPLICATION_SECRET matches the secret shown when the app was created\n"
                "  2. OVH_APPLICATION_KEY and OVH_CONSUMER_KEY belong to the *same* application\n"
                "  3. OVH_ENDPOINT matches your account (try ovh-eu, ovh-ca, or ovh-us)\n"
                "  4. No stray quotes/spaces in .env; copy-paste can add hidden characters\n",
                file=sys.stderr,
            )
        raise SystemExit(exc) from exc
    except APIError as exc:
        raise SystemExit(exc) from exc

    print("Welcome", me["firstname"])

    # Request RO, /me API access (only needed when bootstrapping a new consumer key)
    ck = client.new_consumer_key_request()
    ck.add_rules(ovh.API_READ_ONLY, "/me")
    validation = ck.request()
    print("Btw, your 'consumerKey' is '%s'" % validation["consumerKey"])


if __name__ == "__main__":
    main()
