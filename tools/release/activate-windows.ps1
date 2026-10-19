# Dot-source this script to select this extracted SDK for the current session.
param([string]$Clang = $env:MLF_CLANG)
$env:MLF_NATIVE_PREFIX = $PSScriptRoot
$env:MLF_PACKAGE_MANAGER = Join-Path $PSScriptRoot 'bin/mlfpkg.exe'
$env:PATH = (Join-Path $PSScriptRoot 'bin') + ';' + $env:PATH
if ($Clang) { $env:MLF_CLANG = $Clang }
