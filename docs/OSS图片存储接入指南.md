# OSS 图片存储接入指南（lbwnb111）

> 目标：在 StoryRole 项目里用阿里云 OSS 存图片，并能在代码里上传、读取、生成访问链接。
> 本文所有 Bucket 信息均为控制台实读 + 实际公网请求验证，不是猜的。

---

## 0. 一页速查

| 项 | 值 |
|---|---|
| Bucket | `lbwnb111` |
| 地域 | 华南3（广州） / region id `cn-guangzhou` |
| 外网 Endpoint | `https://oss-cn-guangzhou.aliyuncs.com` |
| 内网 Endpoint | `https://oss-cn-guangzhou-internal.aliyuncs.com`（同地域 ECS 用） |
| Bucket 域名 | `lbwnb111.oss-cn-guangzhou.aliyuncs.com` |
| 自定义域名 | `lbwnb111.cn-guangzhou.taihangztn.cn` |
| 读写权限 | **公共读**（文件可被公网直接访问） |
| 存储类型 | 标准存储 / 本地冗余 |
| 当前用量 | 26 个对象，18.15 MB |
| 已有目录 | `2025/`、`2026/`、`rag/`，根目录另有若干图片 |

**公网访问已实测通**：

```
HEAD https://lbwnb111.oss-cn-guangzhou.aliyuncs.com/1781705211620.jpeg
→ 200, Content-Type: image/jpeg, Content-Length: 472592
```

**URL 规则**：`https://lbwnb111.oss-cn-guangzhou.aliyuncs.com/<对象键>`

**关键结论**：

- **读图片**：公共读，不需要 AccessKey，拼 URL 就能用
- **通过代码写图片**：需要 AccessKey（控制台上传不需要）

---

## 1. 关于 AccessKey：为什么本文没有明文 Key

阿里云 OSS 用的是 **AccessKey**（`AccessKeyId` + `AccessKeySecret`），不是 "API Key"。

两条硬事实：

1. **AccessKeySecret 在控制台永远不会回显**。创建时只显示一次，页面之后只显示 ID。你"找不到"是正常的——找不到 Secret 就等于没有，只能新建一对。
2. 账号密码和 Secret 属于认证凭据，我不会写进文档或聊天记录里，即使是测试账号。这不是不信任你，是这条规则对任何账号都一致。

### 正确做法（3 分钟）

1. 打开 **RAM 控制台 → AccessKey 管理**：`https://ram.console.aliyun.com/manage/ak`
   - 你现在停在 `/roles`（角色页），那里没有 AccessKey，所以找不到
   - 也可以从控制台右上角头像 → 「AccessKey 管理」进入
2. 建议先建一个 **RAM 子账号**（RAM → 身份管理 → 用户 → 创建用户），只授 `AliyunOSSFullAccess`
3. 选中对应用户 → 「AccessKey」→ **创建 AccessKey** → 短信/扫码验证
4. 弹窗里会同时给出 **AccessKeyId** 和 **AccessKeySecret**，**当场复制**，关掉就没了
5. 直接把两个值粘进项目根目录的 `.env`，**不要发给我、不要贴进本文档、不要提交 Git**

`.env` 已被 `.gitignore` 忽略（第 1 行 `.env`），放这里不会进仓库。

> 如果你暂时不想建 AccessKey：控制台「文件管理 → 文件列表 → 上传文件」可以直接传图，读图用公网 URL，完全不需要密钥。只有要让代码自动上传时才必须配。

---

## 2. 环境变量（已写进 `.env.example`）

在项目根目录 `.env` 末尾追加：

```dotenv
# --- Alibaba Cloud OSS ---
OSS_REGION=cn-guangzhou
OSS_ENDPOINT=https://oss-cn-guangzhou.aliyuncs.com
OSS_BUCKET=lbwnb111
OSS_ACCESS_KEY_ID=
OSS_ACCESS_KEY_SECRET=
OSS_PUBLIC_BASE_URL=https://lbwnb111.oss-cn-guangzhou.aliyuncs.com
OSS_IMAGE_PREFIX=images
OSS_MAX_IMAGE_BYTES=10485760
```

