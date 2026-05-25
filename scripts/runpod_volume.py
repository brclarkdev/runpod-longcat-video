#!/usr/bin/env python3
"""RunPod Network Volume helper.

Uses UNPOD_API_KEY as requested by the user, with RUNPOD_API_KEY fallback.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

BASE_URL = "https://rest.runpod.io/v1"


def api_key() -> str:
    key = os.environ.get("UNPOD_API_KEY") or os.environ.get("RUNPOD_API_KEY")
    if not key:
        raise SystemExit("ERROR: set UNPOD_API_KEY (or RUNPOD_API_KEY) in the environment.")
    return key


def request(method: str, path: str, body=None):
    data = None
    headers = {"Authorization": f"Bearer {api_key()}", "Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE_URL + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", "replace")
        raise SystemExit(f"RunPod API error {e.code}: {msg}")


def list_volumes():
    return request("GET", "/networkvolumes")


def create_volume(name: str, size: int, datacenter: str):
    return request("POST", "/networkvolumes", {"name": name, "size": size, "dataCenterId": datacenter})


def print_json(obj):
    print(json.dumps(obj, indent=2, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage RunPod network volume for LongCat.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    ensure = sub.add_parser("ensure")
    ensure.add_argument("--name", default="longcat-video-primary")
    ensure.add_argument("--size", type=int, default=250)
    ensure.add_argument("--datacenter", default=os.environ.get("RUNPOD_DATACENTER_ID", "US-KS-2"))
    create = sub.add_parser("create")
    create.add_argument("--name", default="longcat-video-primary")
    create.add_argument("--size", type=int, default=250)
    create.add_argument("--datacenter", default=os.environ.get("RUNPOD_DATACENTER_ID", "US-KS-2"))
    args = parser.parse_args()

    if args.cmd == "list":
        print_json(list_volumes())
        return 0

    if args.cmd == "create":
        print_json(create_volume(args.name, args.size, args.datacenter))
        return 0

    if args.cmd == "ensure":
        vols = list_volumes()
        matches = [v for v in vols if v.get("name") == args.name]
        if matches:
            print("Existing volume found; not creating a duplicate.")
            print_json(matches[0])
            return 0
        print(f"Creating RunPod network volume {args.name!r} size={args.size}GB datacenter={args.datacenter}...", file=sys.stderr)
        print_json(create_volume(args.name, args.size, args.datacenter))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
