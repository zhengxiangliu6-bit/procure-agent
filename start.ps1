$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) { throw '请先按照 README 创建虚拟环境并安装 requirements.txt。' }
if (-not (Test-Path -LiteralPath 'frontend\dist\index.html')) { throw '请先在 frontend 中运行 npm install 和 npm run build。' }
& '.\.venv\Scripts\python.exe' -m uvicorn backend.main:app --host 127.0.0.1 --port 8010
