import time
import requests
import os

HEARTBEAT_INTERVAL = 2
DIRECTORY_TIMEOUT  = 4

class CacheNodeMembership:
    def __init__(self, self_id, self_address, directory_service):

        if "," in directory_service:
            directory_service = directory_service.split(",")[0]

        self.self_id = self_id
        self.self_address = self_address
        self.directory = directory_service

    def register_with_directory(self):
        url = f"http://{self.directory}/join"

        try:
            requests.post(
                url,
                params={"node_id": self.self_id, "address": self.self_address},
                timeout=3
            )
            print(f"[Cache {self.self_id}] Registered with {self.directory}")

        except Exception as e:
            print(f"[Cache {self.self_id}] Failed to register with directory: {e}")

    def heartbeat_thread(self):
        url = f"http://{self.directory}/heartbeat"

        while True:
            try:
                requests.post(
                    url,
                    params={"node_id": self.self_id},
                    timeout=2
                )
            except:
                pass
            time.sleep(HEARTBEAT_INTERVAL)

    def active_nodes(self):
        try:
            resp = requests.get(
                f"http://{self.directory}/nodes",
                timeout=2
            )
            data = resp.json()

            nodes_dict = data.get("nodes", {})

            cache_nodes = [
                meta["address"]
                for nid, meta in nodes_dict.items()
                if nid.startswith("cache") and "address" in meta
            ]

            return cache_nodes

        except Exception:
            return []