from fastapi import APIRouter, HTTPException, Body
from typing import Dict
import state

router = APIRouter()

@router.get("/object/{key}")
def get_object(key: str):
    rec = state.store_engine.read(key)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")

    return {
        "value": rec["data"],
        "version": 1
    }


@router.post("/object/{key}")
def put_object(key: str, payload: Dict = Body(...)):
    try:
        value = payload["value"]
        version = payload.get("version", None)

        write_payload = {
            "photo_id": key,
            "photo_data": value,
            "volume_id": "V1"
        }

        state.store_engine.write(write_payload)

        return {"status": "ok", "version": 1}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/object/{key}")
def delete_object(key: str):
    rec = state.store_engine.read(key)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")

    state.store_engine.mark_deleted(key)

    return {"status": "deleted", "key": key}

@router.post("/replicate")
def replicate(payload: Dict[str, dict]):
    accepted = []
    for key, rec in payload.items():
        try:
            write_payload = {
                "photo_id": key,
                "photo_data": rec["value"],
                "volume_id": "V1"
            }
            state.store_engine.write(write_payload)
            accepted.append(key)
        except:
            pass

    return {"accepted": accepted}

@router.get("/list_keys")
def list_keys():
    keys = list(state.store_engine.index.keys())
    return {"keys": keys}

@router.post("/join")
def join(node_id: str = None, address: str = None):
    return {"status": "ok"}


@router.post("/heartbeat")
def heartbeat(node_id: str = None):
    return {"status": "alive"}