# [Choice] Python version (use -bullseye variants on local arm64/Apple Silicon): 3, 3.11, 3.10, 3.9, 3.8, 3-bullseye, 3.11-bullseye, 3.10-bullseye, 3.9-bullseye, 3.8-bullseye
ARG VARIANT="3.11-bookworm"
FROM mcr.microsoft.com/devcontainers/python:${VARIANT}

# Node.js is not needed for this CLI package
ARG NODE_VERSION="none"

# Install uv - fast Python package installer
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    mkdir -p /usr/local/bin && \
    if [ -f /root/.cargo/bin/uv ]; then \
        mv /root/.cargo/bin/uv /usr/local/bin/uv; \
    elif [ -f /root/.local/bin/uv ]; then \
        mv /root/.local/bin/uv /usr/local/bin/uv; \
    fi && \
    chmod +x /usr/local/bin/uv && \
    uv --version
