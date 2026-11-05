# Competition sandbox (data/docker/Dockerfile.public) with two changes:
# - apt skips its _apt user, which rootless Podman with one user ID can't switch to.
# - typing-inspection is added because the competition's wheel set leaves it out.
# Build context: data/docker
FROM docker.io/library/python:3.13-slim

RUN echo 'APT::Sandbox::User "root";' > /etc/apt/apt.conf.d/90-sandbox-root \
    && apt-get update -qq \
    && apt-get install -y -qq --no-install-recommends git patch protobuf-compiler pigz \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir pytest pytest-timeout==2.1.0 typer pdm-backend setuptools wheel poetry-core hatchling flit-core editables typing-inspection==0.4.5 \
    && mkdir -p /wheels

COPY imp.py /usr/local/lib/python3.13/site-packages/imp.py
COPY telnetlib.py /usr/local/lib/python3.13/site-packages/telnetlib.py

RUN git config --global user.email "agent@eval" \
    && git config --global user.name "Agent" \
    && git config --global init.defaultBranch main

ENV TEST_TMPDIR=/tmp

WORKDIR /workspace

COPY wheels/ /wheels/
