# 罗辑新旧链路对比测试

这个目录记录 `scripts/compare_luoji.py` 每次运行的结果。

## 运行

在 `D:\AgentCode\two` 下执行：

```powershell
.\.venv\Scripts\python.exe scripts\compare_luoji.py
```

只跑某一类：

```powershell
.\.venv\Scripts\python.exe scripts\compare_luoji.py --categories q3,爱情
```

只跑旧项目或新项目：

```powershell
.\.venv\Scripts\python.exe scripts\compare_luoji.py --project old
```

查看计划、不真正调用：

```powershell
.\.venv\Scripts\python.exe scripts\compare_luoji.py --dry-run
```

## 每次运行会记录

```text
data/evals/luoji_compare/
├── history.md                 # 所有 run 的总览表，最新在顶部
├── history.jsonl              # 机器可读的 run 索引
└── runs/
    └── <run_id>/
        ├── results.json       # 完整回答、meta、trace 模型调用
        └── summary.md         # 本次运行的指标和回答摘要
```

`history.md` 打开就能看到每次的字数、证据数、耗时、降级情况。需要原始回答时进对应的 `runs/<run_id>/results.json`。

## 常用参数

- `--label regression`：给这次运行打标签，方便回看。
- `--timeout 420`：单题超时秒数，默认 420；深度题旧项目可能到 340s 左右。
- `--retries 0`：默认不重试；超时不会自动重试，避免一次慢请求变两次。
- `--fail-on-degraded`：有降级时返回非零退出码，适合放进 CI。
- `--no-trace`：不查询 `/api/v1/models/traces/{trace_id}`，少几次请求。

## 说明

- 两套项目默认端口：旧项目 `1314`，新项目 `1315`。
- 使用根目录 `.env` 的阿里云 MaaS 配置，模型为 `deepseek-v4.1-flash-1017`。
- 每题都会新建独立 `thread_name`，避免同一项目内六题互相串上下文。
- 记录里不写 API key 或 JWT。
