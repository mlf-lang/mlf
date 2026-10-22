#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Compiler,
    [Parameter(Mandatory)][string]$Manager,
    [Parameter(Mandatory)][string]$Clang,
    [Parameter(Mandatory)][string]$Output
)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/windows-common.ps1"
Assert-Release $IsWindows 'Use native Windows PowerShell 7'
$root = (Resolve-Path "$PSScriptRoot/../..").Path
$Compiler = (Resolve-Path -LiteralPath $Compiler).Path
$Manager = (Resolve-Path -LiteralPath $Manager).Path
$Clang = (Resolve-Path -LiteralPath $Clang).Path
$Output = [IO.Path]::GetFullPath($Output)
Assert-Release (!(Test-Path -LiteralPath $Output)) 'Use a fresh manager bootstrap directory'
New-Item -ItemType Directory -Path "$Output/source" -Force | Out-Null
Copy-Item -LiteralPath "$root/mlf-package.json" -Destination "$Output/root-manifest.json"
$manifest = Read-ReleaseJson "$Output/root-manifest.json"
$target = [ordered]@{}
foreach ($entry in $manifest.executables.mlfpkg.GetEnumerator()) { $target[$entry.Key] = $entry.Value }
$names = if ($target.Contains('dependencies')) { @($target.dependencies) } else { @($manifest.dependencies.Keys) }
$target.Remove('dependencies')
$dependencies = [ordered]@{}
foreach ($name in $names) {
    $dependency = $manifest.dependencies[$name]
    Assert-Release ($dependency.Count -eq 1 -and $dependency.path -is [string]) 'Bootstrap requires local source dependencies'
    $dependencies[$name] = @{path=[IO.Path]::GetFullPath((Join-Path $root $dependency.path))}
}
$bootstrap = [ordered]@{format=1;name='mlf-bootstrap-manager';version=$manifest.version;dependencies=$dependencies;executables=@{mlfpkg=$target}}
Write-ReleaseJson "$Output/source/mlf-package.json" $bootstrap
$sources = @($target.main)
if ($target.modules) { $sources += @($target.modules.Values) }
foreach ($source in $sources) {
    $destination = Join-Path "$Output/source" $source
    New-Item -ItemType Directory -Path (Split-Path $destination) -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $root $source) -Destination $destination
}
Write-Output 'Building the current manager from library crates with the verified seed manager.'
$arguments = @('--manifest',"$Output/source/mlf-package.json",'--compiler',$Compiler,'--clang',$Clang,'--runtime',"$root/runtime/mlf_runtime.c",'--timeout','1800','--build-dir',$Output,'build','--target','mlfpkg')
$null = Invoke-ReleaseCommand $Manager $arguments "$Output/seed-manager.log" $root
$report = Read-ReleaseJson "$Output/build-report.json"
Assert-Release ($report.complete -eq $true -and $report.implementation -eq 'MLF') 'Incomplete source manager bootstrap'
Assert-Release ((Get-ReleaseHash "$root/mlf-package.json") -eq (Get-ReleaseHash "$Output/root-manifest.json")) 'Root manifest changed during bootstrap'
foreach ($source in $sources) {
    Assert-Release ((Get-ReleaseHash (Join-Path $root $source)) -eq (Get-ReleaseHash (Join-Path "$Output/source" $source))) "Manager source changed during bootstrap: $source"
}
$flags = @('-O2','-std=c11','-Wall','-Wextra','-Werror','-municode','-mno-incremental-linker-compatible','-Wl,--no-insert-timestamp')
$null = Invoke-ReleaseCommand $Clang ($flags + @("$root/runtime/mlf_windows_host.c",'-o',"$Output/bin/mlf-host.exe")) "$Output/host-helper.log" $root
$null = Invoke-ReleaseCommand $Clang ($flags + @("$root/runtime/mlf_build_runner.c",'-lpsapi','-o',"$Output/bin/mlf-build-runner.exe")) "$Output/build-runner.log" $root
$protocol = Invoke-ReleaseCommand "$Output/bin/mlf-build-runner.exe" @('--protocol-version') "$Output/build-runner-protocol.log" $root
Assert-Release ($protocol.Trim() -eq '1') 'Unsupported build runner protocol'
Write-ReleaseJson "$Output/bootstrap.json" @{complete=$true;seed_manager_sha256=(Get-ReleaseHash $Manager);compiler_sha256=(Get-ReleaseHash $Compiler);manager_sha256=(Get-ReleaseHash "$Output/bin/mlfpkg.exe");build_runner_sha256=(Get-ReleaseHash "$Output/bin/mlf-build-runner.exe");build_runner_protocol=1;build_report_sha256=(Get-ReleaseHash "$Output/build-report.json")}
Write-Output "$Output/bin/mlfpkg.exe"
