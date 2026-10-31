# XiaoZhi on TrueNAS (Dockge): deployment guide

How the self-hosted XiaoZhi voice assistant is deployed on the TrueNAS box
(`192.168.8.122`) with Dockge, and how to rebuild or redeploy it.

## Overview

| Stack (Dockge) | What it runs | Host port(s) |
|---|---|---|
| `xiaozhi` | XiaoZhi server: device WebSocket, admin console + OTA, MySQL, Redis, MCP endpoint, one-shot `init` | 8000 (WebSocket), 8002 (console/OTA), 8003 (vision/MCP), 8004 (MCP endpoint) |
| `vieneu-tts` | VieNeu-TTS: Vietnamese text-to-speech, OpenAI-compatible API, CPU | 8010 |
| `mcp-tools` | MCP bridge: Brave web/news search for the agent, via the MCP endpoint | — (outgoing only) |
| `ollama` (existing) | Ollama `latest` on CPU: Qwen3-ASR speech recognition (+ Open WebUI on 3000) | 11434 |
| `ollama-2` (optional) | Ollama `0.24.0` on the Quadro P2000 GPU: local chat model | 11435 |

Voice path for one request: device → `xiaozhi` server → speech recognition
(Ollama Qwen3-ASR) → LLM (OpenAI, Gemini or local Ollama) → text-to-speech
(VieNeu-TTS or Edge TTS) → device.

## Files (`deploy/`)

Everything for these stacks lives in `deploy/`, each folder with its own
README. The `.env` files and `restore/` hold secrets and are git-ignored; they
exist only on the PC (and on the NAS).

| File | Use |
|---|---|
| `deploy/xiaozhi-server/compose.yaml` | Paste into the `xiaozhi` Dockge stack |
| `deploy/xiaozhi-server/.env` | Paste into the `xiaozhi` stack's `.env` editor (MySQL password, VieNeu key). Not in git; template: `.env.example` |
| `deploy/xiaozhi-server/restore/xiaozhi.sql` | Database dump from the first (PC) install; only for restoring. Not in git |
| `deploy/xiaozhi-server/init/` | Source of the `init` image: `init.sh`, English console data (`i18n/`), SQL additions (`sql/`), Ollama ASR provider (`custom/`) |
| `deploy/vieneu-tts/compose.yaml` | Paste into the `vieneu-tts` Dockge stack |
| `deploy/vieneu-tts/.env` | Paste into the `vieneu-tts` stack's `.env` editor. Not in git |
| `deploy/vieneu-tts/Dockerfile` | Layer on top of upstream's VieNeu-TTS CPU image |

## Images

| Image | Built from | Notes |
|---|---|---|
| `ghcr.io/xinnan-tech/xiaozhi-esp32-server:server_0.9.8`, `web_0.9.8` | upstream | Pulled as is; the server image is ~3.5 GB |
| `ghcr.io/kerrydinh/xiaozhi-server-init:latest` | `deploy/xiaozhi-server/init/` | Provisioning, English console data, Ollama ASR provider, extra voices, VieNeu entries |
| `ghcr.io/kerrydinh/vieneu-tts:cpu` | upstream VieNeu-TTS @ `04044e1b` + `deploy/vieneu-tts/Dockerfile` | ~2.7 GB |
| `ghcr.io/kerrydinh/xiaozhi-mcp-bridge:latest` | `deploy/mcp-bridge/` | Brave Search MCP server + bridge, ~470 MB |

Both `kerrydinh` packages must be **Public** (GitHub → Packages → package →
Package settings) so the NAS can pull them without logging in. They contain no
secrets.

### Rebuilding and pushing

Run on the PC from the root of this repo
(`E:\Development\Development\Projects\IoT\xiaozhi\xiaozhi-esp32-server`,
Docker Desktop running). Log in once with a GitHub token that has
`write:packages`:

```sh
echo <token> | docker login ghcr.io -u kerrydinh --password-stdin
```

`init` image (after any change under `deploy/xiaozhi-server/init/`):

```sh
docker build --platform linux/amd64 -t ghcr.io/kerrydinh/xiaozhi-server-init:latest deploy/xiaozhi-server/init
docker push ghcr.io/kerrydinh/xiaozhi-server-init:latest
```

VieNeu-TTS image (only when moving to a newer VieNeu-TTS commit):

