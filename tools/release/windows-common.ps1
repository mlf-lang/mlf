# Shared release bookkeeping; all compilation and package policy stays in MLF.
function Get-ReleaseHash([string]$Path) {
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256 -ErrorAction Stop).Hash.ToLowerInvariant()
}
function Read-ReleaseJson([string]$Path) {
    Get-Content -LiteralPath $Path -Raw -Encoding utf8 | ConvertFrom-Json -AsHashtable
}
function Write-ReleaseJson([string]$Path, $Value) {
    [IO.File]::WriteAllText($Path, ($Value | ConvertTo-Json -Depth 30) + "`n", [Text.UTF8Encoding]::new($false))
}
function Assert-Release($Condition, [string]$Message) {
    if (!$Condition) { throw $Message }
}
function Get-ReleaseSources([string]$Root) {
    $snapshot = [ordered]@{}
    $files = @(& git -C $Root ls-files --cached --others --exclude-standard)
    if ($LASTEXITCODE) { throw 'Cannot enumerate release source inputs' }
    foreach ($relative in ($files | Sort-Object -Unique)) {
        if ($relative -match '^(bootstrap|package|runtime|src|app|test|scripts|tests|examples|benchmarks)/' -or
            $relative -in @('VERSION','mlf.cabal','mlf-package.json','mlfpkg','mlfpkg.cmd','mlfpkg.ps1')) {
            $path = Join-Path $Root $relative
            if (Test-Path -LiteralPath $path -PathType Leaf) { $snapshot[$relative] = Get-ReleaseHash $path }
        }
    }
    return $snapshot
}
function Assert-ReleaseSources([string]$Root, $Expected) {
    $actual = Get-ReleaseSources $Root
    Assert-Release ($actual.Count -eq $Expected.Count) 'Release source input set changed after qualification'
    foreach ($entry in $Expected.GetEnumerator()) {
        Assert-Release ($actual[$entry.Key] -eq $entry.Value) "Release source changed after qualification: $($entry.Key)"
    }
}
function Invoke-ReleaseCommand([string]$Executable, [string[]]$Arguments, [string]$Log, [string]$Directory) {
    $start = [Diagnostics.ProcessStartInfo]::new($Executable)
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.WorkingDirectory = $Directory
    foreach ($argument in $Arguments) { $start.ArgumentList.Add($argument) }
    $process = [Diagnostics.Process]::Start($start)
    $output = $process.StandardOutput.ReadToEndAsync()
    $errors = $process.StandardError.ReadToEndAsync()
    $process.WaitForExit()
    $text = $output.GetAwaiter().GetResult() + $errors.GetAwaiter().GetResult()
    [IO.File]::WriteAllText($Log, $text, [Text.UTF8Encoding]::new($false))
    if ($process.ExitCode) { throw "Command exited $($process.ExitCode): $Executable; see $Log" }
    return $text
}
function Get-PeImports([string]$Path) {
    # Read the PE import directory directly, so qualification needs no objdump.
    $bytes = [IO.File]::ReadAllBytes($Path)
    Assert-Release ($bytes.Length -gt 128 -and $bytes[0] -eq 77 -and $bytes[1] -eq 90) "Not a PE executable: $Path"
    $pe = [BitConverter]::ToInt32($bytes, 60)
    Assert-Release ([BitConverter]::ToUInt32($bytes, $pe) -eq 0x4550) "Invalid PE signature: $Path"
    Assert-Release ([BitConverter]::ToUInt16($bytes, $pe + 4) -eq 0x8664) "Expected Windows x64 PE: $Path"
    $count = [BitConverter]::ToUInt16($bytes, $pe + 6)
    $optionalSize = [BitConverter]::ToUInt16($bytes, $pe + 20)
    $optional = $pe + 24
    Assert-Release ([BitConverter]::ToUInt16($bytes, $optional) -eq 0x20b) "Expected PE32+: $Path"
    $importRva = [BitConverter]::ToUInt32($bytes, $optional + 120)
    $sections = @()
    for ($i = 0; $i -lt $count; $i++) {
        $offset = $optional + $optionalSize + $i * 40
        $sections += @{ rva=[BitConverter]::ToUInt32($bytes,$offset+12); size=[Math]::Max([BitConverter]::ToUInt32($bytes,$offset+8),[BitConverter]::ToUInt32($bytes,$offset+16)); raw=[BitConverter]::ToUInt32($bytes,$offset+20) }
    }
    function Convert-Rva([uint32]$Rva) {
        foreach ($section in $sections) { if ($Rva -ge $section.rva -and $Rva -lt ($section.rva+$section.size)) { return [int]($Rva-$section.rva+$section.raw) } }
        throw "Unmapped PE RVA in $Path"
    }
    $imports = @()
    if ($importRva) {
        $offset = Convert-Rva $importRva
        while ([BitConverter]::ToUInt32($bytes,$offset+12)) {
            $name = Convert-Rva ([BitConverter]::ToUInt32($bytes,$offset+12))
            $end = $name
            while ($bytes[$end]) { $end++ }
            $imports += [Text.Encoding]::ASCII.GetString($bytes,$name,$end-$name)
            $offset += 20
        }
    }
    Assert-Release (!($imports | Where-Object { $_ -match '^(msys-|cygwin)' })) "POSIX runtime imported by $Path"
    return ,$imports
}
