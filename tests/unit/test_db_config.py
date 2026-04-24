"""Tests for PostgreSQL URL helpers."""

from nabla.db_config import (
    ensure_supavisor_pooler_username,
    extract_supabase_project_ref_from_url,
    get_sqlalchemy_psycopg_connect_args,
    is_supabase_postgres_host,
    is_supabase_supavisor_pooler_host,
    merge_postgres_query_sslmode_require,
    resolve_supabase_project_ref,
    supabase_session_pooler_targets,
)


def test_supabase_session_pooler_targets_rewrites_direct_host() -> None:
    h, u, p, rew = supabase_session_pooler_targets(
        "db.abcdefghijklmnopqrs.supabase.co",
        "postgres",
        5432,
        pooler_region="eu-west-3",
    )
    assert rew is True
    assert h == "aws-0-eu-west-3.pooler.supabase.com"
    assert u == "postgres.abcdefghijklmnopqrs"
    assert p == 5432


def test_supabase_session_pooler_targets_preserves_custom_user() -> None:
    _h, user, _port, rew = supabase_session_pooler_targets(
        "db.myref.supabase.co",
        "custom_role",
        5432,
        pooler_region="us-east-1",
    )
    assert rew is True
    assert user == "custom_role"


def test_supabase_session_pooler_targets_no_region_noop() -> None:
    host, _user, _port, rew = supabase_session_pooler_targets(
        "db.myref.supabase.co",
        "postgres",
        5432,
        pooler_region=None,
    )
    assert rew is False
    assert host == "db.myref.supabase.co"


def test_merge_postgres_query_sslmode_require() -> None:
    assert merge_postgres_query_sslmode_require(None) == "sslmode=require"
    assert merge_postgres_query_sslmode_require("foo=bar") == "foo=bar&sslmode=require"
    assert merge_postgres_query_sslmode_require("sslmode=disable") == "sslmode=disable"


def test_get_sqlalchemy_psycopg_connect_args_for_pgbouncer() -> None:
    assert get_sqlalchemy_psycopg_connect_args("pgbouncer=true") == {"prepare_threshold": None}
    assert get_sqlalchemy_psycopg_connect_args("foo=bar&pgbouncer=1") == {"prepare_threshold": None}
    assert get_sqlalchemy_psycopg_connect_args("pgbouncer=YES") == {"prepare_threshold": None}


def test_get_sqlalchemy_psycopg_connect_args_without_pgbouncer() -> None:
    assert get_sqlalchemy_psycopg_connect_args(None) == {}
    assert get_sqlalchemy_psycopg_connect_args("foo=bar") == {}
    assert get_sqlalchemy_psycopg_connect_args("pgbouncer=false") == {}


def test_get_sqlalchemy_psycopg_connect_args_for_supavisor_pooler_host() -> None:
    assert (
        get_sqlalchemy_psycopg_connect_args(
            "foo=bar",
            host="aws-0-eu-west-3.pooler.supabase.com",
        )
        == {"prepare_threshold": None}
    )


def test_get_sqlalchemy_psycopg_connect_args_for_non_pooler_host() -> None:
    assert get_sqlalchemy_psycopg_connect_args("foo=bar", host="db.myref.supabase.co") == {}
    assert get_sqlalchemy_psycopg_connect_args("foo=bar", host="localhost") == {}


def test_is_supabase_postgres_host() -> None:
    assert is_supabase_postgres_host("db.x.supabase.co") is True
    assert is_supabase_postgres_host("aws-0-eu-west-3.pooler.supabase.com") is True
    assert is_supabase_postgres_host("localhost") is False


def test_is_supabase_supavisor_pooler_host() -> None:
    assert is_supabase_supavisor_pooler_host("aws-0-eu-west-3.pooler.supabase.com") is True
    assert is_supabase_supavisor_pooler_host("db.abc.supabase.co") is False


def test_extract_supabase_project_ref_from_url() -> None:
    assert extract_supabase_project_ref_from_url("https://myref.supabase.co") == "myref"
    assert extract_supabase_project_ref_from_url("myref.supabase.co") == "myref"


def test_ensure_supavisor_pooler_username() -> None:
    pooler = "aws-0-eu-west-3.pooler.supabase.com"
    assert ensure_supavisor_pooler_username(pooler, "postgres", "abc") == "postgres.abc"
    assert ensure_supavisor_pooler_username(pooler, "postgres.abc", "ignored") == "postgres.abc"
    assert ensure_supavisor_pooler_username("localhost", "postgres", "abc") == "postgres"


def test_resolve_supabase_project_ref_priority() -> None:
    assert (
        resolve_supabase_project_ref(
            explicit="from_explicit",
            supabase_url="https://fromurl.supabase.co",
            db_style_host="db.fromdb.supabase.co",
        )
        == "from_explicit"
    )
    assert (
        resolve_supabase_project_ref(
            explicit=None,
            supabase_url="https://fromurl.supabase.co",
            db_style_host="db.fromdb.supabase.co",
        )
        == "fromurl"
    )
    assert (
        resolve_supabase_project_ref(
            explicit="  ",
            supabase_url=None,
            db_style_host="db.fromdb.supabase.co",
        )
        == "fromdb"
    )
