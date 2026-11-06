import time
import requests
import os
import logging

HEARTBEAT_INTERVAL = 2
DIRECTORY_TIMEOUT  = 4
logger = logging.getLogger("cache-service.cluster")

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
            logger.info("Cache %s registered with directory %s", self.self_id, self.directory)

        except Exception:
            logger.exception("Cache %s failed to register with directory %s", self.self_id, self.directory)

    def heartbeat_thread(self):
        url = f"http://{self.directory}/heartbeat"

        while True:
            try:
                requests.post(
                    url,
                    params={"node_id": self.self_id},
                    timeout=2
                )
            except Exception:
                logger.exception("Cache %s heartbeat failed against directory %s", self.self_id, self.directory)
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
            logger.exception("Cache %s failed to fetch active cache nodes", self.self_id)
            return []
