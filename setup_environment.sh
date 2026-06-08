#!/bin/bash
# ============================================================
# ArcGIS AI Assistant - Linux Environment Setup Script
# ============================================================
# Usage: bash setup_environment.sh [--full] [--pip-only] [--name ENV_NAME]
#
# Options:
#   --full       Full setup: create conda env + install all dependencies
#   --pip-only   Only install pip packages (requires existing conda env)
#   --name NAME  Conda environment name (default: arcgis_llm_linux)
#   --help       Show this help
# ============================================================

set -e  # Exit on error

# --- Defaults ---
ENV_NAME="arcgis_llm_linux"
MODE="full"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_CONFS_DIR="${PROJECT_DIR}/env_confs"

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# --- Parse arguments ---
while [[ $# -gt 0 ]]; do
    case "$1" in
        --full)       MODE="full"; shift ;;
        --pip-only)   MODE="pip-only"; shift ;;
        --name)       ENV_NAME="$2"; shift 2 ;;
        --help|-h)    head -30 "$0"; exit 0 ;;
        *) echo -e "${RED}Unknown option: $1${NC}"; head -30 "$0"; exit 1 ;;
    esac
done

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}  ArcGIS AI Assistant - Linux Setup${NC}"
echo -e "${BLUE}============================================${NC}"
echo -e "Mode: ${YELLOW}${MODE}${NC}"
echo -e "Environment name: ${YELLOW}${ENV_NAME}${NC}"
echo ""

