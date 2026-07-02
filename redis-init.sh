#!/bin/bash
set -e

echo "[init] Creating Redis cluster..."
sleep 2

yes yes | redis-cli --cluster create \
  redis1:6379 \
  redis2:6379 \
  redis3:6379 \
  redis4:6379 \
  redis5:6379 \
  redis6:6379 \
  --cluster-replicas 1

echo "[init] Waiting for cluster to be ready..."

for i in {1..20}; do
  state=$(redis-cli -h redis1 cluster info | grep cluster_state:ok || true)
  if [[ -n "$state" ]]; then
    echo "[init] Redis Cluster is READY"
    exit 0
  fi
  echo "[init] Cluster not ready yet... retrying"
  sleep 1
done

echo "[init] Cluster FAILED to reach ok state"
exit 1
