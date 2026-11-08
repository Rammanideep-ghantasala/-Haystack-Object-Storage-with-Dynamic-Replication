import random

import pytest
from fastapi import BackgroundTasks, HTTPException

from conftest import import_service_module


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


def test_read_falls_back_to_next_replica_when_first_store_fails(monkeypatch):
    router = import_service_module("webserver", "router")

    class Directory:
        def get_replica_nodes(self, key):
            assert key == "object-key"
            return ["store1:7101", "store2:7102"]

    requested_urls = []

    def fake_get(url, timeout):
        requested_urls.append(url)
        if "store1" in url:
            return FakeResponse(500, text="store failure")
        return FakeResponse(200, {"value": "object-value"})

    cache_writes = []
    monkeypatch.setattr(router, "cache_get", lambda key: None)
    monkeypatch.setattr(router, "cache_set", lambda key, value, ttl=None: cache_writes.append((key, value, ttl)))
    monkeypatch.setattr(router.requests, "get", fake_get)
    monkeypatch.setattr(random, "shuffle", lambda values: None)
    router.state.directory_client = Directory()

    result = router.read_object("object-key", BackgroundTasks())

    assert result == {"value": "object-value", "cached": False}
    assert requested_urls == [
        "http://store1:7101/object/object-key",
        "http://store2:7102/object/object-key",
    ]
    assert cache_writes == [("object-key", "object-value", None)]


def test_read_returns_clear_error_after_all_replicas_fail(monkeypatch):
    router = import_service_module("webserver", "router")

    class Directory:
        def get_replica_nodes(self, key):
            return ["store1:7101", "store2:7102"]

    monkeypatch.setattr(router, "cache_get", lambda key: None)
    monkeypatch.setattr(router.requests, "get", lambda url, timeout: FakeResponse(503, text="unavailable"))
    monkeypatch.setattr(random, "shuffle", lambda values: None)
    router.state.directory_client = Directory()

    with pytest.raises(HTTPException) as exc:
        router.read_object("missing-key", BackgroundTasks())

    assert exc.value.status_code == 404
    assert exc.value.detail == "Key not found on replicas"


def test_partial_write_rolls_back_successful_replica_and_skips_placement(monkeypatch):
    router = import_service_module("webserver", "router")

    class FixedUuid:
        hex = "fixed-object-key"

    class Directory:
        def __init__(self):
            self.set_calls = []

        def get_active_stores(self):
            return [
                {"id": "store1", "address": "store1:7101"},
                {"id": "store2", "address": "store2:7102"},
            ]

        def set_placement(self, key, replica_ids):
            self.set_calls.append((key, replica_ids))
            return True

    directory = Directory()
    post_calls = []
    delete_calls = []
    cache_sets = []

    def fake_post(url, json, timeout):
        post_calls.append((url, json))
        if "store1" in url:
            return FakeResponse(200, {"status": "ok"})
        return FakeResponse(500, text="write failed")

    def fake_delete(url, timeout):
        delete_calls.append(url)
        return FakeResponse(200, {"status": "deleted"})

    monkeypatch.setattr(router.uuid, "uuid4", lambda: FixedUuid())
    monkeypatch.setattr(random, "sample", lambda population, count: population[:count])
    monkeypatch.setattr(router.requests, "post", fake_post)
    monkeypatch.setattr(router.requests, "delete", fake_delete)
    monkeypatch.setattr(router, "cache_set", lambda key, value, ttl=None: cache_sets.append((key, value, ttl)))
    router.state.directory_client = directory

    with pytest.raises(HTTPException) as exc:
        router.write_object(router.WriteRequest(value="payload"))

    assert exc.value.status_code == 500
    assert exc.value.detail == "Replication failed: wrote 1 of 2 required replicas"
    assert post_calls == [
        ("http://store1:7101/object/fixed-object-key", {"value": "payload", "version": None}),
        ("http://store2:7102/object/fixed-object-key", {"value": "payload", "version": None}),
    ]
    assert delete_calls == ["http://store1:7101/object/fixed-object-key"]
    assert directory.set_calls == []
    assert cache_sets == []