```sh
docker build --platform linux/amd64 -t vieneu-tts-upstream:cpu -f docker/Dockerfile.cpu \
  https://github.com/pnnbao97/VieNeu-TTS.git#04044e1b8f822f946bafb2c88b716459f4164152
docker build --platform linux/amd64 -t ghcr.io/kerrydinh/vieneu-tts:cpu deploy/vieneu-tts
docker push ghcr.io/kerrydinh/vieneu-tts:cpu
```

After pushing, open the stack in Dockge and click **Update** to pull the new
image and restart.

## 1. Deploy VieNeu-TTS

Deploy this first so the `xiaozhi` stack can register it.

1. Dockge → **+ Compose** → name `vieneu-tts`.
2. Paste `deploy/vieneu-tts/compose.yaml` into the compose editor and
   `deploy/vieneu-tts/.env` into the `.env` editor.
3. **Deploy**. The first start downloads the v3 Turbo model (~0.5 GB) into
   the `hf_cache` volume; later starts take about a minute.
4. Check `http://192.168.8.122:8010/health` → `"status":"ok"`.

`.env` settings:

| Variable | Value | Notes |
|---|---|---|
| `VIENEU_IMAGE` | `ghcr.io/kerrydinh/vieneu-tts:cpu` | |
| `VIENEU_PORT` | `8010` | 8000 is taken by XiaoZhi |
| `VIENEU_API_KEY` | random string | Must equal `VIENEU_TTS_API_KEY` in the `xiaozhi` `.env` |
| `VIENEU_PRECISION` | `fp32` | `int8` is ~2x faster but needs a CPU with VNNI; check with `grep -o -m1 'avx512_vnni\|avx_vnni' /proc/cpuinfo` (no output = keep `fp32`, int8 would garble audio) |
| `TZ` | `Australia/Sydney` | |

It runs on CPU because the GPU build needs a newer GPU and NVIDIA driver than
the P2000 / driver 550. The NAS CPU has no VNNI, so keep `fp32`. It generates
one sentence at a time, at `rtf` ~1.2 on the NAS (`done: ... rtf=1.2` in its
log = 1.2 s of work per 1 s of audio), i.e. slower than real time.

XiaoZhi streams it (provider `vieneu_stream`, see `VIENEU_TTS_STREAM` below)
instead of waiting for whole sentences (~5 s). Because generation is slower
than playback, the provider holds back the start of each sentence just long
enough that playback never catches up: (rtf - 1) x the rest of the sentence,
plus an *Extra buffer* (default 1.0 s). It learns rtf from recent sentences.
On a CPU like the NAS's, a sentence starts ~1.5-2 s after it is sent and
plays without gaps. Tune *Extra buffer* in *Model Config → Text-to-Speech →
VieNeu-TTS (Vietnamese)*: raise it if speech still stutters, lower it (e.g.
0.5) for an earlier start. The server log shows each sentence as
`语音生成成功: <text>，首包 <first audio>s，缓冲 <held>s，... rtf <estimate>`.
VieNeu is Vietnamese only; use Edge TTS for English.

## 2. Deploy the XiaoZhi server

1. Dockge → **+ Compose** → name `xiaozhi`.
2. Paste `deploy/xiaozhi-server/compose.yaml` and `deploy/xiaozhi-server/.env`.
3. Choose one:
   - **Restore the existing setup** (accounts, agent, bound device, model
     settings): click **Save** (not Deploy). Copy `deploy/xiaozhi-server/restore/xiaozhi.sql` into
     the stack folder on the NAS as `restore/xiaozhi.sql` (SMB, or
     `scp` + TrueNAS shell). Then **Deploy**. MySQL imports it only while
     creating an empty database.
   - **Fresh install:** click **Deploy**. Open `http://192.168.8.122:8002`
     and register; the first account becomes the super admin.
4. The first start pulls ~4 GB of images. Watch the `init` container log; it
   ends with `[init] Done`, after which `server` starts. Expected lines:
   ```
   [init] Device URLs: ws://192.168.8.122:8000/xiaozhi/v1/ , OTA http://192.168.8.122:8002/xiaozhi/ota/
   [init] Applied English console data
   [init] ASR model 'Ollama Qwen3-ASR' available (...)
   [init] TTS model 'VieNeu-TTS (Vietnamese)' available (...)
   [init] Done
   ```
