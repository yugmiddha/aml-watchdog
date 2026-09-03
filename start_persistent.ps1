$port = 8000
$conns = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
if ($conns) {
    foreach ($c in $conns) {
        if ($c.OwningProcess -gt 0) {
            Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
        }
    }
}
Start-Sleep -Milliseconds 500
Start-Process -FilePath "python" -ArgumentList "run_dashboard.py" -WorkingDirectory "D:\fintech\AML"
Start-Sleep -Seconds 2
Write-Host "Spawned persistent background AML server process!"
