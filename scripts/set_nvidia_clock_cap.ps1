param(
    [Parameter(Mandatory=$true)][string]$AuditPath,
    [ValidateRange(300,800)][int]$MaximumClockMHz = 450
)
$ErrorActionPreference = 'Stop'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Setting the NVIDIA hard clock cap requires Windows Administrator'
}
$exe = (Get-Command nvidia-smi.exe -ErrorAction Stop).Source
$output = & $exe -i 0 -lgc "300,$MaximumClockMHz" 2>&1 | Out-String
if ($LASTEXITCODE -ne 0 -or $output -notmatch 'GPU clocks set to') {
    throw "Hard clock cap failed: $output"
}
$payload = @{
    minimum_clock_mhz = 300
    maximum_clock_mhz = $MaximumClockMHz
    applied_at_utc = [DateTimeOffset]::UtcNow.ToString('o')
    clock_command_output = $output.Trim()
    workload_started = $false
}
$temporary = $AuditPath + '.tmp'
[IO.File]::WriteAllText($temporary, ($payload | ConvertTo-Json -Depth 5), [Text.UTF8Encoding]::new($false))
Move-Item -LiteralPath $temporary -Destination $AuditPath -Force
[Console]::WriteLine($output.Trim())