5. After a restore works, delete `restore/xiaozhi.sql` from the NAS (it holds
   API keys and the password hash).

`.env` settings:

| Variable | Value | Notes |
|---|---|---|
| `XIAOZHI_VERSION` | `0.9.8` | Upstream release |
| `INIT_IMAGE` | `ghcr.io/kerrydinh/xiaozhi-server-init:latest` | |
| `PUBLIC_HOST` | `192.168.8.122` | Address the device uses; overrides the URLs in the console on every start |
| `WEB_PORT` / `WS_PORT` / `HTTP_PORT` | `8002` / `8000` / `8003` | |
| `MYSQL_ROOT_PASSWORD` | random | Only applied when the database is first created |
| `TZ` | `Australia/Sydney` | |
| `DATA_ROOT` | `.` | `mysql/`, `data/`, `models/`, `uploadfile/` under the stack folder |
| `CONSOLE_DATA_LANGUAGE` | `en` | Translates console data to English |
| `SENSEVOICE_DOWNLOAD` | `false` | Built-in FunASR model not needed (it cannot do Vietnamese) |
| `OLLAMA_ASR_URL` | `http://192.168.8.122:11434/v1/audio/transcriptions` | Creates *Ollama Qwen3-ASR* once |
| `OLLAMA_ASR_MODEL` | `hf.co/foryoung365/Qwen3-ASR-1.7B-Q4_K_M-GGUF` | Must be pulled in the `ollama` stack |
| `VIENEU_TTS_URL` | `http://192.168.8.122:8010/v1/audio/speech` | Creates *VieNeu-TTS (Vietnamese)* and its 25 voices once |
| `VIENEU_TTS_API_KEY` | same as `VIENEU_API_KEY` | Only used when the TTS entry is created; later fix the key in the console (*Model Config → Text-to-Speech*) |
| `MCP_PORT` | `8004` | MCP endpoint host port; `init` writes it into `server.mcp_endpoint` |
| `MCP_ENDPOINT_VERSION` | `0.0.7` | `mcp-endpoint-server` image tag |
| `VIENEU_TTS_STREAM` | `true` (default) | `true` = stream VieNeu audio (`vieneu_stream`); `false` = built-in OpenAI TTS, waits for whole sentences. Applied on every start |

The ASR and TTS entries are created once (if missing); after that, edit them
in the console under *Model Config*. `init` runs on every deploy and is safe
to re-run.

## 3. Point the device at the server

1. Triple-click the device's power button to enter Wi-Fi configuration mode.
2. Join the `Xiaozhi-xxxx` hotspot and open the portal; under **Advanced** set
   the OTA URL to `http://192.168.8.122:8002/xiaozhi/ota/`, save, reboot.
3. Restored install: the device connects straight away. Fresh install: it
   shows a 6-digit code; in the console go to *Agents → (agent) → Manage
   devices / Add device* and enter it.

## 4. Configure the agent

Console `http://192.168.8.122:8002` → *Agents* → *Configure role*.

| Setting | Choice | Notes |
|---|---|---|
| Speech recognition (ASR) | **Ollama Qwen3-ASR** | Vietnamese + English, runs on the `ollama` stack |
| Large language model | **ChatGPT** / **Gemini** / local Ollama | See below |
| Intent recognition | **LLM Autonomous Function Calling** with ChatGPT/Gemini; **No Intent Recognition** with small local models | Small models misuse the tools and answer in Chinese |
| Memory | **No Memory**, or *Local Short-term Memory* with its `llm` pointed at your LLM entry | *Mem0AI* needs its own API key |
| Text-to-speech | **VieNeu-TTS (Vietnamese)** + a voice (e.g. Ngọc Huyền, Mai Anh), or **Edge TTS** + Language Vietnamese/English | |
| Role prompt | e.g. `Bạn là trợ lý giọng nói thân thiện. Luôn trả lời ngắn gọn bằng tiếng Việt.` | |

Save, then restart the device (or wait for it to reconnect).

### LLM entries (*Model Config → Large Language Model → Add*)

ChatGPT and Ollama use provider **OpenAI API**; Gemini uses **Gemini
(OpenAI-compatible, tool calls)**. The server appends `/chat/completions` to
`base_url`, so never include it (or `/responses`).

