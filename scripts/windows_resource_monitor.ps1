$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'windows_memory.ps1')
while ($true) {
    $text2sql_timer = [Diagnostics.Stopwatch]::StartNew()
    $text2sql_payload = @{
        available_ram_gib = [Text2SqlHostMemory]::AvailableBytes() / 1073741824.0
        swap_used_gib = [Text2SqlHostMemory]::PageFileUsedBytes() / 1073741824.0
        sampled_at_ms = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    }
    if ($text2sql_timer.ElapsedMilliseconds -gt 500) { throw 'Windows memory sensor exceeded 500ms' }
    [Console]::WriteLine(($text2sql_payload | ConvertTo-Json -Compress))
    [Console]::Out.Flush()
    $text2sql_delay = [Math]::Max(0, 250 - $text2sql_timer.ElapsedMilliseconds)
    Start-Sleep -Milliseconds $text2sql_delay
}
