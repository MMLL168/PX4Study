# OpenOCD Relay Server - 在 Windows 背景執行
# 監聽 TCP 9998，收到 Docker 容器觸發後自動啟動 OpenOCD
# 設定為開機啟動後，完全不需要手動操作

param([switch]$Install, [switch]$Uninstall)

$scriptPath = $MyInvocation.MyCommand.Path
$taskName   = "PX4-OpenOCD-Relay"

if ($Uninstall) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "已移除開機啟動排程" -ForegroundColor Yellow
    exit 0
}

if ($Install) {
    # 加入 Windows 工作排程器，登入時自動在背景執行
    $action  = New-ScheduledTaskAction -Execute "powershell.exe" `
        -Argument "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$scriptPath`""
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit 0 -RestartCount 3
    Register-ScheduledTask -TaskName $taskName -Action $action `
        -Trigger $trigger -Settings $settings -RunLevel Highest -Force | Out-Null
    Write-Host "已設定開機自動啟動 (工作排程器：$taskName)" -ForegroundColor Green

    # 立刻啟動一個實例
    Start-Process powershell.exe -ArgumentList "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$scriptPath`"" -WindowStyle Hidden
    Write-Host "Relay 已在背景啟動，之後開機自動執行" -ForegroundColor Green
    exit 0
}

# ── 主服務邏輯 ──────────────────────────────────────────
function Find-OpenOCD {
    foreach ($root in @("C:\ST\", "C:\Program Files\ST\", "C:\Program Files (x86)\ST\")) {
        if (Test-Path $root) {
            $f = (Get-ChildItem $root -Recurse -Filter "openocd.exe" -ErrorAction SilentlyContinue | Select-Object -First 1).FullName
            if ($f) { return $f }
        }
    }
    return $null
}

function Is-OpenOCDRunning {
    try {
        $tcp = [System.Net.Sockets.TcpClient]::new()
        $tcp.Connect("127.0.0.1", 3333)
        $tcp.Close()
        return $true
    } catch { return $false }
}

function Start-OpenOCD {
    if (Is-OpenOCDRunning) { return }

    $ocd = Find-OpenOCD
    if (-not $ocd) { return }

    $stlink  = (Get-ChildItem "C:\ST\" -Recurse -Filter "stlink-dap.cfg" -ErrorAction SilentlyContinue | Select-Object -First 1).FullName
    $scripts = Split-Path (Split-Path $stlink -Parent) -Parent

    $rule = Get-NetFirewallRule -DisplayName "OpenOCD GDB 3333" -ErrorAction SilentlyContinue
    if (-not $rule) {
        New-NetFirewallRule -DisplayName "OpenOCD GDB 3333" -Direction Inbound `
            -Protocol TCP -LocalPort 3333 -Action Allow | Out-Null
    }

    # 只做 init，不做 reset halt（STM32H7 VECTRESET 會 timeout）
    # reset halt 由 GDB preLaunchCommands 的 monitor reset_config srst_only + monitor reset halt 處理
    Start-Process -FilePath $ocd -ArgumentList "-s `"$scripts`" -f interface/stlink-dap.cfg -c `"set AP_NUM 0`" -c `"set CONNECT_UNDER_RESET 1`" -c `"set ENABLE_LOW_POWER 1`" -c `"set STOP_WATCHDOG 1`" -f target/stm32h7x.cfg -c `"tcl_port disabled`" -c `"init`"" -WindowStyle Minimized
}

# TCP listener
$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Any, 9998)
$listener.Start()

while ($true) {
    try {
        $client = $listener.AcceptTcpClient()
        $client.Close()
        Start-OpenOCD
    } catch { break }
}
$listener.Stop()
