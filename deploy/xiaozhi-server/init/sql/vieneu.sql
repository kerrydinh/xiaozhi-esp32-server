-- VieNeu-TTS v3 Turbo preset voices for the TTS_VieNeuTTS model (created by
-- init.sh when VIENEU_TTS_URL is set). tts_voice must match GET /v1/voices.
SET NAMES utf8mb4;

INSERT IGNORE INTO ai_tts_voice (id, tts_model_id, name, tts_voice, languages, remark, sort) VALUES
  ('TTS_VieNeu_01', 'TTS_VieNeuTTS', 'Adam bựa',      'Adam bựa',      'Vietnamese', 'Male, Northern, natural', 1),
  ('TTS_VieNeu_02', 'TTS_VieNeuTTS', 'Trúc Ly',       'Trúc Ly',       'Vietnamese', 'Female, Northern, natural', 2),
  ('TTS_VieNeu_03', 'TTS_VieNeuTTS', 'Thiện Minh',    'Thiện Minh',    'Vietnamese', 'Male, Northern, storytelling', 3),
  ('TTS_VieNeu_04', 'TTS_VieNeuTTS', 'Mai Anh',       'Mai Anh',       'Vietnamese', 'Female, Northern, news', 4),
  ('TTS_VieNeu_05', 'TTS_VieNeuTTS', 'Hải Đăng',      'Hải Đăng',      'Vietnamese', 'Male, Northern, natural (default)', 5),
  ('TTS_VieNeu_06', 'TTS_VieNeuTTS', 'Thùy Dung',     'Thùy Dung',     'Vietnamese', 'Female, Southern, news', 6),
  ('TTS_VieNeu_07', 'TTS_VieNeuTTS', 'Thiền Tâm Đức', 'Thiền Tâm Đức', 'Vietnamese', 'Male, Northern, storytelling', 7),
  ('TTS_VieNeu_08', 'TTS_VieNeuTTS', 'Ngọc Huyền',    'Ngọc Huyền',    'Vietnamese', 'Female, Northern, natural', 8),
  ('TTS_VieNeu_09', 'TTS_VieNeuTTS', 'Quang Sơn',     'Quang Sơn',     'Vietnamese', 'Male, Central, natural', 9),
  ('TTS_VieNeu_10', 'TTS_VieNeuTTS', 'Ngọc Trân',     'Ngọc Trân',     'Vietnamese', 'Female, Central, natural', 10),
  ('TTS_VieNeu_11', 'TTS_VieNeuTTS', 'Minh Đức',      'Minh Đức',      'Vietnamese', 'Male, Northern, news', 11),
  ('TTS_VieNeu_12', 'TTS_VieNeuTTS', 'Phạm Tuyên',    'Phạm Tuyên',    'Vietnamese', 'Male, Northern, natural', 12),
  ('TTS_VieNeu_13', 'TTS_VieNeuTTS', 'Thái Sơn',      'Thái Sơn',      'Vietnamese', 'Male, Southern, storytelling', 13),
  ('TTS_VieNeu_14', 'TTS_VieNeuTTS', 'Xuân Vĩnh',     'Xuân Vĩnh',     'Vietnamese', 'Male, Northern, natural', 14),
  ('TTS_VieNeu_15', 'TTS_VieNeuTTS', 'Thanh Bình',    'Thanh Bình',    'Vietnamese', 'Male, Northern, storytelling', 15),
  ('TTS_VieNeu_16', 'TTS_VieNeuTTS', 'Ngọc Linh',     'Ngọc Linh',     'Vietnamese', 'Female, Northern, storytelling', 16),
  ('TTS_VieNeu_17', 'TTS_VieNeuTTS', 'Đoan Trang',    'Đoan Trang',    'Vietnamese', 'Female, Northern, natural', 17),
  ('TTS_VieNeu_18', 'TTS_VieNeuTTS', 'Thục Đoan',     'Thục Đoan',     'Vietnamese', 'Female, Southern, storytelling', 18),
  ('TTS_VieNeu_19', 'TTS_VieNeuTTS', 'Minh Triết',    'Minh Triết',    'Vietnamese', 'Male, Southern, news', 19),
  ('TTS_VieNeu_20', 'TTS_VieNeuTTS', 'Mỹ Duyên',      'Mỹ Duyên',      'Vietnamese', 'Female, Southern, story reading', 20),
  ('TTS_VieNeu_21', 'TTS_VieNeuTTS', 'Quỳnh Anh',     'Quỳnh Anh',     'Vietnamese', 'Female, Northern, story reading', 21),
  ('TTS_VieNeu_22', 'TTS_VieNeuTTS', 'Đức Trí',       'Đức Trí',       'Vietnamese', 'Male, Southern, story reading', 22),
  ('TTS_VieNeu_23', 'TTS_VieNeuTTS', 'Kim Thanh',     'Kim Thanh',     'Vietnamese', 'Female, Southern, story reading', 23),
  ('TTS_VieNeu_24', 'TTS_VieNeuTTS', 'Adam',          'Adam',          'Vietnamese', 'Male, Southern, natural', 24),
  ('TTS_VieNeu_25', 'TTS_VieNeuTTS', 'Quốc Tuấn',     'Quốc Tuấn',     'Vietnamese', 'Male, Northern, natural', 25);
