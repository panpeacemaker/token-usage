from __future__ import annotations

import contextlib
import importlib
import shutil
import sqlite3
import tempfile
from pathlib import Path

_FIREFOX_FAMILY_ROOTS: dict[str, Path] = {
    "zen": Path.home() / ".zen",
    "firefox": Path.home() / ".mozilla" / "firefox",
}


def _profile_cookie_dbs(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(root.glob("*/cookies.sqlite"))


def _count_cookies(db_path: Path, domain: str) -> int:
    if not db_path.exists():
        return 0
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        # Copy first: a running Firefox/Zen holds a SQLite write-lock on the live DB.
        shutil.copy2(db_path, tmp_path)
        con = sqlite3.connect(f"file:{tmp_path}?mode=ro", uri=True)
        try:
            cur = con.execute(
                "SELECT COUNT(*) FROM moz_cookies WHERE host = ? OR host LIKE ?",
                (domain, f"%.{domain}"),
            )
            row = cur.fetchone()
            return int(row[0]) if row else 0
        finally:
            con.close()
    except (sqlite3.DatabaseError, OSError):
        return 0
    finally:
        if tmp_path is not None:
            with contextlib.suppress(OSError):
                tmp_path.unlink()


def _pick_firefox_profile(root: Path, domain: str) -> Path | None:
    scored: list[tuple[int, Path]] = []
    for db in _profile_cookie_dbs(root):
        n = _count_cookies(db, domain)
        if n > 0:
            scored.append((n, db))
    if not scored:
        return None
    scored.sort(key=lambda kv: -kv[0])
    return scored[0][1]


def load_cookies(browser: str, domain: str):
    browser_cookie3 = importlib.import_module("browser_cookie3")
    b = (browser or "").lower()

    root = _FIREFOX_FAMILY_ROOTS.get(b)
    if root is not None:
        if not root.exists():
            raise FileNotFoundError(f"{b} profile root not found: {root}")
        cookie_db = _pick_firefox_profile(root, domain)
        if cookie_db is None:
            raise FileNotFoundError(
                f"no {b} profile contains cookies for {domain} "
                f"(searched {len(_profile_cookie_dbs(root))} profile(s) under {root})"
            )
        return browser_cookie3.firefox(cookie_file=str(cookie_db), domain_name=domain)

    fn = {
        "chrome": getattr(browser_cookie3, "chrome", None),
        "chromium": getattr(browser_cookie3, "chromium", None),
        "brave": getattr(browser_cookie3, "brave", None),
        "vivaldi": getattr(browser_cookie3, "vivaldi", None),
        "edge": getattr(browser_cookie3, "edge", None),
        "opera": getattr(browser_cookie3, "opera", None),
    }.get(b)
    if fn is None:
        raise ValueError(f"unknown browser: {browser}")
    return fn(domain_name=domain)
