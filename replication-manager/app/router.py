from fastapi import APIRouter
import state

router = APIRouter()

@router.post("/access/{key}")
def record_access(key: str):
    state.replica_manager.record_access(key)
    return {"ok": True}

@router.get("/status")
def status():
    return {
        "rates": state.replica_manager.access_rate,
    }
