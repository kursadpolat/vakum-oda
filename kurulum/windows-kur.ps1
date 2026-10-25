# Windows (yedek makine) kurulumu. Proje klasorunde, .venv kurulduktan sonra calistir:
#   powershell -ExecutionPolicy Bypass -File kurulum\windows-kur.ps1
# Yapar: oturum acilisinda baslayan gizli Gorev Zamanlayici gorevi + guvenlik duvari gelen kurallari (yonetici gerekir).
$ErrorActionPreference = 'Stop'
$Kok = Split-Path -Parent $PSScriptRoot
$Pyw = Join-Path $Kok '.venv\Scripts\pythonw.exe'
$Bekci = Join-Path $Kok 'bekci.py'
$Ad = 'VakumOda'

$act = New-ScheduledTaskAction -Execute $Pyw -Argument ('"' + $Bekci + '"') -WorkingDirectory $Kok
$trg = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
        -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
        -MultipleInstances IgnoreNew -Hidden
$prn = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $Ad -Action $act -Trigger $trg -Settings $set -Principal $prn -Force | Out-Null
Write-Output "gorev kayitli: $Ad"

try {
    # port bazli kural (venv python'u temel python'u baslattigi icin program bazli kural guvenilmez)
    if (-not (Get-NetFirewallRule -DisplayName 'VakumOda 8765 TCP' -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName 'VakumOda 8765 TCP' -Direction Inbound -Protocol TCP -LocalPort 8765 -Action Allow -Profile Private | Out-Null
    }
    if (-not (Get-NetFirewallRule -DisplayName 'VakumOda mDNS UDP 5353' -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName 'VakumOda mDNS UDP 5353' -Direction Inbound -Protocol UDP -LocalPort 5353 -Action Allow -Profile Private | Out-Null
    }
    Write-Output 'guvenlik duvari kurallari tamam'
} catch {
    Write-Output ('GUVENLIK DUVARI KURALI EKLENEMEDI (yonetici PowerShell ile tekrar calistir): ' + $_.Exception.Message)
}
Start-ScheduledTask -TaskName $Ad
Write-Output 'gorev baslatildi'
