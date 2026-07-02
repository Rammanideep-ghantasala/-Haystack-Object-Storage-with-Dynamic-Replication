from fastapi import APIRouter, HTTPException
from typing import List
from pydantic import BaseModel
import state  

router = APIRouter()


class PlacementRequest(BaseModel):
    replicas: List[str]

@router.post("/join")
def join_node(node_id: str, address: str):
    state.set_member(
        node_id,
        {
            "id": node_id,
            "address": address,
            "last_heartbeat": state.now(),
        }
    )
    return {"status": "ok", "msg": f"{node_id} registered"}

@router.post("/heartbeat")
def heartbeat(node_id: str):
    member = state.get_member(node_id)
    if not member:
        return {"status": "unknown"}

    state.set_member(
        node_id,
        {
            "id": node_id,
            "address": member["address"],
            "last_heartbeat": state.now(),
        }
    )
    return {"status": "alive"}

@router.get("/nodes")
def list_nodes():
    return {"nodes": state.get_all_members()}


@router.get("/placements/{object_key}")
def get_placement(object_key: str):
    replicas = state.get_placement(object_key)
    if not replicas:
        raise HTTPException(404, "No placement found")

    return {"replicas": replicas}

@router.post("/placements/{object_key}")
def set_placement(object_key: str, req: PlacementRequest):
    if not req.replicas:
        raise HTTPException(400, "Replicas cannot be empty")

    state.set_placement(object_key, req.replicas)
    return {"status": "ok", "key": object_key, "replicas": req.replicas}

@router.delete("/placements/{object_key}")
def delete_placement(object_key: str):
    deleted = state.delete_placement(object_key)
    if not deleted:
        raise HTTPException(404, "Placement does not exist")

    return {"status": "deleted", "key": object_key}