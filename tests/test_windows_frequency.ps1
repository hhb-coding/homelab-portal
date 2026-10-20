# Native Windows PowerShell 5.1 synthetic tests / 原生 Windows 合成测试，不读真实计数器。
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/../clients/windows-frequency.ps1" -FunctionsOnly
$script:Checks = 0
function Assert-Equal($Actual,$Expected) {
    if ($Actual -ne $Expected) { throw "Assertion failed: expected $Expected, got $Actual" }
    $script:Checks++
}
function Assert-Throws([scriptblock]$Block) {
    $thrown=$false
    try { & $Block } catch { $thrown=$true }
    Assert-Equal $thrown $true
}
$counters = @(
    [pscustomobject]@{InstanceName='0,0';CookedValue=50;Status=0},
    [pscustomobject]@{InstanceName='0,1';CookedValue=150;Status=0},
    [pscustomobject]@{InstanceName='_Total';CookedValue=999;Status=0},
    [pscustomobject]@{InstanceName='0,_Total';CookedValue=999;Status=0}
)
$row=Convert-FrequencyCounters $counters 2600 2
Assert-Equal $row.cpu_frequency_ghz 2.6
Assert-Equal $row.valid_cpu_count 2
Assert-Equal $row.quality 'ok'
$partial=Convert-FrequencyCounters @($counters[0]) 2600 2
Assert-Equal $partial.cpu_frequency_ghz 1.3
Assert-Equal $partial.quality 'partial'
$missing=Convert-FrequencyCounters @([pscustomobject]@{InstanceName='0,0';CookedValue=100;Status=1}) 2600 2
Assert-Equal $missing.cpu_frequency_ghz $null
Assert-Equal $missing.quality 'unavailable'
$duplicate=Convert-FrequencyCounters @($counters[0],$counters[0]) 2600 2
Assert-Equal $duplicate.valid_cpu_count 1
Assert-Throws { Convert-FrequencyCounters $counters 2600 1 }
# Stub localized lookup and acquisition; verify second counter set is used.
# 替代计数器和本地化读取，验证使用第二组动态样本。
function Get-CimInstance { @([pscustomobject]@{MaxClockSpeed=2600;NumberOfLogicalProcessors=2}) }
function Get-LocalizedCounterName($EnglishName) { $EnglishName }
function Get-Counter { @([pscustomobject]@{CounterSamples=@()},[pscustomobject]@{CounterSamples=$counters}) }
$measured=Get-CurrentFrequency
Assert-Equal $measured.cpu_frequency_ghz 2.6
$directory=Join-Path ([IO.Path]::GetTempPath()) ('frequency-test-'+[Guid]::NewGuid().ToString('N'))
$path=Join-Path $directory 'queue.json'
$config=@{device_id='example-device';portal_url='https://example.invalid';heartbeat_token='synthetic-test'}
try {
    function Send-PortalJson { throw 'synthetic_timeout' }
    Assert-Throws { Invoke-FrequencyPass $config $path $row }
    Assert-Equal @(Get-Content -Raw $path | ConvertFrom-Json).Count 1
    function Send-PortalJson($Config,$Path,$Payload) { @{accepted=@($Payload.samples | ForEach-Object {$_.sample_id});duplicates=@()} }
    Invoke-FrequencyPass $config $path $partial
    Assert-Equal (Get-Content -Raw $path) '[]'
    # Reopen an empty queue on the next minute / 验证下一轮能读取已排空队列。
    Invoke-FrequencyPass $config $path $row
    Assert-Equal (Get-Content -Raw $path) '[]'
    Assert-Throws { Save-FrequencyQueue $path (@($row)*1441) }
    Assert-Throws { Save-FrequencyQueue $path @(@{value=('x'*1048577)}) }
    function Send-PortalJson { @{accepted=@();duplicates=@()} }
    Assert-Throws { Invoke-FrequencyPass $config $path $row }
    Assert-Equal @(Get-Content -Raw $path | ConvertFrom-Json).Count 1
    $lock=[IO.File]::Open("$path.lock",'OpenOrCreate','ReadWrite','None')
    try { Assert-Throws { Invoke-FrequencyPass $config $path $partial } } finally { $lock.Dispose() }
    [xml]$task=Get-Content -Raw "$PSScriptRoot/../clients/windows-frequency.task.xml"
    Assert-Equal $task.Task.Triggers.TimeTrigger.Repetition.Interval 'PT1M'
    Assert-Equal $task.Task.Settings.MultipleInstancesPolicy 'IgnoreNew'
} finally {
    if (Test-Path $directory) { Remove-Item -Recurse -Force $directory }
}
Write-Output "Windows synthetic checks passed: $script:Checks"
