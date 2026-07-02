import hashlib
import bisect
import threading
import time

class ConsistentHashRing:
    def __init__(self, replication_factor=1, virtual_nodes=50):
        self.replication_factor = replication_factor
        self.virtual_nodes = virtual_nodes

        self.ring = []
        self.node_map = {}

        self.lock = threading.Lock()

    def _hash(self, key: str):
        return int(hashlib.sha256(key.encode()).hexdigest(), 16)

    def update_ring(self, nodes):
        with self.lock:
            self.ring.clear()
            self.node_map.clear()

            for node in nodes:
                if isinstance(node, str):
                    parts = node.split(":")
                    if len(parts) != 2:
                        continue
                    node_id, port = parts
                    addr = f"{node_id}:{port}"

                else:
                    node_id, addr = node

                for v in range(self.virtual_nodes):
                    h = self._hash(f"{node_id}-vn-{v}")
                    self.ring.append(h)
                    self.node_map[h] = {"id": node_id, "address": addr}

            self.ring.sort()

    def get_node_for_key(self, key: str):
        if not self.ring:
            return None

        h = self._hash(key)
        idx = bisect.bisect_right(self.ring, h)
        real_i = idx % len(self.ring)

        return self.node_map[self.ring[real_i]]

    def monitor_cluster(self, cluster):
        while True:
            time.sleep(2)
            try:
                nodes = cluster.get_active_caches()
                self.update_ring(nodes)
            except Exception as e:
                print("Error updating ring:", e)