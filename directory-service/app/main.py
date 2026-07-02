from fastapi import FastAPI
from router import router
import state

app = FastAPI(title="Directory Service")

@app.on_event("startup")
def startup_event():
    print("[directory] Booted — using Redis for membership + placement")

app.include_router(router)
