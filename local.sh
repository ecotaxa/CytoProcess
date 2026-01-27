#!/bin/bash


WHEEL_URL="https://github.com/ecotaxa/CytoProcess/releases/download/v1.0.0/CytoProcess-1.0.0-py3-none-linux_x86_64.whl"
WHEEL_FILE="CytoProcess-1.0.0-py3-none-linux_x86_64.whl"
curl -L -O $WHEEL_URL -o $WHEEL_FILE



sudo python3 -m venv /opt/CytoProcess_venv
sudo chmod +x /opt/CytoProcess_venv/bin/*
source /opt/CytoProcess_venv/bin/activate
PYTHON_EXECUTABLE=$(which python)
PYTHON_VERSION=$(python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
SITE_PACKAGES_PATH=$(python -c "import site; print(site.getsitepackages()[0])")

sudo /opt/CytoProcess_venv/bin/pip install "$WHEEL_FILE" 


sudo ln -s "$SITE_PACKAGES_PATH/CytoProcess/bin/Cyz2Json" /opt/CytoProcess_venv/bin/Cyz2Json
sudo ln -s "$SITE_PACKAGES_PATH/CytoProcess/pipeline.py" /opt/CytoProcess_venv/bin/pipeline.py
sudo ln -s "$SITE_PACKAGES_PATH/CytoProcess/convert.py" /opt/CytoProcess_venv/bin/convert.py
sudo ln -s "$SITE_PACKAGES_PATH/CytoProcess/main.py" /opt/CytoProcess_venv/bin/main.py

export LD_LIBRARY_PATH=/opt/CytoProcess_venv/lib/python${PYTHON_VERSION}/site-packages/CytoProcess/lib:${LD_LIBRARY_PATH}

sudo chmod ago+x /opt/CytoProcess_venv/lib/python${PYTHON_VERSION}/site-packages/CytoProcess/bin/*

desactivate


sudo tee /usr/local/bin/CytoProcess << 'EOF'
#!/bin/bash
source /opt/CytoProcess_venv/bin/activate
python /opt/CytoProcess_venv/bin/pipeline.py "$@"
deactivate
EOF

sudo chmod +x /usr/local/bin/CytoProcess

rm $WHEEL_FILE



echo "Installation completed successfully!"
exit 0

