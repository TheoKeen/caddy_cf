# AGENTS.md — Caddy Cloudflare Docker Image

## Objective

Build and maintain a production-ready GitHub repository that automatically builds and publishes a minimal Caddy Docker image with the Cloudflare DNS plugin.

**Target repository:** https://github.com/TheoKeen/caddy_cf

The image must track the latest stable Caddy 2.x release without manually pinning Caddy versions.

Use GitHub Actions for CI/CD and Docker Hub as the container registry.

Implement the complete solution, including source files, workflows, scripts, tests, and documentation.

## 1. Repository and modification permissions

The agent MUST use the existing repository:

`https://github.com/TheoKeen/caddy_cf`

Clone or work directly in this repository. Do not create a new repository or move the project elsewhere.

### Existing files

The agent has permission to:

- Replace, rewrite, or delete existing project files.
- Restructure directories.
- Replace existing Dockerfiles and GitHub Actions workflows.
- Remove obsolete scripts and configuration.
- Create new files as required.
- Refactor the implementation without maintaining backward compatibility with obsolete configurations.

The goal is the best maintainable implementation, not preserving the existing project structure.

### Configuration that MUST be preserved

Preserve these existing GitHub Actions configurations:

| Name | Type | Requirement |
|---|---|---|
| `DOCKER_USERNAME` | GitHub Actions secret | Preserve and reuse |
| `DOCKER_PASSWORD` | GitHub Actions secret | Preserve and reuse |

Do not rename these secrets, change their intended purpose, overwrite their values, or replace them with hardcoded credentials.

The agent may update all other repository files and configuration as necessary.

If either credential is unavailable, do not delete or recreate it. Implement the workflow using the expected names and document any remaining setup.

## 2. Core requirements

- Track the latest stable Caddy 2.x release.
- Exclude beta, release candidate, and development versions.
- Build Caddy with `github.com/caddy-dns/cloudflare`.
- Prefer the official `caddy:2-builder-alpine` image.
- Use `scratch` as the final runtime image.
- Compile statically with `CGO_ENABLED=0`.
- Strip debug symbols to minimize binary size.
- Support `linux/amd64` and `linux/arm64`.
- Run the container as an unprivileged user.
- Include CA certificates.
- Avoid shells and package managers in the final image.
- Publish images to Docker Hub.
- Maintain upstream release history and changelogs in Git.
- Automate builds, verification, and publishing.
- Keep the solution simple and secure.

## 3. Recommended repository structure

```text
.
├── AGENTS.md
├── Dockerfile
├── .dockerignore
├── README.md
├── scripts/
│   ├── update_upstream.py
│   └── verify_image.sh
├── upstream/
│   ├── caddy-version.txt
│   ├── CADDY_CHANGES.md
│   └── state.json
└── .github/
    └── workflows/
        └── caddy.yml
```

This structure is a recommendation, not a strict requirement. The agent may implement a better structure when justified.

## 4. Docker image

Use a multi-stage Dockerfile.

Builder stage:

```dockerfile
FROM caddy:2-builder-alpine AS builder

ARG CADDY_VERSION

ENV CGO_ENABLED=0
ENV GOFLAGS="-ldflags=-s=-w"

RUN xcaddy build "v${CADDY_VERSION}" \
    --with github.com/caddy-dns/cloudflare \
    --output /usr/bin/caddy
```

Runtime stage:

```dockerfile
FROM scratch

COPY --from=builder /usr/bin/caddy /usr/bin/caddy
COPY --from=builder \
    /etc/ssl/certs/ca-certificates.crt \
    /etc/ssl/certs/ca-certificates.crt

ENV XDG_CONFIG_HOME=/config
ENV XDG_DATA_HOME=/data

USER 10001:10001

EXPOSE 80 443 443/udp

ENTRYPOINT ["/usr/bin/caddy"]
CMD ["run", "--config", "/etc/caddy/Caddyfile"]
```

The agent may improve this Dockerfile when necessary.

Ensure the compiled binary works in `scratch` and is fully statically linked.

The runtime must support mounting a Caddyfile and persistent `/data` and `/config` volumes.

Include OCI image metadata referencing:

`https://github.com/TheoKeen/caddy_cf`

## 5. Automatic upstream tracking

Implement a script that uses the official Caddy GitHub releases:

https://github.com/caddyserver/caddy/releases

Requirements:

1. Discover the latest stable Caddy 2.x release.
2. Exclude drafts and prereleases.
3. Compare semantic versions correctly.
4. Never downgrade automatically.
5. Handle API pagination, rate limits, and errors.
6. Use GitHub API authentication when available.
7. Update the tracked Caddy version.
8. Save upstream release notes.
9. Record metadata and version history.
10. Make the operation idempotent.
11. Fail safely when upstream information is unavailable.

Provide GitHub Actions outputs indicating whether a rebuild is required.

Keep version tracking in Git so upstream changes are visible in commit history.

## 6. GitHub Actions automation

Implement workflows inside:

`https://github.com/TheoKeen/caddy_cf/tree/main/.github/workflows`

Use the repository's actual default branch if it differs from `main`.

Required triggers:

- Weekly scheduled checks.
- Manual `workflow_dispatch`.
- Pushes to relevant project files.

The automation must:

1. Check for new stable Caddy releases.
2. Update the tracked version and changelog.
3. Commit upstream changes.
4. Determine whether an image rebuild is necessary.
5. Build and verify the Docker image.
6. Publish successful builds to Docker Hub.
7. Record resulting image digests.

