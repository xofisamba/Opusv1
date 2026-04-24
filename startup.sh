#!/bin/bash
# Startup script for OpusCorev1
# Usage: ./startup.sh [streamlit args...]
# Example: ./startup.sh --server.port=8517 --server.address=0.0.0.0

export PYTHONPATH="${PYTHONPATH}:$(pwd)"
streamlit run src/app.py "$@"
