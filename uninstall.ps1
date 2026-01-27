# Remove executable (if any)
Remove-Item -Path "C:\path\to\your\executable.bat" -Force -ErrorAction SilentlyContinue # Replace with actual executable path

# Stop the webserver (If applicable)
# Stop-Process -Name "CytoProcess" -Force -ErrorAction SilentlyContinue

# Remove the virtual environment
Remove-Item -Path ".venv" -Recurse -Force -ErrorAction SilentlyContinue  # Or wherever your venv is


Write-Host "Cytosense to EcoTaxa Pipeline uninstalled."
