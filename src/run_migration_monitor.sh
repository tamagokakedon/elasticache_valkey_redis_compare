#!/bin/bash
# AWS Elasticache エンジン変更モニタリングツールの実行スクリプト

# 実行権限の確認
if [ ! -x "$(command -v python3)" ]; then
  echo "エラー: python3 が見つかりません。Python 3 をインストールしてください。"
  exit 1
fi

# 必要なライブラリの確認
REQUIRED_PACKAGES="boto3 redis pandas numpy matplotlib seaborn"
MISSING_PACKAGES=""

for package in $REQUIRED_PACKAGES; do
  if ! python3 -c "import $package" &> /dev/null; then
    if [ -z "$MISSING_PACKAGES" ]; then
      MISSING_PACKAGES="$package"
    else
      MISSING_PACKAGES="$MISSING_PACKAGES $package"
    fi
  fi
done

if [ ! -z "$MISSING_PACKAGES" ]; then
  echo "必要なPythonパッケージがインストールされていません: $MISSING_PACKAGES"
  read -p "これらのパッケージをインストールしますか？ (y/n): " -n 1 -r
  echo
  if [[ $REPLY =~ ^[Yy]$ ]]; then
    pip install $MISSING_PACKAGES
  else
    echo "パッケージのインストールをスキップします。スクリプトが正常に動作しない可能性があります。"
  fi
fi

# 引数の処理
CLUSTER_ID=""
REGION="ap-northeast-1"
HOST=""
PORT=""
PASSWORD=""
OUTPUT_DIR="../results/migration"
TEST_INTERVAL="0.1"
MONITORING_INTERVAL="60"

# ヘルプメッセージ
function show_help {
  echo "使用方法: $0 [オプション]"
  echo ""
  echo "オプション:"
  echo "  -h, --help                このヘルプメッセージを表示"
  echo "  -c, --cluster-id ID       モニタリング対象のElasticacheクラスターID (必須)"
  echo "  -r, --region REGION       AWSリージョン (デフォルト: ap-northeast-1)"
  echo "  --host HOST               Redisサーバーのホスト名 (指定しない場合はクラスターIDから自動取得)"
  echo "  --port PORT               Redisサーバーのポート番号 (指定しない場合はデフォルト6379)"
  echo "  --password PASS           Redisサーバーの認証パスワード (必要な場合)"
  echo "  -o, --output-dir DIR      結果の出力ディレクトリ (デフォルト: ../results/migration)"
  echo "  -t, --test-interval SEC   読み書きテストの間隔（秒） (デフォルト: 0.1)"
  echo "  -m, --monitor-interval SEC CloudWatchメトリクスの取得間隔（秒） (デフォルト: 60)"
  echo ""
  echo "例:"
  echo "  $0 --cluster-id my-redis-cluster"
  echo "  $0 --cluster-id my-redis-cluster --region us-west-2"
  echo "  $0 --host my-redis.example.com --port 6379"
  exit 1
}

# 引数のパース
while [[ $# -gt 0 ]]; do
  case $1 in
    -h|--help)
      show_help
      ;;
    -c|--cluster-id)
      CLUSTER_ID="$2"
      shift 2
      ;;
    -r|--region)
      REGION="$2"
      shift 2
      ;;
    --host)
      HOST="$2"
      shift 2
      ;;
    --port)
      PORT="$2"
      shift 2
      ;;
    --password)
      PASSWORD="$2"
      shift 2
      ;;
    -o|--output-dir)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    -t|--test-interval)
      TEST_INTERVAL="$2"
      shift 2
      ;;
    -m|--monitor-interval)
      MONITORING_INTERVAL="$2"
      shift 2
      ;;
    *)
      echo "不明なオプション: $1"
      show_help
      ;;
  esac
done

# クラスターIDまたはホスト名が指定されているか確認
if [ -z "$CLUSTER_ID" ] && [ -z "$HOST" ]; then
  echo "エラー: クラスターID (--cluster-id) またはホスト名 (--host) を指定してください。"
  show_help
fi

# コマンドの構築
CMD="python3 monitor_engine_migration.py"

if [ ! -z "$CLUSTER_ID" ]; then
  CMD="$CMD --cluster-id $CLUSTER_ID"
fi

if [ ! -z "$REGION" ]; then
  CMD="$CMD --region $REGION"
fi

if [ ! -z "$HOST" ]; then
  CMD="$CMD --host $HOST"
fi

if [ ! -z "$PORT" ]; then
  CMD="$CMD --port $PORT"
fi

if [ ! -z "$PASSWORD" ]; then
  CMD="$CMD --password $PASSWORD"
fi

if [ ! -z "$OUTPUT_DIR" ]; then
  CMD="$CMD --output-dir $OUTPUT_DIR"
fi

if [ ! -z "$TEST_INTERVAL" ]; then
  CMD="$CMD --test-interval $TEST_INTERVAL"
fi

if [ ! -z "$MONITORING_INTERVAL" ]; then
  CMD="$CMD --monitoring-interval $MONITORING_INTERVAL"
fi

# スクリプトの実行
echo "モニタリングを開始します..."
echo "コマンド: $CMD"
echo "Ctrl+C で終了します。"
echo ""

cd "$(dirname "$0")"
eval $CMD
