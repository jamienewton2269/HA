FROM ghcr.io/home-assistant/base:latest

LABEL \
    io.hass.version="0.2.2" \
    io.hass.type="app" \
    io.hass.arch="aarch64|amd64" \
    io.hass.name="JNS Secure Transfer Gateway" \
    io.hass.description="Secure SFTP ingress and validated JNS package handoff for Home Assistant." \
    io.hass.url="https://github.com/jamienewton2269/HA" \
    org.opencontainers.image.title="JNS Secure Transfer Gateway" \
    org.opencontainers.image.version="0.2.2" \
    org.opencontainers.image.source="https://github.com/jamienewton2269/HA"

RUN apk add --no-cache \
    openssh-server \
    python3 \
    py3-cryptography \
    bash \
    jq \
    ca-certificates \
    coreutils

COPY run.sh /run.sh
COPY jns_handoff.py /opt/jns/jns_handoff.py

RUN chmod 0755 /run.sh /opt/jns/jns_handoff.py

CMD ["/run.sh"]
