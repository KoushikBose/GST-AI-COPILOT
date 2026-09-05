# Stops every local backend process and frees the embedded-Qdrant folder lock.
#
# Use this when you see:
#   "Storage folder .data/qdrant is already accessed by another instance of Qdrant client"
#
# The usual cause is a stray `uvicorn --reload` worker. Reload workers are
# spawned as bare `python.exe` with a `--multiprocessing-fork` command line,
# so killing "uvicorn" by name misses them — this kills by listening port and
# by the spawn signature instead.

$ErrorActionPreference = 'SilentlyContinue'

Write-Host "Stopping backend processes..." -ForegroundColor Cyan

foreach ($port in 8000, 8001, 8002) {
    $pids = Get-NetTCPConnection -LocalPort $port -State Listen |
        Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($procId in $pids) {
        Write-Host "  killing PID $procId (port $port)"
        taskkill /PID $procId /T /F | Out-Null
    }
}

Get-CimInstance Win32_Process |
    Where-Object {
        ($_.Name -eq 'uvicorn.exe') -or
        ($_.Name -eq 'python.exe' -and
         $_.CommandLine -match 'uvicorn|app\.main|--multiprocessing-fork|spawn_main')
    } |
    ForEach-Object {
        Write-Host "  killing $($_.Name) PID $($_.ProcessId)"
        taskkill /PID $_.ProcessId /T /F | Out-Null
    }

$lock = Join-Path $PSScriptRoot '..\.data\qdrant\.lock'
if (Test-Path $lock) {
    Remove-Item $lock -Force
    Write-Host "  removed stale lock $lock"
}

Start-Sleep -Milliseconds 500
$still = Get-NetTCPConnection -LocalPort 8000 -State Listen
if ($still) {
    Write-Host "WARNING: something is still on port 8000 (PID $($still.OwningProcess))." -ForegroundColor Yellow
} else {
    Write-Host "Clear. Start ONE backend now (no --reload):" -ForegroundColor Green
    Write-Host "  cd backend; .venv\Scripts\uvicorn app.main:app --port 8000"
}
