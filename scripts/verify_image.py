#!/usr/bin/env python3
"""Verify an already built image; no registry credentials or Python packages needed."""

import argparse
import io
import json
from pathlib import Path
import re
import struct
import subprocess
import tarfile
import tempfile
import time
from urllib.error import URLError
from urllib.request import urlopen

SOURCE = "https://github.com/TheoKeen/caddy_cf"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def docker(*args, binary=False):
    result = subprocess.run(["docker", *args], capture_output=True)
    if result.returncode:
        raise RuntimeError(f"docker {args[0]} failed: {result.stderr.decode().strip()}")
    return result.stdout if binary else result.stdout.decode().strip()


def verify_elf(binary, architecture):
    require(binary[:6] == b"\x7fELF\x02\x01", "Expected little-endian ELF64 binary")
    require(struct.unpack_from("<H", binary, 18)[0] == {"amd64": 62, "arm64": 183}[architecture],
            "Binary architecture does not match image")
    phoff, shoff = struct.unpack_from("<QQ", binary, 32)
    phsize, phcount, shsize, shcount = struct.unpack_from("<HHHH", binary, 54)
    require(phcount > 0 and phsize >= 56 and phoff + phcount * phsize <= len(binary),
            "Invalid ELF program headers")
    for index in range(phcount):
        kind = struct.unpack_from("<I", binary, phoff + index * phsize)[0]
        require(kind not in (2, 3), "Binary has a dynamic segment or interpreter; not static")
    require(shoff + shcount * shsize <= len(binary), "Invalid ELF section headers")
    for index in range(shcount):
        kind = struct.unpack_from("<I", binary, shoff + index * shsize + 4)[0]
        require(kind != 2, "Binary still contains a symbol table; expected stripped binary")


def verify_rootfs(archive, architecture):
    allowed = {"usr/bin/caddy", "etc/ssl/certs/ca-certificates.crt", "etc/caddy/Caddyfile",
               ".dockerenv", "etc/hosts", "etc/hostname", "etc/resolv.conf", "dev/console"}
    with tarfile.open(fileobj=io.BytesIO(archive)) as filesystem:
        members = {member.name.removeprefix("./").rstrip("/"): member
                   for member in filesystem.getmembers()}
        for name, member in members.items():
            # Docker creates these runtime placeholders, including in a scratch image.
            runtime_link = name == "etc/mtab" and member.issym() and member.linkname == "/proc/mounts"
            require(member.isdir() or (member.isfile() and name in allowed) or runtime_link,
                    f"Unexpected runtime file (shell, library, tool, or link): {name}")
        for path in ("data", "config"):
            require(path in members and members[path].uid == members[path].gid == 10001,
                    f"/{path} must be owned by 10001:10001")
        for path in ("usr/bin/caddy", "etc/ssl/certs/ca-certificates.crt", "etc/caddy/Caddyfile"):
            require(path in members and members[path].size > 0, f"Missing runtime file: {path}")
        verify_elf(filesystem.extractfile(members["usr/bin/caddy"]).read(), architecture)
        certificates = filesystem.extractfile(members["etc/ssl/certs/ca-certificates.crt"]).read()
        require(b"-----BEGIN CERTIFICATE-----" in certificates, "Invalid CA certificate bundle")


