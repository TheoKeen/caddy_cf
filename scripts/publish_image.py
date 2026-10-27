#!/usr/bin/env python3
"""Push the verified local index, then promote its exact digest to moving tags."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess

from update_upstream import version_tuple, write_if_changed


def command(*args):
    return subprocess.check_output(args, text=True).strip()


def tags_for(version):
    version_tuple(version)
    return [version, ".".join(version.split(".")[:2]), "2", "stable"]


def validate_index(index):
    manifests = index.get("manifests", [])
    images = {entry["digest"]: entry.get("platform", {}) for entry in manifests
              if entry.get("platform", {}).get("os") == "linux"}
    if {(p.get("os"), p.get("architecture")) for p in images.values()} != {
            ("linux", "amd64"), ("linux", "arm64")} or len(images) != 2:
        raise ValueError("Published index must contain exactly linux/amd64 and linux/arm64")
    attested = {entry.get("annotations", {}).get("vnd.docker.reference.digest") for entry in manifests
                if entry.get("annotations", {}).get("vnd.docker.reference.type") == "attestation-manifest"}
    if not set(images).issubset(attested):
        raise ValueError("Published index is missing platform attestations")


def validate_attestation(manifest):
    predicates = {layer.get("annotations", {}).get("in-toto.io/predicate-type", "")
                  for layer in manifest.get("layers", [])}
    if ("https://spdx.dev/Document" not in predicates
            or not any(value.startswith("https://slsa.dev/provenance/") for value in predicates)):
        raise ValueError("Attestation must include both an SBOM and provenance")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", help="docker.io/<username>/caddy-cloudflare")
    parser.add_argument("version")
    parser.add_argument("digest", help="Verified build's OCI index digest")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    tags = tags_for(args.version)
    if not re.fullmatch(r"docker\.io/[a-z0-9][a-z0-9_-]*/caddy-cloudflare", args.image):
        raise ValueError("Unexpected Docker Hub image name")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", args.digest):
        raise ValueError("Invalid build digest")
    reference = f"{args.image}:{args.version}"
    local = json.loads(command("docker", "image", "inspect", reference))[0]
    if local.get("Descriptor", {}).get("digest") != args.digest:
        raise ValueError("Local image index differs from the verified build")
    # No --platform: preserve the tested multi-platform index and all attestations.
    pushed = command("docker", "push", reference)
    print(pushed)
    digests = re.findall(r"digest: (sha256:[0-9a-f]{64})", pushed)
    if not digests or digests[-1] != args.digest:
        raise ValueError("Registry digest differs from the verified build; refusing tag promotion")
    index = json.loads(command("docker", "buildx", "imagetools", "inspect", "--raw", reference))
    validate_index(index)
    for entry in index["manifests"]:
        if entry.get("annotations", {}).get("vnd.docker.reference.type") == "attestation-manifest":
            manifest = json.loads(command("docker", "buildx", "imagetools", "inspect", "--raw",
                                          f"{args.image}@{entry['digest']}"))
            validate_attestation(manifest)
    for tag in tags[1:]:
        # A single source index is copied without rebuilding or modifying its contents.
        command("docker", "buildx", "imagetools", "create", "--tag", f"{args.image}:{tag}",
                f"{args.image}@{args.digest}")
    for tag in tags:
        description = command("docker", "buildx", "imagetools", "inspect", f"{args.image}:{tag}")
        if not re.search(rf"^Digest:\s+{re.escape(args.digest)}\s*$", description, re.MULTILINE):
            raise ValueError(f"Tag {tag} does not reference the verified digest")
    receipt = {"version": args.version, "image": args.image, "digest": args.digest,
               "tags": tags, "platforms": ["linux/amd64", "linux/arm64"],
               "published_at": datetime.now(timezone.utc).isoformat(),
               "source_revision": command("git", "rev-parse", "HEAD"),
               "workflow_run": os.environ.get("GITHUB_RUN_ID")}
    write_if_changed(args.root / "upstream" / "publication.json", json.dumps(receipt, indent=2) + "\n")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as summary:
            summary.write(f"Published `{args.image}@{args.digest}`\n\nTags: {', '.join(tags)}\n")


if __name__ == "__main__":
    main()
