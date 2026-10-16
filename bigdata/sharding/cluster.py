"""Set up a MongoDB sharded cluster: 1 config server replica set, 3 shard replica sets, 1 mongos router.

The processes are started by docker-compose.bigdata.yml (or bigdata/sharding/local_cluster.sh without
Docker); this script only sends the admin commands that turn them into a cluster:

    replSetInitiate on the config server and on each shard  ->  addShard on mongos

    python -m bigdata.sharding.cluster init        # idempotent; safe to run again
    python -m bigdata.sharding.cluster status

Hosts come from environment variables so the same code works inside Docker (service names) and natively
(localhost ports). Defaults match docker-compose.bigdata.yml as seen from the host.
"""

from __future__ import annotations

import argparse
import os
import time

from pymongo import MongoClient
from pymongo.errors import OperationFailure, ServerSelectionTimeoutError

# "<name>=<host:port as reachable from here>|<host:port as the cluster members see each other>"
DEFAULT_MEMBERS = {
    "cfgrs": os.environ.get("CFG_HOST", "localhost:27040|cfg:27019"),
    "shard1rs": os.environ.get("SHARD1_HOST", "localhost:27041|shard1:27018"),
    "shard2rs": os.environ.get("SHARD2_HOST", "localhost:27042|shard2:27018"),
    "shard3rs": os.environ.get("SHARD3_HOST", "localhost:27043|shard3:27018"),
}
MONGOS_URI = os.environ.get("MONGOS_URI", "mongodb://localhost:27030")
SINGLE_URI = os.environ.get("SINGLE_URI", "mongodb://localhost:27031")


def _split(spec: str) -> tuple[str, str]:
    outside, _, inside = spec.partition("|")
    return outside, inside or outside


def _client(host: str, **kw) -> MongoClient:
    return MongoClient(f"mongodb://{host}/?directConnection=true", serverSelectionTimeoutMS=20000, **kw)


def wait_for(host: str, timeout: int = 120) -> None:
    deadline = time.time() + timeout
    while True:
        try:
            _client(host).admin.command("ping")
            return
        except ServerSelectionTimeoutError:
            if time.time() > deadline:
                raise
            time.sleep(1)


def initiate(name: str, spec: str, configsvr: bool) -> None:
    outside, inside = _split(spec)
    wait_for(outside)
    c = _client(outside)
    try:
        c.admin.command("replSetGetStatus")
        print(f"  {name}: already initiated")
    except OperationFailure:
        cfg = {"_id": name, "members": [{"_id": 0, "host": inside}]}
        if configsvr:
            cfg["configsvr"] = True
        c.admin.command("replSetInitiate", cfg)
        print(f"  {name}: initiated ({inside})")
    for _ in range(120):  # wait until this single member is elected primary
        if c.admin.command("hello").get("isWritablePrimary"):
            return
        time.sleep(1)
    raise RuntimeError(f"{name} never became primary")


def init(members: dict | None = None, mongos_uri: str = MONGOS_URI) -> None:
    members = members or DEFAULT_MEMBERS
    for name, spec in members.items():
        initiate(name, spec, configsvr=name.startswith("cfg"))
    mongos = MongoClient(mongos_uri, serverSelectionTimeoutMS=60000)
    for _ in range(120):
        try:
            mongos.admin.command("ping")
            break
        except ServerSelectionTimeoutError:
            time.sleep(1)
    existing = {s["_id"] for s in mongos.admin.command("listShards")["shards"]}
    for name, spec in members.items():
        if name.startswith("cfg") or name in existing:
            continue
        mongos.admin.command("addShard", f"{name}/{_split(spec)[1]}", name=name)
        print(f"  addShard {name}")
    print(status(mongos_uri))


def status(mongos_uri: str = MONGOS_URI) -> str:
    m = MongoClient(mongos_uri, serverSelectionTimeoutMS=20000)
    shards = m.admin.command("listShards")["shards"]
    lines = [f"mongos {mongos_uri}: {len(shards)} shards"]
    lines += [f"  {s['_id']}: {s['host']} (state {s.get('state')})" for s in shards]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=["init", "status"])
    args = ap.parse_args()
    if args.command == "init":
        init()
    else:
        print(status())


if __name__ == "__main__":
    main()
