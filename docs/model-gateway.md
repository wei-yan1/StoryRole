# 模型网关：一把 key 取对应模型

> 语言模型端点与 DeepSeek 官方端点回滚约束直接写在根目录 `.env` 的阿里云 / DeepSeek 配置段注释中。

项目只保留一个聊天语言模型 `deepseek-v4.1-flash-1017`，但同一把 key 在阿里云 MaaS 端点上还能调用 182 个模型。embedding、rerank、图像、语音、翻译、OCR 这类需求，不应该借用聊天模型，而应按能力取对应 id。

## 端点与凭据

```env
OPENAI_API_KEY=<同一把阿里云 key>
OPENAI_BASE_URL=https://ws-7jebjvrt7pqdp1fj.cn-beijing.maas.aliyuncs.com/compatible-mode/v1
```

`OPENAI_*` 缺失时回退到 `DASHSCOPE_API_KEY` / `DASHSCOPE_BASE_URL`。密钥只放在本地 `.env`，不要提交。

## 角色表

| role | capability | model | API | 实测 |
| --- | --- | --- | --- | --- |
| `chat` / `reasoning` / `guard` | 对话 | `deepseek-v4.1-flash-1017` | OpenAI-compatible chat | 已验证 |
| `embedding` | 向量 | `qwen3.7-text-embedding` | OpenAI-compatible embeddings（1024 维） | 已验证 |
| `rerank` | 重排 | `qwen3.7-text-rerank` | DashScope `TextReRank` | 已验证 |
| `image` | 出图 | `qwen-image-3.0-pro` | OpenAI-compatible `images.generate` | 已实测 |
| `image_fast` | 快速出图 | `wan2.7-image` | 待确认 | 未实测 |
| `asr` | 语音识别 | `fun-asr-flash-2026-06-15` | 原生 HTTP `multimodal-generation` + `input_audio` | 已实测 |
| `tts` | 语音合成 | `qwen3-tts-flash` | DashScope `qwen_tts.SpeechSynthesizer` | 已实测 |
| `omni` | 图片理解 | `qwen3.8-max` | OpenAI-compatible chat vision | 已实测 |
| `translate` | 翻译 | `qwen-mt-plus` | DashScope `Generation` + `translation_options` | 已实测 |
| `ocr` | 文字识别 | `qwen3.5-ocr` | OpenAI-compatible chat vision | 已实测 |

旗舰切换的边界也要记下来：`qwen3.8-max` 是视觉旗舰，细节描述和推理比 `qwen3.8-omni-flash` 更稳；`qwen-mt-plus` 是翻译专业版；`fun-asr-flash-2026-06-15` 更新，支持七大方言、30 语种和标点归一化。`wan2.7-image-pro` 虽然支持 4K，但走原生异步图片协议，OpenAI 兼容的 `images.generate` 会报 `url error`，当前 UI 仍以同步 2K 的 `qwen-image-3.0-pro` 为旗舰；`MiniMax/speech-2.8-hd` 在当前 workspace 返回 `The product is not activated`，所以 TTS 仍用已验证的 `qwen3-tts-flash`，要换 MiniMax 需先在百炼控制台开通产品。`qwen-mt-uni` 在纯文本输入上会报 `url error`；`image_fast` 仍未实测。

## 多模态调用协议

同一个 key，不同能力走的接口并不一样：

- 出图、图片理解、OCR：MaaS 的 OpenAI 兼容端点。
  - `images.generate(model="qwen-image-3.0-pro", prompt=..., size="1024x1024")`
  - `chat.completions.create(model="qwen3.5-ocr" / "qwen3.8-max", messages=[... image_url ...])`
- ASR：`fun-asr-flash-2026-06-15` 走原生 HTTP `POST /api/v1/services/aigc/multimodal-generation/generation`，本地音频转 data URI，`parameters.format` 显式传 `wav` / `mp3` / `m4a` / `ogg` / `flac`，`parameters.language_hints` 可传 `["zh"]` / `["en"]`。若把 `MODEL_ASR` 覆盖成 `qwen-audio-3.0-asr-flash`，服务层会自动回退到 `MultiModalConversation.call`。
- TTS：原生 `dashscope.audio.qwen_tts.SpeechSynthesizer.call(model="qwen3-tts-flash", text=..., voice="Cherry")`，返回 wav URL。
- 翻译：原生 `dashscope.Generation.call(model="qwen-mt-plus", translation_options={"source_lang": ..., "target_lang": ...})`。

服务层封装在 `app/services/multimodal_service.py`，HTTP 路由见 `docs/multimodal-api.md`。

## 查询当前 key 能调什么

```bash
# 按能力分组列出全部模型
python scripts/list_models.py

# 只看某一类
python scripts/list_models.py --capability embedding
python scripts/list_models.py --capability image

# 看项目角色表（含 env 覆盖项）
python scripts/list_models.py --roles

# 校验角色表里的 id 是否都还在网关上
python scripts/list_models.py --check
```

代码侧统一从 `app.core.config.model_catalog` 取：

```python
from app.core.config.model_catalog import resolve_model, available_models

model = resolve_model("embedding")      # 默认 qwen3.7-text-embedding
ids = available_models()                # 当前 key 的全部 id
```

覆盖角色模型时优先加环境变量，不改代码：

```env
MODEL_EMBEDDING=qwen3.7-text-embedding
DASHSCOPE_RERANK_MODEL=qwen3.7-text-rerank
MODEL_IMAGE=qwen-image-3.0-pro
MODEL_ASR=fun-asr-flash-2026-06-15
MODEL_OMNI=qwen3.8-max
MODEL_TRANSLATE=qwen-mt-plus
```

## 边界

- 聊天、推理、一致性检查仍只走 `deepseek-v4.1-flash-1017`；不要为了“模型多”把对话模型换成 qwen/GLM/Kimi。
- embedding 换模型会让已有 Chroma 索引失效（维度和语义空间都变了），必须整库重建后再切；当前默认仍是 Ollama `bge-m3`。网关向量后端已支持 `EMBEDDING_PROVIDER=openai`（模型取 `MODEL_EMBEDDING`，默认 `qwen3.7-text-embedding`，1024 维），只作为可选能力，未切换默认。
- rerank 改动不需要重建索引，只影响候选排序；`qwen3.7-text-rerank` 与旧的 `qwen3-rerank` 在原生 `TextReRank` 上都实测 200，项目默认已切到 `qwen3.7-text-rerank`。
- 端点的 `/models` 返回的是可调用清单，不包含每个模型的请求协议、价格和上下文上限；价格在 `.env` 的 `MODEL_PRICING_JSON` 里单独配置。
