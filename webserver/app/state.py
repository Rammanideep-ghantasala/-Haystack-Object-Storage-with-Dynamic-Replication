import os

REPLICATION_MANAGER_URL = os.getenv("REPLICATION_MANAGER_URL", "http://replication_manager:7300")

directory_client = None
cluster = None
hash_ring = None