| 变量 | 必填 | 说明 |
|---|---|---|
| `OSS_ACCESS_KEY_ID` | 上传必填 | RAM 创建后复制 |
| `OSS_ACCESS_KEY_SECRET` | 上传必填 | 只显示一次，粘完保存 |
| `OSS_BUCKET` | 是 | 默认 `lbwnb111` |
| `OSS_IMAGE_PREFIX` | 否 | 默认 `images`，对象键会落在 `images/2026/11/...` |
| `OSS_MAX_IMAGE_BYTES` | 否 | 默认 10 MB，超过直接拒绝 |

**读图不需要填 AK/SK**；填了空值也不影响应用启动，只有调用上传/删除时才报错。

---

## 3. 已经写好的三个文件

| 文件 | 作用 |
|---|---|
| `app/services/oss_storage.py` | 服务层：上传、读取、签名 URL、删除、列举、图片处理 URL |
| `app/api/v1/uploads.py` | 两个接口：`POST /api/v1/uploads/image`、`GET /api/v1/uploads/images` |
| `scripts/oss_image.py` | 命令行工具：upload / list / url / download |

依赖不用装：`pyproject.toml` 里已有 `alibabacloud-oss-v2>=1.2.4`（当前环境实际版本 1.3.1，默认 V4 签名）。

### 3.1 注册上传路由（已完成）

已经写进 `app/main.py`：

- 顶部 `from app.api.v1.uploads import router as uploads_router`
- 下方 `app.include_router(uploads_router)`

验证结果：`app.openapi()["paths"]` 里能看到 `/api/v1/uploads/image` 和 `/api/v1/uploads/images`，说明已挂载成功。

---

## 4. 代码里怎么用

### 4.1 上传一张图（最简单）

```python
from app.services import oss_storage

result = oss_storage.upload_image_file(
    r"D:\pics\cat.jpg",
    scope="users/1",          # 可选：会落到 images/2026/11/users/1/<uuid>.jpg
)
print(result["url"])
# https://lbwnb111.oss-cn-guangzhou.aliyuncs.com/images/2026/11/users/1/xxxx.jpg
```

`result` 结构：

```python
{
  "bucket": "lbwnb111",
  "key": "images/2026/11/users/1/xxxx.jpg",
  "url": "https://lbwnb111.oss-cn-guangzhou.aliyuncs.com/images/2026/11/users/1/xxxx.jpg",
  "size": 123456,
  "content_type": "image/jpeg",
}
```

### 4.2 上传内存里的字节（比如 FastAPI 的 UploadFile）

```python
from app.services import oss_storage

data = await file.read()
result = oss_storage.upload_image(
    data,
    file.filename or "image.jpg",
    content_type=file.content_type,
    scope=f"users/{user.id}",
)
```

### 4.3 读取图片

公共读，两种方式：

```python
# 方式一：直接拼 URL（推荐，零成本）
url = oss_storage.public_url("images/2026/11/users/1/xxxx.jpg")

# 方式二：服务端拉取字节（要二次处理、转 base64 给模型时用）
data = oss_storage.read_image_bytes("images/2026/11/users/1/xxxx.jpg")
```

如果以后把 Bucket 改成**私有读**，改用临时签名链接：

```python
url = oss_storage.signed_url("images/2026/11/users/1/xxxx.jpg", expires_seconds=3600)
```

### 4.4 删图 / 列举

```python
oss_storage.delete_image("images/2026/11/users/1/xxxx.jpg")

items = oss_storage.list_images(prefix="images", limit=50)
for item in items:
    print(item["key"], item["size"], item["url"])
```

### 4.5 图片处理（省流量、省存储）

```python
url = oss_storage.image_process_url(
    oss_storage.public_url("images/2026/11/cat.jpg"),
    width=800,
    quality=80,
    fmt="webp",
)
# https://.../cat.jpg?x-oss-process=image/resize,w_800/quality,q_80/format,webp
```

原图不动，按需生成，适合网页/小程序图源。

