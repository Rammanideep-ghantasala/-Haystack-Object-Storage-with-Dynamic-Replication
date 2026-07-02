import requests
import random

class DirectoryClient:
    def __init__(self, nodes):
        self.nodes = nodes

    def _try_all(self, fn):
        nodes = list(self.nodes)
        random.shuffle(nodes)

        for node in nodes:
            try:
                ok, data = fn(node)
                if ok:
                    return data
            except Exception as e:
                print("[directory_client] Error contacting", node, e)

        return None

    def get_replica_nodes(self, key: str):
        def fn(node):
            r = requests.get(f"http://{node}/placements/{key}", timeout=2)
            if r.status_code == 200:
                return True, r.json().get("replicas", [])
            return False, None

        replica_ids = self._try_all(fn) or []
        if not replica_ids:
            return []

        def fn2(node):
            r = requests.get(f"http://{node}/nodes", timeout=2)
            if r.status_code == 200:
                return True, r.json().get("nodes", {})
            return False, None

        nodes_dict = self._try_all(fn2) or {}

        resolved = []
        for rid in replica_ids:
            if rid in nodes_dict and "address" in nodes_dict[rid]:
                resolved.append(nodes_dict[rid]["address"])
            else:
                print(f"[directory_client] WARNING: Missing node metadata for {rid}")

        return resolved

    def get_active_stores(self):
        def fn(node):
            r = requests.get(f"http://{node}/nodes", timeout=2)
            if r.status_code == 200:
                return True, r.json().get("nodes", {})
            return False, None

        nodes_dict = self._try_all(fn) or {}

        stores = []
        for nid, meta in nodes_dict.items():
            if nid.startswith("store") and "address" in meta:
                stores.append({"id": nid, "address": meta["address"]})

        return stores

    def get_active_caches(self):
        def fn(node):
            r = requests.get(f"http://{node}/nodes", timeout=2)
            if r.status_code == 200:
                return True, r.json().get("nodes", {})
            return False, None

        nodes_dict = self._try_all(fn) or {}

        caches = []
        for nid, meta in nodes_dict.items():
            if nid.startswith("cache") and "address" in meta:
                caches.append(meta["address"])

        return caches

    def set_placement(self, object_key: str, replicas: list):
        def fn(node):
            r = requests.get(f"http://{node}/nodes", timeout=2)
            if r.status_code == 200:
                return True, r.json().get("nodes", {})
            return False, None

        nodes_dict = self._try_all(fn) or {}

        addr_to_id = {}
        for nid, meta in nodes_dict.items():
            if "address" in meta:
                addr_to_id[meta["address"]] = nid

        replica_ids = []
        for r in replicas:
            if r in nodes_dict:
                replica_ids.append(r)
            elif r in addr_to_id:
                replica_ids.append(addr_to_id[r])
            else:
                print(f"[directory_client] WARNING: unknown replica {r}")

        def fn_write(node):
            r = requests.post(
                f"http://{node}/placements/{object_key}",
                json={"replicas": replica_ids},
                timeout=2
            )
            return (r.status_code == 200), True

        return self._try_all(fn_write) is not None

    def delete_placement(self, object_key: str):
        def fn(node):
            r = requests.delete(f"http://{node}/placements/{object_key}", timeout=2)
            return (r.status_code in (200, 204)), True

        return self._try_all(fn) is not None