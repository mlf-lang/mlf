#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Source,
    [string]$Output,
    [string]$Clang = $env:MLF_CLANG,
    [string[]]$IncludeDirectory = @()
)
$ErrorActionPreference = 'Stop'
if (!$Clang) { $Clang = (Get-Command clang -ErrorAction Stop).Source }
$sourcePath = (Resolve-Path -LiteralPath $Source).Path
if (!$Output) { $Output = [IO.Path]::ChangeExtension($sourcePath, '.exe') }
$outputPath = [IO.Path]::GetFullPath($Output)
$outputDirectory = [IO.Path]::GetDirectoryName($outputPath)
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
$irPath = [IO.Path]::ChangeExtension($outputPath, '.ll')
$compiler = Join-Path $PSScriptRoot 'bin/emlf.exe'
$start = [Diagnostics.ProcessStartInfo]::new($compiler)
$start.UseShellExecute = $false
$start.CreateNoWindow = $true
$start.RedirectStandardOutput = $true
$start.RedirectStandardError = $true
foreach ($directory in $IncludeDirectory) { $start.ArgumentList.Add('-i'); $start.ArgumentList.Add([IO.Path]::GetFullPath($directory)) }
$start.ArgumentList.Add('--emit-llvm')
$start.ArgumentList.Add($sourcePath)
$process = [Diagnostics.Process]::Start($start)
$errors = $process.StandardError.ReadToEndAsync()
$file = [IO.File]::Create($irPath)
try { $process.StandardOutput.BaseStream.CopyTo($file) } finally { $file.Dispose() }
$process.WaitForExit()
$diagnostic = $errors.GetAwaiter().GetResult()
if ($process.ExitCode) { throw "MLF compilation failed: $diagnostic" }
if ($diagnostic) { Write-Warning $diagnostic }
$clangVersion = (& $Clang --version | Out-String)
if ($LASTEXITCODE) { throw 'Cannot run Clang' }
$irFlags = @()
if ($clangVersion -match 'clang version (\d+)' -and [int]$Matches[1] -lt 15) { $irFlags = @('-mllvm', '-opaque-pointers') }
$include = Join-Path $PSScriptRoot 'include'
$runtime = Join-Path $PSScriptRoot 'runtime/mlf_runtime.c'
$gmp = Join-Path $PSScriptRoot 'lib/libgmp.dll.a'
$runtimeObject = [IO.Path]::ChangeExtension($outputPath, '.runtime.o')
# LLVM 14's opaque-pointer switch is only for the IR input. Applying it to
# the C frontend can crash that compiler's loop vectorizer.
& $Clang -O2 -std=c11 "-I$include" -c $runtime -o $runtimeObject
if ($LASTEXITCODE) { throw 'Runtime compilation failed' }
& $Clang -O2 -Wno-override-module @irFlags $irPath $runtimeObject $gmp -lshell32 -lm '-Wl,--stack,268435456' -o $outputPath
if ($LASTEXITCODE) { throw 'Native linking failed' }
$dll = Join-Path $PSScriptRoot 'bin/libgmp-10.dll'
$destination = Join-Path $outputDirectory 'libgmp-10.dll'
if ([IO.Path]::GetFullPath($dll) -ne $destination) {
    if ((Test-Path -LiteralPath $destination) -and (Get-FileHash -LiteralPath $dll).Hash -ne (Get-FileHash -LiteralPath $destination).Hash) {
        throw "A different GMP DLL already exists at $destination; keep the program in a separate directory."
    }
    Copy-Item -LiteralPath $dll -Destination $destination -Force
}
Write-Output $outputPath
