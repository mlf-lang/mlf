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
    driver_sha256=(Get-ReleaseHash $PSCommandPath)
    clang_sha256=(Get-ReleaseHash $Clang); runtime=[ordered]@{}; profiles=[ordered]@{}
}
foreach ($file in (Get-ChildItem "$root/runtime/*.c","$root/runtime/*.h")) {
    $report.runtime[$file.Name] = Get-ReleaseHash $file.FullName
}
try {
    $env:PATH = "$NativePrefix/bin;$(Split-Path $Clang);" + $env:PATH
    if (!$HostHelper) {
        $HostHelper = "$Output/mlf-host.exe"
        $null = Invoke-ReleaseCommand $Clang @('-O2','-std=c11','-Wall','-Wextra','-Werror','-municode','-mno-incremental-linker-compatible','-Wl,--no-insert-timestamp',"$root/runtime/mlf_windows_host.c",'-o',$HostHelper) "$Output/helper-build.log" $root
    }
    $HostHelper = (Resolve-Path -LiteralPath $HostHelper).Path
    $env:MLF_WINDOWS_HOST = $HostHelper
    $report.helper_sha256 = Get-ReleaseHash $HostHelper
    # Exercise the production helper on native Windows, including Job Object
    # cleanup when its coordinator or the runner itself is forcibly terminated.
    $BuildRunner = "$Output/mlf-build-runner.exe"
    $RunnerFixture = "$Output/build-runner-fixture.exe"
    $RunnerTests = "$Output/build-runner-tests.exe"
    $runnerFlags = @('-O2','-std=c11','-Wall','-Wextra','-Werror','-municode','-mno-incremental-linker-compatible','-Wl,--no-insert-timestamp')
    $null = Invoke-ReleaseCommand $Clang ($runnerFlags + @("$root/runtime/mlf_build_runner.c",'-lpsapi','-o',$BuildRunner)) "$Output/build-runner-build.log" $root
    $null = Invoke-ReleaseCommand $Clang ($runnerFlags + @("$root/tests/native/build_runner_fixture.c",'-o',$RunnerFixture)) "$Output/build-runner-fixture-build.log" $root
    $null = Invoke-ReleaseCommand $Clang ($runnerFlags + @("$root/tests/native/build_runner_tests.c",'-o',$RunnerTests)) "$Output/build-runner-tests-build.log" $root
    $text = Invoke-ReleaseCommand $RunnerTests @($BuildRunner,$RunnerFixture,"$Output/build-runner") "$Output/build-runner.log" $Output
    Assert-Release ($text -match '22 native build runner tests passed') 'Missing build runner lifecycle success marker'
    $report.build_runner = @{
        passed=$true; tests=22; binary_sha256=(Get-ReleaseHash $BuildRunner)
        fixture_sha256=(Get-ReleaseHash $RunnerFixture); tests_sha256=(Get-ReleaseHash $RunnerTests)
        log_sha256=(Get-ReleaseHash "$Output/build-runner.log")
    }
    Write-Output 'Windows native build runner lifecycle tests passed'
    $SupervisorTests = "$Output/process-supervisor-tests.exe"
    $null = Invoke-ReleaseCommand $Clang ($runnerFlags + @("$root/tests/native/process_supervisor_tests.c","$root/runtime/mlf_process_supervisor.c",'-lpsapi','-o',$SupervisorTests)) "$Output/process-supervisor-build.log" $root
    $text = Invoke-ReleaseCommand $SupervisorTests @($RunnerFixture,"$Output/process-supervisor") "$Output/process-supervisor.log" $Output
    Assert-Release ($text -match 'native process supervisor tests passed') 'Missing dynamic process scope success marker'
    $report.process_supervisor = @{
        passed=$true; tests_sha256=(Get-ReleaseHash $SupervisorTests)
        log_sha256=(Get-ReleaseHash "$Output/process-supervisor.log")
    }
    Write-Output 'Windows native process supervisor lifecycle tests passed'

    $report.async_completions = [ordered]@{}
    foreach ($case in @('completion_cell_tests','async_completion_primitives')) {
        $binary = "$Output/$case.exe"
        $arguments = @('-O2','-std=c11','-Wall','-Wextra','-Werror','-mno-incremental-linker-compatible','-Wl,--no-insert-timestamp',"-I$NativePrefix/include","$root/tests/native/$case.c","$root/runtime/mlf_runtime.c","$NativePrefix/lib/libgc.dll.a","$NativePrefix/lib/libgmp.dll.a",'-lshell32','-lm','-o',$binary)
        $null = Invoke-ReleaseCommand $Clang $arguments "$Output/$case-build.log" $root
        $text = Invoke-ReleaseCommand $binary @() "$Output/$case.log" $Output
        Assert-Release ($text -match 'Native completion (representation|primitives): [0-9]+ checks, [0-9]+ callbacks passed') "Missing $case success marker"
        $report.async_completions[$case] = @{
            passed=$true; binary_sha256=(Get-ReleaseHash $binary)
            source_sha256=(Get-ReleaseHash "$root/tests/native/$case.c")
            log_sha256=(Get-ReleaseHash "$Output/$case.log")
        }
    }
    Write-Output 'Windows native typed completion and timer tests passed'

    # Independently compile C and LLVM twice, across a timestamp boundary and
    # into different directories. Compare real object/PE bytes, never a hash
    # with headers removed or rewritten after compilation.
    [IO.File]::WriteAllText("$Output/repro.c","int main(void) { return 0; }`n")
    [IO.File]::WriteAllText("$Output/repro.ll","define i32 @main() { ret i32 0 }`n")
    foreach ($round in @(1,2)) {
        $directory = "$Output/repro-$round"
        New-Item -ItemType Directory -Path $directory | Out-Null
        foreach ($language in @('c','ll')) {
            $null = Invoke-ReleaseCommand $Clang @('-O2','-Wno-override-module','-mno-incremental-linker-compatible','-c',"$Output/repro.$language",'-o',"$directory/$language.o") "$Output/repro-$round-$language-object.log" $directory
            $null = Invoke-ReleaseCommand $Clang @("$directory/$language.o",'-Wl,--no-insert-timestamp','-o',"$directory/$language.exe") "$Output/repro-$round-$language-link.log" $directory
            $null = Invoke-ReleaseCommand "$directory/$language.exe" @() "$Output/repro-$round-$language-run.log" $directory
        }
        if ($round -eq 1) { Start-Sleep -Milliseconds 2100 }
    }
    $reproducible = [ordered]@{}
    foreach ($language in @('c','ll')) {
        foreach ($extension in @('o','exe')) {
            $name = "$language.$extension"
            $hash = Get-ReleaseHash "$Output/repro-1/$name"
            Assert-Release ($hash -eq (Get-ReleaseHash "$Output/repro-2/$name")) "Windows rebuild changed $name"
            $bytes = [IO.File]::ReadAllBytes("$Output/repro-1/$name")
            $offset = if ($extension -eq 'o') { 4 } else { [BitConverter]::ToInt32($bytes,60) + 8 }
            Assert-Release ([BitConverter]::ToUInt32($bytes,$offset) -eq 0) "Windows $name contains a wall-clock timestamp"
            $reproducible[$name] = $hash
        }
    }
    $report.reproducible = $reproducible
    $null = Invoke-ReleaseCommand $Clang @('-O2','-std=c11','-Wall','-Wextra','-Werror','-municode','-mno-incremental-linker-compatible','-Wl,--no-insert-timestamp',"$root/tests/native/windows_paths.c",'-o',"$Output/path-test.exe") "$Output/paths-build.log" $root
    $text = Invoke-ReleaseCommand "$Output/path-test.exe" @() "$Output/paths.log" $Output
    Assert-Release ($text -match 'Windows path guards passed') 'Missing path guard success marker'
    $report.path_guards = @{passed=$true;source_sha256=(Get-ReleaseHash "$root/tests/native/windows_paths.c");binary_sha256=(Get-ReleaseHash "$Output/path-test.exe")}
    foreach ($profile in @('compact-gc')) {
        $directory = "$Output/$profile"
        New-Item -ItemType Directory -Path $directory | Out-Null
        $arguments = @('-O2','-std=c11','-mno-incremental-linker-compatible','-Wl,--no-insert-timestamp',"-I$NativePrefix/include","$root/tests/native/windows_runtime.c")
        $arguments += @("$NativePrefix/lib/libgc.dll.a")
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
