import os
import threading
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from router import router
import state

from cluster import DirectoryClient
from hash_ring import ConsistentHashRing


app = FastAPI(title="Haystack Webserver")

DIRECTORY_CLUSTERS = os.getenv("DIRECTORY_SERVICE", "directory1:7001").split(",")


@app.on_event("startup")
def startup_event():

    print("[webserver] Starting with directory nodes:", DIRECTORY_CLUSTERS)

    state.directory_client = DirectoryClient(DIRECTORY_CLUSTERS)

    state.hash_ring = ConsistentHashRing()

    threading.Thread(
        target=state.hash_ring.monitor_cluster,
        args=(state.directory_client,),
        daemon=True
    ).start()

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def serve_index():
    return FileResponse("static/index.html")

app.include_router(router)