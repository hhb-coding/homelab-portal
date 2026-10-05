param(
    [string]$ConfigPath = "$env:USERPROFILE\.config\homelab-portal\heartbeat.json"
)

<#
HomeLab Portal Windows Heartbeat Client
=======================================

Reports hostname, LAN IPv4 address, and optional ZeroTier IPv4 address
to the HomeLab Portal heartbeat API.

向 HomeLab Portal heartbeat API 上报 Windows 设备的主机名、
LAN IPv4 地址以及可选的 ZeroTier IPv4 地址。
#>

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"


function Get-ZeroTierAdapter {
    <#
    Find the first active ZeroTier network adapter.
    查找第一个活动的 ZeroTier 网络适配器。
    #>

    return Get-NetAdapter -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Status -eq "Up" -and (
                $_.Name -match "ZeroTier" -or
                $_.InterfaceDescription -match "ZeroTier"
            )
        } |
        Select-Object -First 1
}


function Get-ZeroTierIPv4 {
    <#
    Return the IPv4 address assigned to ZeroTier, if available.
    如果存在 ZeroTier，则返回它的 IPv4 地址。
    #>

    $adapter = Get-ZeroTierAdapter

    if (-not $adapter) {
        return $null
    }

    $address = Get-NetIPAddress `
        -AddressFamily IPv4 `
        -InterfaceIndex $adapter.ifIndex `
        -ErrorAction SilentlyContinue |
        Where-Object {
            $_.IPAddress -notlike "169.254.*"
        } |
        Select-Object -First 1

    if ($address) {
        return $address.IPAddress
    }

    return $null
}


function Get-PrimaryLanIPv4 {
    <#
    Determine the LAN IPv4 address through the default route.

    根据默认路由识别主要 LAN IPv4 地址。
    ZeroTier 地址不会被当成 LAN 地址。
    #>

    $zeroTierAdapter = Get-ZeroTierAdapter

    $routes = Get-NetRoute `
        -AddressFamily IPv4 `
        -DestinationPrefix "0.0.0.0/0" `
        -ErrorAction SilentlyContinue |
        Sort-Object RouteMetric

    foreach ($route in $routes) {

        if (
            $zeroTierAdapter -and
            $route.InterfaceIndex -eq $zeroTierAdapter.ifIndex
        ) {
            continue
        }

        $address = Get-NetIPAddress `
            -AddressFamily IPv4 `
            -InterfaceIndex $route.InterfaceIndex `
            -ErrorAction SilentlyContinue |
            Where-Object {
                $_.IPAddress -ne "127.0.0.1" -and
                $_.IPAddress -notlike "169.254.*"
            } |
            Select-Object -First 1

        if ($address) {
            return $address.IPAddress
        }
    }

    return $null
}


function Send-Heartbeat {
    <#
    Read local configuration and send one heartbeat.
    读取本机配置并发送一次 heartbeat。
    #>

    if (-not (Test-Path $ConfigPath)) {
        throw "Configuration file not found: $ConfigPath"
    }

    $config = Get-Content `
        -Raw `
        -Path $ConfigPath |
        ConvertFrom-Json

    if (-not $config.portal_url) {
        throw "portal_url is missing from configuration."
    }

    if (-not $config.heartbeat_token) {
        throw "heartbeat_token is missing from configuration."
    }

    if (-not $config.device_id) {
        throw "device_id is missing from configuration."
    }

    $portalUrl = $config.portal_url.TrimEnd("/")

    $payload = @{
        device_id    = $config.device_id
        hostname     = $env:COMPUTERNAME
        display_name = $config.display_name
        lan_ip       = Get-PrimaryLanIPv4
        zerotier_ip  = Get-ZeroTierIPv4
    }

    $headers = @{
        "X-Heartbeat-Token" = $config.heartbeat_token
    }

    $response = Invoke-RestMethod `
        -Uri "$portalUrl/api/heartbeat" `
        -Method Post `
        -Headers $headers `
        -ContentType "application/json" `
        -Body ($payload | ConvertTo-Json -Compress) `
        -TimeoutSec 10

    Write-Output ($response | ConvertTo-Json -Compress)
}


try {
    Send-Heartbeat
    exit 0
}
catch {
    Write-Error "Heartbeat failed: $($_.Exception.Message)"
    exit 1
}
