$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'windows_memory.ps1')
[Console]::WriteLine('{"protocol":"text2sql-memory-rpc-v2","kind":"ready"}')
[Console]::Out.Flush()
while ($null -ne ($text2sql_request_line = [Console]::ReadLine())) {
    $text2sql_request = $text2sql_request_line | ConvertFrom-Json
    if ($text2sql_request.request_id -notmatch '^[a-f0-9]{32}$') { throw 'Invalid memory request ID' }
    $text2sql_timer = [Diagnostics.Stopwatch]::StartNew()
    $text2sql_payload = @{
        protocol = 'text2sql-memory-rpc-v2'
        kind = 'sample'
        request_id = $text2sql_request.request_id
        available_ram_gib = [Text2SqlHostMemory]::AvailableBytes() / 1073741824.0
        swap_used_gib = [Text2SqlHostMemory]::PageFileUsedBytes() / 1073741824.0
        sampled_at_ms = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    }
    if ($text2sql_timer.ElapsedMilliseconds -gt 500) { throw 'Windows memory sensor exceeded 500ms' }
    [Console]::WriteLine(($text2sql_payload | ConvertTo-Json -Compress))
    [Console]::Out.Flush()
}
