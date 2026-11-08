import os
import time
import json
from redis.cluster import RedisCluster, ClusterNode

REDIS_NODES = os.getenv(
    "REDIS_NODES",
    "redis1:6379,redis2:6379,redis3:6379"
).split(",")

startup_nodes = []
for node in REDIS_NODES:
    host, port = node.split(":")
    startup_nodes.append(ClusterNode(host, int(port)))

_redis_client = None


def get_redis_client():
    global _redis_client
    if _redis_client is None:
        _redis_client = RedisCluster(
            startup_nodes=startup_nodes,
            decode_responses=True,
            read_from_replicas=True,
            skip_full_coverage_check=True
        )
    return _redis_client

MEMBERS_KEY = "directory:members"
PLACEMENTS_KEY = "directory:placements"
HEARTBEAT_TIMEOUT = 10

def now():
    return int(time.time())


def set_member(node_id: str, data: dict):
    get_redis_client().hset(MEMBERS_KEY, node_id, json.dumps(data))


def get_member(node_id: str):
    raw = get_redis_client().hget(MEMBERS_KEY, node_id)
    return json.loads(raw) if raw else None


def get_all_members():
    all_members = get_redis_client().hgetall(MEMBERS_KEY)
    alive = {}
    now_ts = now()

    for node_id, raw in all_members.items():
        data = json.loads(raw)

        if now_ts - data["last_heartbeat"] <= HEARTBEAT_TIMEOUT:
            alive[node_id] = data

    return alive

def set_placement(object_key: str, replicas: list):
    get_redis_client().hset(PLACEMENTS_KEY, object_key, json.dumps(replicas))


def get_placement(object_key: str):
    raw = get_redis_client().hget(PLACEMENTS_KEY, object_key)
    return json.loads(raw) if raw else None


def delete_placement(object_key: str) -> bool:
    removed = get_redis_client().hdel(PLACEMENTS_KEY, object_key)
    return removed == 1
