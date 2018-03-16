param($packages, [switch]$pack)

$root = $script:MyInvocation.MyCommand.Path | Split-Path -parent;
if ($env:BUILD_BINARIESDIRECTORY) {
    $bin = mkdir -Force $env:BUILD_BINARIESDIRECTORY\$bin
    $obj = mkdir -Force $env:BUILD_BINARIESDIRECTORY\$obj
    $dist = mkdir -Force $env:BUILD_BINARIESDIRECTORY\$dist
} else {
    $bin = mkdir -Force $root\bin
    $obj = mkdir -Force $root\obj
    $dist = mkdir -Force $root\dist
}

if (-not $pack) {
    (gci $packages\python* -Directory) | %{ gi $_\tools\python.exe } | ?{ Test-Path $_ } | %{
        Write-Host "Building with $_"
        & $_ -m pip install -U D:\repos\pyfindvs setuptools wheel cython
        pushd "$root\..\ptvsd\pydevd"
        & $_ setup_cython.py enable_msbuildcompiler build_ext -b "$bin" -t "$obj"
        popd
    }

} else {
    gci $dist\*.whl | Remove-Item -Force

    (gci $packages\python* -Directory) | %{ gi $_\tools\python.exe } | ?{ Test-Path $_ } | select -last 1 | %{
        Write-Host "Building wheel with $_"
        & $_ setup.py build -b "$bin" -t "$obj" bdist_wheel -d "$dist"
        gci $dist\ptvsd-*.whl | %{
            Copy-Item $_ (Join-Path $_.Directory ($_.Name -replace '(ptvsd-.+?)-any\.whl', '$1-win_amd64.whl'))
            Copy-Item $_ (Join-Path $_.Directory ($_.Name -replace '(ptvsd-.+?)-any\.whl', '$1-win32.whl'))
        }
    }
}

