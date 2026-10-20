# Thin native Windows launcher. Package policy is implemented in MLF.
$manager = $env:MLF_PACKAGE_MANAGER
if (!$manager) { $manager = Join-Path $PSScriptRoot '.mlf-build/windows-package-tools/bin/mlfpkg.exe' }
if (!(Test-Path -LiteralPath $manager -PathType Leaf)) { throw 'Build the Windows package manager with scripts/bootstrap-package-windows.ps1 first, or set MLF_PACKAGE_MANAGER.' }
& $manager @args
exit $LASTEXITCODE
