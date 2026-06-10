from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from token_usage import _cookies


def _make_profile(root: Path, name: str, hosts: list[str]) -> Path:
    profile = root / name
    profile.mkdir(parents=True)
    db = profile / "cookies.sqlite"
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE moz_cookies (id INTEGER PRIMARY KEY, host TEXT, name TEXT, value TEXT)"
    )
    for i, h in enumerate(hosts):
        con.execute("INSERT INTO moz_cookies (host, name, value) VALUES (?, ?, ?)", (h, f"c{i}", "v"))
    con.commit()
    con.close()
    return db


def test_pick_firefox_profile_chooses_one_with_cookies(tmp_path: Path) -> None:
    _make_profile(tmp_path, "default", [])
    hardened = _make_profile(tmp_path, "hardened", [".chatgpt.com", "chatgpt.com", ".sub.chatgpt.com"])

    picked = _cookies._pick_firefox_profile(tmp_path, "chatgpt.com")
    assert picked == hardened


def test_pick_firefox_profile_picks_highest_count(tmp_path: Path) -> None:
    _make_profile(tmp_path, "a", [".chatgpt.com"])
    busy = _make_profile(tmp_path, "b", [".chatgpt.com", "chatgpt.com", ".x.chatgpt.com"])

    picked = _cookies._pick_firefox_profile(tmp_path, "chatgpt.com")
    assert picked == busy


def test_pick_firefox_profile_returns_none_when_no_match(tmp_path: Path) -> None:
    _make_profile(tmp_path, "default", [".other.com"])
    assert _cookies._pick_firefox_profile(tmp_path, "chatgpt.com") is None


def test_count_cookies_handles_locked_db(tmp_path: Path) -> None:
    db = _make_profile(tmp_path, "p", ["chatgpt.com", ".chatgpt.com"])
    holder = sqlite3.connect(db)
    holder.execute("BEGIN EXCLUSIVE")
    try:
        assert _cookies._count_cookies(db, "chatgpt.com") == 2
    finally:
        holder.rollback()
        holder.close()


def test_load_cookies_unknown_browser_raises_valueerror() -> None:
    fake_bc3 = type("X", (), {"firefox": staticmethod(lambda **kw: object())})()
    with (
        patch.object(_cookies.importlib, "import_module", return_value=fake_bc3),
        pytest.raises(ValueError, match="unknown browser: opera"),
    ):
        _cookies.load_cookies("opera", "example.com")


def test_load_cookies_zen_uses_picked_profile(tmp_path: Path) -> None:
    db = _make_profile(tmp_path, "hardened", ["chatgpt.com", ".chatgpt.com"])
    captured = {}

    def fake_firefox(cookie_file=None, domain_name=None):
        captured["cookie_file"] = cookie_file
        captured["domain_name"] = domain_name
        return "JAR"

    fake_bc3 = type("X", (), {"firefox": staticmethod(fake_firefox)})()
    with (
        patch.object(_cookies.importlib, "import_module", return_value=fake_bc3),
        patch.dict(_cookies._FIREFOX_FAMILY_ROOTS, {"zen": tmp_path}),
    ):
        result = _cookies.load_cookies("zen", "chatgpt.com")
    assert result == "JAR"
    assert captured["cookie_file"] == str(db)
    assert captured["domain_name"] == "chatgpt.com"


def test_load_cookies_zen_raises_when_no_profile_matches(tmp_path: Path) -> None:
    _make_profile(tmp_path, "p", [".other.com"])
    fake_bc3 = type("X", (), {"firefox": staticmethod(lambda **kw: "JAR")})()
    with (
        patch.object(_cookies.importlib, "import_module", return_value=fake_bc3),
        patch.dict(_cookies._FIREFOX_FAMILY_ROOTS, {"zen": tmp_path}),
        pytest.raises(FileNotFoundError, match="no zen profile contains cookies"),
    ):
        _cookies.load_cookies("zen", "chatgpt.com")


def test_load_cookies_zen_raises_when_root_missing(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist"
    with (
        patch.dict(_cookies._FIREFOX_FAMILY_ROOTS, {"zen": missing}),
        pytest.raises(FileNotFoundError, match="profile root not found"),
    ):
        _cookies.load_cookies("zen", "chatgpt.com")
