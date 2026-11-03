#requires -Version 5.1
param(
    [ValidateSet('status', 'enable', 'disable', 'repair', 'update')]
    [string]$Action = 'status'
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding
$script:Notes = New-Object 'System.Collections.Generic.List[string]'
$script:Reboot = $false

function Get-DefenderSnapshot {
    $snapshot = [ordered]@{
        available = $false; realtime = $null; antivirus = $null
        tamper = $null; service = $null; mode = $null
        signature = $null; signature_updated = $null; error = $null
    }
    try {
        $state = Get-MpComputerStatus -ErrorAction Stop
        if ($null -eq $state) { throw 'Defender не вернул состояние.' }
        $snapshot.available = $true
        $snapshot.realtime = $state.RealTimeProtectionEnabled
        $snapshot.antivirus = $state.AntivirusEnabled
        $snapshot.tamper = $state.IsTamperProtected
        $snapshot.mode = $state.AMRunningMode
        $snapshot.signature = $state.AntivirusSignatureVersion
        if ($null -ne $state.AntivirusSignatureLastUpdated) {
            $snapshot.signature_updated = $state.AntivirusSignatureLastUpdated.ToString('yyyy-MM-dd HH:mm:ss')
        }
    } catch { $snapshot.error = $_.Exception.Message }
    try { $snapshot.service = (Get-Service -Name WinDefend -ErrorAction Stop).Status.ToString() }
    catch {
        if (-not $snapshot.error) { $snapshot.error = $_.Exception.Message }
    }
    return $snapshot
}

function Enable-Defender {
    Write-Output 'Проверка службы Microsoft Defender...'
    try {
        $service = Get-Service -Name WinDefend -ErrorAction Stop
        if ($service.StartType -eq 'Disabled') {
            Set-Service -Name WinDefend -StartupType Automatic -ErrorAction Stop
        }
        if ($service.Status -ne 'Running') { Start-Service -Name WinDefend -ErrorAction Stop }
    } catch { $script:Notes.Add(('Служба: ' + $_.Exception.Message)) }

    # Восстанавливаем только перечисленные настройки, не затрагивая исключения,
    # сетевые правила, журналы, сторонние антивирусы и политики организации.
    $preferences = $null
    try { $preferences = Get-MpPreference -ErrorAction Stop } catch { }
    foreach ($name in @('DisableRealtimeMonitoring', 'DisableBehaviorMonitoring', 'DisableIOAVProtection', 'DisableScriptScanning')) {
        try {
            if ($null -eq $preferences -or $preferences.$name -ne $false) {
                $parameters = @{ ErrorAction = 'Stop' }
                $parameters[$name] = $false
                Set-MpPreference @parameters
                Write-Output ('Включена настройка: ' + $name)
            }
        } catch { $script:Notes.Add(($name + ': ' + $_.Exception.Message)) }
    }
}

function Wait-Realtime([bool]$Expected) {
    $snapshot = Get-DefenderSnapshot
    for ($i = 0; $i -lt 5; $i++) {
        if ($snapshot.available -and $snapshot.realtime -eq $Expected) { break }
        Start-Sleep -Seconds 1
        $snapshot = Get-DefenderSnapshot
    }
    return $snapshot
}

function Repair-Components {
    Write-Output 'Восстановление хранилища компонентов DISM. Может потребоваться интернет; дождитесь завершения.'
    & "$env:SystemRoot\System32\dism.exe" /Online /Cleanup-Image /RestoreHealth /NoRestart /English | ForEach-Object { Write-Output $_ }
    $dismExit = $LASTEXITCODE
    if ($dismExit -eq 3010) { $script:Reboot = $true }
    elseif ($dismExit -ne 0) { $script:Notes.Add(('DISM завершился с кодом ' + $dismExit + '. Подробности: C:\Windows\Logs\DISM\dism.log')) }

    Write-Output 'Проверка системных файлов SFC...'
    & "$env:SystemRoot\System32\sfc.exe" /scannow | ForEach-Object { Write-Output ($_ -replace "`0", '') }
    $sfcExit = $LASTEXITCODE
    if ($sfcExit -ne 0) { $script:Notes.Add(('SFC завершился с кодом ' + $sfcExit + '. Проверьте вывод и C:\Windows\Logs\CBS\CBS.log')) }
    Enable-Defender
}

$ok = $false
$message = ''
$snapshot = $null
try {
    switch ($Action) {
        'status' {
            $snapshot = Get-DefenderSnapshot
            $ok = $snapshot.available
            $message = if ($ok) { 'Состояние обновлено.' } else { 'Не удалось получить состояние Defender. ' + $snapshot.error }
        }
        'enable' {
            Enable-Defender
            $snapshot = Wait-Realtime $true
            $ok = $snapshot.available -and $snapshot.realtime -eq $true -and $snapshot.antivirus -eq $true -and $script:Notes.Count -eq 0
            $message = if ($ok) { 'Защита Microsoft Defender включена.' } else { 'Включение выполнено не полностью. Проверьте состояние и журнал. Возможны политики, сторонний антивирус или повреждённые компоненты.' }
        }
        'disable' {
            $before = Get-DefenderSnapshot
            if (-not $before.available) { throw ('Состояние Defender неизвестно: ' + $before.error) }
            if ($before.tamper -eq $true) {
                throw 'Отключение заблокировано защитой от подделки. Её состояние можно изменить вручную в «Безопасность Windows» → «Защита от вирусов и угроз» → «Управление настройками». Затем повторите действие.'
            }
            Write-Output 'Запрос временного отключения защиты в реальном времени...'
            Set-MpPreference -DisableRealtimeMonitoring $true -ErrorAction Stop
            $snapshot = Wait-Realtime $false
            $ok = $snapshot.available -and $snapshot.realtime -eq $false
            $message = if ($ok) { 'Защита в реальном времени отключена. Windows может автоматически включить её снова.' } else { 'Windows не подтвердила отключение. Проверьте защиту от подделки и политики организации.' }
        }
        'repair' {
            Repair-Components
            $snapshot = Wait-Realtime $true
            $ok = $snapshot.available -and $snapshot.realtime -eq $true -and $snapshot.antivirus -eq $true -and $script:Notes.Count -eq 0
            $message = if ($ok) { 'Проверка и восстановление завершены, защита включена. Проверьте вывод SFC; после исправления файлов может потребоваться перезагрузка.' } else { 'Восстановление завершено с замечаниями. Проверьте журнал; может потребоваться перезагрузка или восстановительная установка Windows с сохранением файлов.' }
        }
        'update' {
            Write-Output 'Обновление антивирусных баз Microsoft...'
            Update-MpSignature -ErrorAction Stop
            $snapshot = Get-DefenderSnapshot
            $ok = $snapshot.available
            $message = if ($ok) { 'Обновление антивирусных баз завершено.' } else { 'Обновление выполнено, но прочитать состояние не удалось.' }
        }
    }
} catch {
    $ok = $false
    $message = $_.Exception.Message
}
if ($null -eq $snapshot) { $snapshot = Get-DefenderSnapshot }
$result = [ordered]@{
    ok = [bool]$ok; message = $message; status = $snapshot
    warnings = @($script:Notes.ToArray()); reboot_required = $script:Reboot
}
Write-Output ('DEFENDERPILOT_RESULT:' + ($result | ConvertTo-Json -Depth 6 -Compress))
if (-not $ok) { exit 1 }
exit 0
