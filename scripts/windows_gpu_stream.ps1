$ErrorActionPreference = 'Stop'
$text2sql_gpu_stream = $null
$text2sql_gpu_pending = $null
$text2sql_gpu_stderr = $null
$text2sql_gpu_journal = $null
function Start-Text2SqlGpuStream {
    $info = New-Object Diagnostics.ProcessStartInfo
    $info.FileName = (Get-Command nvidia-smi.exe -ErrorAction Stop).Source
    $info.Arguments = '--id=0 --query-gpu=memory.used,temperature.gpu,power.draw.average,power.draw.instant,utilization.gpu,clocks.current.graphics --format=csv,noheader,nounits --loop-ms=200'
    $info.UseShellExecute = $false
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $info.CreateNoWindow = $true
    $script:text2sql_gpu_stream = [Diagnostics.Process]::Start($info)
    $script:text2sql_gpu_pending = $text2sql_gpu_stream.StandardOutput.ReadLineAsync()
    $script:text2sql_gpu_stderr = $text2sql_gpu_stream.StandardError.ReadToEndAsync()
}
function Read-Text2SqlGpuStream([bool]$Startup = $false) {
    if ($null -eq $text2sql_gpu_stream -or $text2sql_gpu_stream.HasExited) {
        throw 'GPU sensor stream is not running'
    }
    # A longer startup allowance is used only before any model server starts.
    # Every running read requires a new line; no cached-safe fallback or retry.
    $timeout = if ($Startup) { 5000 } else { 500 }
    if (-not $text2sql_gpu_pending.Wait($timeout)) { throw 'GPU sensor stream timeout' }
    $peak = $null
    $frames = 0
    while ($text2sql_gpu_pending.IsCompleted) {
        $line = $text2sql_gpu_pending.GetAwaiter().GetResult()
        if ($null -eq $line) { throw 'GPU sensor stream stdout closed' }
        $parts = $line.Trim().Split(',')
        if ($parts.Count -ne 6) { throw 'GPU sensor malformed or multiple GPUs' }
        $values = @()
        foreach ($part in $parts) {
            $number = [double]::Parse($part.Trim(), [Globalization.CultureInfo]::InvariantCulture)
            if ([double]::IsNaN($number) -or [double]::IsInfinity($number) -or $number -lt 0) {
                throw 'Invalid GPU sensor value'
            }
            $values += $number
        }
        foreach ($index in @(0,1,4,5)) {
            if ($values[$index] -ne [Math]::Floor($values[$index])) { throw 'Invalid integral GPU sensor' }
        }
        if ($values[4] -gt 100) { throw 'Invalid GPU utilization' }
        if ($null -ne $text2sql_gpu_journal) {
            $frame = @{ received_at_ms = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds(); source = 'windows-nvidia-smi'; raw = $line.Trim(); power_average_w = $values[2]; power_instant_w = $values[3] }
            [IO.File]::AppendAllText($text2sql_gpu_journal, (($frame | ConvertTo-Json -Compress) + "`n"), [Text.UTF8Encoding]::new($false))
        }
        if ($null -eq $peak) { $peak = $values.Clone() }
        else { for ($index = 0; $index -lt 6; $index++) { $peak[$index] = [Math]::Max($peak[$index], $values[$index]) } }
        $frames += 1
        if ($frames -gt 16) { throw 'GPU stream backlog; freshness unverified' }
        $script:text2sql_gpu_pending = $text2sql_gpu_stream.StandardOutput.ReadLineAsync()
    }
    if ($text2sql_gpu_stream.HasExited) { throw 'GPU sensor stream exited' }
    return ,$peak
}
function Stop-Text2SqlGpuStream {
    if ($null -ne $text2sql_gpu_stream) {
        try {
            if (-not $text2sql_gpu_stream.HasExited) { $text2sql_gpu_stream.Kill() }
            if (-not $text2sql_gpu_stream.WaitForExit(2000)) { throw 'GPU sensor cleanup timeout' }
        } finally { $text2sql_gpu_stream.Dispose() }
    }
}
