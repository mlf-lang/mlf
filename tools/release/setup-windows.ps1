#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Output,
    [string]$Cache,
    [string]$Clang
)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/windows-common.ps1"
Assert-Release $IsWindows 'Use native Windows PowerShell 7'
$Output = [IO.Path]::GetFullPath($Output)
Assert-Release (!(Test-Path -LiteralPath $Output)) 'Use a new dependency output directory'
if (!$Cache) { $Cache = "$Output/downloads" }
$Cache = [IO.Path]::GetFullPath($Cache)
$unpack = "$Output/packages"
New-Item -ItemType Directory -Path $Cache,$unpack -Force | Out-Null
$tar = "$env:SystemRoot/System32/tar.exe"
Assert-Release (Test-Path -LiteralPath $tar) 'Native Windows tar.exe is required (with zstd support)'
function Get-PinnedDownload([string]$Url,[string]$Name,[string]$Hash) {
    $path = Join-Path $Cache $Name
    if (!(Test-Path -LiteralPath $path)) {
        Write-Host "Downloading $Name"
        Invoke-WebRequest -Uri $Url -OutFile $path -MaximumRetryCount 3 -RetryIntervalSec 5 | Out-Null
    }
    Assert-Release ((Get-ReleaseHash $path) -eq $Hash) "Dependency checksum mismatch: $Name"
    return $path
}
$packages = @(
    @{package='mingw-w64-ucrt-x86_64-gmp-6.3.0-2-any.pkg.tar.zst';sha256='e82a75968a556484a50084578238a84eb60fb93e34986fd6695c537975bd39ea'},
    @{package='mingw-w64-ucrt-x86_64-gc-8.2.12-1-any.pkg.tar.zst';sha256='68724a16fccaa9481971a988899178514b2d4df8e84c32997270796839d62645'},
    @{package='mingw-w64-ucrt-x86_64-libwinpthread-14.0.0.r426.g4564ee4b5-2-any.pkg.tar.zst';sha256='a02f5e09d666d3be657c78c86fe67c975d04fe33b5211cd5ff1b23a91c118524'},
    @{package='mingw-w64-ucrt-x86_64-pkgconf-1~3.0.9-1-any.pkg.tar.zst';sha256='4ea9bdd77df366333b973771c2ec377e77a4354e60c16a4556af7d849494366f'}
)
foreach ($package in $packages) {
    $package.url = 'https://repo.msys2.org/mingw/ucrt64/' + $package.package
    $archive = Get-PinnedDownload $package.url $package.package $package.sha256
    & $tar -xf $archive -C $unpack
    if ($LASTEXITCODE) { throw "Native tar extraction failed: $archive" }
}
$prefix = "$unpack/ucrt64"
Copy-Item -LiteralPath "$prefix/bin/pkgconf.exe" -Destination "$prefix/bin/pkg-config.exe"
New-Item -ItemType Directory -Path "$prefix/lib/pkgconfig","$prefix/licenses/gmp-6.3.0","$prefix/licenses/libwinpthread","$prefix/licenses/pkgconf","$prefix/sources","$Output/material" -Force | Out-Null
foreach ($entry in @(@('gmp','6.3.0','gmp'),@('bdw-gc','8.2.12','gc'))) {
    $pc = 'prefix=${pcfiledir}/../..' + "`n" + 'libdir=${prefix}/lib' + "`n" + 'includedir=${prefix}/include' + "`n"
    $pc += "Name: $($entry[0])`nDescription: MLF native Windows dependency`nVersion: $($entry[1])`n"
    $pc += 'Libs: -L${libdir} -l' + $entry[2] + "`n" + 'Cflags: -I${includedir}' + "`n"
    [IO.File]::WriteAllText("$prefix/lib/pkgconfig/$($entry[0]).pc",$pc)
}
$gmp = Get-PinnedDownload 'https://ftp.gnu.org/gnu/gmp/gmp-6.3.0.tar.xz' 'gmp-6.3.0.tar.xz' 'a3c2b80201b89e68616f4ad30bc66aee4927c3ce50e33929ca819d5c43538898'
$gc = Get-PinnedDownload 'https://github.com/ivmai/bdwgc/releases/download/v8.2.12/gc-8.2.12.tar.gz' 'gc-8.2.12.tar.gz' '42e5194ad06ab6ffb806c83eb99c03462b495d979cda782f3c72c08af833cd4e'
Copy-Item -LiteralPath $gmp,$gc -Destination "$prefix/sources"
& $tar -xf $gmp -C "$Output/material" gmp-6.3.0/COPYING gmp-6.3.0/COPYINGv3 gmp-6.3.0/COPYING.LESSERv3
if ($LASTEXITCODE) { throw 'Cannot extract GMP license notices' }
Copy-Item -Path "$Output/material/gmp-6.3.0/COPYING*" -Destination "$prefix/licenses/gmp-6.3.0"
Copy-Item -LiteralPath "$prefix/share/licenses/libwinpthread/COPYING" -Destination "$prefix/licenses/libwinpthread/COPYING"
Copy-Item -LiteralPath "$prefix/share/doc/pkgconf/COPYING","$prefix/share/doc/pkgconf/AUTHORS" -Destination "$prefix/licenses/pkgconf"
Write-ReleaseJson "$prefix/sources/msys2-package-provenance.json" $packages
if (!$Clang) {
    $name = 'llvm-mingw-20261006-ucrt-x86_64.zip'
    $archive = Get-PinnedDownload "https://github.com/mstorsjo/llvm-mingw/releases/download/20261006/$name" $name '317492c456aa27ee607a5919f1d2d38dcdc1112516a24d0bf4b00d078f52d17a'
    Expand-Archive -LiteralPath $archive -DestinationPath "$Output/llvm"
    $Clang = "$Output/llvm/llvm-mingw-20261006-ucrt-x86_64/bin/clang.exe"
}
$Clang = (Resolve-Path -LiteralPath $Clang).Path
$env:MLF_NATIVE_PREFIX = $prefix
$env:MLF_CLANG = $Clang
$env:PKG_CONFIG_PATH = "$prefix/lib/pkgconfig"
$env:PATH = "$prefix/bin;" + $env:PATH
if ($env:GITHUB_ENV) {
    Add-Content -LiteralPath $env:GITHUB_ENV -Value "MLF_NATIVE_PREFIX=$prefix`nMLF_CLANG=$Clang`nPKG_CONFIG_PATH=$prefix/lib/pkgconfig"
}
if ($env:GITHUB_PATH) { Add-Content -LiteralPath $env:GITHUB_PATH -Value "$prefix/bin`n$(Split-Path $Clang)" }
Write-Host "Native Windows dependency prefix: $prefix"
