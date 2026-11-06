#!/usr/bin/env python3
import argparse
import base64
import json
import sys
import time
import urllib.error
import urllib.request


def request_json(method, url, body=None, timeout=5, allow_404=False):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        if allow_404 and exc.code == 404:
            return exc.code, {}
        raw = exc.read().decode("utf-8")
        raise RuntimeError(f"{method} {url} failed with {exc.code}: {raw}") from exc


def placement_count(directory_url, key):
    status, payload = request_json(
        "GET",
        f"{directory_url}/placements/{key}",
        allow_404=True,
    )
    if status == 404:
        return 0, []
    replicas = payload.get("replicas", [])
    return len(replicas), replicas


def main():
    parser = argparse.ArgumentParser(
        description="End-to-end verifier for the Haystack-inspired object store."
    )
    parser.add_argument("--base-url", default="http://localhost")
    parser.add_argument("--directory-url", default="http://localhost:7001")
    parser.add_argument("--hot-read-count", type=int, default=20)
    parser.add_argument("--promotion-timeout", type=int, default=45)
    args = parser.parse_args()

    value = base64.b64encode(b"haystack-e2e-verification-payload").decode("ascii")

    print("[verify] Uploading object")
    _, upload = request_json("POST", f"{args.base_url}/object", {"value": value})
    key = upload["key"]

    try:
        count, replicas = placement_count(args.directory_url, key)
        print(f"[verify] Initial placement: {replicas}")
        if count != 2:
            raise RuntimeError(f"expected 2 initial replicas, found {count}: {replicas}")

        print("[verify] Reading object back")
        _, read_payload = request_json("GET", f"{args.base_url}/object/{key}")
        if read_payload.get("value") != value:
            raise RuntimeError("read payload did not match uploaded value")

        print(f"[verify] Issuing {args.hot_read_count} reads to trigger hot replication")
        for _ in range(args.hot_read_count):
            _, read_payload = request_json("GET", f"{args.base_url}/object/{key}")
            if read_payload.get("value") != value:
                raise RuntimeError("read payload changed during hot-read loop")
            time.sleep(0.1)

        deadline = time.time() + args.promotion_timeout
        promoted_replicas = []
        while time.time() < deadline:
            count, promoted_replicas = placement_count(args.directory_url, key)
            if count == 3:
                break
            time.sleep(2)

        print(f"[verify] Promoted placement: {promoted_replicas}")
        if len(promoted_replicas) != 3:
            raise RuntimeError(
                f"expected placement to grow to 3 replicas, found {len(promoted_replicas)}: "
                f"{promoted_replicas}"
            )

        print("[verify] Deleting object")
        request_json("DELETE", f"{args.base_url}/object/{key}")

        count, replicas = placement_count(args.directory_url, key)
        if count != 0:
            raise RuntimeError(f"expected placement removal after delete, found {replicas}")

        print("[verify] PASS")
        return 0
    except Exception:
        print(f"[verify] Created key was {key}; attempting cleanup", file=sys.stderr)
        try:
            request_json("DELETE", f"{args.base_url}/object/{key}", allow_404=True)
        except Exception as cleanup_error:
            print(f"[verify] Cleanup failed: {cleanup_error}", file=sys.stderr)
        raise


if __name__ == "__main__":
    sys.exit(main())
