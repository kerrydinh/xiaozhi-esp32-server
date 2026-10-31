-- Additions owned by this stack; applied by init.sh on every start.
SET NAMES utf8mb4;

-- Provider for custom/asr/openai_compat.py (OpenAI-compatible /v1/audio/transcriptions,
-- strips Qwen3-ASR language tags). Lets the console create/edit models of this type.
INSERT INTO ai_model_provider (id, model_type, provider_code, name, fields, sort, creator, create_date, updater, update_date)
VALUES ('CUSTOM_ASR_OpenaiCompat', 'ASR', 'openai_compat', 'OpenAI-compatible ASR (Ollama)',
        '[{"key": "base_url", "type": "string", "label": "Transcriptions URL (.../v1/audio/transcriptions)"},
          {"key": "model_name", "type": "string", "label": "Model name"},
          {"key": "api_key", "type": "string", "label": "API key (any value for Ollama)"},
          {"key": "timeout", "type": "number", "label": "Timeout (s)"},
          {"key": "output_dir", "type": "string", "label": "Output directory"}]',
        99, 1, NOW(), 1, NOW())
ON DUPLICATE KEY UPDATE provider_code = VALUES(provider_code), name = VALUES(name), fields = VALUES(fields);

-- Provider for custom/llm/gemini_openai (Gemini's OpenAI-compatible API; keeps
-- Gemini 3 thought signatures on tool calls). Same fields as "OpenAI API".
INSERT INTO ai_model_provider (id, model_type, provider_code, name, fields, sort, creator, create_date, updater, update_date)
VALUES ('CUSTOM_LLM_GeminiOpenAI', 'LLM', 'gemini_openai', 'Gemini (OpenAI-compatible, tool calls)',
        '[{"key": "base_url", "type": "string", "label": "Base URL (https://generativelanguage.googleapis.com/v1beta/openai)"},
          {"key": "model_name", "type": "string", "label": "Model name"},
          {"key": "api_key", "type": "string", "label": "API key"},
          {"key": "temperature", "type": "number", "label": "Temperature"},
          {"key": "max_tokens", "type": "number", "label": "Max tokens"},
          {"key": "top_p", "type": "number", "label": "top_p value"},
          {"key": "frequency_penalty", "type": "number", "label": "Frequency penalty"}]',
        99, 1, NOW(), 1, NOW())
ON DUPLICATE KEY UPDATE provider_code = VALUES(provider_code), name = VALUES(name), fields = VALUES(fields);

-- LLM entries pointing at Gemini's OpenAI-compatible API use gemini_openai
-- (a superset of "openai": tool calls also work on Gemini 3).
UPDATE ai_model_config SET config_json = JSON_SET(config_json, '$.type', 'gemini_openai')
WHERE model_type = 'LLM' AND JSON_UNQUOTE(JSON_EXTRACT(config_json, '$.type')) = 'openai'
  AND JSON_UNQUOTE(JSON_EXTRACT(config_json, '$.base_url')) LIKE '%generativelanguage.googleapis.com%';

-- Provider for custom/tts/vieneu_stream.py (VieNeu-TTS, streamed as it is generated).
INSERT INTO ai_model_provider (id, model_type, provider_code, name, fields, sort, creator, create_date, updater, update_date)
VALUES ('CUSTOM_TTS_VieneuStream', 'TTS', 'vieneu_stream', 'VieNeu-TTS (streaming)',
        '[{"key": "api_url", "type": "string", "label": "Speech URL (.../v1/audio/speech)"},
          {"key": "api_key", "type": "string", "label": "API key (VIENEU_API_KEY)"},
          {"key": "model", "type": "string", "label": "Model"},
          {"key": "voice", "type": "string", "label": "Default voice"},
          {"key": "buffer_margin", "type": "number", "label": "Extra buffer (s, default 1.0): higher = smoother, later start"},
          {"key": "output_dir", "type": "string", "label": "Output directory"}]',
        99, 1, NOW(), 1, NOW())
ON DUPLICATE KEY UPDATE provider_code = VALUES(provider_code), name = VALUES(name), fields = VALUES(fields);

-- Extra Edge TTS voices (names max 20 chars). The "languages" value feeds the
-- agent's Language dropdown; Edge TTS itself only uses the voice code.
INSERT IGNORE INTO ai_tts_voice (id, tts_model_id, name, tts_voice, languages, sort) VALUES
  ('TTS_EdgeTTS_vi_HoaiMy',  'TTS_EdgeTTS', 'Vietnamese F HoaiMy',  'vi-VN-HoaiMyNeural',  'Vietnamese', 101),
  ('TTS_EdgeTTS_vi_NamMinh', 'TTS_EdgeTTS', 'Vietnamese M NamMinh', 'vi-VN-NamMinhNeural', 'Vietnamese', 102),
  ('TTS_EdgeTTS_en_Aria',    'TTS_EdgeTTS', 'English F Aria (US)',  'en-US-AriaNeural',    'English',    111),
  ('TTS_EdgeTTS_en_Guy',     'TTS_EdgeTTS', 'English M Guy (US)',   'en-US-GuyNeural',     'English',    112),
  ('TTS_EdgeTTS_en_Natasha', 'TTS_EdgeTTS', 'English F Natasha AU', 'en-AU-NatashaNeural', 'English',    113),
  ('TTS_EdgeTTS_en_Sonia',   'TTS_EdgeTTS', 'English F Sonia (UK)', 'en-GB-SoniaNeural',   'English',    114);
