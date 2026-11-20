# v2 运行封装：显式切到独立库，避免误用根 .env 的旧库默认值。
# 用法：
#   .\scripts\run_v2.ps1                       # 启动 API（127.0.0.1:8000）
#   .\scripts\run_v2.ps1 scripts\harness_gate.py
#   .\scripts\run_v2.ps1 -m pytest tests\rolerag -q
$ErrorActionPreference = "Stop"
$env:POSTGRES_DATABASE = "three_body_agent_v2"
$env:STORYROLE_ALIGNMENT_CHECK = "1"
# Laya 权重从 Hugging Face 镜像拉取；官方域名在当前网络不可达。
if (-not $env:HF_ENDPOINT) { $env:HF_ENDPOINT = "https://hf-mirror.com" }
if (-not $env:HF_HUB_DISABLE_SYMLINKS_WARNING) { $env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1" }
# 模型缓存统一放 D 盘，避免 C 盘继续增长。
if ([string]::IsNullOrWhiteSpace($env:HF_HOME)) { $env:HF_HOME = "D:\AI\Models\huggingface" }
if ([string]::IsNullOrWhiteSpace($env:HUGGINGFACE_HUB_CACHE)) { $env:HUGGINGFACE_HUB_CACHE = $env:HF_HOME + "\hub" }
# 本地已有 Laya snapshot 时优先离线加载，避免启动预热被 DNS 失败拖回。
if ([string]::IsNullOrWhiteSpace($env:HF_HUB_OFFLINE)) {
    $layaSnapshots = $env:HF_HOME + "\hub\models--convaiinnovations--laya\snapshots"
    if (Test-Path -LiteralPath $layaSnapshots) { $env:HF_HUB_OFFLINE = "1" }
}
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$python = "D:\AgentCode\two\.venv\Scripts\python.exe"
if ($args.Count -gt 0) {
    & $python @args
} else {
    & $python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
}
exit $LASTEXITCODE
