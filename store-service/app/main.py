import os
import threading
from fastapi import FastAPI
from router import router
from cluster import StoreNode
import state
from engine import StoreEngine

app = FastAPI(title="Store Node")

PORT = int(os.getenv("PORT", "7101"))
NODE_NAME = os.getenv("NODE_NAME", "store-unknown")
SELF_ADDR = f"{NODE_NAME}:{PORT}"
DIRECTORY = os.getenv("DIRECTORY_SERVICE", "").split(",")
DATA_PATH = os.getenv("DATA_PATH", "/data")
HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", "2"))

state.store_engine = StoreEngine()
state.store_backend = state.store_engine

state.node = StoreNode(
    NODE_NAME,
    SELF_ADDR,
    DIRECTORY,
    state.store_backend,
    heartbeat_interval=HEARTBEAT_INTERVAL
)

@app.on_event("startup")
def startup_event():
    threading.Thread(target=state.node.register_and_ensure, daemon=True).start()
    threading.Thread(target=state.node.heartbeat_loop, daemon=True).start()

app.include_router(router)