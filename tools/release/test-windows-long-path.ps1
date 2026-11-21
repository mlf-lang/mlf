#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Clang,
    [Parameter(Mandatory)][string]$Output
)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/windows-common.ps1"
# Original e7da00f201bfb66bf6e26d59e56184dd37a83abd, mapped after reviewed history cleanup.
$baseline = 'bf38dc538598a0389a3310fe26c16f6609c912fc'
git fetch --no-tags --depth=1 origin $baseline
Assert-Release ($LASTEXITCODE -eq 0) 'Cannot fetch the immutable pre-fix runner'
$source = git show "${baseline}:runtime/mlf_build_runner.c"
Assert-Release ($LASTEXITCODE -eq 0) 'Cannot read the immutable pre-fix runner'
$output = [IO.Path]::GetFullPath($Output)
$oldSource = "$output/pre-fix-build-runner.c"
[IO.File]::WriteAllText($oldSource, ($source -join "`n") + "`n", [Text.UTF8Encoding]::new($false))
$expectedOldSource = 'fce82f0710edd910557956a2225f211f195f10b69e95c3676d86bb01fd2f6abd'
Assert-Release ((Get-FileHash -Algorithm SHA256 $oldSource).Hash.ToLowerInvariant() -eq $expectedOldSource) 'Pre-fix runner differs from the independently pinned source'
$oldRunner = "$output/pre-fix-build-runner.exe"
$flags = @('-O2','-std=c11','-Wall','-Wextra','-Werror','-municode',"-I$PWD/runtime",$oldSource,'-lpsapi','-o',$oldRunner)
$null = Invoke-ReleaseCommand $Clang $flags "$output/pre-fix-build-runner-build.log" $PWD.Path
$negative = "$output/build-runner/negative-control"
Assert-Release (!(Test-Path -LiteralPath $negative)) 'Negative control needs a fresh directory'
$rejected = $false
$savedExact = $env:MLF_TEST_EXACT
$savedEvents = $env:MLF_TEST_EVENTS
try {
  $env:MLF_TEST_EXACT = 'native-build-runner/redirected-input'
  $env:MLF_TEST_EVENTS = $null
  try {
    $null = Invoke-ReleaseCommand "$output/build-runner-tests.exe" @($oldRunner,"$output/build-runner-fixture.exe",$negative) "$output/long-path-negative.log" $PWD.Path
  } catch { $rejected = $true }
} finally {
  $env:MLF_TEST_EXACT = $savedExact
  $env:MLF_TEST_EVENTS = $savedEvents
}
Assert-Release $rejected 'Regression unexpectedly accepted the pre-fix runner'
$results = @(Get-ChildItem -Path "$negative/build-runner-*/long-redirections.result" -File)
Assert-Release ($results.Count -eq 1) 'Missing unique long-path negative result'
$result = Read-ReleaseJson $results[0].FullName
Assert-Release ($result.complete -eq $true -and $result.exit_code -eq 126) 'Negative control did not reach the expected launch failure'
$task = @($result.tasks | Where-Object { $_.id -eq 'absolute' })
Assert-Release ($task.Count -eq 1 -and $task[0].state -eq 'failed' -and $task[0].exit_code -eq 126 -and $task[0].pid -eq 0) 'Negative control failed for a different reason'
Write-ReleaseJson "$output/long-path-negative.json" @{passed=$true;baseline=$baseline;pre_fix_runner_sha256=(Get-ReleaseHash $oldRunner);result=$result}
Write-Output 'Pre-fix runner rejected long stream paths with exit 126 and PID 0'
