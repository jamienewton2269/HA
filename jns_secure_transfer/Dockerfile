ARG BUILD_FROM=ghcr.io/home-assistant/base:latest
FROM ${BUILD_FROM}

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
