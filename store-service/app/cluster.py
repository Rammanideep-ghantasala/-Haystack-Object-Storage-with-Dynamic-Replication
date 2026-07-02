import time
import requests
import traceback
import random

class StoreNode:
    def __init__(self, node_id: str, address: str, directories, backend, heartbeat_interval=2):
        self.node_id = node_id
        self.address = address

        if isinstance(directories, str):
            self.directories = [directories]
        else:
            self.directories = directories

        self.backend = backend
        self.heartbeat_interval = heartbeat_interval
        self.registered = False

    def pick_directory(self):
        return random.choice(self.directories)

    def register_with_directory(self):
        directory = self.pick_directory()
        url = f"http://{directory}/join"

        try:
            requests.post(
                url,
                params={"node_id": self.node_id, "address": self.address},
                timeout=3
            )
            self.registered = True
            print(f"[store-{self.node_id}] registered with directory {directory}")

        except Exception as e:
            print(f"[store-{self.node_id}] register failed ({directory}): {e}")

    def register_and_ensure(self):
        while not self.registered:
            self.register_with_directory()
            time.sleep(2)

    def heartbeat_loop(self):
        while True:
            directory = self.pick_directory()
            url = f"http://{directory}/heartbeat"

            try:
                requests.post(url, params={"node_id": self.node_id}, timeout=2)
            except Exception as e:
                print(f"[store-{self.node_id}] heartbeat err ({directory}): {e}")

            time.sleep(self.heartbeat_interval)