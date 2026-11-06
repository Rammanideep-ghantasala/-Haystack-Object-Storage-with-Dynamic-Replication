import time
import requests
import os
import logging
from redis.cluster import RedisCluster, ClusterNode
from collections import defaultdict
from threading import Lock

DIRECTORY = os.getenv("DIRECTORY_SERVICE", "directory1:7001")

SCAN_INTERVAL = 5
STORE_TIMEOUT = 3
ALPHA = 0.3

MIN_REPLICAS = 2
MAX_REPLICAS = 3

logger = logging.getLogger("replication-manager.replicator")

REDIS_NODES = os.getenv(
    "REDIS_NODES",
    "redis1:6379,redis2:6379,redis3:6379,redis4:6379,redis5:6379,redis6:6379"
).split(",")


def _startup_nodes():
    nodes = []
    for node in REDIS_NODES:
        host, port = node.strip().split(":")
        nodes.append(ClusterNode(host, int(port)))
    return nodes


redis_client = RedisCluster(
    startup_nodes=_startup_nodes(),
    decode_responses=True,
    read_from_replicas=True,
    skip_full_coverage_check=True,
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
                logger.exception("Directory request failed against %s", h)
        return None

    def get_store_nodes(self):

        def fn(node):
            r = requests.get(f"http://{node}/nodes", timeout=2)
            if r.status_code == 200:
                return True, r.json().get("nodes", {})
            logger.warning("Directory %s returned %s for /nodes", node, r.status_code)
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
            r = requests.get(f"http://{h}/placements/{key}", timeout=2)
            if r.status_code == 200:
                return True, r.json().get("replicas", [])
            logger.warning(
                "Directory %s returned %s for placement key=%s",
                h,
                r.status_code,
                key,
            )
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
                logger.warning(
                    "Directory %s returned %s while updating placement for key=%s",
                    h,
                    r.status_code,
                    key,
                )
            except Exception:
                logger.exception("Placement update failed against directory=%s key=%s", h, key)

        return False
    
    def fetch_object(self, node, key):
        try:
            r = requests.get(f"http://{node['address']}/object/{key}", timeout=STORE_TIMEOUT)
            if r.status_code == 200:
                return r.json().get("value")
            logger.warning(
                "Store %s returned %s while fetching key=%s",
                node["address"],
                r.status_code,
                key,
            )
        except Exception:
            logger.exception("Failed to fetch key=%s from store=%s", key, node["address"])
        
        return None

    def push_object(self, node, key, value):
        try:
            r = requests.post(
                f"http://{node['address']}/object/{key}",
                json={"value": value, "version": 0},
                timeout=STORE_TIMEOUT
            )
            if r.status_code in (200, 201):
                return True
            logger.warning(
                "Store %s returned %s while pushing key=%s",
                node["address"],
                r.status_code,
                key,
            )
        except Exception:
            logger.exception("Failed to push key=%s to store=%s", key, node["address"])
        return False

    def delete_object(self, node, key):
        try:
            r = requests.delete(f"http://{node['address']}/object/{key}", timeout=STORE_TIMEOUT)
            if r.status_code in (200, 204):
                return True
            logger.warning(
                "Store %s returned %s while deleting key=%s",
                node["address"],
                r.status_code,
                key,
            )
        except Exception:
            logger.exception("Failed to delete key=%s from store=%s", key, node["address"])
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

                try:
                    redis_client.srem("hot_keys", key)
                except Exception:
                    logger.exception("Failed to remove cooled key=%s from hot_keys", key)

    def monitor_loop(self):

        while True:
            time.sleep(SCAN_INTERVAL)
            try:
                self.update_access_rates()
            except Exception:
                logger.exception("Failed to update access rates")
                continue

            try:
                hot_keys = redis_client.smembers("hot_keys")
            except Exception:
                logger.exception("Failed to read hot_keys from Redis Cluster")
                hot_keys = set()

            for key in hot_keys:
                self.adjust_replicas(key)

replica_manager = ReplicaManager()
