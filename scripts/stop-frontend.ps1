# Release native dependency locks held by frontend processes from this checkout.
# Never stop Node processes merely because they share a name or port.
param([string]$RepoRoot = (Split-Path -Parent $PSScriptRoot))

$ErrorActionPreference = "Stop"
$repoPath = (Resolve-Path -LiteralPath $RepoRoot).Path
if (-not (Test-Path -LiteralPath (Join-Path $repoPath "frontend/package.json"))) {
    throw "Not a Team Science checkout: $repoPath"
}
$modulesPath = ([IO.Path]::GetFullPath((Join-Path $repoPath "frontend/node_modules"))).Replace('\', '/').TrimEnd('/') + '/'

function Test-CheckoutFrontendProcess($Process) {
    if ($Process.Name -ne "node.exe" -or -not $Process.CommandLine) { return $false }
    $command = $Process.CommandLine.Replace('\', '/')
    # Match a complete path boundary, including quoted paths with spaces.
    return $command -match ('(?:^|[\s"''])' + [regex]::Escape($modulesPath))
}

$targets = @(Get-CimInstance Win32_Process -Filter "Name = 'node.exe'" | Where-Object { Test-CheckoutFrontendProcess $_ })
foreach ($target in $targets) {
    # Recheck identity so a reused PID cannot target an unrelated process.
    $current = Get-CimInstance Win32_Process -Filter "ProcessId = $($target.ProcessId)"
    if ($current -and $current.CommandLine -ceq $target.CommandLine -and (Test-CheckoutFrontendProcess $current)) {
        Write-Host "Stopping this checkout's frontend process $($target.ProcessId)..."
        Stop-Process -Id $target.ProcessId -Force -ErrorAction Stop
    }
}
foreach ($target in $targets) {
    $remaining = Get-Process -Id $target.ProcessId -ErrorAction SilentlyContinue
    if ($remaining) { $remaining.WaitForExit(5000) | Out-Null }
}
