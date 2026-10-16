$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$text2sql_memory_source = @'
using System;
using System.Runtime.InteropServices;
public static class Text2SqlHostMemory {
    [StructLayout(LayoutKind.Sequential)]
    public struct Status {
        public uint Length, Load;
        public ulong TotalPhys, AvailPhys, TotalPage, AvailPage;
        public ulong TotalVirtual, AvailVirtual, AvailExtendedVirtual;
    }
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern bool GlobalMemoryStatusEx(ref Status status);
    public static ulong AvailableBytes() {
        var status = new Status();
        status.Length = (uint)Marshal.SizeOf(typeof(Status));
        if (!GlobalMemoryStatusEx(ref status)) throw new InvalidOperationException("Memory sensor failed");
        return status.AvailPhys;
    }
    [StructLayout(LayoutKind.Sequential)]
    public struct PageFileInfo {
        public uint Size, Reserved;
        public UIntPtr TotalSize, TotalInUse, PeakUsage;
    }
    [UnmanagedFunctionPointer(CallingConvention.Winapi, CharSet=CharSet.Unicode)]
    public delegate bool PageFileCallback(IntPtr context, ref PageFileInfo info, string name);
    [DllImport("psapi.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    public static extern bool EnumPageFilesW(PageFileCallback callback, IntPtr context);
    public static ulong PageFileUsedBytes() {
        ulong pages = 0;
        PageFileCallback callback = delegate(IntPtr context, ref PageFileInfo info, string name) {
            pages = checked(pages + info.TotalInUse.ToUInt64());
            return true;
        };
        if (!EnumPageFilesW(callback, IntPtr.Zero))
            throw new InvalidOperationException("Pagefile sensor failed: " + Marshal.GetLastWin32Error());
        GC.KeepAlive(callback);
        return checked(pages * (ulong)Environment.SystemPageSize);
    }
}
'@
$text2sql_source_bytes = [Text.Encoding]::UTF8.GetBytes($text2sql_memory_source)
$text2sql_sha = [Security.Cryptography.SHA256]::Create()
try {
    $text2sql_source_hash = ([BitConverter]::ToString($text2sql_sha.ComputeHash($text2sql_source_bytes))).Replace('-', '').ToLowerInvariant()
} finally { $text2sql_sha.Dispose() }
if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) { throw 'Windows local cache directory unavailable' }
$text2sql_cache_dir = Join-Path $env:LOCALAPPDATA ("AgenticText2Sql\monitor\" + $text2sql_source_hash)
[void][IO.Directory]::CreateDirectory($text2sql_cache_dir)
$text2sql_cache_manifest = Join-Path $text2sql_cache_dir 'assembly.json'
if (-not (Test-Path -LiteralPath $text2sql_cache_manifest)) {
    # Compile once per source version, before any model worker is allowed to start.
    # Publish the manifest last; interrupted compilation cannot expose a partial cache.
    [Console]::Error.WriteLine('WINDOWS MEMORY INIT: compiling native helper cache')
    $text2sql_assembly_name = 'memory-' + [Guid]::NewGuid().ToString('N') + '.dll'
    $text2sql_assembly_path = Join-Path $text2sql_cache_dir $text2sql_assembly_name
    Add-Type -TypeDefinition $text2sql_memory_source -OutputAssembly $text2sql_assembly_path -ErrorAction Stop
    $text2sql_manifest_payload = @{
        source_sha256 = $text2sql_source_hash
        assembly_file = $text2sql_assembly_name
        assembly_sha256 = (Get-FileHash -LiteralPath $text2sql_assembly_path -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $text2sql_manifest_temporary = Join-Path $text2sql_cache_dir ([Guid]::NewGuid().ToString('N') + '.json.tmp')
    [IO.File]::WriteAllText($text2sql_manifest_temporary, ($text2sql_manifest_payload | ConvertTo-Json -Compress), [Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $text2sql_manifest_temporary -Destination $text2sql_cache_manifest -Force -ErrorAction Stop
}
$text2sql_cached = Get-Content -LiteralPath $text2sql_cache_manifest -Raw | ConvertFrom-Json
if ($text2sql_cached.source_sha256 -ne $text2sql_source_hash -or $text2sql_cached.assembly_file -notmatch '^memory-[a-f0-9]{32}\.dll$') {
    throw 'Invalid Windows memory helper cache manifest'
}
$text2sql_assembly_path = Join-Path $text2sql_cache_dir $text2sql_cached.assembly_file
if ((Get-FileHash -LiteralPath $text2sql_assembly_path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $text2sql_cached.assembly_sha256) {
    throw 'Windows memory helper cache checksum mismatch'
}
if (-not ('Text2SqlHostMemory' -as [type])) {
    Add-Type -Path $text2sql_assembly_path -ErrorAction Stop
}
[Console]::Error.WriteLine('WINDOWS MEMORY INIT: verified native helper loaded')
