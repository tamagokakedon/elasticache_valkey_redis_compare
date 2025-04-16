#!/bin/bash
# このスクリプトは、プロジェクト用の仮想環境を作成し、必要なライブラリをインストールします

# 現在のディレクトリを取得
PROJECT_DIR=$(pwd)

# 仮想環境を作成
echo "仮想環境を作成しています..."
python3 -m venv venv

# 仮想環境をアクティベート
echo "仮想環境をアクティベートしています..."
source venv/bin/activate

# 必要なライブラリをインストール
echo "必要なライブラリをインストールしています..."
pip install pandas numpy matplotlib seaborn jupyter ipykernel

# Jupyter Notebookのカーネルを設定
echo "Jupyterカーネルを設定しています..."
python -m ipykernel install --user --name=elasticache-benchmark --display-name="ElastiCache Benchmark"

# 仮想環境内でJupyter Notebookを起動するためのスクリプトを作成
cat > run_jupyter.sh << 'EOF'
#!/bin/bash
# 仮想環境をアクティベート
source venv/bin/activate

# Jupyter Notebookを起動
jupyter notebook --ip=0.0.0.0 --port=8888 --no-browser
EOF

# 実行権限を付与
chmod +x run_jupyter.sh

echo "セットアップが完了しました！"
echo "以下のコマンドでJupyter Notebookを起動できます："
echo "./run_jupyter.sh"
echo ""
echo "注意: EC2インスタンスでJupyter Notebookを実行する場合は、セキュリティグループで8888ポートを開放してください。"
