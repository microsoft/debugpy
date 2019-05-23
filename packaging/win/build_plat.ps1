param($packages, [switch]$pack, [string]$platform, [string]$pyver)

$root = $script:MyInvocation.MyCommand.Path | Split-Path -parent;
if ($env:BUILD_BINARIESDIRECTORY) {
    $bin = mkdir -Force $env:BUILD_BINARIESDIRECTORY\bin
    $obj = mkdir -Force $env:BUILD_BINARIESDIRECTORY\obj
    $dist = mkdir -Force $env:BUILD_BINARIESDIRECTORY\dist
} else {
    $bin = mkdir -Force $root\bin
    $obj = mkdir -Force $root\obj
    $dist = mkdir -Force $root\dist
}

$env:SKIP_CYTHON_BUILD = "1"

$filter = "*python.$pyver*"
if ($platform -eq 'win32'){
    $filter = "*pythonx86.$pyver*"
}
Write-Host "Filter: $filter"

if (-not $pack) {
    (Get-ChildItem $packages\python* -Directory -Filter $filter) | ForEach-Object{ Get-Item $_\tools\python.exe } | Where-Object{ Test-Path $_ } | Select-Object -last 1 | ForEach-Object{
        Write-Host "Building with $_"
        & $_ -m pip install -U pip
        & $_ -m pip install -U pyfindvs setuptools wheel cython

        Push-Location "$root\..\src\ptvsd\_vendored\pydevd"
        & $_ setup_cython.py enable_msbuildcompiler build_ext -b "$bin" -t "$obj"
        Pop-Location
    }
} else {
    Get-ChildItem $dist\*.whl, $dist\*.zip | Remove-Item -Force

    (Get-ChildItem $packages\python* -Directory -Filter $filter) | ForEach-Object{ Get-Item $_\tools\python.exe } | Where-Object{ Test-Path $_ } | Select-Object -last 1 | ForEach-Object{
        Write-Host "Building  wheel with $_ for platform."
        & $_ setup.py build -b "$bin" -t "$obj" bdist_wheel -d "$dist" -p "$platform" --abi
        Get-ChildItem $dist\ptvsd-*.whl | ForEach-Object{
            Write-Host "Built wheel found at $_"
        }
    }
}
