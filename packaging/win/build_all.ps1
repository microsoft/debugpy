param($packages, [switch]$pack, [string]$wheeltype)

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

Get-ChildItem $dist\*.whl, $dist\*.zip | Remove-Item -Force

(Get-ChildItem $packages\python* -Directory -Filter '*python.3.8*') | ForEach-Object{ Get-Item $_\tools\python.exe } | Where-Object{ Test-Path $_ } | Select-Object -last 1 | ForEach-Object{
    Write-Host "Building with $_"
    & $_ -m pip install -U pip
    & $_ -m pip install -U pyfindvs setuptools wheel cython

    if ($wheeltype -eq 'sdist') {
        Write-Host "Building sdist with $_"
        & $_ setup.py sdist -d "$dist" --formats zip
    }

    if ($wheeltype -eq 'pure') {
        Write-Host "Building wheel with $_ pure python wheel"
        & $_ setup.py bdist_wheel -d "$dist" --pure
    }

    if ($wheeltype -eq 'universal') {
        Write-Host "Building wheel with $_ universal wheel"
        & $_ setup.py bdist_wheel -d "$dist" --universal
    }

    Get-ChildItem $dist\ptvsd-*.whl, $dist\*.zip | ForEach-Object{
        Write-Host "Built wheel found at $_"
    }
}

