from __future__ import annotations

from dataclasses import asdict, is_dataclass

from wp05_ranking_helpers import rank_golden

from itaa_application.errors import ApplicationError
from itaa_ranking.errors import RankingError

FORBIDDEN = (
    "alice@example.com",
    "password",
    "sk-",
    "BEGIN PRIVATE",
)


def _walk(value: object) -> str:
    if is_dataclass(value) and not isinstance(value, type):
        value = asdict(value)
    if isinstance(value, dict):
        return " ".join(_walk(item) for item in value.values())
    if isinstance(value, list | tuple | set | frozenset):
        return " ".join(_walk(item) for item in value)
    return str(value)


def test_ranking_and_errors_do_not_leak_sensitive_text() -> None:
    result = rank_golden()
    haystack = _walk(result).lower()
    for needle in FORBIDDEN:
        assert needle.lower() not in haystack
    for exc in (
        RankingError("supplier_token", "mismatch"),
        ApplicationError("invitation", "wrong_channel"),
    ):
        text = str(exc)
        assert "sp_" not in text
        assert "iv_" not in text
        assert "@" not in text
