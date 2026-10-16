#!/usr/bin/env bash
# Start the same sharded cluster as docker-compose.bigdata.yml with plain mongod/mongos binaries
# (Linux / macOS, no Docker). Data goes to data/cluster/. Stop with:  bigdata/sharding/local_cluster.sh stop
#
# Ports: config 27040, shards 27041-27043, mongos 27030, standalone baseline 27031.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DIR="$ROOT/data/cluster"
BIN="${MONGO_BIN:-}"
mongod="${BIN:+$BIN/}mongod"; mongos="${BIN:+$BIN/}mongos"
CACHE="${WT_CACHE_GB:-1}"

if [[ "${1:-start}" == "stop" ]]; then
  pkill -f "$DIR" || true; echo "stopped"; exit 0
fi

mkdir -p "$DIR"/{cfg,shard1,shard2,shard3,single,logs}
"$mongod" --configsvr --replSet cfgrs --port 27040 --bind_ip 127.0.0.1 --dbpath "$DIR/cfg" \
  --wiredTigerCacheSizeGB "$CACHE" --fork --logpath "$DIR/logs/cfg.log"
for i in 1 2 3; do
  "$mongod" --shardsvr --replSet "shard${i}rs" --port "2704$i" --bind_ip 127.0.0.1 --dbpath "$DIR/shard$i" \
    --wiredTigerCacheSizeGB "$CACHE" --fork --logpath "$DIR/logs/shard$i.log"
done
"$mongod" --port 27031 --bind_ip 127.0.0.1 --dbpath "$DIR/single" --wiredTigerCacheSizeGB "$CACHE" \
  --fork --logpath "$DIR/logs/single.log"

export CFG_HOST="localhost:27040" SHARD1_HOST="localhost:27041" SHARD2_HOST="localhost:27042" SHARD3_HOST="localhost:27043"
cd "$ROOT"
python -c "from bigdata.sharding.cluster import DEFAULT_MEMBERS, initiate
for n, s in DEFAULT_MEMBERS.items(): initiate(n, s, n.startswith('cfg'))"
"$mongos" --configdb cfgrs/localhost:27040 --port 27030 --bind_ip 127.0.0.1 --fork --logpath "$DIR/logs/mongos.log"
python -m bigdata.sharding.cluster init
