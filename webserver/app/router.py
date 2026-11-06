from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
import requests
import uuid
from typing import Optional
import logging
import state

router = APIRouter()
logger = logging.getLogger("webserver.router")

class WriteRequest(BaseModel):
    value: str


def cache_get(key: str) -> Optional[str]:
    node = state.hash_ring.get_node_for_key(key)
    if not node:
        return None

    try:
        r = requests.get(f"http://{node['address']}/get/{key}", timeout=1)
        if r.status_code != 200:
            logger.warning(
                "Cache get for key=%s returned status=%s from node=%s",
                key,
                r.status_code,
                node["address"],
            )
            return None
        data = r.json()
        if data.get("hit"):
            return data.get("value")
    except Exception:
        logger.exception("Cache get failed for key=%s node=%s", key, node["address"])

    return None


def cache_set(key: str, value: str, ttl: int | None = None):
    node = state.hash_ring.get_node_for_key(key)
    if not node:
        return

    payload = {"value": value}
    if ttl is not None:
        payload["ttl"] = ttl

    try:
        r = requests.post(
            f"http://{node['address']}/set/{key}",
            json=payload,
            timeout=1
        )
        if r.status_code not in (200, 201):
            logger.warning(
                "Cache set for key=%s returned status=%s from node=%s",
                key,
                r.status_code,
                node["address"],
            )
    except Exception:
        logger.exception("Cache set failed for key=%s node=%s", key, node["address"])


def cache_invalidate(key: str):
    node = state.hash_ring.get_node_for_key(key)
    if not node:
        return

    try:
        r = requests.post(
            f"http://{node['address']}/invalidate/{key}",
            timeout=1
        )
        if r.status_code not in (200, 204):
            logger.warning(
                "Cache invalidate for key=%s returned status=%s from node=%s",
                key,
                r.status_code,
                node["address"],
            )
    except Exception:
        logger.exception("Cache invalidate failed for key=%s node=%s", key, node["address"])

async def notify_replication_manager(key: str):
    try:
        import httpx
        async with httpx.AsyncClient(timeout=0.5) as client:
            response = await client.post(f"{state.REPLICATION_MANAGER_URL}/access/{key}")
            if response.status_code not in (200, 202):
                logger.warning(
                    "Replication manager access notification for key=%s returned status=%s",
                    key,
                    response.status_code,
                )
    except Exception:
        logger.exception("Replication manager access notification failed for key=%s", key)


@router.get("/object/{key}")
def read_object(key: str, background_tasks: BackgroundTasks):

    cached = cache_get(key)
    if cached is not None:
        background_tasks.add_task(notify_replication_manager, key)
        return {"value": cached, "cached": True}

    replica_addresses = state.directory_client.get_replica_nodes(key)
    if not replica_addresses:
        raise HTTPException(404, "No replicas available")

    import random
    random.shuffle(replica_addresses)

    for address in replica_addresses:
        try:
            r = requests.get(f"http://{address}/object/{key}", timeout=2)

            if r.status_code == 200:
                data = r.json()

                cache_set(key, data["value"])

                background_tasks.add_task(notify_replication_manager, key)

                return {"value": data["value"], "cached": False}

        except Exception:
            logger.exception("Store read failed for key=%s address=%s", key, address)
            continue

    raise HTTPException(404, "Key not found on replicas")

@router.post("/object")
def write_object(req: WriteRequest):

    value = req.value.strip()
    if not value:
        raise HTTPException(400, "Value cannot be empty")

    key = uuid.uuid4().hex

    nodes = state.directory_client.get_active_stores()
    if not nodes:
        raise HTTPException(500, "No store nodes available")

    import random
    REPLICA_COUNT = 2

    if len(nodes) < REPLICA_COUNT:
        raise HTTPException(500, "Not enough store nodes available")

    replicas = random.sample(nodes, REPLICA_COUNT)

    payload = {"value": value, "version": None}
    successful_replicas = []

    for replica in replicas:
        try:
            r = requests.post(
                f"http://{replica['address']}/object/{key}",
                json=payload,
                timeout=2
            )
            if r.status_code == 200:
                successful_replicas.append(replica)
            else:
                logger.warning(
                    "Store write failed for key=%s replica=%s status=%s body=%s",
                    key,
                    replica["id"],
                    r.status_code,
                    r.text,
                )
        except Exception:
            logger.exception(
                "Store write request failed for key=%s replica=%s address=%s",
                key,
                replica["id"],
                replica["address"],
            )

    if len(successful_replicas) < REPLICA_COUNT:
        rollback_failures = []
        for replica in successful_replicas:
            try:
                r = requests.delete(f"http://{replica['address']}/object/{key}", timeout=2)
                if r.status_code not in (200, 204, 404):
                    rollback_failures.append(replica["id"])
                    logger.warning(
                        "Rollback delete returned status=%s for key=%s replica=%s",
                        r.status_code,
                        key,
                        replica["id"],
                    )
            except Exception:
                rollback_failures.append(replica["id"])
                logger.exception(
                    "Rollback delete failed for key=%s replica=%s address=%s",
                    key,
                    replica["id"],
                    replica["address"],
                )

        detail = (
            f"Replication failed: wrote {len(successful_replicas)} of "
            f"{REPLICA_COUNT} required replicas"
        )
        if rollback_failures:
            detail += f"; rollback failed on replicas: {rollback_failures}"
        raise HTTPException(500, detail)

    replica_ids = [n["id"] for n in successful_replicas]
    ok = state.directory_client.set_placement(key, replica_ids)
    if not ok:
        rollback_failures = []
        for replica in successful_replicas:
            try:
                r = requests.delete(f"http://{replica['address']}/object/{key}", timeout=2)
                if r.status_code not in (200, 204, 404):
                    rollback_failures.append(replica["id"])
            except Exception:
                rollback_failures.append(replica["id"])
                logger.exception(
                    "Rollback after placement failure failed for key=%s replica=%s",
                    key,
                    replica["id"],
                )
        detail = "Replication writes succeeded, but placement registration failed"
        if rollback_failures:
            detail += f"; rollback failed on replicas: {rollback_failures}"
        raise HTTPException(500, detail)

    cache_set(key, value)

    return {"status": "ok", "key": key, "replicas": replica_ids}


@router.delete("/object/{key}")
def delete_object(key: str):

    replica_addresses = state.directory_client.get_replica_nodes(key)
    if not replica_addresses:
        raise HTTPException(404, "No replicas found for key")

    deleted_any = False
    for addr in replica_addresses:
        try:
            r = requests.delete(f"http://{addr}/object/{key}", timeout=2)
            if r.status_code in (200, 204):
                deleted_any = True
        except Exception:
            logger.exception("Store delete failed for key=%s address=%s", key, addr)
            continue

    if not deleted_any:
        raise HTTPException(500, "Failed to delete from replicas")

    state.directory_client.delete_placement(key)

    cache_invalidate(key)

    return {"status": "deleted", "key": key}
