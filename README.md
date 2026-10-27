# Caddy Cloudflare

[![Caddy Cloudflare](https://github.com/TheoKeen/caddy_cf/actions/workflows/caddy.yml/badge.svg)](https://github.com/TheoKeen/caddy_cf/actions/workflows/caddy.yml)

[TheoKeen/caddy_cf](https://github.com/TheoKeen/caddy_cf) builds Caddy with
[`dns.providers.cloudflare`](https://github.com/caddy-dns/cloudflare) for DNS-01
certificate issuance. The runtime uses `scratch`: a stripped, statically linked
Caddy binary, CA certificates, and a default Caddyfile. There is no shell, package
manager, libc, or build toolchain. Supported platforms: `linux/amd64` and `linux/arm64`.
The process runs as UID/GID `10001:10001` and receives SIGTERM directly.

## Image and tags

Images are published to `docker.io/<namespace>/caddy-cloudflare`.
The namespace defaults to the repository owner (`theokeen`), matching the existing
publisher account. Set the optional Actions variable `DOCKER_NAMESPACE` to override
it. Every verified stable Caddy release receives four tags:

| Tag | Meaning |
| --- | --- |
| `stable` | Latest verified stable Caddy 2 release |
| `2` | Latest verified Caddy 2 release |
| `2.<minor>` | Latest verified patch in that minor series |
| `2.<minor>.<patch>` | Caddy release version |

There is no `latest` tag. All tags, including patch tags, can be rebuilt to refresh
the Cloudflare plugin, Go toolchain, builder image, and dependencies. Pin the
published digest for an immutable deployment. `upstream/publication.json` records
the most recent successful publication, its tags, source revision, architectures,
and OCI index digest. Earlier receipts remain in Git history and workflow artifacts.

## Run

Replace `YOUR_DOCKER_NAMESPACE` with the configured publisher's username:

```sh
docker run -d --name caddy --restart unless-stopped \
  --cap-drop=ALL --security-opt=no-new-privileges:true \
  --sysctl net.ipv4.ip_unprivileged_port_start=0 \
  --read-only --tmpfs /tmp:rw,noexec,nosuid,size=16m \
  -p 80:80 -p 443:443 -p 443:443/udp \
  --mount type=bind,src="$PWD/Caddyfile",dst=/etc/caddy/Caddyfile,readonly \
  --mount type=volume,src=caddy_data,dst=/data \
  --mount type=volume,src=caddy_config,dst=/config \
  --env-file /secure/path/caddy.env \
  docker.io/YOUR_DOCKER_NAMESPACE/caddy-cloudflare:stable
```

The bundled Caddyfile returns an HTTP response on port 80 and requests no certificates.
Mount your own Caddyfile for production. For example:

```caddyfile
example.com {
    tls {
        dns cloudflare {env.CF_API_TOKEN}
    }

    reverse_proxy backend:8080
}
```

Create a Cloudflare API token restricted to the zones Caddy manages, with
**Zone:Zone:Read** and **Zone:DNS:Edit** permissions. Follow the
[plugin's configuration guidance](https://github.com/caddy-dns/cloudflare#configuration).
Do not use your global API key. Keep tokens outside Git and the image; restrict
the environment file to its owner. Set `CF_API_TOKEN` through your deployment's
secret manager or a protected environment file. Docker administrators can inspect
container environments, so restrict access to the Docker daemon. Rotate tokens
through Cloudflare and recreate the container when needed.

Docker Compose example (`compose.yaml`):

```yaml
services:
  caddy:
    image: docker.io/${DOCKER_NAMESPACE:?set publisher namespace}/caddy-cloudflare:stable
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
      - "443:443/udp"
    env_file:
      - /secure/path/caddy.env
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    read_only: true
    tmpfs:
      - /tmp:rw,noexec,nosuid,size=16m
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    sysctls:
      net.ipv4.ip_unprivileged_port_start: "0"

volumes:
  caddy_data:
  caddy_config:
```

The `backend` in the Caddyfile must be reachable on a shared Docker network.
Protect and back up `/data`: it contains ACME account keys and certificates.
Persist `/config` for Caddy's saved configuration. Fresh Docker named volumes
inherit the image's UID/GID ownership. For bind mounts, prepare writable directories
for UID/GID 10001 (account for UID mappings with a rootless daemon); make the
Caddyfile readable by that user. Never run the container as root to fix ownership.

Dropping all capabilities works with the container network namespace sysctl above,
which permits the non-root process to bind ports 80/443. This does not change host
sysctls. Rootless Docker may separately restrict **host** ports below 1024; use
`8080:80` and `8443:443` or configure your host's rootless port forwarding.
The Caddy admin API is not exposed by the image; the default Caddyfile disables it.

## Release tracking and publication

`scripts/update_upstream.py` uses the official
[Caddy releases API](https://github.com/caddyserver/caddy/releases), follows all
pagination links, and chooses the highest semantic `v2.<minor>.<patch>` version.
Drafts, betas, release candidates, development versions, and other major versions
are excluded. No Caddy patch version is hardcoded in build logic.

The tracker updates `upstream/caddy-version.txt`, appends newly observed releases
and their original notes to `upstream/CADDY_CHANGES.md`, and records metadata in
`upstream/state.json`. Bootstrap records the latest stable release; subsequent
updates also record any intervening stable releases. Notes are preserved as
upstream text. Checks on the same UTC date with unchanged releases are idempotent.
Later check dates are committed even if Caddy has not changed.

The script uses `GH_TOKEN` or `GITHUB_TOKEN` when available, retries transient
failures three times, reports rate/access limits, and exits nonzero without writing
tracking files when discovery fails. It refuses to downgrade. GitHub Actions outputs
include `version`, `version_changed`, `changed`, and `rebuild_required`.
An unpublished tracked release is eligible for retry.

[The workflow](.github/workflows/caddy.yml) runs on relevant pushes to `main`,
every Monday at 05:23 UTC, and manual dispatch. Pull requests run the credential-free
unit tests; publication is restricted to the default branch of this repository.
Each release run:

1. Tests the current default-branch sources, checks upstream, and commits tracking changes.
2. Pulls `caddy:2-builder-alpine` and reruns `xcaddy` with the current Cloudflare plugin.
   Cross compilation uses the runner's native builder, `CGO_ENABLED=0`, and stripped symbols.
   The `nobadger,nomysql,nopgx` build tags exclude database drivers, matching xcaddy's
   size-saving defaults; ordinary file storage and Cloudflare DNS remain available.
3. Builds **once**, with Buildx caching, maximum OCI provenance, and SBOMs, into a local
   containerd image store. QEMU enables ARM64 runtime checks on the AMD64 runner.
4. Verifies both architectures before any registry login or upload.
5. Rejects stale default-branch state, logs in to Docker Hub, and pushes the tested
   multi-platform index under the patch tag. It checks that the registry digest
   equals the build digest and that both architectures and attestations survived.
6. Promotes the same index digest to the minor, major, and `stable` tags, verifies
   every resulting tag, and commits the publication receipt.

The workflow continues after its own tracking commit; it does not depend on another
workflow being triggered by `GITHUB_TOKEN`. Release runs are serialized and queued
runs check out the current default branch to avoid publishing obsolete event SHAs.
A newer user commit detected before publication aborts the run; rerun it to use the
new sources. Branch protection must permit the automation's tracking and receipt
commits. Pushes are ordinary fast-forward pushes; the workflow never force-pushes.
If a user push races with the receipt commit, the failed push is visible and the
receipt is retained as an artifact. The registry update and Git commit cannot form
one transaction; a network failure during promotion may leave some tags updated.
All updated tags still point to verified images. A rerun repairs publication.

Weekly builds refresh dependencies even when Caddy has no new release. The builder
stage bypasses cached build steps; cache storage remains available for other layers.
Actions are pinned to reviewed commits and Dependabot proposes weekly action updates.

## GitHub setup

Preserve and reuse these existing repository secrets under **Settings → Secrets
and variables → Actions**:

| Name | Kind | Value |
| --- | --- | --- |
| `DOCKER_USERNAME` | Secret | Docker Hub login identity (username or email) |
| `DOCKER_PASSWORD` | Secret | Docker Hub access token with write access to `caddy-cloudflare` |

The workflow uses `${{ secrets.DOCKER_USERNAME }}` and
`${{ secrets.DOCKER_PASSWORD }}` unchanged. The image namespace comes from
`DOCKER_NAMESPACE` or the repository owner, independently of the login identity,
which may be an email address. The namespace is lowercased and surrounding
whitespace is trimmed to produce a valid Docker reference. No credentials
belong in source files.
Confirm that the destination Docker Hub repository exists and that Actions can push
tracking commits to `main`. The default token grants read access globally and write
access only to the trusted release job. No Docker Hub credentials reach pull request jobs.

To run manually, open **Actions → Caddy Cloudflare → Run workflow → main**, or:

```sh
gh workflow run caddy.yml --repo TheoKeen/caddy_cf --ref main
gh run list --repo TheoKeen/caddy_cf --workflow caddy.yml
```

GitHub can disable scheduled workflows in public repositories after 60 days of
inactivity; check-date commits are an audit trail, **not a scheduling guarantee**.
Schedules may also be delayed. Monitor successful runs and re-enable the workflow
when necessary. Optionally have an external scheduler call the
[workflow dispatch API](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event)
weekly with an appropriately scoped GitHub App token or fine-grained token having
Actions write access. Store that token in the external scheduler's secret store.

## Local development and verification

Requirements: Python 3.10+, Docker Engine 28+ with the containerd image store,
Docker Buildx, and working ARM64 binfmt/QEMU registration to **run** ARM64 images
on an AMD64 host. No Python packages are required. GitHub-hosted CI prepares its
own image store and QEMU without changing this machine's configuration.
For a host without binfmt registration, the verifier also accepts
`--emulator /absolute/path/to/qemu-aarch64`: an existing static QEMU user binary
is mounted read-only into ARM64 test containers. The image itself stays unchanged.
Add `--preserve-argv0` for binfmt-style QEMU builds such as `tonistiigi/binfmt`.

```sh
python3 -m unittest discover -s tests -v
python3 scripts/update_upstream.py
docker buildx build --platform linux/amd64,linux/arm64 --pull \
  --no-cache-filter builder --load --provenance=mode=max --sbom=true \
  --metadata-file build-metadata.json \
  --build-arg "CADDY_VERSION=$(cat upstream/caddy-version.txt)" \
  --build-arg "VCS_REF=$(git rev-parse HEAD)" \
  --build-arg "BUILD_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  -t caddy-cloudflare:test .
sh scripts/verify_image.sh caddy-cloudflare:test "$(cat upstream/caddy-version.txt)" --platform linux/amd64
sh scripts/verify_image.sh caddy-cloudflare:test "$(cat upstream/caddy-version.txt)" --platform linux/arm64
```

The version file controls the compiled version. The matching `CADDY_VERSION` build
argument supplies its OCI label. Verification catches a mismatch. The verifier
checks the reported version, Cloudflare module, database-exclusion build tags, static
ELF headers, stripped symbols, architecture, non-root user, OCI labels, CA bundle,
persistence ownership, exact
runtime file allowlist, representative DNS Caddyfile validation, HTTP startup with
all capabilities dropped and a read-only root filesystem, and graceful termination.
Unit tests exercise release filtering, semantic comparison, pagination, authentication,
API errors/retries, idempotence, history, downgrade prevention, image checks, and tags.

Troubleshooting:

- `exec format error`: ARM64 emulation is unavailable; use a native ARM64 host or CI.
- Unsupported multi-platform loading/attestations: enable Docker's containerd image store.
- API rate/access limit: provide `GH_TOKEN`, check its permissions, and rerun after reset.
- `/data` or `/config` permission denied: fix mount ownership for UID/GID 10001.
- Binding 80/443 fails: apply the namespace sysctl shown above, or configure Caddy to use higher ports.
- Cloudflare authentication/zone errors: check the token's zone scope and both required permissions.
- Tracking commit fails: review branch protection and the release job's `contents: write` permission.
- Publishing fails: verify the existing Actions secrets, namespace, and Docker Hub token scope.

Use `docker logs caddy` and `docker exec caddy version` for diagnostics; `docker exec
caddy sh` cannot work because the image contains no shell. Do not run
`scripts/publish_image.py` by itself: the release workflow invokes it only after
both platform verifiers pass.
