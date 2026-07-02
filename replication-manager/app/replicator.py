import time
import requests
import os
import redis
from collections import defaultdict
from threading import Lock

DIRECTORY = os.getenv("DIRECTORY_SERVICE", "directory1:7001")

SCAN_INTERVAL = 5
STORE_TIMEOUT = 3
ALPHA = 0.3

MIN_REPLICAS = 2
MAX_REPLICAS = 3

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    decode_responses=True
)


class ReplicaManager:
    def __init__(self):
        self.access_counts = defaultdict(int)
        self.access_rate = defaultdict(float)
        self.lock = Lock()

    def record_access(self, key: str):
        with self.lock:
            self.access_counts[key] += 1

    def update_access_rates(self):

        with self.lock:
            all_keys = set(self.access_counts.keys()) | set(self.access_rate.keys())

            for key in all_keys:
                count = self.access_counts.get(key, 0)
                prev = self.access_rate.get(key, 0.0)

                new_rate = ALPHA * count + (1 - ALPHA) * prev
                self.access_rate[key] = new_rate

                target = self.desired_replica_count(new_rate)

                in_hot = redis_client.sismember("hot_keys", key)

                if target > MIN_REPLICAS:
                    if not in_hot:
                        redis_client.sadd("hot_keys", key)
                            
            self.access_counts = defaultdict(int)

    def desired_replica_count(self, rate: float):
        return 3 if rate >= 3 else 2

    def _try_all(self, fn):
        hosts = DIRECTORY.split(",")
        for h in hosts:
            try:
                ok, data = fn(h)
                if ok:
                    return data
            except Exception:
                continue
        return None

    def get_store_nodes(self):

        def fn(node):
            try:
                r = requests.get(f"http://{node}/nodes", timeout=2)
                if r.status_code == 200:
                    return True, r.json().get("nodes", {})
                return False, None
            except Exception:
                return False, None

        node_dict = self._try_all(fn) or {}

        stores = []
        for node_id, meta in node_dict.items():
            addr = meta.get("address")
            if node_id.startswith("store") and addr:
                stores.append({"id": node_id, "address": addr})

        return stores

    def get_current_replicas(self, key):

        def fn_fetch(h):
            try:
                r = requests.get(f"http://{h}/placements/{key}", timeout=2)
                if r.status_code == 200:
                    return True, r.json().get("replicas", [])
                return False, None
            except Exception:
                return False, None

        replica_ids = self._try_all(fn_fetch) or []

        if not replica_ids:
            return []

        stores = self.get_store_nodes()
        id_to_node = {n["id"]: n for n in stores}

        resolved = []
        for rid in replica_ids:
            if rid in id_to_node:
                resolved.append(id_to_node[rid])

        if not resolved:
            return []

        return resolved

    def _update_directory_placement(self, key, replica_ids):
        payload = {"replicas": list(replica_ids)}

        hosts = DIRECTORY.split(",")
        for h in hosts:
            try:
                r = requests.post(f"http://{h}/placements/{key}", json=payload, timeout=2)
                if r.status_code in (200, 201):
                    return True
            except Exception:
                continue

        return False
    
    def fetch_object(self, node, key):

        r = requests.get(f"http://{node['address']}/object/{key}", timeout=STORE_TIMEOUT)
        if r.status_code == 200:
            return r.json().get("value")
        
        return None

    def push_object(self, node, key, value):
        try:
            r = requests.post(
                f"http://{node['address']}/object/{key}",
                json={"value": value, "version": 0},
                timeout=STORE_TIMEOUT
            )
            return r.status_code in (200, 201)
        except Exception:
            return False

    def delete_object(self, node, key):
        try:
            r = requests.delete(f"http://{node['address']}/object/{key}", timeout=STORE_TIMEOUT)
            return r.status_code in (200, 204)
        except Exception:
            return False

    def adjust_replicas(self, key):
        rate = self.access_rate.get(key, 0.0)
        target = self.desired_replica_count(rate)


        current_nodes = self.get_current_replicas(key)
        if not current_nodes:
            return

        all_nodes = self.get_store_nodes()
        current_ids = set(n["id"] for n in current_nodes)

        source_node = current_nodes[0]
        data_value = self.fetch_object(source_node, key)
        if data_value is None:
            return

        if len(current_nodes) < target:
            needed = target - len(current_nodes)

            candidates = [n for n in all_nodes if n["id"] not in current_ids]
            added = []

            for node in candidates[:needed]:
                if self.push_object(node, key, data_value):
                    current_ids.add(node["id"])
                    added.append(node["id"])

            if added:
                self._update_directory_placement(key, current_ids)

        elif len(current_nodes) > target:
            excess = len(current_nodes) - target

            to_delete = current_nodes[-excess:]
            removed = []

            for node in to_delete:
                if self.delete_object(node, key):
                    current_ids.discard(node["id"])
                    removed.append(node["id"])

            if removed:
                self._update_directory_placement(key, current_ids)

                redis_client.srem("hot_keys", key)

    def monitor_loop(self):

        while True:
            time.sleep(SCAN_INTERVAL)
            self.update_access_rates()

            try:
                hot_keys = redis_client.smembers("hot_keys")
            except Exception:
                hot_keys = set()

            for key in hot_keys:
                self.adjust_replicas(key)

replica_manager = ReplicaManager()