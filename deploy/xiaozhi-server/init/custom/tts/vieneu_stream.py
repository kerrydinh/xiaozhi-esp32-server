"""Streaming TTS provider for a VieNeu-TTS server (installed by the stack's init image).

VieNeu-TTS serves an OpenAI-compatible POST /v1/audio/speech that streams audio
while it is generated. The built-in "openai" provider waits for the whole
sentence before playing it; this one requests raw PCM at the device's sample
rate and encodes it to Opus frame by frame as it arrives, so playback starts
after the first chunk.

The server sends audio to the device in real time with almost no buffer, so
when VieNeu generates slower than real time (rtf > 1, e.g. on a NAS CPU)
playback would catch up and stutter. Each sentence's audio is therefore held
back until the buffer covers (rtf - 1) x the rest of the sentence (+ a small
margin): just enough that playback never runs dry. rtf comes from earlier
sentences and the current sentence's own pace; the sentence's length is
estimated from its text. At rtf < 0.9 nothing is held back.

Config (same shape as the "openai" TTS type):
    api_url   e.g. http://<host>:8010/v1/audio/speech
    api_key   the server's VIENEU_API_KEY (empty if it has none)
    model     reported back by the server; default vieneu-v3-turbo
    voice     preset name from GET /v1/voices (overridden by the agent's voice)
    buffer_margin  optional, seconds of extra head start (default 1.0); raise it
                   if speech still stutters, lower it for an earlier start
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
# Extra audio to hold back for uneven generation speed. With rtf varying
# 1.0-1.5 within sentences, 0.3-0.6 s still left short stalls and 1.0 s none;
# config "buffer_margin" overrides it.
BUFFER_MARGIN_S = 1.0
DURATION_SAFETY = 1.15  # overestimate a sentence's length rather than underestimate it


class TTSProvider(TTSProviderBase):
    # Shared by all connections (one VieNeu server); updated after each sentence.
    # Starting values are on the slow side, so the first sentence does not stutter.
    rtf = 1.25  # generation seconds per second of audio
    chars_per_second = 15.0  # speaking rate, to estimate a sentence's duration


    def __init__(self, config, delete_audio_file):
        super().__init__(config, delete_audio_file)
        self.api_url = config.get("api_url", "http://127.0.0.1:8010/v1/audio/speech")
        self.api_key = config.get("api_key", "")
        self.model = config.get("model") or "vieneu-v3-turbo"
        self.voice = config.get("private_voice") or config.get("voice") or None
        self.audio_file_type = "wav"
        self.output_file = config.get("output_dir", "tmp/")
        margin = config.get("buffer_margin")
        self.buffer_margin = float(margin) if margin not in (None, "") else BUFFER_MARGIN_S

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
        bytes_per_second = sample_rate * 2
        expected = len(text) / TTSProvider.chars_per_second * DURATION_SAFETY
        start = time.monotonic()
        first_audio = None
        held_for = None  # seconds between the first audio and the start of playback
        held = bytearray()  # audio received but not yet released to the device
        received = 0

        def release(pcm, end_of_stream):
            nonlocal held_for
            if not state["started"]:
                state["started"] = True
                held_for = time.monotonic() - start - first_audio
                self.tts_audio_queue.put((SentenceType.FIRST, None, original_text, sentence_id))
            self._emit(pcm, end_of_stream, frame_bytes, opus_handler)

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
                if first_audio is None:
                    first_audio = time.monotonic() - start
                received += len(chunk)
                pending.extend(chunk)
                whole = len(pending) - len(pending) % frame_bytes
                if not whole:
                    continue
                held.extend(pending[:whole])
                del pending[:whole]
                if state["started"] or self._ready(
                    received / bytes_per_second, time.monotonic() - start - first_audio, expected
                ):
                    release(bytes(held), False)
                    held.clear()
        finally:
            if not handed_off:
                resp.close()

        if first_audio is None:
            raise RuntimeError("server returned no audio")
        total = time.monotonic() - start
        held.extend(pending[: len(pending) - len(pending) % 2])  # whole samples only
        release(bytes(held), True)
        audio_seconds = received / bytes_per_second
        self._learn(text, total - first_audio, audio_seconds)
        logger.bind(tag=TAG).info(
            f"语音生成成功: {original_text}，首包 {first_audio:.2f}s，缓冲 {held_for:.2f}s，"
            f"总计 {total:.2f}s，音频 {audio_seconds:.2f}s，rtf {TTSProvider.rtf:.2f}"
        )

    def _ready(self, buffered, elapsed, expected):
        """Whether playback can start now without catching up with generation.

        buffered: seconds of audio received so far; elapsed: seconds since the
        first audio; expected: estimated length of the sentence in seconds.
        Playing the rest takes `remaining` seconds while generating it takes
        rtf x remaining, so the buffer must cover (rtf - 1) x remaining.
        """
        rtf = TTSProvider.rtf
        if elapsed > 0.3 and buffered > 0.3:
            rtf = max(rtf, elapsed / buffered)  # this sentence's own pace so far
        if rtf < 0.9:
            return True
        remaining = max(0.0, expected - buffered)
        return buffered >= (rtf - 1.0) * remaining + self.buffer_margin

    @staticmethod
    def _learn(text, generation_seconds, audio_seconds):
        if audio_seconds < 0.5:  # too short to say much
            return
        cls = TTSProvider
        rtf = min(max(generation_seconds / audio_seconds, 0.3), 3.0)
        cps = min(max(len(text) / audio_seconds, 5.0), 40.0)
        weight = 0.7 if rtf > cls.rtf else 0.3  # follow a slowdown quickly, a speed-up slowly
        cls.rtf = (1 - weight) * cls.rtf + weight * rtf
        cls.chars_per_second = 0.5 * cls.chars_per_second + 0.5 * cps

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
