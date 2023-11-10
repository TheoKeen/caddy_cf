FROM caddy:builder AS builder
MAINTAINER Theo@keennews.nl

RUN apk add -q --progress --update --no-cache git ca-certificates tzdata
RUN mkdir -p /caddydir/data && \
    chmod -R 700 /caddydir

RUN caddy-builder \
    github.com/caddy-dns/cloudflare

FROM caddy:latest

COPY --from=builder /usr/bin/caddy /usr/bin/caddy



FROM scratch
MAINTAINER Theo@keennews.nl

COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
COPY --from=builder /usr/share/zoneinfo /usr/share/zoneinfo

ENV HOME=/caddydir \
    CADDYPATH=/caddydir/data \
    TZ=Europe/Amsterdam

COPY --from=builder --chown=1000 /caddydir /caddydir
VOLUME ["/caddydir"]
ENTRYPOINT ["/caddy"]
USER 1000
# see https://caddyserver.com/docs/cli
CMD ["run","--config","/caddydir/Caddyfile"]
COPY --chown=1000 Caddyfile /caddydir/Caddyfile
COPY --from=builder --chown=1000 /usr/bin/caddy /caddy
