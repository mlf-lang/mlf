#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Build,
    [Parameter(Mandatory)][string]$NativePrefix,
    [Parameter(Mandatory)][string]$Evidence,
    [Parameter(Mandatory)][string]$Output,
    [Parameter(Mandatory)][string]$Clang
)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/windows-common.ps1"
Assert-Release $IsWindows 'Package Windows releases on native Windows PowerShell 7'
$root = (Resolve-Path "$PSScriptRoot/../..").Path
$Build = (Resolve-Path -LiteralPath $Build).Path
$NativePrefix = (Resolve-Path -LiteralPath $NativePrefix).Path
$Evidence = (Resolve-Path -LiteralPath $Evidence).Path
$Output = [IO.Path]::GetFullPath($Output)
Assert-Release (!(Test-Path -LiteralPath $Output)) 'Use a new release output directory'
$status = @(& git -C $root status --porcelain)
Assert-Release ($LASTEXITCODE -eq 0 -and $status.Count -eq 0) 'Commit release sources before packaging'
$commit = (& git -C $root rev-parse HEAD).Trim()
$version = (Get-Content "$root/VERSION" -Raw).Trim()
Assert-Release ($version -match '^\d+\.\d+\.\d+$') 'Invalid release VERSION'
foreach ($path in @('mlf-package.json','bootstrap/mlf-package.json','package/mlf-package.json','tests/mlf-package.json')) {
    Assert-Release ((Read-ReleaseJson "$root/$path").version -eq $version) "Version mismatch: $path"
}
Assert-Release ((Get-Content "$root/CHANGELOG.md" -Raw) -match "(?m)^## $([regex]::Escape($version)) ") 'Missing versioned changelog entry'
$qualification = Read-ReleaseJson "$Evidence/release-validation.json"
Assert-Release ($qualification.complete -eq $true -and $qualification.platform -eq 'windows-x64' -and $qualification.version -eq $version) 'Incomplete or stale Windows qualification'
$compilerHash = Get-ReleaseHash "$Build/bin/emlf.exe"
$managerHash = Get-ReleaseHash "$Build/bin/mlfpkg.exe"
Assert-Release ($qualification.compiler_sha256 -eq $compilerHash -and $qualification.manager_sha256 -eq $managerHash) 'Release tools differ from the qualified binaries'
Assert-Release ($qualification.helper_sha256 -eq (Get-ReleaseHash "$Build/bin/mlf-host.exe")) 'Release host helper differs from qualification'
Assert-Release ($qualification.clang_sha256 -eq (Get-ReleaseHash $Clang)) 'Release smoke must use the qualified Clang'
Assert-ReleaseSources $root $qualification.sources
foreach ($entry in $qualification.dependencies.GetEnumerator()) { Assert-Release ((Get-ReleaseHash (Join-Path $NativePrefix $entry.Key)) -eq $entry.Value) "Native dependency changed after qualification: $($entry.Key)" }
foreach ($entry in $qualification.evidence.GetEnumerator()) {
    Assert-Release ($entry.Key -eq [IO.Path]::GetFileName($entry.Key)) 'Invalid qualification evidence path'
    Assert-Release ((Get-ReleaseHash (Join-Path $Evidence $entry.Key)) -eq $entry.Value) "Qualification evidence changed: $($entry.Key)"
}
Assert-Release ($qualification.tests.fixed_point.complete -eq $true -and $qualification.tests.fixed_point.reused_candidate_build -eq $false) 'Fresh native compiler and manager fixed point required'
Assert-Release ($qualification.tests.fixed_point.stages -eq 2 -and $qualification.tests.fixed_point.tools.emlf.binary_sha256 -eq $compilerHash -and $qualification.tests.fixed_point.tools.mlfpkg.binary_sha256 -eq $managerHash) 'Fixed point report does not identify the released tools'
Assert-Release ($qualification.tests.resolver.passed -eq 18 -and $qualification.tests.integration.passed -eq 29) 'All 47 native Windows package checks are required'
Assert-Release ($qualification.tests.resolver.manager_sha256 -eq $managerHash -and $qualification.tests.integration.compiler_sha256 -eq $compilerHash -and $qualification.tests.integration.manager_sha256 -eq $managerHash) 'Package tests identify different tools'
Assert-Release ($qualification.tests.integration.coverage_report_sha256 -eq (Get-ReleaseHash "$Evidence/packages.coverage.jsonl") -and $qualification.tests.integration.coverage_inventory_sha256 -eq (Get-ReleaseHash "$Evidence/unit-inventory.json") -and $qualification.tests.integration.coverage_inventory_sha256 -eq (Get-ReleaseHash "$root/tests/golden/unit-inventory.json")) 'Package completion evidence differs from its frozen inventory or verified report'
Assert-Release ($qualification.tests.parity.cases -eq 7086 -and $qualification.tests.parity.source_compilations -eq 7075 -and $qualification.tests.parity.shared_source_cases -eq 11 -and $qualification.tests.parity.runtime_executions -eq 160) 'Full independent compiler parity is required'
Assert-Release ($qualification.tests.parity.compiler_sha256 -eq $compilerHash) 'Parity report identifies a different compiler'
Assert-Release ($qualification.runner_sha256 -match '^[0-9a-f]{64}$' -and $qualification.tests.resolver.runner_sha256 -eq $qualification.runner_sha256 -and $qualification.tests.integration.runner_sha256 -eq $qualification.runner_sha256 -and $qualification.tests.parity.runner_sha256 -eq $qualification.runner_sha256) 'Package and parity reports identify different compiler test runners'
Assert-Release ($qualification.tests.runtime.complete -eq $true -and $qualification.tests.runtime.profiles.Count -eq 1 -and $qualification.tests.runtime.profiles.'compact-gc'.passed -eq $true) 'The compact-GC runtime profile is required'
# Redistributable LGPL dependencies include their notices and exact source.
foreach ($path in @('licenses/gmp-6.3.0/COPYING','licenses/gmp-6.3.0/COPYING.LESSERv3','licenses/libwinpthread/COPYING','licenses/pkgconf/COPYING','sources/gmp-6.3.0.tar.xz','sources/gc-8.2.12.tar.gz','sources/msys2-package-provenance.json')) {
    Assert-Release (Test-Path -LiteralPath "$NativePrefix/$path" -PathType Leaf) "Missing dependency redistribution material: $path"
}
$name = "mlf-$version-windows-x64"
$bundle = "$Output/$name"
New-Item -ItemType Directory -Path "$bundle/bin","$bundle/runtime","$bundle/evidence","$bundle/licenses","$bundle/examples" -Force | Out-Null
Copy-Item -LiteralPath "$Build/bin/emlf.exe","$Build/bin/mlfpkg.exe","$Build/bin/mlf-host.exe" -Destination "$bundle/bin"
foreach ($file in @('libgmp-10.dll','libgc-1.dll','libwinpthread-1.dll','pkg-config.exe','libpkgconf-8.dll')) { Copy-Item -LiteralPath "$NativePrefix/bin/$file" -Destination "$bundle/bin" }
Copy-Item -LiteralPath "$NativePrefix/include","$NativePrefix/lib","$NativePrefix/licenses","$NativePrefix/sources" -Destination $bundle -Recurse -Force
Copy-Item -Path "$root/runtime/*.c","$root/runtime/*.h" -Destination "$bundle/runtime"
Copy-Item -LiteralPath "$root/VERSION","$root/LICENSE","$root/CHANGELOG.md" -Destination $bundle
Copy-Item -LiteralPath "$root/docs/windows.md" -Destination "$bundle/Windows-bootstrap.md"
Copy-Item -LiteralPath "$PSScriptRoot/activate-windows.ps1" -Destination "$bundle/Activate.ps1"
Copy-Item -LiteralPath "$PSScriptRoot/build-program-windows.ps1" -Destination "$bundle/Build-Program.ps1"
Copy-Item -LiteralPath "$PSScriptRoot/licenses/BDWGC.txt" -Destination "$bundle/licenses/BDWGC.txt"
Copy-Item -LiteralPath "$root/runtime/khash.h" -Destination "$bundle/licenses/khash.h"
[IO.File]::WriteAllText("$bundle/COMMIT",$commit+"`n")
# Only source inputs are copied, never generated locks, caches or executables.
foreach ($relative in @('examples/io-hello.emlf','examples/modules/Main.emlf','examples/modules/Geometry/Point.emlf','examples/packages/Main.emlf','examples/packages/mlf-package.json','examples/packages/greeting/Greeting.emlf','examples/packages/greeting/mlf-package.json','examples/packages/message/Message.emlf','examples/packages/message/mlf-package.json')) {
    $destination = Join-Path $bundle $relative
    New-Item -ItemType Directory -Path (Split-Path $destination) -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $root $relative) -Destination $destination
}
Copy-Item -LiteralPath "$Evidence/release-validation.json" -Destination "$bundle/evidence"
foreach ($file in $qualification.evidence.Keys) { Copy-Item -LiteralPath (Join-Path $Evidence $file) -Destination "$bundle/evidence" }
$release = [ordered]@{schema_version=1;version=$version;commit=$commit;platform='windows-x64';compiler_sha256=$compilerHash;manager_sha256=$managerHash;host_helper_sha256=$qualification.helper_sha256;qualification='evidence/release-validation.json';compiler_parity_cases=7086;compiler_source_compilations=7075;compiler_shared_source_cases=11;compiler_runtime_executions=160;package_resolver_tests=18;package_integration_cases=29;native_fixed_point=@('emlf','mlfpkg');runtime_profiles=@('compact-gc');internal_compiler_release_groups='POSIX transports; not qualified on Windows';external_tools=@('PowerShell 7 for helper scripts','MinGW-targeting Clang for native compilation')}
Write-ReleaseJson "$bundle/release.json" $release
[IO.File]::WriteAllText("$bundle/README.md", @'
# MLF native Windows developer preview

Extract the entire archive. From PowerShell 7, dot-source `./Activate.ps1`.
Run `emlf --version` and `mlfpkg --version`; both are native x64 executables.
The compiler and package manager need no GHC, Cabal, Python, WSL or MSYS shell.

Native compilation additionally requires MinGW-targeting Clang. Select it with
`./Activate.ps1 -Clang C:/path/to/clang.exe` (dot-source the command), or set
MLF_CLANG. The release includes GMP, BDWGC, pkg-config, import libraries, headers,
runtime sources and dependency DLLs. Preserve this directory structure.

Try `mlfpkg --manifest examples/packages/mlf-package.json test`, then
`mlfpkg --manifest examples/packages/mlf-package.json run hello`.
Build-Program.ps1 compiles a standalone .emlf source into a native .exe.

release.json identifies the source commit and unchanged qualified executables.
CHECKSUMS covers every bundled file. evidence/ records a native fixed point for
both tools, all 7,086 independent parity cases, 160 compiler runtime executions,
the compact-GC runtime, and 47 package cases. The compiler repository's six
internal POSIX release/benchmark groups are not qualified on Windows.

MLF is BSD-3-Clause. Dependency notices and redistribution sources are bundled
under licenses/ and sources/. The binaries are unsigned developer previews.
'@ + "`n")
& "$PSScriptRoot/smoke-windows.ps1" -Package $bundle -Clang $Clang -Output "$Output/smoke-work" | Tee-Object -FilePath "$Output/smoke.log"
Copy-Item -LiteralPath "$Output/smoke-work/verification.json" -Destination "$bundle/evidence/release-smoke.json"
Copy-Item -LiteralPath "$Output/smoke.log" -Destination "$bundle/evidence/release-smoke.log"
$checksums = foreach ($file in (Get-ChildItem -LiteralPath $bundle -Recurse -File | Sort-Object FullName)) {
    $relative = [IO.Path]::GetRelativePath($bundle,$file.FullName).Replace('\','/')
    "$(Get-ReleaseHash $file.FullName)  $relative"
}
[IO.File]::WriteAllLines("$bundle/CHECKSUMS",$checksums,[Text.UTF8Encoding]::new($false))
$archive = "$Output/$name.zip"
[IO.Compression.ZipFile]::CreateFromDirectory($bundle,$archive,[IO.Compression.CompressionLevel]::Optimal,$true)
$zip = [IO.Compression.ZipFile]::OpenRead($archive)
try {
    foreach ($line in $checksums) {
        $hash,$relative = $line -split '  ',2
        $entry = $zip.GetEntry("$name/$relative")
        Assert-Release ($null -ne $entry) "Archive entry missing: $relative"
        $stream = $entry.Open()
        try { $actual = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($stream)).ToLowerInvariant() } finally { $stream.Dispose() }
        Assert-Release ($actual -eq $hash) "Archive checksum mismatch: $relative"
    }
} finally { $zip.Dispose() }
[IO.File]::WriteAllText("$archive.sha256","$(Get-ReleaseHash $archive)  $name.zip`n")
Write-Output "Windows release package: $archive"
