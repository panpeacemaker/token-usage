from __future__ import annotations

import json
import time

from token_usage import cache


def test_write_then_read(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cache, "CACHE_FILE", tmp_path / "summary.json")
    cache.write({"summary": {"available": True}})
    result = cache.read(max_age_seconds=60)
    assert result is not None
    assert result["summary"]["available"] is True


def test_read_returns_none_when_expired(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cache, "CACHE_FILE", tmp_path / "summary.json")
    cache.write({"summary": {"x": 1}})
    data = json.loads((tmp_path / "summary.json").read_text())
    data["fetched_at"] = time.time() - 500
    (tmp_path / "summary.json").write_text(json.dumps(data))
    assert cache.read(max_age_seconds=60) is None


def test_read_returns_none_when_version_mismatch(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cache, "CACHE_FILE", tmp_path / "summary.json")
    cache.write({"summary": {"x": 1}})
    data = json.loads((tmp_path / "summary.json").read_text())
    data["_version"] = cache.CACHE_VERSION - 1
    (tmp_path / "summary.json").write_text(json.dumps(data))
    assert cache.read(max_age_seconds=300) is None


def test_read_returns_none_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cache, "CACHE_FILE", tmp_path / "summary.json")
    assert cache.read(max_age_seconds=300) is None


def test_read_returns_none_when_max_age_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cache, "CACHE_FILE", tmp_path / "summary.json")
    cache.write({"summary": {"x": 1}})
    assert cache.read(max_age_seconds=0) is None


def test_read_raw_returns_none_on_corrupt_json(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cache, "CACHE_FILE", tmp_path / "summary.json")
    (tmp_path / "summary.json").write_text("{bad json")
    assert cache.read_raw() is None


def test_atomic_write_uses_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cache, "CACHE_FILE", tmp_path / "summary.json")
    cache.write({"k": "v"})
    assert (tmp_path / "summary.json").exists()
    assert not (tmp_path / "summary.json.tmp").exists()
