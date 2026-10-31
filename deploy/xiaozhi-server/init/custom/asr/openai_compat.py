"""OpenAI-compatible transcription ASR (e.g. Ollama serving Qwen3-ASR).

Mounted into the server image as core/providers/asr/openai_compat.py and
selected with "type": "openai_compat". Unlike the upstream `openai` provider it
posts without blocking the event loop and removes the Qwen3-ASR language tags
("language Vietnamese<asr_text>...") that Ollama returns in `text`.
"""

import re
import time
from typing import List, Optional, Tuple

import aiohttp

from config.logger import setup_logging
from core.providers.asr.base import ASRProviderBase
from core.providers.asr.dto.dto import InterfaceType

TAG = __name__
logger = setup_logging()

# Qwen3-ASR prefixes each segment with "language <Name><asr_text>"
LANG_TAG = re.compile(r"language\s+([^<]*?)\s*<asr_text>", re.IGNORECASE)


def parse_transcript(raw: str) -> Tuple[str, Optional[str]]:
    """Split a Qwen3-ASR transcript into (text, language)."""
    languages = [lang for lang in LANG_TAG.findall(raw) if lang and lang.lower() != "none"]
    text = " ".join(part.strip() for part in LANG_TAG.split(raw)[::2] if part.strip())
    return text, (languages[0] if languages else None)


class ASRProvider(ASRProviderBase):
    def __init__(self, config: dict, delete_audio_file: bool):
        super().__init__()
        self.interface_type = InterfaceType.NON_STREAM
        self.api_url = config.get("base_url")
        self.model = config.get("model_name")
        self.api_key = config.get("api_key") or "none"
        self.timeout = float(config.get("timeout") or 60)
        self.output_dir = config.get("output_dir", "tmp/")
        self.delete_audio_file = delete_audio_file

    def requires_file(self) -> bool:
        return True

    def prefers_temp_file(self) -> bool:
        return True

    async def speech_to_text(
        self, opus_data: List[bytes], session_id: str, artifacts=None
    ) -> Tuple[Optional[object], Optional[str]]:
        if artifacts is None:
            return "", None
        wav_path = artifacts.temp_path or artifacts.file_path
        if not wav_path:
            return "", None

        try:
            start_time = time.time()
            with open(wav_path, "rb") as audio_file:
                form = aiohttp.FormData()
                form.add_field("model", self.model)
                form.add_field("file", audio_file, filename="audio.wav", content_type="audio/wav")
                async with aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as session:
                    async with session.post(
                        self.api_url,
                        data=form,
                        headers={"Authorization": f"Bearer {self.api_key}"},
                    ) as response:
                        body = await response.text()
                        if response.status != 200:
                            raise Exception(f"HTTP {response.status}: {body[:200]}")
                        raw = (await response.json(content_type=None)).get("text", "")

            text, language = parse_transcript(raw)
            logger.bind(tag=TAG).debug(
                f"ASR took {time.time() - start_time:.3f}s | raw: {raw}"
            )
            if not text:
                return "", artifacts.file_path
            # Same shape as FunASR: only "content" is passed on to the LLM
            result = {"content": text}
            if language:
                result["language"] = language
            return result, artifacts.file_path
        except Exception as e:
            logger.bind(tag=TAG).error(f"ASR request failed: {e}")
            return "", artifacts.file_path
