param(
    [Parameter(Mandatory=$true)][string]$BindAddress,
    [Parameter(Mandatory=$true)][string]$ModelsDir,
    [Parameter(Mandatory=$true)][string]$StopFile,
    [Parameter(Mandatory=$true)][string]$StopRequest,
    [Parameter(Mandatory=$true)][string]$Heartbeat,
    [Parameter(Mandatory=$true)][string]$Journal,
    [Parameter(Mandatory=$true)][string]$LimitsPath
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'windows_memory.ps1')
. (Join-Path $PSScriptRoot 'windows_ollama_job.ps1')
$text2sql_job = $null
$text2sql_server = $null
$text2sql_peak = $null
$text2sql_sample = $null
$text2sql_samples = 0
$text2sql_reason = $null
$text2sql_limits = Get-Content -LiteralPath $LimitsPath -Raw | ConvertFrom-Json
$text2sql_gpu_exe = (Get-Command nvidia-smi.exe -ErrorAction Stop).Source
function Get-Text2SqlSample {
    $info = New-Object Diagnostics.ProcessStartInfo
    $info.FileName = $text2sql_gpu_exe
    $info.Arguments = '--query-gpu=memory.used,temperature.gpu,power.draw.average,power.draw.instant,utilization.gpu,clocks.current.graphics --format=csv,noheader,nounits'
    $info.UseShellExecute = $false
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $info.CreateNoWindow = $true
    $sensor = [Diagnostics.Process]::Start($info)
    try {
        if (-not $sensor.WaitForExit(500)) {
            $sensor.Kill()
            throw 'GPU sensor timeout'
        }
        if ($sensor.ExitCode -ne 0) { throw 'GPU sensor failed' }
        $parts = $sensor.StandardOutput.ReadToEnd().Trim().Split(',')
        if ($parts.Count -ne 6) { throw 'GPU sensor malformed or multiple GPUs' }
        $values = @()
        foreach ($part in $parts) {
            $number = [double]::Parse($part.Trim(), [Globalization.CultureInfo]::InvariantCulture)
            if ([double]::IsNaN($number) -or [double]::IsInfinity($number) -or $number -lt 0) {
                throw 'Invalid GPU sensor value'
            }
            $values += $number
        }
        return @{
            available_ram_gib = [Text2SqlHostMemory]::AvailableBytes() / 1073741824.0
            swap_used_gib = [Text2SqlHostMemory]::PageFileUsedBytes() / 1073741824.0
            gpu_memory_mib = $values[0]
            gpu_temperature_c = $values[1]
            gpu_power_w = [Math]::Max($values[2], $values[3])
            gpu_utilization_pct = $values[4]
            gpu_clock_mhz = $values[5]
        }
    } finally { $sensor.Dispose() }
}
function Assert-Text2SqlSafe($sample) {
    $checks = @(
        @('available_ram_gib', 'minimum_available_ram_gib', 'RAM'),
        @('swap_used_gib', 'maximum_swap_used_gib', 'pagefile'),
        @('gpu_memory_mib', 'maximum_gpu_memory_mib', 'VRAM'),
        @('gpu_temperature_c', 'maximum_gpu_temperature_c', 'temperature'),
        @('gpu_power_w', 'maximum_gpu_power_w', 'power'),
        @('gpu_clock_mhz', 'maximum_gpu_clock_mhz', 'clock')
    )
    foreach ($check in $checks) {
        $threshold = $text2sql_limits.($check[1])
        if ($null -eq $threshold -or [double]$threshold -le 0 -or [double]::IsNaN([double]$threshold) -or [double]::IsInfinity([double]$threshold)) {
            throw "Missing or invalid safety limit: $($check[1])"
        }
        $value = $sample[$check[0]]
        $breach = if ($check[0] -eq 'available_ram_gib') { $value -lt $threshold }
                  elseif ($check[0] -eq 'gpu_clock_mhz') { $value -gt $threshold }
                  else { $value -ge $threshold }
        if ($breach) { throw "$($check[2]) observed=$value limit=$threshold" }
    }
    if ($sample.gpu_utilization_pct -gt 100) { throw 'Invalid utilization sensor' }
}
function Merge-Text2SqlPeak($sample) {
    if ($null -eq $script:text2sql_peak) { $script:text2sql_peak = $sample.Clone(); return }
    foreach ($key in $sample.Keys) {
        if ($key -eq 'available_ram_gib') {
            $script:text2sql_peak[$key] = [Math]::Min($script:text2sql_peak[$key], $sample[$key])
        } else {
            $script:text2sql_peak[$key] = [Math]::Max($script:text2sql_peak[$key], $sample[$key])
        }
    }
}
try {
    if (Test-Path -LiteralPath $StopFile) { throw 'Resource stop already latched; never auto retry' }
    if (-not (Test-Path -LiteralPath (Join-Path $ModelsDir 'manifests'))) { throw 'Existing model store missing' }
    $text2sql_sample = Get-Text2SqlSample
    Merge-Text2SqlPeak $text2sql_sample
    Assert-Text2SqlSafe $text2sql_sample
    $text2sql_job = New-Object Text2SqlJob
    $env:OLLAMA_HOST = $BindAddress
    $env:OLLAMA_MODELS = $ModelsDir
    $env:OLLAMA_NUM_PARALLEL = '1'
    $env:OLLAMA_MAX_LOADED_MODELS = '1'
    $env:OLLAMA_MAX_QUEUE = '2'
    $env:OLLAMA_KEEP_ALIVE = '0'
    $env:OLLAMA_CONTEXT_LENGTH = '4096'
    $env:OLLAMA_FLASH_ATTENTION = '1'
    $env:OLLAMA_KV_CACHE_TYPE = 'q8_0'
    $info = New-Object Diagnostics.ProcessStartInfo
    $info.FileName = (Get-Command ollama.exe -ErrorAction Stop).Source
    $info.Arguments = 'serve'
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $text2sql_server = [Diagnostics.Process]::Start($info)
    # No client can send inference before the harness verifies readiness.
    $text2sql_job.Assign($text2sql_server)
    $text2sql_server.PriorityClass = [Diagnostics.ProcessPriorityClass]::BelowNormal
    [Console]::WriteLine("NATIVE SERVER OWNED: pid=$($text2sql_server.Id) address=$BindAddress")
    while (-not (Test-Path -LiteralPath $StopRequest)) {
        $timer = [Diagnostics.Stopwatch]::StartNew()
        if ($text2sql_server.HasExited) { throw 'Owned native Ollama exited' }
        if (-not (Test-Path -LiteralPath $Heartbeat)) { throw 'Harness heartbeat missing' }
        $age = ([DateTime]::UtcNow - (Get-Item -LiteralPath $Heartbeat).LastWriteTimeUtc).TotalSeconds
        if ($age -gt 10) { throw 'Harness heartbeat stale; stop orphaned native runners' }
        $text2sql_sample = Get-Text2SqlSample
        Merge-Text2SqlPeak $text2sql_sample
        $text2sql_samples += 1
        Assert-Text2SqlSafe $text2sql_sample
        # An observation slower than the sensor budget is itself a failure.
        if ($timer.ElapsedMilliseconds -gt 1000) { throw 'Windows sensor loop exceeded one second' }
        $payload = @{ sample = $text2sql_sample; sampled_at_ms = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() }
        [IO.File]::AppendAllText($Journal, (($payload | ConvertTo-Json -Compress) + "`n"), [Text.UTF8Encoding]::new($false))
        Start-Sleep -Milliseconds ([Math]::Max(0, 500 - $timer.ElapsedMilliseconds))
    }
} catch {
    $text2sql_reason = $_.Exception.Message
} finally {
    $text2sql_cleanup_complete = $true
    # Stop the entire owned process tree before writing evidence.
    if ($null -ne $text2sql_job) { $text2sql_job.Dispose() }
    if ($null -ne $text2sql_server) {
        if (-not $text2sql_server.WaitForExit(2000)) { $text2sql_server.Kill(); $text2sql_reason = 'Native cleanup timeout'; $text2sql_cleanup_complete = $false }
        $text2sql_server.Dispose()
    }
    if ($null -ne $text2sql_reason) {
        $payload = @{ reason = $text2sql_reason; last_sample = $text2sql_sample; observed_peak = $text2sql_peak; samples = $text2sql_samples; cleanup_complete = $text2sql_cleanup_complete; limits = $text2sql_limits }
        if (-not (Test-Path -LiteralPath $StopFile)) {
            $temporary = $StopFile + '.tmp'
            [IO.File]::WriteAllText($temporary, ($payload | ConvertTo-Json -Depth 6), [Text.UTF8Encoding]::new($false))
            [IO.File]::Move($temporary, $StopFile)
        }
        [Console]::WriteLine("NATIVE RESOURCE STOP: $text2sql_reason")
    } else {
        [Console]::WriteLine('NATIVE SERVER CLEANLY STOPPED; job and runners closed')
    }
}
if ($null -ne $text2sql_reason) { exit 1 }
