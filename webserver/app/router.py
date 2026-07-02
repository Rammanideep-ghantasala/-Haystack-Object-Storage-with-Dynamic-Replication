from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
import requests
import uuid
from typing import Optional
import state

router = APIRouter()

class WriteRequest(BaseModel):
    value: str


def cache_get(key: str) -> Optional[str]:
    node = state.hash_ring.get_node_for_key(key)
    if not node:
        return None

    try:
        r = requests.get(f"http://{node['address']}/get/{key}", timeout=1)
        data = r.json()
        if data.get("hit"):
            return data.get("value")
    except:
        pass

    return None


def cache_set(key: str, value: str, ttl: int | None = None):
    node = state.hash_ring.get_node_for_key(key)
    if not node:
        return

    payload = {"value": value}
    if ttl is not None:
        payload["ttl"] = ttl

    try:
        requests.post(
            f"http://{node['address']}/set/{key}",
            json=payload,
            timeout=1
        )
    except:
        pass


def cache_invalidate(key: str):
    node = state.hash_ring.get_node_for_key(key)
    if not node:
        return

    try:
        requests.post(
            f"http://{node['address']}/invalidate/{key}",
            timeout=1
        )
    except:
        pass

async def notify_replication_manager(key: str):
    try:
        import httpx
        async with httpx.AsyncClient(timeout=0.5) as client:
            await client.post(f"{state.REPLICATION_MANAGER_URL}/access/{key}")
    except:
        pass


@router.get("/object/{key}")
def read_object(key: str, background_tasks: BackgroundTasks):

    cached = cache_get(key)
    if cached is not None:
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

                background_tasks.add_task(notify_replication_manager, key)

                return {"value": data["value"], "cached": False}

        except:
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

    replica_ids = [n["id"] for n in replicas]

    ok = state.directory_client.set_placement(key, replica_ids)
    if not ok:
        raise HTTPException(500, "Failed to register placement")

    success = False
    payload = {"value": value, "version": None}

    for replica in replicas:
        try:
            r = requests.post(
                f"http://{replica['address']}/object/{key}",
                json=payload,
                timeout=2
            )
            if r.status_code == 200:
                success = True
        except:
            continue

    if not success:
        raise HTTPException(500, "All replicas unavailable")

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
        except:
            continue

    if not deleted_any:
        raise HTTPException(500, "Failed to delete from replicas")

    state.directory_client.delete_placement(key)

    cache_invalidate(key)

    return {"status": "deleted", "key": key}
