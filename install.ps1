# Install script for Windows (install.ps1)

# Check if running as administrator
if (-Not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
  Write-Error "This script requires administrator privileges. Please run it as administrator."
  exit 1
}


$latestTag = (Invoke-WebRequest -Uri "https://api.github.com/repos/ecotaxa/CytoProcess/releases/latest" | ConvertFrom-Json).tag_name
$tagWithoutV = $latestTag -replace "^v", ""

$wheelFileName = "CytoProcess-${tagWithoutV}-py3-none-${platformTag}.whl"
  $wheelUrl = "https://github.com/ecotaxa/CytoProcess/releases/download/${latestTag}/${wheelFileName}"

  # Some debug messages
  Write-Host "System architecture: $arch"
  Write-Host "Using platform tag: $platformTag"
  Write-Host "Latest tag: $latestTag"
  Write-Host "Tag without 'v': $tagWithoutV"
  Write-Host "Wheel file name: $wheelFileName"
  Write-Host "Wheel URL: $wheelUrl"

  # Download the wheel file (PowerShell equivalent)
  $wheelFile = "$env:TEMP\$wheelFileName"
  Write-Host "Downloading wheel from: $wheelUrl"
  try {
    Invoke-WebRequest -Uri $wheelUrl -OutFile $wheelFile
  }
  catch {
    Write-Error "Error downloading wheel file. Exiting."
    exit 1
  }

    # Check if the file was downloaded successfully (PowerShell equivalent)
    if (!(Test-Path $wheelFile)) {
      Write-Error "Downloaded file not found: $wheelFile"
      exit 1

# Create virtual environment
python -m venv $env:LOCALAPPDATA\CytoProcess_venv

# Activate virtual environment
& "$env:LOCALAPPDATA\CytoProcess_venv\Scripts\Activate.ps1"

# Install Python packages within the virtual environment
# pip install -r requirements.txt
# pip install . # Install the package
pip install $wheelFile

# Create installation directory
$installDir = "$env:ProgramFiles\CytoProcess"
New-Item -ItemType Directory -Path $installDir -Force

# Get Python executable path within the virtual environment
$pythonExec = (Get-Command python).Source

# Get site-packages path dynamically
$sitePackagesPath = & python -c "import site; print(site.getsitepackages()[0])"

# Copy files to the installation directory
# Copy-Item -Path "$sitePackagesPath\CytoProcess\bin\Cyz2Json.exe" -Destination "$installDir\Cyz2Json.exe"
Copy-Item -Path "$sitePackagesPath\CytoProcess\bin" -Destination "$installDir\bin" -Recurse -Force
Copy-Item -Path "$sitePackagesPath\CytoProcess\pipeline.py" -Destination "$installDir\pipeline.py"
Copy-Item -Path "$sitePackagesPath\CytoProcess\convert.py" -Destination "$installDir\convert.py"
Copy-Item -Path "$sitePackagesPath\CytoProcess\main.py" -Destination "$installDir\main.py"



# Create executable wrappers (using batch files for simplicity)
# Cyz2Json.bat
@"
@echo off
"$env:LOCALAPPDATA\CytoProcess_venv\Scripts\python.exe" "$installDir\pipeline.py" %*
"@ | Out-File -Encoding ascii "$installDir\CytoProcess.bat"


# Add installation directory to PATH
$currentPath = [Environment]::GetEnvironmentVariable("PATH", "Machine")
if (-not ($currentPath -like "*$installDir*")) {
  [Environment]::SetEnvironmentVariable("PATH", "$installDir;$currentPath", "Machine")
  Write-Host "Added '$installDir' to the system PATH.  You may need to restart your PowerShell session or log out and back in for this change to take effect."
}


# Deactivate virtual environment
deactivate

Write-Host "Installation complete."

