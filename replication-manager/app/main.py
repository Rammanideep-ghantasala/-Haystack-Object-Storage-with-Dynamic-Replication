from fastapi import FastAPI
from router import router
import threading
import state

app = FastAPI(title="Replication Manager")

@app.on_event("startup")
def start_background_tasks():
    threading.Thread(target=state.replica_manager.monitor_loop, daemon=True).start()

app.include_router(router)
