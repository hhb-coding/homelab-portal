param(
    [string]$ConfigPath = "$env:USERPROFILE\.config\homelab-portal\heartbeat.json",
    [string]$QueuePath = "$env:LOCALAPPDATA\homelab-portal\frequency.json",
    [switch]$FunctionsOnly
)
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'portal-transport.psm1') -Force

function Convert-FrequencyCounters {
    param($Counters, [double]$NominalMHz, [int]$LogicalCount)
    # Dynamic APERF/MPERF-derived performance percentage, scaled by nominal MHz.
    # 动态性能百分比换算；标称 MHz 仅为比例基准，绝不单独作为采样值。
    $values = @()
    $seen = @{}
    foreach ($counter in $Counters) {
        if ($counter.InstanceName -notmatch '^\d+,\d+$' -or $seen.ContainsKey($counter.InstanceName)) { continue }
        $seen[$counter.InstanceName] = $true
        $ghz = $NominalMHz * [double]$counter.CookedValue / 100000.0
        if ($counter.Status -eq 0 -and -not [double]::IsNaN($ghz) -and -not [double]::IsInfinity($ghz) -and $ghz -gt 0 -and $ghz -le 20) {
            $values += $ghz
        }
    }
    if ($values.Count -gt $LogicalCount) { throw 'invalid_counter_count' }
    $quality = if ($values.Count -eq 0) { 'unavailable' } elseif ($values.Count -eq $LogicalCount) { 'ok' } else { 'partial' }
    $value = if ($values.Count) { ($values | Measure-Object -Average).Average } else { $null }
    @{
        sample_id = [Guid]::NewGuid().ToString('N')
        sampled_utc = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ss.fffZ')
        cpu_frequency_ghz = $value
        source = 'windows_processor_performance'
        quality = $quality
        logical_cpu_count = $LogicalCount
        valid_cpu_count = $values.Count
        window_ms = 1000
        error = $(if ($quality -eq 'ok') { $null } elseif ($values.Count) { 'partial_read' } else { 'invalid_counter' })
    }
}

function Get-LocalizedCounterName {
    param([string]$EnglishName)
    $english = (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Perflib\009').Counter
    $local = (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Perflib\CurrentLanguage').Counter
    for ($i = 1; $i -lt $english.Length; $i += 2) {
        if ($english[$i] -eq $EnglishName) {
            for ($j = 0; $j -lt $local.Length; $j += 2) {
                if ($local[$j] -eq $english[$i-1]) { return $local[$j+1] }
            }
        }
    }
    throw 'counter_unavailable'
}

function Get-CurrentFrequency {
    $cpus = @(Get-CimInstance Win32_Processor)
    # X230 target has one package; refuse ambiguous cross-package scaling.
    # X230 单插槽；多插槽基准不明确时拒绝生成错误频率。
    if ($cpus.Count -ne 1 -or $cpus[0].MaxClockSpeed -le 0) { throw 'nominal_reference_unavailable' }
    $category = Get-LocalizedCounterName 'Processor Information'
    $counter = Get-LocalizedCounterName '% Processor Performance'
    $sets = @(Get-Counter -Counter "\$category(*)\$counter" -SampleInterval 1 -MaxSamples 2)
    Convert-FrequencyCounters $sets[-1].CounterSamples $cpus[0].MaxClockSpeed $cpus[0].NumberOfLogicalProcessors
}

function Save-FrequencyQueue {
    param([string]$Path, [object[]]$Rows)
    $json = ConvertTo-Json -InputObject @($Rows) -Depth 10 -Compress
    if ($Rows.Count -gt 1440 -or [Text.Encoding]::UTF8.GetByteCount($json) -gt 1048576) { throw 'client_queue_full' }
    $temporary = "$Path.tmp"
    $bytes = [Text.Encoding]::UTF8.GetBytes($json)
    $stream = [IO.File]::Open($temporary, [IO.FileMode]::Create, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try { $stream.Write($bytes, 0, $bytes.Length); $stream.Flush($true) } finally { $stream.Dispose() }
    if ([IO.File]::Exists($Path)) { [IO.File]::Replace($temporary, $Path, $null) } else { [IO.File]::Move($temporary, $Path) }
}

function Invoke-FrequencyPass {
    param($Config, [string]$Path, $Observation)
    if (-not $Config.device_id -or -not $Config.heartbeat_token -or -not $Config.portal_url) { throw 'configuration_missing' }
    $parent = Split-Path -Parent $Path
    $null = [IO.Directory]::CreateDirectory($parent)
    # Private inherited ACL is required; never store credentials in this queue.
    # 队列继承用户私有目录 ACL，不保存凭据。文件独占锁阻止并发任务。
    $lock = [IO.File]::Open("$Path.lock", [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    try {
        $rows = @()
        if (Test-Path $Path) {
            if ((Get-Item $Path).Length -gt 1048576) { throw 'client_queue_full' }
            $rows = @(Get-Content -Raw $Path | ConvertFrom-Json)
        }
        $cutoff = [DateTime]::UtcNow.AddHours(-24)
        $retained = @($rows | Where-Object { [DateTimeOffset]::Parse($_.sampled_utc).UtcDateTime -ge $cutoff })
        $expired = $rows.Count - $retained.Count
        if ($expired) { Write-Warning "Frequency queue expired samples: $expired" }
        if ($retained.Count -ge 1440) {
            $batch = @($retained | Select-Object -First 120)
            $reply = Send-PortalJson $Config '/api/telemetry/cpu-frequency' @{ device_id = $Config.device_id; samples = $batch }
            $expected = @($batch | ForEach-Object { $_.sample_id } | Sort-Object -Unique)
            $ack = @(@($reply.accepted) + @($reply.duplicates) | Sort-Object -Unique)
            if (@(Compare-Object $expected $ack).Count) { throw 'invalid_acknowledgement' }
            $retained = @($retained | Select-Object -Skip $batch.Count)
            Save-FrequencyQueue $Path $retained
        }
        $rows = @($retained) + @($Observation)
        Save-FrequencyQueue $Path $rows
        for ($pass = 0; $pass -lt 12 -and $rows.Count; $pass++) {
            $batch = @($rows | Select-Object -First 120)
            $reply = Send-PortalJson $Config '/api/telemetry/cpu-frequency' @{ device_id = $Config.device_id; samples = $batch }
            $expected = @($batch | ForEach-Object { $_.sample_id } | Sort-Object -Unique)
            $ack = @(@($reply.accepted) + @($reply.duplicates) | Sort-Object -Unique)
            if (@(Compare-Object $expected $ack).Count) { throw 'invalid_acknowledgement' }
            $rows = @($rows | Select-Object -Skip $batch.Count)
            Save-FrequencyQueue $Path $rows
        }
        if ($expired) { throw 'client_samples_expired' }
    } finally { $lock.Dispose() }
}

if (-not $FunctionsOnly) {
    try {
        $config = Get-Content -Raw $ConfigPath | ConvertFrom-Json
        try { $observation = Get-CurrentFrequency } catch {
            $observation = Convert-FrequencyCounters @() 0 0
        }
        Invoke-FrequencyPass $config $QueuePath $observation
        exit 0
    } catch {
        Write-Error 'Frequency sampling/upload failed; inspect configuration, counters and queue capacity.'
        exit 1
    }
}