---

## 5. 命令行直接用

```powershell
# 上传
uv run python scripts/oss_image.py upload D:\pics\cat.jpg --scope users/1

# 列出现有图片
uv run python scripts/oss_image.py list --prefix images --limit 20

# 取公网链接
uv run python scripts/oss_image.py url images/2026/11/cat.jpg

# 取 1 小时有效的签名链接
uv run python scripts/oss_image.py url images/2026/11/cat.jpg --signed --expires 3600

# 下载回来
uv run python scripts/oss_image.py download images/2026/11/cat.jpg D:\tmp\out.jpg
```

脚本会自动读取项目根目录 `.env`。

---

## 6. 接到现有业务上

### 6.1 用户头像

`users` 表已经有 `avatar_url VARCHAR(512)` 字段（见 `app/storage/postgres/schema.py`），上传后直接把 `result["url"]` 存进去即可：

```python
avatar = oss_storage.upload_image_file(path, scope=f"users/{user.id}")
# UPDATE users SET avatar_url = avatar["url"] WHERE id = ...
```

### 6.2 角色立绘 / 小说配图

建议按业务分目录，别全堆根目录：

```
images/
  2026/11/
    users/1/...
    characters/{character_id}/...
    novels/{novel_id}/...
```

调用时传 `scope` 即可，服务层会自动加时间前缀。

### 6.3 给大模型读图

你现在的 `deepseek-v4.1-flash-1017` 支持视觉输入，OpenAI 兼容接口的 `image_url` 直接填 OSS 公网 URL：

```python
completion = client.chat.completions.create(
    model="deepseek-v4.1-flash-1017",
    messages=[{
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": {"url": img_url}},
            {"type": "text", "text": "描述这张图"},
        ],
    }],
)
```

不用本地转 base64，但要求图片 URL **公网可访问**——你现在的公共读正好满足。

---

## 7. 安全与费用

**公共读的风险**：任何拿到 URL 的人都能直接下载原图。放头像、文章配图没问题；身份证、合同、私密照片必须改私有读 + 签名 URL。

**不要在前端放 AccessKey**。浏览器/小程序里需要直传时，走 STS 临时凭证或后端签名，绝不要把 Secret 写进 JS。

**费用**：存储按 GB/月计，标准存储很便宜；主要成本是**外网流出流量**，图片做 WebP + 缩放能显著降低。OSS 图片处理按处理请求数计费，量小可忽略。

---

## 8. 排错对照表

| 报错 | 原因 | 处理 |
|---|---|---|
| `InvalidAccessKeyId` | AK 不存在或已禁用 | RAM 里确认 AK 状态，重新创建 |
| `SignatureDoesNotMatch` | Secret 错、复制时带了空格/换行 | 重新粘贴，别带空格 |
| `AccessDenied` (403) | RAM 子账号没有 OSS 权限，或对象 ACL 拒绝 | 授 `AliyunOSSFullAccess`，检查 Bucket/对象 ACL |
| `NoSuchBucket` | Bucket 名或 region 写错 | 确认 `lbwnb111` + `cn-guangzhou` |
| 浏览器 404 | 对象键拼错、大小写不一致、目录少一层 | 控制台文件列表里直接复制 key |
| 上传 413 | 反向代理/网关限制请求体 | 调 nginx `client_max_body_size`，或改分片上传 |
| 上传超时 | 图片过大或网络差 | 压缩后再传；大文件用 SDK 的 uploader 分片 |
| `oss2` 相关报错 | 装错 SDK | 本项目用 `alibabacloud-oss-v2`，不是 `oss2` |

---

## 9. 待你补的两行

文档里唯一需要你亲手填的就是 `.env` 的这两行：

```dotenv
OSS_ACCESS_KEY_ID=
OSS_ACCESS_KEY_SECRET=
```

填完重启服务，跑一次：

```powershell
uv run python scripts/oss_image.py upload D:\pics\cat.jpg
```

能打印出 `https://lbwnb111.oss-cn-guangzhou.aliyuncs.com/images/...` 就通了。
