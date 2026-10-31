# Self-hosted XiaoZhi server (Docker / TrueNAS Dockge)

Runs the full [xinnan-tech/xiaozhi-esp32-server](https://github.com/xinnan-tech/xiaozhi-esp32-server)
stack: voice server, admin console (manager-web + manager-api), MySQL and Redis.

Compared with the upstream `docker-compose_all.yml`, this stack:

- needs no manual secret copy/paste or restart: a one-shot `init` service reads
  `server.secret`, writes `data/.config.yaml` and sets the device-facing
  WebSocket/OTA URLs from `.env`;
- downloads and checksums the SenseVoiceSmall ASR model;
- translates console data to English (see [English console](#english-console));
- pins image versions and keeps every setting in `.env`.

| Service  | Image | Port (host) | Purpose |
|----------|-------|-------------|---------|
| `server` | `ghcr.io/xinnan-tech/xiaozhi-esp32-server:server_<ver>` | 8000, 8003 | Device WebSocket, vision/MCP HTTP |
| `web`    | `ghcr.io/xinnan-tech/xiaozhi-esp32-server:web_<ver>` | 8002 | Admin console, management API, OTA |
| `db`     | `mysql:8.4` | — | Console database |
| `redis`  | `redis:8.0` | — | API cache |
| `init`   | `ghcr.io/kerrydinh/xiaozhi-server-init` (built from `init/`) | — | One-shot provisioning, exits when done |

Release 0.9.8 publishes amd64 and arm64 images. The first start downloads
about 4 GB of images (the server image alone is 3.5 GB compressed) plus the
0.9 GB ASR model.

## Install with Dockge on TrueNAS SCALE

Everything stack-specific is in the `init` image, so no files need copying.

1. Make sure the `init` image is published (see [Building the init image](#building-the-init-image)).
2. In Dockge, click **+ Compose**, name the stack `xiaozhi` and paste
   `compose.yaml`.
3. In the stack's `.env` editor paste the contents of `.env.example` and set at least:
   - `PUBLIC_HOST`: the TrueNAS LAN IP the ESP32 can reach;
   - `MYSQL_ROOT_PASSWORD`: a password of your choice (before the first start);
   - ports, if 8000/8002/8003 are used by other apps.
4. Click **Start**. The first start downloads ~4 GB of images and the ~900 MB
   ASR model; follow progress in the `init` log. `server` starts once `init` has
   exited successfully.
5. Open `http://<PUBLIC_HOST>:8002`, **register the first account: it becomes
   the super admin** (later sign-ups are normal users).
6. In the console, configure an LLM: *Model Config → LLM*, edit a provider and
   enter its API key (or point the OpenAI-compatible/Ollama provider at your
   own endpoint), then select it in your agent's role configuration.

Plain Docker works the same way: `cp .env.example .env`, edit, `docker compose up -d`.

## Building the init image

`init` runs from an image built from `init/`: the script, English console
data, `init/sql/custom.sql` and the providers in `init/custom/`. Rebuild and
push it after changing anything under `init/`:

```sh
docker build --platform linux/amd64 -t ghcr.io/<owner>/xiaozhi-server-init:latest deploy/xiaozhi-server/init
echo <token> | docker login ghcr.io -u <owner> --password-stdin   # token with write:packages
docker push ghcr.io/<owner>/xiaozhi-server-init:latest
```

The image holds no secrets. Make the package public in its GitHub package
settings so hosts can pull it without logging in, and set `INIT_IMAGE` if
`<owner>` is not `kerrydinh`. ARM hosts need a `linux/arm64` build
(`docker buildx build --platform linux/amd64,linux/arm64 --push ...`).

## Point the device at it

The OTA URL is `http://<PUBLIC_HOST>:<WEB_PORT>/xiaozhi/ota/`. On the device,
open the Wi-Fi configuration portal (hotspot `Xiaozhi-xxxx`), go to
**Advanced** and set the OTA URL, or build firmware with `CONFIG_OTA_URL` set
to it. The device then fetches the WebSocket URL from the server, shows a
6-digit code, and you bind it in the console under *Agents → Add device*.

## English console

The console UI itself ships an English translation (language menu, top
right). What upstream leaves in Chinese is data seeded into the database:
provider names, settings field labels, model help texts, firmware/country
dropdowns, parameter descriptions and role template names. With
`CONSOLE_DATA_LANGUAGE=en`, `init` applies `init/i18n/en.sql` on each start.

- Each update matches the row id **and** the exact original Chinese text, so
  values you edited in the console, or rows changed by a newer upstream
  release, are left alone. Rows added by newer releases stay Chinese until the
  translation is extended.
- Deliberately not translated, because the server uses them as values:
  config placeholders such as `你的api_key` (the server treats `你的` as
  "not configured"), TTS voice languages (`普通话` = Mandarin, passed to TTS
  engines), wake words, exit commands, and role system prompts. Voice names
  (vendor character names) are also left as is.
- To change or extend translations, edit `init/i18n/en.json`, run
  `python3 init/i18n/build_en_sql.py`, and restart the stack.

## Extras added by this stack

`init` also applies `init/sql/custom.sql` on every start:

- **Ollama / OpenAI-compatible speech recognition.** `init/custom/asr/openai_compat.py`
  is installed into the server as ASR type `openai_compat` (`init` puts it in
  `data/custom/`; the server copies it into its providers on start). It posts audio to any
  `/v1/audio/transcriptions` endpoint and strips the `language X<asr_text>` tags
  that Qwen3-ASR returns. The console lists it as provider
  *OpenAI-compatible ASR (Ollama)*. If `OLLAMA_ASR_URL` is set, `init` creates
  the ready-to-use model **Ollama Qwen3-ASR** once; pick it under *Speech
  Recognition* in the agent's role configuration. Qwen3-ASR handles Vietnamese
  and English; the bundled SenseVoice/FunASR model does not handle Vietnamese.
  The first request after Ollama unloads the model takes ~10 s; set
  `OLLAMA_KEEP_ALIVE` on the Ollama host to keep it loaded.
- **VieNeu-TTS (Vietnamese speech).** With `VIENEU_TTS_URL` set to a
  [VieNeu-TTS](../vieneu-tts/) server, `init` creates the TTS model
  **VieNeu-TTS (Vietnamese)** (provider *OpenAI TTS*) and its 25 preset voices
  (`init/sql/vieneu.sql`) once. Choose it under *Text-to-Speech* in the agent's
  role configuration, then a voice.
- **Extra Edge TTS voices:** Vietnamese (`vi-VN-HoaiMyNeural`,
  `vi-VN-NamMinhNeural`) and English (US, AU, UK). Choose *Text-to-Speech:
  Edge TTS*, then *Language: Vietnamese/English* and the voice.

## Moving to another host

To keep accounts, agents, bound devices and model settings, start the new
host from a dump of the old database:

1. On the old host:
   `docker exec xiaozhi-db-1 sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysqldump -uroot --single-transaction --databases xiaozhi_esp32_server' > restore/xiaozhi.sql`
2. On the new host, create the stack with its `.env` (`PUBLIC_HOST` set for
   that host) but do not start it; put the dump in the stack folder as
   `restore/xiaozhi.sql`.
3. Start the stack. MySQL imports `restore/*.sql` only while creating an
   empty database; `init` then rewrites the device URLs for the new host.
4. Change the device's OTA URL to the new host and restart it. The binding is
   kept.

The dump contains API keys and password hashes; delete `restore/xiaozhi.sql`
once the new host works.

## Configuration reference (`.env`)

| Variable | Default | Notes |
|----------|---------|-------|
| `XIAOZHI_VERSION` | `0.9.8` | Upstream release tag |
| `INIT_IMAGE` | `ghcr.io/kerrydinh/xiaozhi-server-init:latest` | Provisioning image built from `init/` |
| `PUBLIC_HOST` | — | LAN IP/host for device URLs; empty = set them in the console |
| `WEB_PORT` / `WS_PORT` / `HTTP_PORT` | 8002 / 8000 / 8003 | Host ports |
| `MYSQL_ROOT_PASSWORD` | — | Required; only applied when the database is first created |
| `TZ` | `Etc/UTC` | Container time zone |
| `DATA_ROOT` | `.` | Where `mysql/`, `data/`, `models/`, `uploadfile/` live |
| `CONSOLE_DATA_LANGUAGE` | `en` | `en` = translate console data; anything else = leave it |
| `SENSEVOICE_DOWNLOAD` | `true` | Download the local FunASR model; `false` if you only use remote ASR |
| `SENSEVOICE_URL` | Hugging Face | ModelScope mirror is listed in `.env.example` |
| `OLLAMA_ASR_URL` | — | e.g. `http://<ollama-host>:11434/v1/audio/transcriptions`; creates the *Ollama Qwen3-ASR* model once |
| `OLLAMA_ASR_MODEL` | — | Ollama model name, e.g. `hf.co/foryoung365/Qwen3-ASR-1.7B-Q4_K_M-GGUF` |
| `VIENEU_TTS_URL` | — | e.g. `http://<host>:8010/v1/audio/speech`; creates the *VieNeu-TTS (Vietnamese)* model once |
| `VIENEU_TTS_API_KEY` | — | The VieNeu server's `VIENEU_API_KEY` |

Notes:

- `.env` is the source of truth for `server.websocket`, `server.ota` and
  `server.fronted_url` while `PUBLIC_HOST` is set; edits to those three in the
  console are overwritten on the next start.
- `init` clears the API's Redis cache when it changed the database, which
  also ends open console sessions on that start.
- Upgrading: change `XIAOZHI_VERSION`, back up `mysql/`, then redeploy. The
  API migrates the database on start.
