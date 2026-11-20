# StoryRole 书架优先改版交付记录

## 1. 本次交付

- 产品入口改为书架：登录后默认进入 `/`，首页是小说封面网格，而不是对话收件箱。
- 新增 `/novels`、`/novels/new`、`/novels/{slug}` 三个小说页面。
- 新增小说 slug 路由与人类可读地址，例如 `/novels/三体-三部曲`。
- 小说详情页提供书封、角色统计、角色卡、最近对话；角色卡整卡可点，卡内可开始对话。
- 用量页按任务环节重排，后端补充 `by_stage`、`recent.stage`。
- 设置页去掉“对话模型 / 路由模型”双输入，改为运行模型只读展示 + WeKnora 式自定义模型接入。
- 前端 API 根地址支持 `window.APP_API_BASE` / `localStorage.storyrole_api_base` / `App.setApiBase()` 配置。
- 设计系统整体重写：暖纸色、深绿/砖红、Noto Serif SC 标题、低阴影、书封和书脊。

## 2. 真实接口验证

服务：`http://127.0.0.1:8765`（本轮启动 PID 98328，编写时仍在监听）。

| 接口 | 结果 |
|---|---|
| `GET /api/app/novels` | 200，返回 `builtin_three_body_v1`、名称、slug、角色/对话计数 |
| `GET /api/app/novels/三体-三部曲` | 200，返回小说与 5 位角色 |
| `GET /api/app/usage?days=30` | 200，返回 `totals`、`daily`、`by_stage`、`by_agent`、`recent` |
| `GET /api/app/settings` | 200，返回 `runtime_models` 与 `models.custom.*` 定义 |
| `GET /api/app/characters?novel_id=builtin_three_body_v1` | 200 |
| `GET /api/app/conversations?novel_id=builtin_three_body_v1` | 200 |
| `GET /api/app/tools/models` | 200，图片/OCR/Omni/ASR/TTS/翻译均返回模型 |
| `POST /api/app/models/test` | 200；无效 key 返回 `ok:false`，响应不含 key；有效 key 返回 `ok:true`、`model_count=182`、`latency_ms=1704` |

用量真实分组（近 30 天当前账号）：

| 环节 | 调用 | Token | 费用 |
|---|---:|---:|---:|
| 角色对话 | 3 | 17,637 | ¥0.04 |
| 场景分析 | 2 | 67,890 | ¥0.18 |
| 人设生成 | 2 | 48,279 | ¥0.21 |

## 3. 浏览器验收

脚本：

- `docs/app-ui-smoke-v4.js`：17 个页面 × 1440 / 768 / 390。
- `docs/app-ui-flow-v4.js`：书架点书 → 小说页 → 角色卡 → 角色页；用量切换 7 天；设置加载。
- 报告：`docs/app-ui-report-v4.json`、`docs/app-ui-flow-report-v4.json`。
- 截图：`docs/ui-shots-v4/`。

结果：

- 所有页面 HTTP 200。
- `errors` 为空，无 `console` / `pageerror`。
- 三档均无横向溢出。
- 书架 2 张卡（1 本小说 + 新增卡）；小说详情 5 张角色卡；用量 3 张环节卡；设置 11 行运行模型。
- 点击流程成功：书架 → `/novels/三体-三部曲` → `/characters/81`。
- 用量页切换 7 天后仍返回 3 张环节卡。

## 4. 后端与模型

- `MODEL_ROLES` 全部 12 个角色均可解析到网关可用模型；`scripts/list_models.py --check` 输出 `all 12 roles resolve to models on the gateway`。
- 语言模型继续按项目约束使用 `deepseek-v4.1-flash-1017`，没有因“选最好模型”擅自改成 pro，避免与既有“只用 DeepSeek flash”的约束冲突。
- 重排模型：网关当前只有 `qwen3.7-text-rerank` 一个可用的 rerank 型号，项目已经指向它；没有更高版本可换，因此不是遗漏，而是当前可用上限。后续网关新增 rerank 型号时再替换。
- 多模态：`qwen-image-3.0-pro`（图片生成）、`qwen3.5-ocr`（OCR）、`qwen3.8-max`（图片理解）、`fun-asr-flash-2026-06-15`（ASR）、`qwen3-tts-flash`（TTS）、`qwen-mt-plus`（翻译）。
- 自定义模型接入只做定义、测试、保存；保存的 `models.custom.*` 不会自动覆盖 `MODEL_ROLES`，页面已明确说明，避免“保存即切换”的误解。

## 5. 测试

```powershell
Set-Location D:\AgentCode\two\rolerag-v2
D:\AgentCode\two\.venv\Scripts\python.exe -m pytest tests\rolerag -q
# 132 passed
```

## 6. 未覆盖 / 后续

- 没有实际提交一本新小说文件做端到端导入验证，避免污染测试账号；文件过滤、导入表单和跳转逻辑已由浏览器打开页面验证。
- 没有在设置页 UI 里实际点击“测试连接”走一遍表单提交；接口正反例已分别用真实/无效 key 验证。
- 旧页面 `library.html`、`library.js` 已不再被 `/library` 路由使用，仍保留在 `frontend/app/` 作为历史文件，未删除。
- 自定义模型连接尚未真正驱动核心聊天/重排，只完成了 WeKnora 式接入层。