| Name | Provider | base_url | model_name | api_key |
|---|---|---|---|---|
| ChatGPT | OpenAI API | `https://api.openai.com/v1` | a fast "mini" model | OpenAI API key (platform.openai.com; needs API credit, separate from a ChatGPT subscription) |
| Gemini | Gemini (OpenAI-compatible, tool calls) | `https://generativelanguage.googleapis.com/v1beta/openai` | a Flash model, e.g. a Gemini 3 Flash or `gemini-2.5-flash` | Key from aistudio.google.com/apikey |
| Local Ollama (GPU) | OpenAI API | `http://192.168.8.122:11435/v1` | e.g. `llama3.2:3b` | `ollama` |

Use these instead of the built-in *Google Gemini* / *Ollama* providers. Fast
models matter for voice: LLM latency is silence on the device.

Gemini 3 models reject a tool result unless the function call is sent back
with its *thought signature* (error `Function call is missing a
thought_signature`); the server drops it. The Gemini provider
(`init/custom/llm/gemini_openai`, type `gemini_openai`) records the signatures
and puts them back. `init` switches every *OpenAI API* entry whose base_url is
Gemini's to it on each start, so an entry created with *OpenAI API* is fixed
automatically.

## MCP endpoint (your own tools for the agent)

The `mcp-endpoint` service (xinnan-tech's `mcp-endpoint-server`, port 8004)
lets MCP tools running anywhere on the network (a PC, the NAS, a Home
Assistant box) give the agent new abilities. `init` creates its secret key in
`mcp-endpoint/.mcp-endpoint-server.cfg` (stack folder) and sets the console
parameter `server.mcp_endpoint` to
`http://192.168.8.122:8004/mcp_endpoint/health?key=...`.

1. Console → *Parameter Dictionary → System Function Config*: tick **MCP
   endpoint** and save (once).
2. *Agents → Configure role → Edit functions*: the **MCP endpoint** section
   shows this agent's address, `ws://192.168.8.122:8004/mcp_endpoint/mcp/?token=...`.
   The token identifies the agent; treat the address like a password.
3. Run MCP tools connected to that address: the `mcp-tools` stack below, or
   e.g. the XiaoZhi sample [mcp-calculator](https://github.com/78/mcp-calculator)
   (`MCP_ENDPOINT='ws://...'` then `python mcp_pipe.py calculator.py`).
4. Reconnect the device (it loads the agent's tools when it connects) and ask
   it to use the tool. Intent recognition must be *LLM Autonomous Function
   Calling*.

Check the service: `http://192.168.8.122:8004/mcp_endpoint/health?key=<key>`
answers `"status":"success"`.

### Web search: `mcp-tools` stack (Brave Search)

`deploy/mcp-bridge/` runs Brave's MCP server and connects it to the agent's
MCP endpoint address (details in its README).

1. Get a Brave Search API key: https://brave.com/search/api/ → plan →
   *API keys*. Each search the agent does uses one query of the plan.
2. Dockge → **+ Compose** → `mcp-tools`; paste `deploy/mcp-bridge/compose.yaml`
   and, as `.env`, `deploy/mcp-bridge/.env.example` with `MCP_ENDPOINT` (the
   agent's address from step 2 above) and `BRAVE_API_KEY` filled in.
3. **Deploy**; the log shows `brave-search: connected to the endpoint`.
4. Restart the device and ask e.g. "Tìm tin tức mới nhất về Sydney".

By default the agent gets `brave_web_search` and `brave_news_search`
(`BRAVE_MCP_ENABLED_TOOLS`). Other MCP servers can be added through
`mcp_config.json` (see the README).

## Ollama stacks

- `ollama` (`ollama/ollama:latest`, CPU, port 11434): serves Qwen3-ASR; set
  `OLLAMA_KEEP_ALIVE: 30m` so the first request is not slow. Pull the model
  once: `docker exec ollama ollama pull hf.co/foryoung365/Qwen3-ASR-1.7B-Q4_K_M-GGUF`.
- Current Ollama cannot use the P2000: Ollama ≥ 0.30 needs NVIDIA driver ≥ 570
  for Pascal GPUs and TrueNAS ships 550 (newer TrueNAS drops Pascal entirely).
- `ollama-2` (`ollama/ollama:0.24.0`, GPU, port 11435) still runs on the P2000
  and is for a local chat model only (0.24 cannot run Qwen3-ASR). Pull models
  into it with `docker exec ollama-2 ollama pull <model>` and check
  `docker exec ollama-2 ollama ps` shows `100% GPU`. Only this stack should
  reserve the GPU.
- One Open WebUI can use both: *Admin Panel → Settings → Connections → Ollama
  API → +* `http://192.168.8.122:11435`.

## Updating

- **XiaoZhi upstream release:** back up the stack's `mysql/` folder, change
  `XIAOZHI_VERSION` in `.env`, click **Update**. The API migrates the database
  on start. Rows added by a new release may stay in Chinese until the English
  data in `init` is extended.
- **init or VieNeu image:** rebuild and push (see *Rebuilding and pushing*),
  then **Update** the stack.

## Backing up / moving

Dump the database from the TrueNAS shell (container name as shown in Dockge):

```sh
sudo docker exec xiaozhi-db-1 sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysqldump -uroot --single-transaction --databases xiaozhi_esp32_server' > xiaozhi.sql
```

To restore on a new host, follow step 2 with that file as
`restore/xiaozhi.sql`, set `PUBLIC_HOST` to the new address, and repoint the
device (step 3).

## Troubleshooting

Read the `server` container log in Dockge. The server logs in Chinese; useful
markers: `大模型收到用户消息` (LLM received the user's message), `识别文本`
(recognised text), `语音生成失败` (speech generation failed).

| Symptom | Cause / fix |
|---|---|
| Device says it is busy, or ~10 s silence then nothing | The LLM call failed; the next `ERROR` line after `大模型收到用户消息` says why. The fallback reply is Chinese, which a Vietnamese voice cannot speak, so TTS also fails and retries. |
| `404 Invalid URL (POST /v1/responses/chat/completions)` | `base_url` must end in `/v1` (OpenAI) or `/v1beta/openai` (Gemini) |
| `400 ... Function call is missing a thought_signature` (Gemini 3, after a tool call) | The Gemini entry must use provider *Gemini (OpenAI-compatible, tool calls)*; `init` switches entries with Gemini's base_url on start, so redeploy the stack with the current init image |
| `'ascii' codec can't encode` from memory (`powermem`, `mem0ai`) | The memory module still has its placeholder key `你的...`: set Memory to *No Memory* or configure it |
| `429 ... credit_balance_exhausted` / `insufficient_quota` | Add API credit at platform.openai.com → Billing |
| Header/ascii error with `你的api_key` | The API key field still holds the placeholder |
| Replies in Chinese / calls "exit" on hello | Small local model confused by the tool descriptions: set Intent to *No Intent Recognition*, or use ChatGPT/Gemini |
| `Mem0ai 的 API key 未设置` | Memory is *Mem0AI* without a key: choose *No Memory* |
| First reply after a pause is slow | Ollama unloaded the ASR model: `OLLAMA_KEEP_ALIVE` on the `ollama` stack |
| VieNeu: `401` | `VIENEU_TTS_API_KEY` / the TTS entry's API key differs from `VIENEU_API_KEY` |
| VieNeu: `400 unknown voice` | Voice name must match `GET /v1/voices` exactly (with diacritics) |
| VieNeu: `429` | Requests queued too long on CPU; raise `VIENEU_QUEUE` or use Edge TTS |
| VieNeu audio stutters mid-sentence | Generation speed varies more than the head start covers: raise *Extra buffer* on the VieNeu-TTS model (e.g. 1.5), or `VIENEU_TTS_STREAM=false` (no gaps, ~5 s wait per sentence) |
| Long pause before each VieNeu sentence | The head start for a slow CPU; lower *Extra buffer* (e.g. 0.5) if speech stays smooth, keep replies short, or use Edge TTS |
| Reply after interrupting the device starts late | Expected: VieNeu (one CPU slot) first finishes the interrupted sentence, then the next |
| VieNeu container restarts on first start | Model download still running or failed; check its log and `/health` |
| MySQL fails with a permission error | Stack folder is on an SMB-shared dataset with restricted ACLs: set `DATA_ROOT` to a dataset with the Apps preset |
| Console edits to the WebSocket/OTA URL revert | Expected: `PUBLIC_HOST` in `.env` is the source of truth |
