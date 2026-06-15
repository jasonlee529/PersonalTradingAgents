$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

$env:PYTHONPATH = $scriptDir
$env:NO_PROXY = "127.0.0.1,localhost"
$env:no_proxy = "127.0.0.1,localhost"

$logDir = "$scriptDir\data\logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }

$startupLog = "$logDir\startup.log"

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "$timestamp | $Level | startup | $Message"
    Add-Content -Path $startupLog -Value $line
    Write-Host $Message
}

function Stop-ProcessOnPort($port) {
    $conns = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
    if (-not $conns) { return }
    foreach ($conn in $conns) {
        $proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
        if ($proc -and $proc.Id -gt 0) {
            Write-Log "释放端口 $port (PID $($proc.Id) $($proc.ProcessName))..."
            Stop-Process -Id $proc.Id -Force
            Start-Sleep -Seconds 1
        }
    }
}
Stop-ProcessOnPort 8000
Stop-ProcessOnPort 5173

Write-Log "========================================"
Write-Log "   个人AI投研助手  开发环境启动器"
Write-Log "========================================"

$venvPython = "$scriptDir\.venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    $python = @{ Source = $venvPython }
} else {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) { $python = Get-Command python3 -ErrorAction SilentlyContinue }
}

function Test-HttpReady {
    param(
        [string[]]$Uris,
        [int]$Attempts = 60
    )

    for ($i = 1; $i -le $Attempts; $i++) {
        foreach ($uri in $Uris) {
            try {
                $r = Invoke-WebRequest -Uri $uri -TimeoutSec 3 -UseBasicParsing
                if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 400) {
                    return $true
                }
            } catch {
            }
        }
        Start-Sleep -Seconds 1
    }

    return $false
}
if (-not $python) {
    $pyPath = "E:\Python\Python310\python.exe"
    if (Test-Path $pyPath) { $python = @{ Source = $pyPath } }
    else { Write-Log "未找到 python" "ERROR"; exit 1 }
}

$node = Get-Command node -ErrorAction SilentlyContinue
if (-not $node) {
    $nodePath = "E:\nodejs\node.exe"
    if (Test-Path $nodePath) { $node = @{ Source = $nodePath } }
    else { Write-Log "未找到 node" "ERROR"; exit 1 }
}

if (-not (Test-Path "$scriptDir\.env")) {
    Write-Log "未找到 .env，请先复制 .env.example 为 .env 并填写本地配置" "ERROR"
    Write-Log "安装说明见 README.md"
    exit 1
}

$backendCheck = & $python.Source -c "import fastapi, uvicorn" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Log '未找到后端依赖，请先执行: python -m pip install -e ".[dev]"' "ERROR"
    Write-Log "安装说明见 README.md"
    exit 1
}

if (-not (Test-Path "$scriptDir\web\node_modules\vite\bin\vite.js")) {
    Write-Log "未找到前端依赖，请先执行: cd web; npm install; cd .." "ERROR"
    Write-Log "安装说明见 README.md"
    exit 1
}

Write-Log "[后端] 启动 FastAPI ..."
$backendProc = Start-Process -FilePath $python.Source `
    -ArgumentList "main.py" `
    -WorkingDirectory $scriptDir `
    -RedirectStandardOutput "$logDir\backend.out.log" `
    -RedirectStandardError "$logDir\backend.err.log" `
    -WindowStyle Hidden -PassThru

Start-Sleep -Seconds 2

Write-Log "[前端] 启动 React ..."
$frontendProc = Start-Process -FilePath $node.Source `
    -ArgumentList @("$scriptDir\web\node_modules\vite\bin\vite.js", "--host", "127.0.0.1", "--strictPort") `
    -WorkingDirectory "$scriptDir\web" `
    -RedirectStandardOutput "$logDir\frontend.log" `
    -RedirectStandardError "$logDir\frontend.err.log" `
    -WindowStyle Hidden -PassThru

Write-Log "等待服务启动 ..."
Start-Sleep -Seconds 5

$backendOk = Test-HttpReady -Uris @("http://127.0.0.1:8000/docs") -Attempts 30
if ($backendOk) {
    Write-Log "[成功] 后端已启动: http://127.0.0.1:8000/docs"
} else {
    Write-Log "[失败] 后端未响应" "ERROR"
    if (Test-Path "$logDir\backend.err.log") {
        Write-Host "--- backend.err.log (last 20 lines) ---" -ForegroundColor Yellow
        Get-Content "$logDir\backend.err.log" -Tail 20 | ForEach-Object { Write-Host $_ }
    }
}

$frontendOk = $false
if (Test-HttpReady -Uris @("http://127.0.0.1:5173/", "http://localhost:5173/") -Attempts 60) {
    $frontendOk = $true
    Write-Log "[成功] 前端已启动: http://127.0.0.1:5173"
}

if (-not $frontendOk) {
    Write-Log "[失败] 前端未响应" "ERROR"
    if (Test-Path "$logDir\frontend.err.log") {
        Write-Host "--- frontend.err.log (last 20 lines) ---" -ForegroundColor Yellow
        Get-Content "$logDir\frontend.err.log" -Tail 20 | ForEach-Object { Write-Host $_ }
    }
}

Write-Log "按 Enter 键停止所有服务..."
$null = Read-Host

Write-Log "正在停止..."
function Stop-Tree($proc) {
    if (-not $proc) { return }
    $processId = $proc.Id
    # Kill children first
    Get-CimInstance Win32_Process -Filter "ParentProcessId=$processId" -ErrorAction SilentlyContinue | ForEach-Object {
        try { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } catch {}
    }
    try { Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue } catch {
        Write-Log "停止 PID $processId 失败: $_" "WARN"
    }
}
Stop-Tree $backendProc
Stop-Tree $frontendProc
Write-Log "已停止"
Start-Sleep -Seconds 1
