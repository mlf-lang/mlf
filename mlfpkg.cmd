@echo off
if defined MLF_PACKAGE_MANAGER (
  "%MLF_PACKAGE_MANAGER%" %*
) else (
  "%~dp0.mlf-build\windows-package-tools\bin\mlfpkg.exe" %*
)
exit /b %errorlevel%
