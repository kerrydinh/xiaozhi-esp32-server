# MCP tools for XiaoZhi agents (Brave Search)

Gives a XiaoZhi agent web and news search through
[Brave Search](https://brave.com/search/api/). It runs Brave's official MCP
server (`@brave/brave-search-mcp-server`, stdio) and `mcp_bridge.py`, which
connects it to the agent's address on the [XiaoZhi stack's](../xiaozhi-server/)
MCP endpoint.

```
device ⇄ xiaozhi server ⇄ mcp-endpoint (8004) ⇄ mcp-bridge ⇄ brave-search-mcp-server ⇄ Brave API
```

## Requirements

- The XiaoZhi stack with its `mcp-endpoint` service, and *MCP endpoint*
  ticked under *Parameter Dictionary → System Function Config*.
- The agent's *Intent recognition* set to **LLM Autonomous Function
  Calling**; with other settings the LLM never sees MCP tools.
- A Brave Search API key: sign up at https://brave.com/search/api/, choose a
  plan, then create a key under *API keys*. Check the plan's monthly query
  allowance; every question that triggers a search uses one query.

## Run

1. In the console open *Agents → Configure role → Edit functions* and copy the
   **MCP endpoint** address (`ws://<host>:8004/mcp_endpoint/mcp/?token=...`).
   The token identifies the agent: keep it secret.
2. Create a Dockge stack `mcp-tools` from `compose.yaml`; in its `.env` (see
   `.env.example`) set `MCP_ENDPOINT` to that address and `BRAVE_API_KEY`.
3. Deploy. The log shows
   `brave-search: connected to the endpoint, started brave-search-mcp-server`.
   Under *Edit functions* the MCP endpoint section lists the Brave tools.
4. Restart the device (it loads the agent's tools when it connects) and ask,
   e.g. "Tìm tin tức mới nhất về Sydney" or "Search the web for ...".

The bridge reconnects by itself when the endpoint restarts.

`BRAVE_MCP_ENABLED_TOOLS` picks the tools offered (default
`brave_web_search brave_news_search`). Each tool's description is added to
the LLM prompt, so enable only what the agent needs. Others:
`brave_local_search`, `brave_place_search`, `brave_video_search`,
`brave_image_search`, `brave_summarizer`, `brave_llm_context` (some need a
paid Brave plan).

## More MCP servers

`mcp_config.json` lists the stdio servers to bridge (one endpoint connection
each), in the `mcpServers` format of XiaoZhi's `mcp_pipe.py`. To add your
own, put an `mcp_config.json` next to `compose.yaml`, uncomment the volume in
`compose.yaml` and redeploy. The image has Node.js 22 and Python 3, so
`"command": "npx", "args": ["-y", "<package>"]` works; `${VAR}` in `args` and
`env` is read from the container environment.

## Image

```sh
docker build --platform linux/amd64 -t ghcr.io/<owner>/xiaozhi-mcp-bridge:latest deploy/mcp-bridge
docker push ghcr.io/<owner>/xiaozhi-mcp-bridge:latest
```

Pinned versions: Node.js 22, `@brave/brave-search-mcp-server` 2.1.4,
`websockets` 15.0.1. The image holds no keys.
