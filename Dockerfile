# syntax=docker/dockerfile:1
FROM --platform=$BUILDPLATFORM caddy:2-builder-alpine AS builder

ARG TARGETOS
ARG TARGETARCH
ENV CGO_ENABLED=0 \
    XCADDY_SETCAP=0 \
    XCADDY_PRINT_VERSION=0 \
    XCADDY_GO_BUILD_FLAGS="-trimpath -tags nobadger,nomysql,nopgx -ldflags '-s -w'"

COPY upstream/caddy-version.txt /tmp/caddy-version.txt
RUN GOOS="$TARGETOS" GOARCH="$TARGETARCH" \
    xcaddy build "v$(cat /tmp/caddy-version.txt)" \
      --with github.com/caddy-dns/cloudflare \
      --output /usr/bin/caddy
RUN mkdir -p /runtime/data /runtime/config /runtime/tmp && \
    chown 10001:10001 /runtime/data /runtime/config /runtime/tmp && \
    chmod 700 /runtime/data /runtime/config && chmod 1777 /runtime/tmp

FROM scratch
ARG CADDY_VERSION
ARG VCS_REF=unknown
ARG BUILD_DATE
LABEL org.opencontainers.image.title="Caddy with Cloudflare DNS" \
      org.opencontainers.image.description="Static, unprivileged Caddy with dns.providers.cloudflare" \
      org.opencontainers.image.source="https://github.com/TheoKeen/caddy_cf" \
      org.opencontainers.image.url="https://github.com/TheoKeen/caddy_cf" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.version="$CADDY_VERSION" \
      org.opencontainers.image.revision="$VCS_REF" \
      org.opencontainers.image.created="$BUILD_DATE"

COPY --from=builder /usr/bin/caddy /usr/bin/caddy
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
COPY --from=builder /runtime/ /
COPY Caddyfile /etc/caddy/Caddyfile

ENV HOME=/config XDG_CONFIG_HOME=/config XDG_DATA_HOME=/data
USER 10001:10001
WORKDIR /config
VOLUME ["/data", "/config"]
EXPOSE 80 443 443/udp
STOPSIGNAL SIGTERM
ENTRYPOINT ["/usr/bin/caddy"]
CMD ["run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
