# Shared Heartbeat authentication and transport / 共享心跳认证及传输。
function Send-PortalJson {
    param($Config, [string]$Path, $Payload)
    Invoke-RestMethod -Uri ($Config.portal_url.TrimEnd('/') + $Path) -Method Post `
        -Headers @{ 'X-Heartbeat-Token' = $Config.heartbeat_token } `
        -ContentType 'application/json' -Body ($Payload | ConvertTo-Json -Depth 10 -Compress) -TimeoutSec 10
}
Export-ModuleMember -Function Send-PortalJson
