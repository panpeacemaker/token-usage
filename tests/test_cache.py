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


def test_v7_cache_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cache, "CACHE_FILE", tmp_path / "summary.json")
    (tmp_path / "summary.json").write_text(
        json.dumps({"_version": 7, "fetched_at": time.time(), "summary": {"x": 1}})
    )
    assert cache.read_raw() is None


def test_write_stamps_only_fetched_providers(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cache, "CACHE_FILE", tmp_path / "summary.json")
    cache.write({"summary": {}, "openai": {}, "kimi": {}}, fetched_providers={"claude", "kimi"})
    raw = cache.read_raw()
    assert raw is not None
    assert set(raw["_provider_fetched_at"].keys()) == {"claude", "kimi"}


def test_write_preserves_unfetched_provider_stamps(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cache, "CACHE_FILE", tmp_path / "summary.json")
    cache.write({"summary": {}, "openai": {}, "kimi": {}}, fetched_providers={"chatgpt", "kimi"})
    initial = cache.read_raw()
    initial_chatgpt = initial["_provider_fetched_at"]["chatgpt"]
    initial_kimi = initial["_provider_fetched_at"]["kimi"]

    time.sleep(0.01)
    cache.write({"summary": {}, "openai": {}, "kimi": {}}, fetched_providers={"claude"})
    raw = cache.read_raw()
    per = raw["_provider_fetched_at"]
    assert per["chatgpt"] == initial_chatgpt
    assert per["kimi"] == initial_kimi
    assert per["claude"] > initial_chatgpt


def test_is_provider_fresh_uses_per_provider_stamp(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cache, "CACHE_FILE", tmp_path / "summary.json")
    cache.write({"summary": {}, "openai": {}, "kimi": {}}, fetched_providers={"claude"})
    raw = cache.read_raw()
    assert cache.is_provider_fresh(raw, "claude", max_age_seconds=300) is True
    assert cache.is_provider_fresh(raw, "kimi", max_age_seconds=300) is False


def test_is_provider_fresh_falls_back_to_global_fetched_at(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cache, "CACHE_FILE", tmp_path / "summary.json")
    now = time.time()
    (tmp_path / "summary.json").write_text(
        json.dumps({"_version": cache.CACHE_VERSION, "fetched_at": now, "_written_at": now, "summary": {}})
    )
    raw = cache.read_raw()
    assert cache.is_provider_fresh(raw, "claude", max_age_seconds=300) is True


def test_is_provider_fresh_returns_false_for_zero_max_age(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cache, "CACHE_FILE", tmp_path / "summary.json")
    cache.write({"summary": {}}, fetched_providers={"claude"})
    raw = cache.read_raw()
    assert cache.is_provider_fresh(raw, "claude", max_age_seconds=0) is False


def test_is_provider_fresh_rejects_future_stamp(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cache, "CACHE_FILE", tmp_path / "summary.json")
    now = time.time()
    (tmp_path / "summary.json").write_text(
        json.dumps(
            {
                "_version": cache.CACHE_VERSION,
                "fetched_at": now,
                "_written_at": now,
                "summary": {},
                "_provider_fetched_at": {"claude": now + 48000},
            }
        )
    )
    raw = cache.read_raw()
    assert cache.is_provider_fresh(raw, "claude", max_age_seconds=300) is False


def test_is_provider_fresh_accepts_recent_stamp(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cache, "CACHE_FILE", tmp_path / "summary.json")
    now = time.time()
    (tmp_path / "summary.json").write_text(
        json.dumps(
            {
                "_version": cache.CACHE_VERSION,
                "fetched_at": now,
                "_written_at": now,
                "summary": {},
                "_provider_fetched_at": {"claude": now - 10},
            }
        )
    )
    raw = cache.read_raw()
    assert cache.is_provider_fresh(raw, "claude", max_age_seconds=300) is True


def test_read_rejects_future_fetched_at(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cache, "CACHE_FILE", tmp_path / "summary.json")
    now = time.time()
    (tmp_path / "summary.json").write_text(
        json.dumps({"_version": cache.CACHE_VERSION, "fetched_at": now + 48000, "_written_at": now, "summary": {}})
    )
    assert cache.read(max_age_seconds=300) is None


def test_write_drops_future_provider_stamp(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cache, "CACHE_FILE", tmp_path / "summary.json")
    now = time.time()
    (tmp_path / "summary.json").write_text(
        json.dumps(
            {
                "_version": cache.CACHE_VERSION,
                "fetched_at": now,
                "_written_at": now,
                "summary": {},
                "_provider_fetched_at": {"claude": now + 48000, "bad": "nan"},
            }
        )
    )
    cache.write({"summary": {}}, fetched_providers={"kimi"})
    per = cache.read_raw()["_provider_fetched_at"]
    assert "claude" not in per
    assert "bad" not in per
    assert "kimi" in per


def test_write_includes_written_at(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cache, "CACHE_FILE", tmp_path / "summary.json")
    cache.write({"summary": {}}, fetched_providers={"claude"})
    raw = cache.read_raw()
    assert "_written_at" in raw
    assert raw["_written_at"] <= time.time()


def test_is_provider_fresh_rejects_stamp_newer_than_written(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cache, "CACHE_FILE", tmp_path / "summary.json")
    now = time.time()
    (tmp_path / "summary.json").write_text(
        json.dumps(
            {
                "_version": cache.CACHE_VERSION,
                "fetched_at": now,
                "_written_at": now - 10,
                "summary": {},
                "_provider_fetched_at": {"claude": now},
            }
        )
    )
    raw = cache.read_raw()
    assert cache.is_provider_fresh(raw, "claude", max_age_seconds=300) is False


def test_read_rejects_fetched_at_newer_than_written(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cache, "CACHE_FILE", tmp_path / "summary.json")
    now = time.time()
    (tmp_path / "summary.json").write_text(
        json.dumps(
            {
                "_version": cache.CACHE_VERSION,
                "fetched_at": now,
                "_written_at": now - 10,
                "summary": {},
            }
        )
    )
    assert cache.read(max_age_seconds=300) is None
