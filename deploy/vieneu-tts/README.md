# VieNeu-TTS speech API (Docker / Dockge)

Runs [VieNeu-TTS](https://github.com/pnnbao97/VieNeu-TTS) v3 Turbo (Vietnamese
text-to-speech, 25 preset voices) on CPU as an OpenAI-compatible
`POST /v1/audio/speech` API, for the [XiaoZhi server stack](../xiaozhi-server/).

## Image

Upstream publishes no v3 image. Build upstream's CPU image at a pinned commit,
then the thin layer in this folder (fixes the model cache volume owner, makes
the speech API the default command), and push it:

```sh
docker build --platform linux/amd64 -t vieneu-tts-upstream:cpu -f docker/Dockerfile.cpu \
  https://github.com/pnnbao97/VieNeu-TTS.git#04044e1b8f822f946bafb2c88b716459f4164152
docker build --platform linux/amd64 -t ghcr.io/<owner>/vieneu-tts:cpu deploy/vieneu-tts
docker push ghcr.io/<owner>/vieneu-tts:cpu
```

The CPU image is used because the GPU image needs a recent NVIDIA driver and
GPU (PyTorch with CUDA 12.8).

## Run

1. Create a Dockge stack `vieneu-tts` from `compose.yaml`; in `.env` set
   `VIENEU_API_KEY` (any random string) and, if needed, `VIENEU_IMAGE`,
   `VIENEU_PORT` (default 8010).
2. Start it. The first start downloads the model (~0.5 GB) and is healthy once
   `GET /health` answers.
3. In the XiaoZhi stack's `.env` set
   `VIENEU_TTS_URL=http://<host>:8010/v1/audio/speech` and
   `VIENEU_TTS_API_KEY` to the same key, then redeploy it: `init` creates the
   TTS model *VieNeu-TTS (Vietnamese)* with all voices.

On CPU one sentence takes roughly 0.5-0.7x its spoken length to generate
(upstream's i5-12th gen figures); one request is served at a time and others
queue. `VIENEU_PRECISION=int8` is about twice as fast but needs a CPU with
AVX-VNNI or AVX512-VNNI (`grep -o -m1 'avx512_vnni\|avx_vnni' /proc/cpuinfo`),
otherwise audio can be garbled.
