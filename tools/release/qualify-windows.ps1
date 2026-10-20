#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Stage1,
    [Parameter(Mandatory)][string]$Stage2,
    [Parameter(Mandatory)][string]$NativePrefix,
    [Parameter(Mandatory)][string]$Clang,
    [Parameter(Mandatory)][string]$Output,
    [string]$Checker,
    [string]$Manifest
)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/windows-common.ps1"
Assert-Release $IsWindows 'Run qualification in native Windows PowerShell 7'
$root = (Resolve-Path "$PSScriptRoot/../..").Path
$Stage1 = (Resolve-Path -LiteralPath $Stage1).Path
$Stage2 = (Resolve-Path -LiteralPath $Stage2).Path
$NativePrefix = (Resolve-Path -LiteralPath $NativePrefix).Path
$Clang = (Resolve-Path -LiteralPath $Clang).Path
$Output = [IO.Path]::GetFullPath($Output)
Assert-Release (!(Test-Path -LiteralPath $Output)) 'Use a new qualification output directory'
New-Item -ItemType Directory -Path $Output,"$Output/temp" | Out-Null
$compiler = "$Stage2/bin/emlf.exe"
$manager = "$Stage2/bin/mlfpkg.exe"
$helper = "$Stage2/bin/mlf-host.exe"
$version = (Get-Content "$root/VERSION" -Raw).Trim()
$report = [ordered]@{
    schema_version=1; complete=$false; platform='windows-x64'; version=$version
    compiler_sha256=(Get-ReleaseHash $compiler); manager_sha256=(Get-ReleaseHash $manager)
    helper_sha256=(Get-ReleaseHash $helper); clang_sha256=(Get-ReleaseHash $Clang)
    sources=(Get-ReleaseSources $root); dependencies=[ordered]@{}; tests=[ordered]@{}; evidence=[ordered]@{}
}
$reportPath = "$Output/release-validation.json"
Write-ReleaseJson $reportPath $report
$saved = @{}
$variables = @('PATH','TEMP','TMP','CC','MLF_COMPILER','MLF_PACKAGE_MANAGER','MLF_NATIVE_PREFIX','MLF_GC_PREFIX','MLF_WINDOWS_HOST','MLF_CLANG')
foreach ($name in $variables) { $saved[$name] = [Environment]::GetEnvironmentVariable($name,'Process') }
try {
    $env:PATH = "$Stage2/bin;$NativePrefix/bin;$(Split-Path $Clang);" + $env:PATH
    $env:TEMP = "$Output/temp"; $env:TMP = $env:TEMP
    $env:MLF_COMPILER = $compiler; $env:MLF_PACKAGE_MANAGER = $manager
    $env:MLF_NATIVE_PREFIX = $NativePrefix; $env:MLF_GC_PREFIX = $NativePrefix
    $env:MLF_WINDOWS_HOST = $helper; $env:MLF_CLANG = $Clang
    $env:CC = $Clang
    $builds = @()
    foreach ($directory in @($Stage1,$Stage2)) {
        $build = Read-ReleaseJson "$directory/build-report.json"
        Assert-Release ($build.complete -eq $true -and $build.implementation -eq 'MLF') "Incomplete native build: $directory"
        Assert-Release ($build.toolchain.clang.sha256 -eq $report.clang_sha256) "Build used a different Clang: $directory"
        foreach ($package in $build.packages.packages) {
            $packageRoot = Join-Path $root $package.path
            Assert-Release ((Get-ReleaseHash "$packageRoot/mlf-package.json") -eq $package.manifest) "Build manifest changed: $packageRoot"
            foreach ($entry in $package.sources.GetEnumerator()) {
                Assert-Release ((Get-ReleaseHash (Join-Path $packageRoot $entry.Key)) -eq $entry.Value) "Build source changed: $packageRoot/$($entry.Key)"
            }
        }
        foreach ($entry in $build.toolchain.runtime.GetEnumerator()) {
            Assert-Release ((Get-ReleaseHash $entry.Key) -eq $entry.Value) "Build runtime changed: $($entry.Key)"
        }
        $outputs = [ordered]@{}
        foreach ($name in @('emlf','mlfpkg')) {
            $target = @($build.builds | Where-Object { $_.kind -eq "executable mlf-compiler:$name" })
            Assert-Release ($target.Count -eq 1 -and $target[0].key -match '^[0-9a-f]{64}$') "Missing unique native $name build: $directory"
            $cache = Join-Path "$directory/cache" $target[0].key
            $binary = Get-ReleaseHash "$directory/bin/$name.exe"
            Assert-Release ((Get-ReleaseHash "$cache/program.exe") -eq $binary) "Published $name differs from its native build artifact"
            $outputs[$name] = @{llvm_sha256=(Get-ReleaseHash "$cache/program.ll"); binary_sha256=$binary}
        }
        $builds += @{report=$build; outputs=$outputs}
    }
    foreach ($name in @('emlf','mlfpkg')) {
        Assert-Release ($builds[0].outputs[$name].llvm_sha256 -eq $builds[1].outputs[$name].llvm_sha256) "Native $name LLVM did not reach a fixed point"
    }
    Assert-Release ($builds[1].report.toolchain.compiler.sha256 -eq $builds[0].outputs.emlf.binary_sha256) 'Second native build did not use the first compiler'
    Assert-Release ($builds[1].report.toolchain.manager.sha256 -eq $builds[0].outputs.mlfpkg.binary_sha256) 'Second native build did not use the first manager'
    Copy-Item -LiteralPath "$Stage1/build-report.json" -Destination "$Output/stage1-build-report.json"
    Copy-Item -LiteralPath "$Stage2/build-report.json" -Destination "$Output/stage2-build-report.json"
    $fixedPoint = @{complete=$true; stages=2; reused_candidate_build=$false; tools=@{emlf=$builds[1].outputs.emlf;mlfpkg=$builds[1].outputs.mlfpkg}}
    Write-ReleaseJson "$Output/fixed-point.json" $fixedPoint
    $report.tests.fixed_point = $fixedPoint
    foreach ($name in @('emlf','mlfpkg')) {
        $text = Invoke-ReleaseCommand "$Stage2/bin/$name.exe" @('--version') "$Output/$name-version.log" $Output
        Assert-Release ($text.Trim() -eq "$name $version") "Embedded $name version does not match VERSION"
    }
    Write-Output 'Windows qualification: standard and compact runtime regressions'
    & "$PSScriptRoot/test-windows-runtime.ps1" -NativePrefix $NativePrefix -Clang $Clang -HostHelper $helper -Output "$Output/runtime"
    $runtime = Read-ReleaseJson "$Output/runtime/runtime-verification.json"
    Copy-Item -LiteralPath "$Output/runtime/runtime-verification.json" -Destination "$Output/runtime-verification.json"
    foreach ($file in (Get-ChildItem "$Output/runtime/*.log")) { Copy-Item -LiteralPath $file.FullName -Destination "$Output/runtime-$($file.Name)" }
    Assert-Release ($runtime.complete -eq $true -and $runtime.helper_sha256 -eq $report.helper_sha256) 'Runtime regressions did not use the qualified filesystem helper'
    $report.tests.runtime = $runtime
    Write-Output 'Windows qualification: native 18 resolver checks and 26 package integration cases'
    $null = Invoke-ReleaseCommand $manager @('compiler-test','packages','--compiler',$compiler,'--build-dir',"$Output/packages") "$Output/package-integration.log" $root
    $integration = Read-ReleaseJson "$Output/packages/verification.json"
    Assert-Release ($integration.complete -eq $true -and $integration.implementation -eq 'MLF' -and $integration.compiler_sha256 -eq $report.compiler_sha256 -and $integration.manager_sha256 -eq $report.manager_sha256) 'Native package qualification failed or tested different tools'
    Assert-Release ($integration.suites.packages.coverage -contains '18 package resolver tests passed' -and $integration.suites.packages.coverage -contains '26 package integration cases passed') 'Native package coverage changed'
    Copy-Item -LiteralPath "$Output/packages/verification.json" -Destination "$Output/package-integration.json"
    Copy-Item -LiteralPath "$Output/packages/packages.log" -Destination "$Output/packages-primary.log"
    $report.tests.resolver = @{passed=18;manager_sha256=$report.manager_sha256;implementation='MLF'}
    $report.tests.integration = @{passed=26;compiler_sha256=$report.compiler_sha256;manager_sha256=$report.manager_sha256;implementation='MLF'}
    Assert-Release (!$Checker -and !$Manifest) 'Native parity builds and verifies its own independent checker and corpus'
    Write-Output 'Windows qualification: native 7,086 parity cases and 160 interpreter/native runtime executions'
    $null = Invoke-ReleaseCommand $manager @('compiler-test','parity','--compiler',$compiler,'--build-dir',"$Output/parity") "$Output/parity.log" $root
    $parity = Read-ReleaseJson "$Output/parity/verification.json"
    Assert-Release ($parity.complete -eq $true -and $parity.implementation -eq 'MLF' -and $parity.compiler_sha256 -eq $report.compiler_sha256 -and $parity.manager_sha256 -eq $report.manager_sha256 -and $parity.parity.cases -eq 7086 -and $parity.parity.runtime_executions -eq 160) 'Native compiler parity qualification failed or coverage changed'
    Copy-Item -LiteralPath "$Output/parity/verification.json" -Destination "$Output/parity-verification.json"
    $report.tests.parity = $parity.parity
    $report.tests.parity.compiler_sha256 = $parity.compiler_sha256
    foreach ($path in (Get-ChildItem "$NativePrefix/include","$NativePrefix/lib" -Recurse -File)) {
        $relative = [IO.Path]::GetRelativePath($NativePrefix,$path.FullName).Replace('\','/')
        $report.dependencies[$relative] = Get-ReleaseHash $path.FullName
    }
    foreach ($name in @('libgmp-10.dll','libgc-1.dll','libwinpthread-1.dll','pkg-config.exe','libpkgconf-8.dll')) {
        $report.dependencies["bin/$name"] = Get-ReleaseHash "$NativePrefix/bin/$name"
    }
    $imports = [ordered]@{}
    foreach ($file in @($compiler,$manager,$helper,"$NativePrefix/bin/pkg-config.exe","$NativePrefix/bin/libgmp-10.dll","$NativePrefix/bin/libgc-1.dll","$NativePrefix/bin/libwinpthread-1.dll","$NativePrefix/bin/libpkgconf-8.dll")) {
        $imports[[IO.Path]::GetFileName($file)] = Get-PeImports $file
    }
    Write-ReleaseJson "$Output/pe-imports.json" $imports
    Assert-ReleaseSources $root $report.sources
    Assert-Release ((Get-ReleaseHash $compiler) -eq $report.compiler_sha256 -and (Get-ReleaseHash $manager) -eq $report.manager_sha256 -and (Get-ReleaseHash $helper) -eq $report.helper_sha256) 'Qualified tools changed during validation'
    foreach ($file in (Get-ChildItem -LiteralPath $Output -File | Where-Object Name -ne 'release-validation.json')) { $report.evidence[$file.Name] = Get-ReleaseHash $file.FullName }
    $report.complete = $true
    Write-ReleaseJson $reportPath $report
    Write-Output "Windows qualification passed: $reportPath"
} catch {
    $report.error = $_.Exception.Message
    Write-ReleaseJson $reportPath $report
    throw
} finally {
    foreach ($name in $variables) { [Environment]::SetEnvironmentVariable($name,$saved[$name],'Process') }
}
