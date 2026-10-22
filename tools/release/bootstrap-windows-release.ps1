#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Seed,
    [Parameter(Mandatory)][string]$NativePrefix,
    [Parameter(Mandatory)][string]$Clang,
    [Parameter(Mandatory)][string]$Output
)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/windows-common.ps1"
Assert-Release $IsWindows 'Use native Windows PowerShell 7'
$root = (Resolve-Path "$PSScriptRoot/../..").Path
$Seed = (Resolve-Path -LiteralPath $Seed).Path
$NativePrefix = (Resolve-Path -LiteralPath $NativePrefix).Path
$Clang = (Resolve-Path -LiteralPath $Clang).Path
$Output = [IO.Path]::GetFullPath($Output)
Assert-Release (!(Test-Path -LiteralPath $Output)) 'Use a fresh native bootstrap directory'
$checksums = @(Get-Content -LiteralPath "$Seed/SHA256SUMS")
Assert-Release ($checksums.Count -eq 2) 'Expected exactly two checked LLVM seed files'
foreach ($name in @('emlf','mlfpkg')) {
    $line = @($checksums | Where-Object { $_ -match "^[0-9a-f]{64}  $name\.ll$" })
    Assert-Release ($line.Count -eq 1) "Missing unique $name LLVM checksum"
    Assert-Release ((Get-ReleaseHash "$Seed/$name.ll") -eq $line[0].Substring(0,64)) "Invalid $name seed LLVM"
}
New-Item -ItemType Directory -Path "$Output/seed/bin" -Force | Out-Null
$env:MLF_NATIVE_PREFIX = $NativePrefix
$env:MLF_CLANG = $Clang
$env:MLF_GC_PREFIX = $NativePrefix
$env:PATH = "$NativePrefix/bin;" + $env:PATH
$compilerVersion = (& $Clang --version | Out-String)
$irFlags = @()
if ($compilerVersion -match 'clang version (\d+)' -and [int]$Matches[1] -lt 15) { $irFlags = @('-mllvm','-opaque-pointers') }
$null = Invoke-ReleaseCommand $Clang @('-O2','-std=c11','-mno-incremental-linker-compatible',"-I$NativePrefix/include",'-c',"$root/runtime/mlf_runtime.c",'-o',"$Output/seed/runtime.o") "$Output/seed/runtime.log" $root
$null = Invoke-ReleaseCommand $Clang @('-O2','-std=c11','-Wall','-Wextra','-Werror','-municode','-mno-incremental-linker-compatible','-Wl,--no-insert-timestamp',"$root/runtime/mlf_windows_host.c",'-o',"$Output/seed/bin/mlf-host.exe") "$Output/seed/helper.log" $root
$null = Invoke-ReleaseCommand $Clang @('-O2','-std=c11','-Wall','-Wextra','-Werror','-municode','-mno-incremental-linker-compatible','-Wl,--no-insert-timestamp',"$root/runtime/mlf_build_runner.c",'-lpsapi','-o',"$Output/seed/bin/mlf-build-runner.exe") "$Output/seed/build-runner.log" $root
$protocol = Invoke-ReleaseCommand "$Output/seed/bin/mlf-build-runner.exe" @('--protocol-version') "$Output/seed/build-runner-protocol.log" $root
Assert-Release ($protocol.Trim() -eq '1') 'Unsupported build runner protocol'
foreach ($file in @('libgmp-10.dll','libgc-1.dll','libwinpthread-1.dll')) { Copy-Item -LiteralPath "$NativePrefix/bin/$file" -Destination "$Output/seed/bin" }
foreach ($name in @('emlf','mlfpkg')) {
    $arguments = @('-O2','-Wno-override-module','-mno-incremental-linker-compatible','-Wl,--no-insert-timestamp') + $irFlags + @("$Seed/$name.ll","$Output/seed/runtime.o","$NativePrefix/lib/libgc.dll.a","$NativePrefix/lib/libgmp.dll.a",'-lshell32','-lm','-Wl,--stack,268435456','-o',"$Output/seed/bin/$name.exe")
    $null = Invoke-ReleaseCommand $Clang $arguments "$Output/seed/$name-link.log" $root
}
Copy-Item -LiteralPath "$Seed/SHA256SUMS" -Destination "$Output/seed/LLVM-SHA256SUMS"
$compiler = "$Output/seed/bin/emlf.exe"
$manager = "$Output/seed/bin/mlfpkg.exe"
foreach ($stage in @('stage1','stage2')) {
    Write-Host "Native Windows $stage"
    $arguments = @('--compiler',$compiler,'--clang',$Clang,'--manifest',"$root/mlf-package.json",'--runtime',"$root/runtime/mlf_runtime.c",'--timeout','21600','--locked','--build-dir',"$Output/$stage",'build')
    $null = Invoke-ReleaseCommand $manager $arguments "$Output/$stage.log" $root
    $compiler = "$Output/$stage/bin/emlf.exe"
    $manager = "$Output/$stage/bin/mlfpkg.exe"
}
Write-Host "Native Windows candidate: $Output/stage2/bin"
