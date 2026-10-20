#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$NativePrefix,
    [Parameter(Mandatory)][string]$Clang,
    [Parameter(Mandatory)][string]$Output,
    [string]$HostHelper
)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/windows-common.ps1"
Assert-Release $IsWindows 'Run runtime regressions in native Windows PowerShell 7'
$root = (Resolve-Path "$PSScriptRoot/../..").Path
$NativePrefix = (Resolve-Path -LiteralPath $NativePrefix).Path
$Clang = (Resolve-Path -LiteralPath $Clang).Path
$Output = [IO.Path]::GetFullPath($Output)
Assert-Release (!(Test-Path -LiteralPath $Output)) 'Use a new runtime regression directory'
New-Item -ItemType Directory -Path $Output | Out-Null
$savedPath = $env:PATH
$savedHelper = $env:MLF_WINDOWS_HOST
$report = [ordered]@{
    complete=$false; source_sha256=(Get-ReleaseHash "$root/tests/native/windows_runtime.c")
    clang_sha256=(Get-ReleaseHash $Clang); runtime=[ordered]@{}; profiles=[ordered]@{}
}
foreach ($file in (Get-ChildItem "$root/runtime/*.c","$root/runtime/*.h")) {
    $report.runtime[$file.Name] = Get-ReleaseHash $file.FullName
}
try {
    $env:PATH = "$NativePrefix/bin;$(Split-Path $Clang);" + $env:PATH
    if (!$HostHelper) {
        $HostHelper = "$Output/mlf-host.exe"
        $null = Invoke-ReleaseCommand $Clang @('-O2','-std=c11','-Wall','-Wextra','-Werror','-municode',"$root/runtime/mlf_windows_host.c",'-o',$HostHelper) "$Output/helper-build.log" $root
    }
    $HostHelper = (Resolve-Path -LiteralPath $HostHelper).Path
    $env:MLF_WINDOWS_HOST = $HostHelper
    $report.helper_sha256 = Get-ReleaseHash $HostHelper
    $null = Invoke-ReleaseCommand $Clang @('-O2','-std=c11','-Wall','-Wextra','-Werror','-municode',"$root/tests/native/windows_paths.c",'-o',"$Output/path-test.exe") "$Output/paths-build.log" $root
    $text = Invoke-ReleaseCommand "$Output/path-test.exe" @() "$Output/paths.log" $Output
    Assert-Release ($text -match 'Windows path guards passed') 'Missing path guard success marker'
    $report.path_guards = @{passed=$true;source_sha256=(Get-ReleaseHash "$root/tests/native/windows_paths.c");binary_sha256=(Get-ReleaseHash "$Output/path-test.exe")}
    foreach ($profile in @('standard','compact-gc')) {
        $directory = "$Output/$profile"
        New-Item -ItemType Directory -Path $directory | Out-Null
        $arguments = @('-O2','-std=c11',"-I$NativePrefix/include","$root/tests/native/windows_runtime.c")
        if ($profile -eq 'compact-gc') { $arguments += @('-DMLF_USE_BDWGC','-DMLF_COMPACT_BDWGC',"$NativePrefix/lib/libgc.dll.a") }
        $arguments += @("$NativePrefix/lib/libgmp.dll.a",'-lshell32','-lm','-Wl,--stack,268435456','-o',"$directory/runtime-test.exe")
        $null = Invoke-ReleaseCommand $Clang $arguments "$Output/$profile-build.log" $directory
        $text = Invoke-ReleaseCommand "$directory/runtime-test.exe" @() "$Output/$profile.log" $directory
        Assert-Release ($text -match 'Windows runtime regressions passed') "Missing $profile runtime success marker"
        $report.profiles[$profile] = @{passed=$true;binary_sha256=(Get-ReleaseHash "$directory/runtime-test.exe");log_sha256=(Get-ReleaseHash "$Output/$profile.log")}
        Write-Output "Windows $profile runtime regressions passed"
    }
    $report.complete = $true
} catch {
    $report.error = $_.Exception.Message
    throw
} finally {
    Write-ReleaseJson "$Output/runtime-verification.json" $report
    $env:PATH = $savedPath
    $env:MLF_WINDOWS_HOST = $savedHelper
}
