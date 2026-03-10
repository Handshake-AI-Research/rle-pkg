# Build stage: compile the trampoline
FROM ubuntu:24.04 AS build
RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*
COPY mcp-server-run.c /tmp/mcp-server-run.c
RUN gcc -o /tmp/mcp-server-run /tmp/mcp-server-run.c

# Main stage
FROM ubuntu:24.04

# Install base dependencies
RUN apt-get update && \
    apt-get install -y bash curl sudo && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Demonstrate pre-installing binaries and libraries for the agent
RUN apt-get update && \
    apt-get install -y python3 python3-pip && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*
RUN pip3 install --break-system-packages numpy

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Create users
#
# - environment (uid 10000): runs the MCP server
# - agent (uid 10001): runs the agent
# - verifier (uid 10002): runs the verifier
# - sandbox (uid 10003): runs the sandbox
#
# - environment is a member of the agent group so it can access the workspace
# - verifier is a member of the agent group so it can access the workspace
# - sandbox is a member of the verifier group so the verifier can share data with the sandbox
RUN useradd -m -u 10000 -d /home/environment -s /bin/bash environment && \
    useradd -m -u 10001 -d /home/agent -s /bin/bash agent && \
    useradd -m -u 10002 -d /home/verifier -s /bin/bash verifier && \
    useradd -m -u 10003 -d /home/sandbox -s /bin/bash sandbox && \
    usermod -aG agent environment && \
    usermod -aG agent verifier && \
    usermod -aG verifier sandbox

# Set up sudo: allow verifier to run commands as sandbox
RUN echo "verifier ALL=(sandbox) NOPASSWD: ALL" >> /etc/sudoers.d/verifier && \
    chmod 440 /etc/sudoers.d/verifier

# Set up the agent workspace directory
RUN mkdir -p /home/agent/workspace && chown -R agent:agent /home/agent && \
    chmod g+w /home/agent/workspace

# Set up /installed-agent owned by agent (for Harbor's installed agents)
RUN mkdir /installed-agent && chown -R agent:agent /installed-agent && chmod -R a+rw /installed-agent

# Set up /oracle directory (for Harbor's oracle agent)
RUN mkdir /oracle && chown -R agent:agent /oracle && chmod -R a+rw /oracle

# Copy and install the MCP server app and associated data, which runs as the environment user
COPY --chown=environment:environment mcp-server /opt/mcp-server
COPY --chown=environment:environment data /opt/mcp-server/data
USER environment
RUN cd /opt/mcp-server && uv sync
USER root

# Lock down /opt/mcp-server so only environment user can access it
RUN chmod 700 /opt/mcp-server

# Install the compiled trampoline
#
# This is a setuid binary that runs the MCP server as the environment user, so
# any user can execute it, and it runs as the environment user
COPY --from=build /tmp/mcp-server-run /usr/bin/mcp-server
RUN chown environment:environment /usr/bin/mcp-server && \
    chmod u+s /usr/bin/mcp-server

# Install the verifier
COPY verifier /tmp/verifier-src
RUN UV_TOOL_DIR=/opt/uv-tools UV_TOOL_BIN_DIR=/usr/local/bin \
    UV_PYTHON_INSTALL_DIR=/opt/uv-python \
    uv tool install /tmp/verifier-src && \
    rm -rf /tmp/verifier-src && \
    chmod -R a+rX /opt/uv-tools /opt/uv-python

WORKDIR /home/agent/workspace
CMD ["/bin/bash"]
