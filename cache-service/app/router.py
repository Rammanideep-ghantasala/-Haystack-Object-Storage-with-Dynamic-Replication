from fastapi import APIRouter, HTTPException, Body
import state
import redis
import os

router = APIRouter()

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=False)

@router.get("/get/{key}")
def get_value(key: str):
    data = r.get(key)
    if data is None:
        return {"hit": False}

    value = data.decode("utf-8")
    return {"hit": True, "value": value}

@router.post("/set/{key}")
def set_value(key: str, body: dict = Body(...)):
    
    if "value" not in body:
        raise HTTPException(400, "Missing 'value' in JSON")

    value = body["value"]
    ttl = body.get("ttl", None)

    responsible = state.hash_ring.get_node_for_key(key)
    if responsible is None:
        raise HTTPException(503, "Hash ring not initialized yet")

    if responsible["id"] != state.cluster.self_id:
        raise HTTPException(403, f"This node is not responsible for key {key}")

    value_bytes = value.encode("utf-8")

    if ttl:
        r.set(key, value_bytes, ex=ttl)
    else:
        r.set(key, value_bytes)

    return {"stored_at": state.cluster.self_id}

@router.post("/invalidate/{key}")
def invalidate(key: str):
    r.delete(key)
    return {"status": "ok"}

@router.get("/health")
def health():
    return {
        "status": "ok",
        "node": state.cluster.self_id,
        "address": state.cluster.self_address
    }