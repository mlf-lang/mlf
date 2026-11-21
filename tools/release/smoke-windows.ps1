#Requires -Version 7.0
[CmdletBinding()]
param([Parameter(Mandatory)][string]$Package,[Parameter(Mandatory)][string]$Clang,[Parameter(Mandatory)][string]$Output)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/windows-common.ps1"
$Package = (Resolve-Path -LiteralPath $Package).Path
$Clang = (Resolve-Path -LiteralPath $Clang).Path
$Output = [IO.Path]::GetFullPath($Output)
Assert-Release (!(Test-Path -LiteralPath $Output)) 'Use a new release smoke directory'
$relocated = "$Output/MLF λ SDK with spaces"
New-Item -ItemType Directory -Path $relocated | Out-Null
Copy-Item -LiteralPath "$Package/bin","$Package/include","$Package/lib","$Package/runtime","$Package/Activate.ps1","$Package/Build-Program.ps1" -Destination $relocated -Recurse
$suite = 'sdk-smoke-windows'
$testCase = 'sdk/windows/relocated-activation'
$saved = @{}
$variables = @('PATH','MLF_COMPILER','MLF_PACKAGE_MANAGER','MLF_NATIVE_PREFIX','MLF_GC_PREFIX','MLF_WINDOWS_HOST','MLF_CLANG','MLF_BUILD_RUNNER','MLF_BUILD_REPORT')
foreach ($name in $variables) { $saved[$name] = [Environment]::GetEnvironmentVariable($name,'Process') }
try {
    # The extracted SDK must discover itself without checkout/environment paths.
    foreach ($name in $variables) { [Environment]::SetEnvironmentVariable($name,$null,'Process') }
    $env:PATH = "$env:SystemRoot/System32;$env:SystemRoot"
    . "$relocated/Activate.ps1" -Clang $Clang
    Write-ReleaseTestEvent $suite $testCase pass @{prefix=$relocated}
    $testCase = 'sdk/windows/versions'
    $version = (Get-Content "$Package/VERSION" -Raw).Trim()
    foreach ($name in @('emlf','mlfpkg')) {
        $text = Invoke-ReleaseCommand "$relocated/bin/$name.exe" @('--version') "$Output/$name-version.log" $Output
        Assert-Release ($text.Trim() -eq "$name $version") "Relocated $name version mismatch"
    }
    Write-ReleaseTestEvent $suite $testCase pass @{version=$version}
    $testCase = 'sdk/windows/build-runner-protocol'
    $protocol = Invoke-ReleaseCommand "$relocated/bin/mlf-build-runner.exe" @('--protocol-version') "$Output/build-runner-protocol.log" $Output
    Assert-Release ($protocol.Trim() -eq '1') 'Relocated build runner protocol mismatch'
    Write-ReleaseTestEvent $suite $testCase pass @{protocol=1}
    $testCase = 'sdk/windows/compiler-type'
    $text = Invoke-ReleaseCommand "$relocated/bin/emlf.exe" @('--type','--expr','\x -> x') "$Output/type.log" $Output
    Assert-Release ($text -match '->') 'Relocated compiler type query failed'
    Write-ReleaseTestEvent $suite $testCase pass @{log="$Output/type.log"}
    $testCase = 'sdk/windows/package-plan'
    $project = "$Output/project λ with spaces"
    Copy-Item -LiteralPath "$Package/examples/packages" -Destination $project -Recurse
    $manifest = "$project/mlf-package.json"
    $build = "$Output/build λ with spaces"
    $prefix = @('--jobs','2','--compiler',"$relocated/bin/emlf.exe",'--manifest',$manifest,'--build-dir',$build,'--clang',$Clang)
    foreach ($action in @('plan','lock','build','test')) {
        $testCase = "sdk/windows/package-$action"
        $null = Invoke-ReleaseCommand "$relocated/bin/mlfpkg.exe" ($prefix + @($action)) "$Output/package-$action.log" $Output
        Write-ReleaseTestEvent $suite $testCase pass @{log="$Output/package-$action.log"}
    }
    $testCase = 'sdk/windows/package-run'
    $text = Invoke-ReleaseCommand "$relocated/bin/mlfpkg.exe" ($prefix + @('run','hello')) "$Output/package-run.log" $Output -StdoutOnly
    Assert-Release ($text -eq "Hello, local packages!`n") 'Relocated package manager run produced unexpected stdout'
    Write-ReleaseTestEvent $suite $testCase pass @{log="$Output/package-run.log"}
    $testCase = 'sdk/windows/standalone-native'
    # The published program must carry its runtime dependencies with it.
    $env:PATH = "$env:SystemRoot/System32;$env:SystemRoot"
    $text = Invoke-ReleaseCommand "$build/bin/hello.exe" @() "$Output/standalone-executable.log" $Output -StdoutOnly
    Assert-Release ($text -eq "Hello, local packages!`n") 'Published native executable cannot run with system-only PATH'
    Write-ReleaseJson "$Output/verification.json" @{complete=$true;platform='windows-x64';version=$version;compiler_sha256=(Get-ReleaseHash "$relocated/bin/emlf.exe");manager_sha256=(Get-ReleaseHash "$relocated/bin/mlfpkg.exe");build_runner_sha256=(Get-ReleaseHash "$relocated/bin/mlf-build-runner.exe");build_runner_protocol=1;checks=@('relocated Unicode/spaced SDK','system-only initial PATH','embedded versions','relocated build runner protocol','bounded parallel package build','compiler type query','plan','lock','build','both package test backends','run stdout','standalone generated executable')}
    Write-ReleaseTestEvent $suite $testCase pass @{log="$Output/standalone-executable.log";receipt="$Output/verification.json"}
    Write-Output 'Windows release smoke passed: relocated SDK, compiler, plan/lock/build/test/run, standalone native executable.'
} catch {
    Write-ReleaseTestEvent $suite $testCase fail $_.Exception.Message
    throw
} finally {
    foreach ($name in $variables) { [Environment]::SetEnvironmentVariable($name,$saved[$name],'Process') }
}
