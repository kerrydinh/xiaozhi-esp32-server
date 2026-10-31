"""Streaming TTS provider for a VieNeu-TTS server (installed by the stack's init image).

VieNeu-TTS serves an OpenAI-compatible POST /v1/audio/speech that streams audio
while it is generated. The built-in "openai" provider waits for the whole
sentence before playing it; this one requests raw PCM at the device's sample
rate and encodes it to Opus frame by frame as it arrives, so playback starts
after the first chunk.

Config (same shape as the "openai" TTS type):
    api_url   e.g. http://<host>:8010/v1/audio/speech
    api_key   the server's VIENEU_API_KEY (empty if it has none)
    model     reported back by the server; default vieneu-v3-turbo
    voice     preset name from GET /v1/voices (overridden by the agent's voice)
"""
import threading
import time

import requests

from config.logger import setup_logging
from core.providers.tts.base import TTSProviderBase
from core.providers.tts.dto.dto import SentenceType
from core.utils.tts import MarkdownCleaner
from core.utils.util import check_model_key

TAG = __name__
logger = setup_logging()

# Sample rates the server can stream directly (it resamples from 48 kHz)
SAMPLE_RATES = (8000, 16000, 24000, 48000)
FRAME_MS = 60
MAX_ATTEMPTS = 3


class TTSProvider(TTSProviderBase):
    def __init__(self, config, delete_audio_file):
        super().__init__(config, delete_audio_file)
        self.api_url = config.get("api_url", "http://127.0.0.1:8010/v1/audio/speech")
        self.api_key = config.get("api_key", "")
        self.model = config.get("model") or "vieneu-v3-turbo"
        self.voice = config.get("private_voice") or config.get("voice") or None
        self.audio_file_type = "wav"
        self.output_file = config.get("output_dir", "tmp/")

        model_key_msg = check_model_key("TTS", self.api_key)
        if model_key_msg:
            logger.bind(tag=TAG).error(model_key_msg)

    def _headers(self):
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _payload(self, text, response_format, sample_rate):
        return {
            "model": self.model,
            "input": text,
            "voice": self.voice,
            "response_format": response_format,
            "sample_rate": sample_rate,
        }

    def to_tts_stream(self, text, opus_handler=None) -> None:
        original_text = text
        text = MarkdownCleaner.clean_markdown(text)
        if self._correct_words_pattern:
            text = self._correct_words_pattern.sub(lambda m: self.correct_words[m.group(0)], text)
        if not text.strip():
            return None

        for attempt in range(1, MAX_ATTEMPTS + 1):
            state = {"started": False}
            try:
                self._stream_sentence(text, original_text, opus_handler, state)
                return None
            except Exception as e:
                if state["started"]:
                    # Part of the sentence already played; repeating it would be worse
                    logger.bind(tag=TAG).error(f"语音生成中断: {original_text}，错误: {e}")
                    return None
                logger.bind(tag=TAG).warning(f"语音生成失败{attempt}次: {original_text}，错误: {e}")
                if attempt < MAX_ATTEMPTS:
                    time.sleep(attempt)
        logger.bind(tag=TAG).error(f"语音生成失败: {original_text}，请检查网络或服务是否正常")
        return None

    def _stream_sentence(self, text, original_text, opus_handler, state):
        sample_rate = self.conn.sample_rate
        if sample_rate not in SAMPLE_RATES:
            raise ValueError(f"device sample rate {sample_rate} not in {SAMPLE_RATES}")
        frame_bytes = sample_rate * FRAME_MS // 1000 * 2  # 16-bit mono
        sentence_id = getattr(self, "current_sentence_id", None)
        start = time.monotonic()
        first_audio = None

        resp = requests.post(
            self.api_url,
            json=self._payload(text, "pcm", sample_rate),
            headers=self._headers(),
            stream=True,
            timeout=(5, self.tts_timeout),
        )
        handed_off = False
        try:
            if resp.status_code != 200:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
            pending = bytearray()
            chunks = resp.iter_content(chunk_size=None)
            for chunk in chunks:
                if self.conn.client_abort:
                    # The server notices a closed connection only after its queue
                    # timeout and holds its single CPU slot until then; reading the
                    # rest in the background frees it as soon as the sentence is
                    # generated. Hand over the iterator itself: dropping it would
                    # close the connection.
                    logger.bind(tag=TAG).info(f"语音生成被打断: {original_text}")
                    threading.Thread(target=self._drain, args=(resp, chunks), daemon=True).start()
                    handed_off = True
                    return
                if not chunk:
                    continue
                if not state["started"]:
                    state["started"] = True
                    first_audio = time.monotonic() - start
                    self.tts_audio_queue.put((SentenceType.FIRST, None, original_text, sentence_id))
                pending.extend(chunk)
                whole = len(pending) - len(pending) % frame_bytes
                if whole:
                    self._emit(bytes(pending[:whole]), False, frame_bytes, opus_handler)
                    del pending[:whole]
        finally:
            if not handed_off:
                resp.close()

        if not state["started"]:
            raise RuntimeError("server returned no audio")
        del pending[len(pending) - len(pending) % 2 :]  # whole samples only
        self._emit(bytes(pending), True, frame_bytes, opus_handler)
        logger.bind(tag=TAG).info(
            f"语音生成成功: {original_text}，首包 {first_audio:.2f}s，总计 {time.monotonic() - start:.2f}s"
        )

    @staticmethod
    def _drain(resp, chunks):
        try:
            for _ in chunks:
                pass
        except Exception as e:
            logger.bind(tag=TAG).debug(f"VieNeu drain stopped: {e}")
        finally:
            resp.close()

    def _emit(self, pcm, end_of_stream, frame_bytes, callback):
        """Send whole 60 ms frames as Opus (or raw PCM for PCM clients)."""
        if self.conn.audio_format == "pcm":
            for i in range(0, len(pcm), frame_bytes):
                frame = pcm[i : i + frame_bytes]
                callback(frame.ljust(frame_bytes, b"\x00"))
        elif pcm:
            # Whole frames are encoded at once; a short final frame is zero-padded
            self.opus_encoder.encode_pcm_to_opus_stream(pcm, end_of_stream=end_of_stream, callback=callback)

    async def text_to_speak(self, text, output_file):
        """Whole-sentence WAV, for callers that need a file or bytes (to_tts)."""
        resp = requests.post(
            self.api_url,
            json=self._payload(text, "wav", 24000),
            headers=self._headers(),
            timeout=(5, self.tts_timeout),
        )
        if resp.status_code != 200:
            raise Exception(f"VieNeu TTS请求失败: {resp.status_code} - {resp.text[:200]}")
        if output_file:
            with open(output_file, "wb") as f:
                f.write(resp.content)
            return None
        return resp.content
