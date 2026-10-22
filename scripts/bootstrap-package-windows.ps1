#Requires -Version 7.0
[CmdletBinding()]
param(
    [string]$Compiler = $env:MLF_COMPILER,
    [string]$Clang = $env:MLF_CLANG,
    [Parameter(Mandatory)][string]$NativePrefix,
    [string]$Output = (Join-Path (Split-Path $PSScriptRoot) '.mlf-build/windows-package-tools')
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot
if (!$Compiler) { $Compiler = (Get-Command emlf -ErrorAction Stop).Source }
if (!$Clang) { $Clang = (Get-Command clang -ErrorAction Stop).Source }
$Compiler = (Resolve-Path -LiteralPath $Compiler).Path
$NativePrefix = (Resolve-Path -LiteralPath $NativePrefix).Path
$Output = [IO.Path]::GetFullPath($Output)
New-Item -ItemType Directory -Force "$Output/bin","$Output/lib/pkgconfig","$Output/include","$Output/runtime","$Output/evidence" | Out-Null
$required = @('libgmp-10.dll','libgc-1.dll','libwinpthread-1.dll','pkg-config.exe','libpkgconf-8.dll')
foreach ($file in $required) { Copy-Item -LiteralPath (Join-Path "$NativePrefix/bin" $file) -Destination "$Output/bin/$file" -Force }
Copy-Item -LiteralPath $Compiler -Destination "$Output/bin/emlf.exe" -Force
Copy-Item -LiteralPath "$NativePrefix/include/gmp.h" -Destination "$Output/include/gmp.h" -Force
Copy-Item -LiteralPath "$NativePrefix/include/gc" -Destination "$Output/include" -Recurse -Force
Copy-Item -LiteralPath "$NativePrefix/lib/libgmp.dll.a","$NativePrefix/lib/libgc.dll.a" -Destination "$Output/lib" -Force
Copy-Item -Path "$root/runtime/*.c","$root/runtime/*.h" -Destination "$Output/runtime" -Force
foreach ($entry in @(@('gmp','6.3.0','gmp'),@('bdw-gc','8.2.12','gc'))) {
    $pc = 'prefix=${pcfiledir}/../..' + "`n" + 'libdir=${prefix}/lib' + "`n" + 'includedir=${prefix}/include' + "`n"
    $pc += "Name: $($entry[0])`nDescription: MLF native Windows dependency`nVersion: $($entry[1])`n"
    $pc += 'Libs: -L${libdir} -l' + $entry[2] + "`n" + 'Cflags: -I${includedir}' + "`n"
    [IO.File]::WriteAllText("$Output/lib/pkgconfig/$($entry[0]).pc",$pc)
}
& $Clang -O2 -std=c11 -Wall -Wextra -Werror -municode "$root/runtime/mlf_windows_host.c" -o "$Output/bin/mlf-host.exe"
if ($LASTEXITCODE) { throw 'Windows filesystem helper build failed' }
& $Clang -O2 -std=c11 -Wall -Wextra -Werror -municode "$root/runtime/mlf_build_runner.c" -lpsapi -o "$Output/bin/mlf-build-runner.exe"
if ($LASTEXITCODE) { throw 'Windows build runner build failed' }
$protocol = (& "$Output/bin/mlf-build-runner.exe" --protocol-version | Out-String).Trim()
if ($LASTEXITCODE -or $protocol -ne '1') { throw 'Unsupported build runner protocol' }
& $Clang -O2 -std=c11 "-I$Output/include" -c "$Output/runtime/mlf_runtime.c" -o "$Output/evidence/runtime.o"
if ($LASTEXITCODE) { throw 'Windows runtime build failed' }
$version = (& $Clang --version | Out-String)
if ($LASTEXITCODE) { throw 'Cannot identify Clang' }
$irFlags = @()
if ($version -match 'clang version (\d+)' -and [int]$Matches[1] -lt 15) { $irFlags = @('-mllvm','-opaque-pointers') }
$identity = [ordered]@{complete=$false;implementation='MLF';compiler_sha256=(Get-FileHash -LiteralPath $Compiler).Hash.ToLower();clang=$version;sources=@{}}
foreach ($source in (Get-ChildItem "$root/package","$root/libraries" -Recurse -File -Filter '*.emlf')) {
    $identity.sources[[IO.Path]::GetRelativePath($root,$source.FullName)] = (Get-FileHash -LiteralPath $source.FullName).Hash.ToLower()
}
$report = "$Output/evidence/package-manager-bootstrap.json"
$identity | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8NoBOM $report
$start = [Diagnostics.ProcessStartInfo]::new($Compiler)
$start.UseShellExecute = $false
$start.CreateNoWindow = $true
$start.WorkingDirectory = $root
$start.RedirectStandardOutput = $true
$start.RedirectStandardError = $true
foreach ($library in (Get-ChildItem "$root/libraries" -Directory | Sort-Object Name)) { $start.ArgumentList.Add('-i'); $start.ArgumentList.Add($library.FullName) }
foreach ($arg in @('--emit-llvm-gc','package/Main.emlf')) { $start.ArgumentList.Add($arg) }
$process = [Diagnostics.Process]::Start($start)
$errors = $process.StandardError.ReadToEndAsync()
$stream = [IO.File]::Create("$Output/evidence/mlfpkg.ll")
try { $process.StandardOutput.BaseStream.CopyTo($stream) } finally { $stream.Dispose() }
$process.WaitForExit()
$errors.GetAwaiter().GetResult() | Set-Content -Encoding utf8NoBOM "$Output/evidence/emission.stderr"
if ($process.ExitCode) { throw 'MLF package-manager emission failed' }
& $Clang -O2 -Wno-override-module @irFlags "$Output/evidence/mlfpkg.ll" "$Output/evidence/runtime.o" "$Output/lib/libgc.dll.a" "$Output/lib/libgmp.dll.a" -lshell32 -lm '-Wl,--stack,268435456' -o "$Output/bin/mlfpkg.exe"
if ($LASTEXITCODE) { throw 'MLF package-manager link failed' }
foreach ($entry in $identity.sources.GetEnumerator()) {
    if ((Get-FileHash -LiteralPath (Join-Path $root $entry.Key)).Hash.ToLower() -ne $entry.Value) { throw "Manager source changed during bootstrap: $($entry.Key)" }
}
$identity.complete = $true
$identity.manager_sha256 = (Get-FileHash "$Output/bin/mlfpkg.exe").Hash.ToLower()
$identity.build_runner_sha256 = (Get-FileHash "$Output/bin/mlf-build-runner.exe").Hash.ToLower()
$identity.build_runner_protocol = 1
$identity.helper_sha256 = (Get-FileHash "$Output/bin/mlf-host.exe").Hash.ToLower()
$identity.llvm_sha256 = (Get-FileHash "$Output/evidence/mlfpkg.ll").Hash.ToLower()
$identity | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8NoBOM $report
Write-Output "$Output/bin/mlfpkg.exe"