Also implement periodic rebuilds for builder-image updates, Cloudflare plugin updates, and security fixes.

Do not rely on a commit created with `GITHUB_TOKEN` automatically triggering another workflow.

### Workflow inactivity

GitHub may disable scheduled workflows in inactive public repositories.

Record periodic upstream checks in Git, but do not assume automated commits guarantee continued scheduling.

Document the limitation and an optional external workflow trigger.

## 7. Docker Hub publishing

Use the existing GitHub Actions secrets:

```yaml
username: ${{ secrets.DOCKER_USERNAME }}
password: ${{ secrets.DOCKER_PASSWORD }}
```

These names must remain unchanged.

Publish to:

```text
docker.io/<DOCKER_USERNAME>/caddy-cloudflare
```

Use the tags:

```text
stable
2
2.x
2.x.y
```

For example, Caddy `2.11.7` produces:

```text
stable
2
2.11
2.11.7
```

The moving tags must only reference the latest successfully verified stable release.

Support multi-architecture publishing for:

- `linux/amd64`
- `linux/arm64`

Use Docker Buildx, GitHub Actions caching, OCI provenance, and SBOM generation.

Never publish an untested or failed image.

Avoid concurrent release jobs overwriting newer tags with older images.

## 8. Security requirements

Use least-privilege GitHub Actions permissions.

Use maintained official Docker actions.

Do not expose Docker Hub credentials to untrusted pull request workflows.

Do not hardcode credentials in Dockerfiles, scripts, or documentation.

Include recommended runtime security configuration:

```yaml
security_opt:
  - no-new-privileges:true

cap_drop:
  - ALL
```

Document secure management of Cloudflare DNS API tokens.

The final image must not contain build tools, package managers, or a shell.

## 9. Testing and validation

Implement verification before publication.

Tests must check:

- Caddy starts successfully.
- The version matches the tracked stable release.
- `dns.providers.cloudflare` is available.
- The binary is statically linked.
- The runtime executes as a non-root user.
- Both architectures build successfully.
- Image metadata is correct.
- A representative Caddyfile validates successfully.
- The image does not contain unnecessary build dependencies.

Provide automated tests for upstream release selection, version comparison, API failures, and idempotent updates.

Publishing must fail if required validation fails.

## 10. Documentation

Create or replace `README.md`.

Document:

- The purpose of the project.
- The official repository URL.
- How stable release tracking works.
- How GitHub Actions builds and publishes images.
- Docker Hub image naming and tags.
- Docker Hub secrets configuration.
- How to run the image.
- Docker Compose examples.
- Cloudflare DNS configuration.
- Rootless execution.
- Data and certificate persistence.
- Supported architectures.
- Manual workflow execution.
- Testing and troubleshooting.
- GitHub scheduled-workflow limitations.

Example Caddyfile:

```caddyfile
example.com {
    tls {
        dns cloudflare {env.CF_API_TOKEN}
    }

    reverse_proxy backend:8080
}
```

## 11. Implementation principles

- Prefer simple, maintainable solutions.
- Minimize dependencies.
- Avoid unnecessary abstractions.
- Avoid hardcoded Caddy patch versions.
- Keep GitHub Actions workflows understandable.
- Make repeated executions safe.
- Handle errors explicitly.
- Use caching where appropriate.
- Do not silently downgrade images.
- Do not publish unverified images.
- Do not overwrite the Docker Hub credentials.
- Prioritize correctness over preserving obsolete project files.

## 12. Acceptance criteria

The task is complete when:

- [ ] The implementation exists in `TheoKeen/caddy_cf`.
- [ ] Obsolete project files have been replaced or removed as necessary.
- [ ] Existing Docker Hub secret names are preserved.
- [ ] Stable Caddy 2 releases are tracked automatically.
- [ ] Upstream changes are recorded in Git.
- [ ] Caddy is compiled with the Cloudflare DNS plugin.
- [ ] The runtime image uses `scratch`.
- [ ] The container runs as an unprivileged user.
- [ ] AMD64 and ARM64 builds succeed.
- [ ] GitHub Actions automation is implemented.
- [ ] Docker Hub tags are generated correctly.
- [ ] Tests execute before publication.
- [ ] Documentation is complete.
- [ ] Available tests pass.
- [ ] No credentials are committed.

## 13. Agent execution instructions

Work directly in `https://github.com/TheoKeen/caddy_cf`.

1. Clone or open the existing repository.
2. Inspect the current project files and GitHub Actions configuration.
3. Preserve the existing Docker Hub secrets.
4. Verify current upstream Caddy and Docker recommendations.
5. Replace or restructure obsolete files as needed.
6. Implement the Dockerfile.
7. Implement upstream release tracking.
8. Implement GitHub Actions automation.
9. Implement validation scripts and automated tests.
10. Create or update the README.
11. Execute tests and fix failures.
12. Review the resulting Git diff.
13. Commit and push the implementation to the existing repository when authorized.
14. Verify workflow execution and Docker Hub publication when credentials and permissions allow.

Do not request confirmation for routine code changes.

Do not preserve obsolete files merely for backward compatibility.

Do not modify or delete the existing Docker Hub credentials.

If publication or repository operations cannot be performed, clearly report the limitation. Never claim success without verification.

**Final goal:** Transform `TheoKeen/caddy_cf` into a self-maintaining Caddy Cloudflare Docker image repository that tracks stable releases, records upstream changes, builds minimal multi-architecture images, and publishes verified images automatically to Docker Hub.
