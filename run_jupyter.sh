#!/bin/bash
# 仮想環境をアクティベート
source venv/bin/activate

# Jupyter Notebookを起動
jupyter notebook --ip=0.0.0.0 --port=8888 --no-browser