# --- Check conda availability ---
check_conda() {
    if command -v conda &> /dev/null; then
        echo -e "${GREEN}[✓] Conda found:${NC} $(conda --version)"
        return 0
    elif [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
        echo -e "${YELLOW}[!] Conda not in PATH, sourcing from ~/miniconda3${NC}"
        source "$HOME/miniconda3/etc/profile.d/conda.sh"
        return 0
    elif [ -f "$HOME/anaconda3/etc/profile.d/conda.sh" ]; then
        echo -e "${YELLOW}[!] Conda not in PATH, sourcing from ~/anaconda3${NC}"
        source "$HOME/anaconda3/etc/profile.d/conda.sh"
        return 0
    elif [ -f "/opt/conda/etc/profile.d/conda.sh" ]; then
        echo -e "${YELLOW}[!] Conda not in PATH, sourcing from /opt/conda${NC}"
        source "/opt/conda/etc/profile.d/conda.sh"
        return 0
    else
        echo -e "${RED}[✗] Conda not found!${NC}"
        echo -e "Please install Miniconda first:"
        echo -e "  https://docs.conda.io/en/latest/miniconda.html"
        echo ""
        echo -e "Quick install (Linux x86_64):"
        echo -e "  wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh"
        echo -e "  bash Miniconda3-latest-Linux-x86_64.sh"
        exit 1
    fi
}

# --- Create conda environment from YAML ---
create_conda_env() {
    local yml_file="${ENV_CONFS_DIR}/environment_linux.yml"

    if [ ! -f "$yml_file" ]; then
        echo -e "${RED}[✗] Environment YAML not found: ${yml_file}${NC}"
        exit 1
    fi

    if conda env list | grep -q "^${ENV_NAME}\s"; then
        echo -e "${YELLOW}[!] Environment '${ENV_NAME}' already exists.${NC}"
        read -p "Remove and recreate? [y/N] " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo -e "${YELLOW}Removing existing environment...${NC}"
            conda env remove -n "$ENV_NAME" -y
        else
            echo -e "${YELLOW}Skipping environment creation. Using existing '${ENV_NAME}'.${NC}"
            return 0
        fi
    fi

    echo -e "${GREEN}[→] Creating conda environment '${ENV_NAME}'...${NC}"
    echo -e "    This may take 10-20 minutes depending on your network speed."
    echo ""

    conda env create -f "$yml_file" -n "$ENV_NAME"

    echo ""
    echo -e "${GREEN}[✓] Conda environment '${ENV_NAME}' created successfully!${NC}"
}

# --- Install pip packages ---
install_pip_packages() {
    local req_file="${ENV_CONFS_DIR}/requirements_linux.txt"

    if [ ! -f "$req_file" ]; then
        echo -e "${RED}[✗] Requirements file not found: ${req_file}${NC}"
        exit 1
    fi

    echo -e "${GREEN}[→] Installing pip packages...${NC}"
    echo "    This may take 5-10 minutes."

    pip install -r "$req_file"

    echo ""
    echo -e "${GREEN}[✓] Pip packages installed successfully!${NC}"
}

# --- Setup .env file ---
setup_env_file() {
    local env_template="${PROJECT_DIR}/.env.template"
    local env_file="${PROJECT_DIR}/.env"

    if [ ! -f "$env_template" ]; then
        echo -e "${YELLOW}[!] No .env.template found, skipping .env setup.${NC}"
        return 0
    fi

    if [ -f "$env_file" ]; then
        echo -e "${YELLOW}[!] .env file already exists.${NC}"
        read -p "Overwrite? [y/N] " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            cp "$env_template" "$env_file"
            echo -e "${GREEN}[✓] .env file overwritten from template.${NC}"
            echo -e "${YELLOW}[!] Please edit ${env_file} to add your API keys!${NC}"
        fi
    else
        cp "$env_template" "$env_file"
        echo -e "${GREEN}[✓] .env file created from template.${NC}"
        echo -e "${YELLOW}[!] Please edit ${env_file} to add your API keys!${NC}"
    fi
}

# --- Verify installation ---
verify_installation() {
    echo ""
    echo -e "${BLUE}----------------------------------------${NC}"
    echo -e "${BLUE}  Verifying Installation${NC}"
    echo -e "${BLUE}----------------------------------------${NC}"
    echo ""

    # Core Python + GIS
    echo -e "${YELLOW}Checking core packages...${NC}"
    python -c "
import sys
print(f'  Python: {sys.version}')

# Core GIS
try:
    import fiona; print(f'  fiona: OK')
except Exception as e: print(f'  fiona: FAIL ({e})')

try:
    import rasterio; print(f'  rasterio: OK')
except Exception as e: print(f'  rasterio: FAIL ({e})')

try:
    import geopandas; print(f'  geopandas: OK')
except Exception as e: print(f'  geopandas: FAIL ({e})')

try:
    import shapely; print(f'  shapely: OK')
except Exception as e: print(f'  shapely: FAIL ({e})')

try:
    import pyproj; print(f'  pyproj: OK')
except Exception as e: print(f'  pyproj: FAIL ({e})')

try:
    import gdal; print(f'  gdal: OK')
except Exception as e: print(f'  gdal: FAIL ({e})')

# Note: arcpy is Windows-only — this import will fail on Linux (expected)
try:
    import arcpy; print(f'  arcpy: OK (unexpected on Linux!)')
except ImportError: print(f'  arcpy: N/A (Windows-only, expected)')
except Exception as e: print(f'  arcpy: FAIL ({e})')
"

    echo ""
    echo -e "${YELLOW}Checking AI/LangChain packages...${NC}"
    python -c "
import langchain; print(f'  langchain: {langchain.__version__}')
import langchain_google_genai; print(f'  langchain-google-genai: OK')
import google.generativeai; print(f'  google-generativeai: OK')
import openai; print(f'  openai: {openai.__version__}')
import aiohttp; print(f'  aiohttp: OK')
import aiofiles; print(f'  aiofiles: OK')
import langgraph; print(f'  langgraph: OK')
"

    echo ""
    echo -e "${YELLOW}Checking ArcGIS API for Python...${NC}"
    python -c "
try:
    from arcgis.gis import GIS
    print('  arcgis (ArcGIS API for Python): OK')
except ImportError as e:
    print(f'  arcgis: FAIL ({e})')
except Exception as e:
    print(f'  arcgis: FAIL ({e})')
"
    echo ""
}

# ========================
# Main
# ========================

check_conda

case "$MODE" in
    full)
        create_conda_env
        echo ""
        echo -e "${GREEN}[→] Activating environment and installing pip packages...${NC}"
        # Use a subshell approach for conda activate
        eval "$(conda shell.bash hook)"
        conda activate "$ENV_NAME"
        install_pip_packages
        setup_env_file
        verify_installation
        ;;
    pip-only)
        echo -e "${YELLOW}[!] Skipping conda environment creation.${NC}"
        echo -e "${YELLOW}[!] Ensure environment '${ENV_NAME}' is active.${NC}"
        install_pip_packages
        verify_installation
        ;;
esac

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Setup Complete!${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo -e "To activate the environment:"
echo -e "  ${BLUE}conda activate ${ENV_NAME}${NC}"
echo ""
echo -e "To run the application:"
echo -e "  ${BLUE}cd ${PROJECT_DIR} && python main.py${NC}"
echo ""
echo -e "${YELLOW}⚠ Note: arcpy is Windows-only and will not work on Linux.${NC}"
echo -e "${YELLOW}  The AI chat + LangChain + ArcGIS API for Python features${NC}"
echo -e "${YELLOW}  will work. See Ideas.md for Linux adaptations.${NC}"
echo ""
