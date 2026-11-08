from conftest import import_service_module


def test_consistent_hashing_maps_the_same_key_to_the_same_cache_node():
    hash_ring_module = import_service_module("cache-service", "hash_ring")
    ring = hash_ring_module.ConsistentHashRing(virtual_nodes=50)
    ring.update_ring(
        [
            ("cache1", "cache1:7201"),
            ("cache2", "cache2:7202"),
            ("cache3", "cache3:7203"),
        ]
    )

    first = ring.get_node_for_key("object-123")
    second = ring.get_node_for_key("object-123")

    assert first == second
    assert first["id"] in {"cache1", "cache2", "cache3"}


def test_consistent_hashing_distributes_keys_and_uses_virtual_nodes():
    hash_ring_module = import_service_module("cache-service", "hash_ring")
    ring = hash_ring_module.ConsistentHashRing(virtual_nodes=50)
    ring.update_ring(
        [
            ("cache1", "cache1:7201"),
            ("cache2", "cache2:7202"),
            ("cache3", "cache3:7203"),
        ]
    )

    owners = {
        ring.get_node_for_key(f"object-{idx}")["id"]
        for idx in range(500)
    }

    assert owners == {"cache1", "cache2", "cache3"}
    assert ring.virtual_nodes == 50
    assert len(ring.ring) == 150
    assert len(ring.node_map) == 150
