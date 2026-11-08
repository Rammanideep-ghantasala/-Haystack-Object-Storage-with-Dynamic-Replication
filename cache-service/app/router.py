from fastapi import APIRouter, HTTPException, Body
import state
import os
import logging
from redis.cluster import RedisCluster, ClusterNode

router = APIRouter()

logger = logging.getLogger("cache-service.router")

REDIS_NODES = os.getenv(
    "REDIS_NODES",
    "redis1:6379,redis2:6379,redis3:6379,redis4:6379,redis5:6379,redis6:6379"
).split(",")


def _startup_nodes():
    nodes = []
    for node in REDIS_NODES:
        host, port = node.strip().split(":")
        nodes.append(ClusterNode(host, int(port)))
    return nodes


_redis_client = None


def get_redis_client():
    global _redis_client
    if _redis_client is None:
        _redis_client = RedisCluster(
            startup_nodes=_startup_nodes(),
            decode_responses=True,
            read_from_replicas=True,
            skip_full_coverage_check=True,
        )
    return _redis_client

@router.get("/get/{key}")
def get_value(key: str):
    try:
        data = get_redis_client().get(key)
        if data is None:
            return {"hit": False}

        return {"hit": True, "value": data}
    except Exception as exc:
        logger.exception("Redis Cluster cache get failed for key=%s", key)
        raise HTTPException(503, f"Cache read failed: {exc}") from exc

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

    try:
        if ttl:
            get_redis_client().set(key, value, ex=ttl)
        else:
            get_redis_client().set(key, value)
    except Exception as exc:
        logger.exception("Redis Cluster cache set failed for key=%s", key)
        raise HTTPException(503, f"Cache write failed: {exc}") from exc

    return {"stored_at": state.cluster.self_id}

@router.post("/invalidate/{key}")
def invalidate(key: str):
    try:
        get_redis_client().delete(key)
        return {"status": "ok"}
    except Exception as exc:
        logger.exception("Redis Cluster cache invalidate failed for key=%s", key)
        raise HTTPException(503, f"Cache invalidate failed: {exc}") from exc

@router.get("/health")
def health():
    return {
        "status": "ok",
        "node": state.cluster.self_id,
        "address": state.cluster.self_address
    }
