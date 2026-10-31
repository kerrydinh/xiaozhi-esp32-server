# MCP tools for XiaoZhi agents: mcp_bridge.py connects stdio MCP servers to the
# stack's MCP endpoint. Ships the Brave Search MCP server.
#   docker build --platform linux/amd64 -t ghcr.io/<owner>/xiaozhi-mcp-bridge:latest deploy/mcp-bridge
FROM node:22-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir websockets==15.0.1 \
    && npm install -g @brave/brave-search-mcp-server@2.1.4 \
    && npm cache clean --force

WORKDIR /app
COPY mcp_bridge.py mcp_config.json ./
USER node
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    MCP_CONFIG=/app/mcp_config.json
CMD ["python", "mcp_bridge.py"]
