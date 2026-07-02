from fastapi import FastAPI
from router import router
import threading
import os

from cluster import CacheNodeMembership
from hash_ring import ConsistentHashRing
import state

app = FastAPI(title="Distributed Cache Node")

DIRECTORY = os.getenv("DIRECTORY_SERVICE")
SELF_ID   = os.getenv("CACHE_NODE_ID")
SELF_ADDR = os.getenv("SELF_ADDRESS")

if DIRECTORY and "," in DIRECTORY:
    DIRECTORY = DIRECTORY.split(",")[0]

state.cluster = CacheNodeMembership(SELF_ID, SELF_ADDR, DIRECTORY)
state.hash_ring = ConsistentHashRing(replication_factor=1)

@app.on_event("startup")
def startup_event():

    threading.Thread(
        target=state.cluster.register_with_directory,
        daemon=True
    ).start()

    threading.Thread(
        target=state.cluster.heartbeat_thread,
        daemon=True
    ).start()

    threading.Thread(
        target=state.hash_ring.monitor_cluster,
        args=(state.cluster,),
        daemon=True
    ).start()

app.include_router(router)