def verify(image, version, platform, revision=None, emulator=None, preserve_argv0=False):
    architecture = platform.split("/")[1]
    metadata = json.loads(docker("image", "inspect", "--platform", platform, image))[0]
    config = metadata["Config"]
    require(metadata["Os"] == "linux" and metadata["Architecture"] == architecture, "Wrong image platform")
    require(config["User"] == "10001:10001", "Image must run as UID/GID 10001")
    require(config["Entrypoint"] == ["/usr/bin/caddy"], "Unexpected entrypoint")
    require(config["Cmd"] == ["run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"],
            "Unexpected default command")
    require(set(config["Volumes"]) == {"/data", "/config"}, "Missing persistence volumes")
    require(set(config["ExposedPorts"]) == {"80/tcp", "443/tcp", "443/udp"}, "Unexpected ports")
    for key, value in {"source": SOURCE, "url": SOURCE, "licenses": "Apache-2.0", "version": version}.items():
        require(config["Labels"].get(f"org.opencontainers.image.{key}") == value, f"Incorrect {key} label")
    if revision:
        require(config["Labels"].get("org.opencontainers.image.revision") == revision, "Incorrect revision label")
    secure = ["--platform", platform, "--cap-drop=ALL", "--security-opt=no-new-privileges:true",
              "--sysctl=net.ipv4.ip_unprivileged_port_start=0"]
    execution = [image]
    if emulator:
        execution = ["--mount", f"type=bind,src={emulator.resolve()},dst=/qemu-static,readonly",
                     "--entrypoint", "/qemu-static", image, "/usr/bin/caddy"]
        if preserve_argv0:
            execution.append("/usr/bin/caddy")
    output = docker("run", "--rm", *secure, "--network=none", *execution, "version")
    require(re.match(rf"^v{re.escape(version)}(?:\s|$)", output), f"Wrong Caddy version: {output}")
    modules = docker("run", "--rm", *secure, "--network=none", *execution, "list-modules")
    require("dns.providers.cloudflare" in modules.splitlines(), "Missing Cloudflare DNS plugin")
    container = docker("create", *secure, image)
    try:
        verify_rootfs(docker("export", container, binary=True), architecture)
    finally:
        docker("rm", "-v", "-f", container)
    with tempfile.TemporaryDirectory() as temporary:
        caddyfile = Path(temporary) / "Caddyfile"
        caddyfile.write_text("example.com {\n tls {\n  dns cloudflare {env.CF_API_TOKEN}\n }\n reverse_proxy backend:8080\n}\n")
        caddyfile.chmod(0o644)
        Path(temporary).chmod(0o755)
        docker("run", "--rm", *secure, "--network=none", "--env", "CF_API_TOKEN=" + "0" * 40,
               "--mount", f"type=bind,src={caddyfile},dst=/etc/caddy/Caddyfile,readonly",
               *execution, "validate", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile")
    container = docker("run", "--detach", *secure, "--read-only", "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m",
                       "--publish", "127.0.0.1::80", *execution, *config["Cmd"])
    try:
        runtime = json.loads(docker("inspect", container))[0]
        require(runtime["Config"]["User"] == "10001:10001", "Runtime user is root")
        port = runtime["NetworkSettings"]["Ports"]["80/tcp"][0]["HostPort"]
        for attempt in range(30):
            require(json.loads(docker("inspect", container))[0]["State"]["Running"],
                    "Caddy exited before serving HTTP")
            try:
                with urlopen(f"http://127.0.0.1:{port}", timeout=2) as response:
                    require(response.status == 200 and b"Caddy with Cloudflare DNS is running" in response.read(),
                            "Unexpected HTTP response")
                break
            except (URLError, TimeoutError, ConnectionError):
                if attempt == 29:
                    raise RuntimeError("Caddy did not become ready")
                time.sleep(1)
        # Graceful SIGTERM must stop the actual Caddy process, without a shell wrapper.
        docker("stop", "--time", "10", container)
        state = json.loads(docker("inspect", container))[0]["State"]
        require(state["ExitCode"] == 0, f"Caddy shutdown failed: {state}")
    except Exception:
        print(docker("logs", container))
        raise
    finally:
        docker("rm", "-v", "-f", container)
    print(f"Verified {image}: {platform}, Caddy {version}, static, stripped, non-root, Cloudflare, HTTP")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image")
    parser.add_argument("version")
    parser.add_argument("--platform", required=True, choices=("linux/amd64", "linux/arm64"))
    parser.add_argument("--revision")
    parser.add_argument("--emulator", type=Path,
                        help="Optional static QEMU user binary; mounted read-only for hosts without binfmt")
    parser.add_argument("--preserve-argv0", action="store_true",
                        help="Use with binfmt-style QEMU builds such as tonistiigi/binfmt")
    args = parser.parse_args()
    if args.preserve_argv0 and not args.emulator:
        parser.error("--preserve-argv0 requires --emulator")
    verify(args.image, args.version, args.platform, args.revision, args.emulator, args.preserve_argv0)
