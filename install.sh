#!/bin/bash

# Determine OS and Architecture
OS=$(uname -s)
ARCH=$(uname -m)

# Determine correct platform tag based on OS and architecture
case "$OS" in
  Darwin)
    if [[ "$ARCH" == "arm64" ]]; then
      PLATFORM_TAG="macosx_11_0_arm64"
    else
      PLATFORM_TAG="macosx_10_9_x86_64"
    fi
    ;;
  Linux)
    PLATFORM_TAG="linux_x86_64"
    ;;
  *)
    echo "Unsupported operating system: $OS"
    exit 1
    ;;
esac

# Get latest tag using GitHub API
LATEST_TAG=$(curl -s "https://api.github.com/repos/ecotaxa/CytoProcess/releases/latest" | jq -r '.tag_name')

if [[ -z "$LATEST_TAG" ]]; then
  echo "Error getting latest tag. Exiting."
  exit 1
fi

# Remove the "v" prefix if it exists
TAG_WITHOUT_V="${LATEST_TAG#v}"

# Check for --github flag
if [[ "$1" == "--github" ]]; then
  WHEEL_FILE_NAME="CytoProcess-${TAG_WITHOUT_V}-py3-none-${PLATFORM_TAG}.whl"
  WHEEL_URL="https://github.com/ecotaxa/CytoProcess/releases/download/${LATEST_TAG}/${WHEEL_FILE_NAME}"

  echo "System architecture: $ARCH"
  echo "Using platform tag: $PLATFORM_TAG"
  echo "Latest tag: $LATEST_TAG"
  #echo "Tag without 'v': $TAG_WITHOUT_V"
  echo "Wheel file name: $WHEEL_FILE_NAME"
  #echo "Wheel URL: $WHEEL_URL"

  # Download the wheel file
  WHEEL_FILE="/tmp/${WHEEL_FILE_NAME}"
  echo "Downloading wheel from: $WHEEL_URL"
  if ! curl -s -L "$WHEEL_URL" -o "$WHEEL_FILE"; then
    echo "Error downloading wheel file. Exiting."
    exit 1
  fi

  if [[ ! -f "$WHEEL_FILE" ]]; then
    echo "Downloaded file not found: $WHEEL_FILE"
    exit 1
  fi

  echo "-------------------------------------------------------------"
  ls -l "$WHEEL_FILE"
  echo "-------------------------------------------------------------"

  # Verify the file is actually a wheel
  if ! unzip -l "$WHEEL_FILE" >/dev/null 2>&1; then
    echo "Error: Downloaded file is not a valid wheel file"
    exit 1
  fi

  echo "Downloaded wheel file: $WHEEL_FILE"

  # Remove quarantine on macOS
  if [[ "$OS" == "Darwin" ]]; then
    if [[ -f "$WHEEL_FILE" ]]; then
      xattr -d com.apple.quarantine "$WHEEL_FILE" 2>/dev/null || true
      echo "Removed quarantine attribute on macOS (if present)."
    fi
  fi

elif [[ "$1" == "--local" || -z "$1" ]]; then
  # Install from local dist directory
  WHEEL_FILE=$(ls dist/*.whl 2>/dev/null | head -n 1)

  if [[ -z "$WHEEL_FILE" ]]; then
    echo "No wheel file found in dist/. Exiting."
    exit 1
  fi

  # Remove quarantine on macOS
  if [[ "$OS" == "Darwin" && -f "$WHEEL_FILE" ]]; then
    xattr -d com.apple.quarantine "$WHEEL_FILE" 2>/dev/null || true
    echo "Removed quarantine attribute."
  fi
else
  echo "Invalid argument. Use --github or --local."
  exit 1
fi

# Create system-wide virtual environment
echo "Creating virtual environment..."
echo "in system folder with sudo command, then you need to type your password"
sudo python3 -m venv /opt/CytoProcess_venv

sudo chmod +x /opt/CytoProcess_venv/bin/*
source /opt/CytoProcess_venv/bin/activate

# Get the Python executable path within the virtual environment
PYTHON_EXECUTABLE=$(which python)
# Get the Python major and minor version
PYTHON_VERSION=$(python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
# Construct the site-packages path using the determined version
SITE_PACKAGES_PATH=$(python -c "import site; print(site.getsitepackages()[0])")

echo "Python executable: $PYTHON_EXECUTABLE"
echo "Python version: $PYTHON_VERSION"
echo "Site-packages path: $SITE_PACKAGES_PATH"

# sudo /opt/CytoProcess_venv/bin/pip install --upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip


# Install the wheel
echo "Installing wheel file: $WHEEL_FILE"
sudo /opt/CytoProcess_venv/bin/pip install "$WHEEL_FILE" || { echo "Failed to create virtual environment. Exiting."; exit 1; }
# Check installation status
# if [ $? -ne 0 ]; then
#     echo "Installation failed!"
#     exit 1
# fi

# debug to show the files
# /opt/CytoProcess_venv/bin/pip show -f CytoProcess


sudo ln -s "$SITE_PACKAGES_PATH/CytoProcess/bin/Cyz2Json" /opt/CytoProcess_venv/bin/Cyz2Json
sudo ln -s "$SITE_PACKAGES_PATH/CytoProcess/pipeline.py" /opt/CytoProcess_venv/bin/pipeline.py
sudo ln -s "$SITE_PACKAGES_PATH/CytoProcess/convert.py" /opt/CytoProcess_venv/bin/convert.py
sudo ln -s "$SITE_PACKAGES_PATH/CytoProcess/main.py" /opt/CytoProcess_venv/bin/main.py


export LD_LIBRARY_PATH=/opt/CytoProcess_venv/lib/python${PYTHON_VERSION}/site-packages/CytoProcess/lib:${LD_LIBRARY_PATH}

sudo chmod ago+x /opt/CytoProcess_venv/lib/python${PYTHON_VERSION}/site-packages/CytoProcess/bin/*

desactivate

# if [[-f /opt/CytoProcess_venv/bin/Cyz2Json]]; then
#     echo "missing Cyz2Json"
#     exit 1
# fi

# if [[-f /opt/CytoProcess_venv/bin/pipeline.py]]; then
#     echo "missing pipeline.py"
#     exit 1
# fi

# if [[-f /opt/CytoProcess_venv/bin/main.py]]; then
#     echo "missing main.py"
#     exit 1
# fi


# echo "Installing main.py to virtual environment..."
# sudo cp src/CytoProcess/pipeline.py /opt/CytoProcess_venv/bin/
# sudo cp src/CytoProcess/main.py /opt/CytoProcess_venv/bin/
# sudo cp src/CytoProcess/bin/* /opt/CytoProcess_venv/bin/
# sudo chmod +x /opt/CytoProcess_venv/bin/pipeline.py
# sudo chmod +x /opt/CytoProcess_venv/bin/main.py
# sudo chmod +x /opt/CytoProcess_venv/bin/Cyz2Json


# Install execution script
echo "Creating launcher script..."
sudo tee /usr/local/bin/CytoProcess << 'EOF'
#!/bin/bash
source /opt/CytoProcess_venv/bin/activate
python -m CytoProcess.pipeline "$@"
deactivate
EOF

sudo chmod +x /usr/local/bin/CytoProcess

rm -rf "$WHEEL_FILE"

echo
echo "Installation completed successfully!"
exit 0
