$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$WhisperRoot = Join-Path $ProjectRoot "whisper.cpp"
$BuildDir = Join-Path $WhisperRoot "build-vulkan-vs2022"
$ModelDir = Join-Path $WhisperRoot "models"
$CMake = "C:\Program Files\CMake\bin\cmake.exe"
$VulkanSdk = "C:\VulkanSDK\1.4.341.1"

if (-not (Test-Path $CMake)) {
    throw "CMake not found at $CMake"
}

if (-not (Test-Path $VulkanSdk)) {
    throw "Vulkan SDK not found at $VulkanSdk"
}

$env:Path = "C:\Program Files\CMake\bin;$VulkanSdk\Bin;$env:Path"
$env:VULKAN_SDK = $VulkanSdk

if (-not (Test-Path $WhisperRoot)) {
    git clone https://github.com/ggml-org/whisper.cpp.git $WhisperRoot
}

& $CMake -S $WhisperRoot -B $BuildDir -G "Visual Studio 17 2022" -A x64 -DGGML_VULKAN=ON
& $CMake --build $BuildDir --config Release --target whisper-server -j 4

cmd.exe /c "cd /d `"$ModelDir`" && download-ggml-model.cmd small `"$ModelDir`""

Write-Host ""
Write-Host "Vulkan build ready:"
Write-Host "  $BuildDir\bin\Release\whisper-server.exe"
Write-Host "Model:"
Write-Host "  $ModelDir\ggml-small.bin"
