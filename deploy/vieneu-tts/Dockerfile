# VieNeu-TTS speech API (CPU, ONNX) on top of upstream's CPU image.
#
# Upstream publishes no v3 image, so build theirs first (pinned commit), then this:
#   docker build --platform linux/amd64 -t vieneu-tts-upstream:cpu -f docker/Dockerfile.cpu \
#     https://github.com/pnnbao97/VieNeu-TTS.git#04044e1b8f822f946bafb2c88b716459f4164152
#   docker build --platform linux/amd64 -t ghcr.io/<owner>/vieneu-tts:cpu deploy/vieneu-tts
ARG BASE=vieneu-tts-upstream:cpu
FROM ${BASE}

# The model cache is a volume; create it owned by the app user so a new volume
# inherits that owner (otherwise the first model download fails as root-owned).
USER root
RUN mkdir -p /home/app/.cache/huggingface && chown -R app:app /home/app/.cache
USER app

ENV HOST=0.0.0.0 \
    PORT=8000 \
    VIENEU_BACKEND=onnx
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=300s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else 1)"
CMD ["python", "-m", "apps.openai_speech"]
