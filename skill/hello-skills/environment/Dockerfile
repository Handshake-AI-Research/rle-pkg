FROM ubuntu:24.04

RUN apt-get update && apt-get install -y \
    bash curl sudo \
    && rm -rf /var/lib/apt/lists/*

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

# Copy skills into the container at /skills so Harbor can distribute them
# to the agent's skills directory via the skills_dir config.
COPY skills/ /skills/

USER agent
WORKDIR /app
