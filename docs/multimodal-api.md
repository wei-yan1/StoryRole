# 多模态 API

项目用同一把阿里云 key 调用图片、OCR、语音和翻译模型。服务层在 `app/services/multimodal_service.py`，路由挂在 `/api/v1/media`，全部接口都需要登录（Bearer JWT）。

## 前端工作台

登录后打开 `http://127.0.0.1:1314/multimodal`。页面沿用 StoryRole 的纸感/墨绿/衬线风格，包含出图、读图/OCR、TTS/ASR、翻译四个区域；JWT 从 `localStorage.access_token` 读取，前端直接调用下面的 `/api/v1/media/*` 接口。生成物通过 `/media/...` 展示和下载。

## 接口一览

| 方法 | 路径 | 输入 | 返回 |
| --- | --- | --- | --- |
| GET | `/api/v1/media/models` | - | 各角色当前模型与是否已实测 |
| POST | `/api/v1/media/images/generate` | JSON `prompt`、`size`、`model?` | 图片 URL、字节数 |
| POST | `/api/v1/media/images/describe` | multipart `file`、`prompt?`、`model?` | 图片描述文本 |
| POST | `/api/v1/media/ocr` | multipart `file`、`prompt?`、`model?` | OCR 文本 |
| POST | `/api/v1/media/audio/transcribe` | multipart `file`、`language?`、`model?` | 转写文本 |
| POST | `/api/v1/media/audio/speech` | JSON `text`、`voice?`、`model?` | wav 音频 URL |
| POST | `/api/v1/media/translate` | JSON `text`、`source_lang?`、`target_lang?`、`model?` | 译文 |

`model` 不传时按 `app/core/config/model_catalog.py` 的角色表取默认值：

```text
image      qwen-image-3.0-pro
ocr        qwen3.5-ocr
omni       qwen3.8-max
asr        fun-asr-flash-2026-06-15
tts        qwen3-tts-flash
translate  qwen-mt-plus
```

## 出图

```bash
curl -X POST http://127.0.0.1:1314/api/v1/media/images/generate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"雨夜里的青石台阶，一盏孤灯，电影感","size":"1024x1024"}'
```

```json
{
  "model": "qwen-image-3.0-pro",
  "size": "1024x1024",
  "url": "/media/images/7d0046f6bf854edc8bf798eb07cc8eaf.png",
  "bytes": 1238208
}
```

图片生成走 OpenAI 兼容的 `images.generate`，服务层会把远程结果下载到 `data/generated/images/`，返回项目内的 `/media/...` 地址，避免依赖会过期的 OSS 链接。

## 图片理解与 OCR

```bash
curl -X POST http://127.0.0.1:1314/api/v1/media/ocr \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@page.png"
```

```json
{
  "model": "qwen3.5-ocr",
  "text": "沈砚被逐出山门\n青云宗 2026 年 11 月\nOCR test 12345"
}
```

图片理解把 `ocr` 换成 `images/describe`：

```bash
curl -X POST http://127.0.0.1:1314/api/v1/media/images/describe \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@photo.jpg" \
  -F "prompt=用一句话描述这张图片里的人物和背景。"
```

OCR 默认提示词是“识别图片中的所有文字，按行输出，不要解释。”；图片理解默认是“用一句话描述这张图片的内容。”。两者都接受 `jpg` / `jpeg` / `png` / `webp`，单文件上限 20MB。

## 语音

转写：

```bash
curl -X POST http://127.0.0.1:1314/api/v1/media/audio/transcribe \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@voice.wav" \
  -F "language=中文"
```

```json
{
  "model": "fun-asr-flash-2026-06-15",
  "text": "你好，我是沈燕。今天天气不错，我们一起下山去看看。",
  "format": "wav"
}
```

合成：

```bash
curl -X POST http://127.0.0.1:1314/api/v1/media/audio/speech \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text":"沈砚下山了，山门外下着细雨。","voice":"Cherry"}'
```

```json
{
  "model": "qwen3-tts-flash",
  "voice": "Cherry",
  "url": "/media/audio/1189e658ee7842128d33ca65b5059f12.wav",
  "bytes": 138284
}
```

ASR 默认走 `fun-asr-flash-2026-06-15` 的原生 HTTP 接口，支持 `wav` / `mp3` / `m4a` / `ogg` / `flac`，单文件上限 25MB；本次实测的是 `wav`。服务层把本地音频转成 data URI，并显式传 `format`，不要求音频有公网 URL；`language=中文` 会映射成 `language_hints=["zh"]`。如果把 `MODEL_ASR` 覆盖成 `qwen-audio-3.0-asr-flash`，服务层回退到 `MultiModalConversation.call`。TTS 返回的 wav 会保存到 `data/generated/audio/`。

## 翻译

```bash
curl -X POST http://127.0.0.1:1314/api/v1/media/translate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text":"沈砚被逐出山门，他回头看了一眼青云宗。","source_lang":"Chinese","target_lang":"English"}'
```

```json
{
  "model": "qwen-mt-plus",
  "source_lang": "Chinese",
  "target_lang": "English",
  "text": "Shen Yan was expelled from the sect. He turned back and glanced at the Qingyun Sect one last time."
}
```

翻译走原生 `dashscope.Generation` 的 `translation_options`，语言名用 `Chinese` / `English` 这类写法。默认 `qwen-mt-plus`（专业版），复杂句子的语序和语气比 `qwen-mt-flash` 更稳；`qwen-mt-uni` 在纯文本上会报 `url error`，不要用它替代。TTS 的 `MiniMax/speech-2.8-hd` 在当前 workspace 返回“产品未开通”，因此仍用已验证的 `qwen3-tts-flash`。

## 生成文件

- 图片：`data/generated/images/<uuid>.png`
- 音频：`data/generated/audio/<uuid>.wav`
- 对外地址：`/media/images/...`、`/media/audio/...`（由 `app/main.py` 的 `StaticFiles` 挂载）
- `data/generated/` 已加入 `.gitignore`，不会把生成物提交进仓库。

## 错误

- 输入格式/大小不合法：`400` / `413`
- 上游模型失败：`502`，`detail` 里带原始错误信息
- 未登录：`401`

调用失败时先看 `detail`：图片生成常见是尺寸或模型 id 不支持，ASR 常见是 `format is empty`（漏传 `format`），翻译常见是 `url error`（错误地用了 `qwen-mt-uni`）。
