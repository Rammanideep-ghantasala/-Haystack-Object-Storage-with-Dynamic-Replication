import base64
import json

from conftest import import_service_module


def _encoded(value: str) -> str:
    return base64.b64encode(value.encode()).decode()


def _decoded(record: dict) -> str:
    return base64.b64decode(record["data"]).decode()


def test_compaction_preserves_live_objects_and_rewrites_offsets(tmp_path):
    engine_module = import_service_module("store-service", "engine")
    engine = engine_module.StoreEngine(
        data_dir=tmp_path,
        num_volumes=1,
        start_compactor=False,
    )

    engine.write({"photo_id": "object-a", "volume_id": "V1", "photo_data": _encoded("alpha")})
    engine.write({"photo_id": "object-b", "volume_id": "V1", "photo_data": _encoded("bravo")})
    engine.write({"photo_id": "object-c", "volume_id": "V1", "photo_data": _encoded("charlie")})

    assert engine.index["object-b"]["deleted"] is False
    assert engine.index["object-c"]["offset"] > 8 + len(b"alpha")

    engine.mark_deleted("object-b")
    engine.compact()

    with engine.cache_lock:
        engine.cache.clear()

    assert _decoded(engine.read("object-a")) == "alpha"
    assert engine.read("object-b") is None
    assert _decoded(engine.read("object-c")) == "charlie"

    expected_c_offset = 8 + len(b"alpha")
    assert engine.index["object-a"]["offset"] == 0
    assert engine.index["object-c"]["offset"] == expected_c_offset
    assert engine.index["object-b"]["deleted"] is True

    persisted_index = json.loads((tmp_path / "index.json").read_text())
    assert persisted_index["object-b"]["deleted"] is True
    assert persisted_index["object-c"]["offset"] == expected_c_offset

    compacted_size = (tmp_path / "volume_1.dat").stat().st_size
    assert compacted_size == expected_c_offset + 8 + len(b"charlie")


def test_tombstone_delete_removes_object_from_reads_cache_and_persisted_index(tmp_path):
    engine_module = import_service_module("store-service", "engine")
    engine = engine_module.StoreEngine(
        data_dir=tmp_path,
        num_volumes=1,
        start_compactor=False,
    )

    engine.write({"photo_id": "deleted-object", "volume_id": "V1", "photo_data": _encoded("payload")})
    assert engine._cache_get("deleted-object") == b"payload"

    engine.mark_deleted("deleted-object")

    assert engine.read("deleted-object") is None
    assert engine._cache_get("deleted-object") is None
    assert engine.index["deleted-object"]["deleted"] is True

    persisted_index = json.loads((tmp_path / "index.json").read_text())
    assert persisted_index["deleted-object"]["deleted"] is True

    restarted = engine_module.StoreEngine(
        data_dir=tmp_path,
        num_volumes=1,
        start_compactor=False,
    )
    assert restarted.read("deleted-object") is None
