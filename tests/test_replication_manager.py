import pytest

from conftest import import_service_module


class FakeRedis:
    def __init__(self):
        self.hot_keys = set()

    def sismember(self, name, key):
        assert name == "hot_keys"
        return key in self.hot_keys

    def sadd(self, name, key):
        assert name == "hot_keys"
        self.hot_keys.add(key)

    def srem(self, name, key):
        assert name == "hot_keys"
        self.hot_keys.discard(key)

    def smembers(self, name):
        assert name == "hot_keys"
        return set(self.hot_keys)


def test_ewma_marks_frequently_read_object_as_hot(monkeypatch):
    replicator = import_service_module("replication-manager", "replicator")
    fake_redis = FakeRedis()
    monkeypatch.setattr(replicator, "get_redis_client", lambda: fake_redis)

    manager = replicator.ReplicaManager()
    for _ in range(10):
        manager.record_access("hot-object")

    manager.update_access_rates()

    assert manager.access_rate["hot-object"] == pytest.approx(3.0)
    assert manager.desired_replica_count(manager.access_rate["hot-object"]) == 3
    assert "hot-object" in fake_redis.hot_keys


def test_hot_object_replication_adds_third_replica_and_updates_directory(monkeypatch):
    replicator = import_service_module("replication-manager", "replicator")
    manager = replicator.ReplicaManager()
    manager.access_rate["hot-object"] = 3.0

    current_replicas = [
        {"id": "store1", "address": "store1:7101"},
        {"id": "store2", "address": "store2:7102"},
    ]
    all_stores = current_replicas + [
        {"id": "store3", "address": "store3:7103"},
    ]
    pushed = []
    placement_updates = []

    monkeypatch.setattr(manager, "get_current_replicas", lambda key: current_replicas)
    monkeypatch.setattr(manager, "get_store_nodes", lambda: all_stores)
    monkeypatch.setattr(manager, "fetch_object", lambda node, key: "object-value")

    def push_object(node, key, value):
        pushed.append((node["id"], key, value))
        return True

    def update_placement(key, replica_ids):
        placement_updates.append((key, set(replica_ids)))
        return True

    monkeypatch.setattr(manager, "push_object", push_object)
    monkeypatch.setattr(manager, "_update_directory_placement", update_placement)

    manager.adjust_replicas("hot-object")

    assert pushed == [("store3", "hot-object", "object-value")]
    assert placement_updates == [
        ("hot-object", {"store1", "store2", "store3"}),
    ]
