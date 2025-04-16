#!/bin/bash

# AWS Elasticache Redis vs Valkey 性能比較ベンチマーク実行スクリプト
# このスクリプトは、RedisとValkeyの両方に対してベンチマークを実行し、結果を比較します。

# 色の定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 設定
# AWS Elasticacheエンドポイントの設定ファイルを確認
CONFIG_FILE="./config/aws_endpoints.json"
if [ -f "$CONFIG_FILE" ]; then
    echo "AWS Elasticacheエンドポイント設定ファイルを使用します: $CONFIG_FILE"
    REDIS_HOST=$(jq -r '.redis.host' "$CONFIG_FILE")
    REDIS_PORT=$(jq -r '.redis.port' "$CONFIG_FILE")
    VALKEY_HOST=$(jq -r '.valkey.host' "$CONFIG_FILE")
    VALKEY_PORT=$(jq -r '.valkey.port' "$CONFIG_FILE")
else
    echo "AWS Elasticacheエンドポイント設定ファイルが見つかりません。環境変数またはデフォルト値を使用します。"
    REDIS_HOST=${REDIS_HOST:-"localhost"}
    REDIS_PORT=${REDIS_PORT:-6379}
    VALKEY_HOST=${VALKEY_HOST:-"localhost"}
    VALKEY_PORT=${VALKEY_PORT:-6380}
fi

PASSWORD=${REDIS_PASSWORD:-""}
RESULTS_DIR="./results"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# AWS Elasticacheモードフラグ
AWS_MODE=false

# 必要なディレクトリを作成
mkdir -p ${RESULTS_DIR}

# ヘルプメッセージ
function show_help {
    echo -e "${BLUE}AWS Elasticache Redis vs Valkey 性能比較ベンチマーク実行スクリプト${NC}"
    echo ""
    echo "使用方法: $0 [オプション]"
    echo ""
    echo "オプション:"
    echo "  -h, --help                このヘルプメッセージを表示"
    echo "  --aws                     AWS Elasticacheモードを有効化（設定ファイルから接続情報を読み込み）"
    echo "  -r, --redis-host HOST     Redisホスト (デフォルト: localhost または設定ファイルの値)"
    echo "  -p, --redis-port PORT     Redisポート (デフォルト: 6379 または設定ファイルの値)"
    echo "  -v, --valkey-host HOST    Valkeyホスト (デフォルト: localhost または設定ファイルの値)"
    echo "  -q, --valkey-port PORT    Valkeyポート (デフォルト: 6380 または設定ファイルの値)"
    echo "  -a, --password PASS       認証パスワード (デフォルト: なし)"
    echo "  -t, --test TYPE           実行するテストタイプ (kv, ds, all) (デフォルト: all)"
    echo "                            kv: キー/バリュー操作のみ"
    echo "                            ds: データ構造操作のみ"
    echo "                            all: すべてのテスト"
    echo "  -s, --size SIZE           値のサイズ (デフォルト: 1024)"
    echo "  -n, --num-keys NUM        キー数 (デフォルト: 10000)"
    echo "  -o, --operations NUM      スレッドあたりの操作数 (デフォルト: 10000)"
    echo "  -j, --threads NUM         スレッド数 (デフォルト: 10)"
    echo "  -d, --data-structure TYPE テスト対象のデータ構造 (string, list, hash, set, zset, all) (デフォルト: all)"
    echo "  -e, --elements NUM        データ構造あたりの要素数 (デフォルト: 100)"
    echo "  -c, --compare             結果の比較を表示"
    echo ""
    echo "環境変数:"
    echo "  REDIS_HOST                Redisホスト"
    echo "  REDIS_PORT                Redisポート"
    echo "  VALKEY_HOST               Valkeyホスト"
    echo "  VALKEY_PORT               Valkeyポート"
    echo "  REDIS_PASSWORD            認証パスワード"
    echo ""
    echo "例:"
    echo "  $0 -t kv -s 1024 -n 10000 -o 10000 -j 10"
    echo "  $0 -t ds -d hash -e 1000 -n 1000 -o 5000 -j 8"
    echo "  $0 -r redis.example.com -p 6379 -v valkey.example.com -q 6380 -a mypassword"
    echo ""
}

# コマンドライン引数の解析
TEST_TYPE="all"
VALUE_SIZE=1024
NUM_KEYS=10000
OPERATIONS=10000
THREADS=10
DATA_STRUCTURE="all"
ELEMENTS=100
COMPARE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        --aws)
            AWS_MODE=true
            shift
            ;;
        -r|--redis-host)
            REDIS_HOST="$2"
            shift 2
            ;;
        -p|--redis-port)
            REDIS_PORT="$2"
            shift 2
            ;;
        -v|--valkey-host)
            VALKEY_HOST="$2"
            shift 2
            ;;
        -q|--valkey-port)
            VALKEY_PORT="$2"
            shift 2
            ;;
        -a|--password)
            PASSWORD="$2"
            shift 2
            ;;
        -t|--test)
            TEST_TYPE="$2"
            shift 2
            ;;
        -s|--size)
            VALUE_SIZE="$2"
            shift 2
            ;;
        -n|--num-keys)
            NUM_KEYS="$2"
            shift 2
            ;;
        -o|--operations)
            OPERATIONS="$2"
            shift 2
            ;;
        -j|--threads)
            THREADS="$2"
            shift 2
            ;;
        -d|--data-structure)
            DATA_STRUCTURE="$2"
            shift 2
            ;;
        -e|--elements)
            ELEMENTS="$2"
            shift 2
            ;;
        -c|--compare)
            COMPARE=true
            shift
            ;;
        *)
            echo "不明なオプション: $1"
            show_help
            exit 1
            ;;
    esac
done

# パスワードオプションの設定
PASSWORD_OPT=""
if [ ! -z "$PASSWORD" ]; then
    PASSWORD_OPT="--password $PASSWORD"
fi

# 結果ファイル名の設定
KV_REDIS_RESULT="${RESULTS_DIR}/kv_redis_${TIMESTAMP}.json"
KV_VALKEY_RESULT="${RESULTS_DIR}/kv_valkey_${TIMESTAMP}.json"
DS_REDIS_RESULT="${RESULTS_DIR}/ds_redis_${TIMESTAMP}.json"
DS_VALKEY_RESULT="${RESULTS_DIR}/ds_valkey_${TIMESTAMP}.json"

# ベンチマーク実行関数
function run_kv_benchmark {
    engine=$1
    host=$2
    port=$3
    output=$4
    
    echo -e "${YELLOW}キー/バリュー操作ベンチマーク実行中 (${engine})...${NC}"
    python3 src/benchmarks/simple_kv_benchmark.py \
        --engine ${engine} \
        --host ${host} \
        --port ${port} \
        ${PASSWORD_OPT} \
        --value-size ${VALUE_SIZE} \
        --num-keys ${NUM_KEYS} \
        --operations ${OPERATIONS} \
        --num-threads ${THREADS} \
        --output ${output}
    
    echo -e "${GREEN}結果を ${output} に保存しました${NC}"
    echo ""
}

function run_ds_benchmark {
    engine=$1
    host=$2
    port=$3
    output=$4
    
    echo -e "${YELLOW}データ構造操作ベンチマーク実行中 (${engine})...${NC}"
    python3 src/benchmarks/data_structure_benchmark.py \
        --engine ${engine} \
        --host ${host} \
        --port ${port} \
        ${PASSWORD_OPT} \
        --data-structure ${DATA_STRUCTURE} \
        --element-size ${VALUE_SIZE} \
        --num-keys ${NUM_KEYS} \
        --operations ${OPERATIONS} \
        --num-threads ${THREADS} \
        --elements ${ELEMENTS} \
        --output ${output}
    
    echo -e "${GREEN}結果を ${output} に保存しました${NC}"
    echo ""
}

# 結果比較関数
function compare_results {
    redis_file=$1
    valkey_file=$2
    test_type=$3
    
    echo -e "${BLUE}===== ${test_type} ベンチマーク結果比較 =====${NC}"
    
    # jqがインストールされているか確認
    if ! command -v jq &> /dev/null; then
        echo -e "${RED}jqがインストールされていません。結果の比較にはjqが必要です。${NC}"
        echo "インストール方法: apt-get install jq または brew install jq"
        return
    fi
    
    # 結果ファイルが存在するか確認
    if [ ! -f "$redis_file" ] || [ ! -f "$valkey_file" ]; then
        echo -e "${RED}結果ファイルが見つかりません。${NC}"
        return
    fi
    
    # 基本的な統計情報を抽出
    redis_ops=$(jq '.stats.operations_per_sec' $redis_file)
    valkey_ops=$(jq '.stats.operations_per_sec' $valkey_file)
    redis_avg=$(jq '.stats.all_stats.avg' $redis_file)
    valkey_avg=$(jq '.stats.all_stats.avg' $valkey_file)
    redis_p95=$(jq '.stats.all_stats.p95' $redis_file)
    valkey_p95=$(jq '.stats.all_stats.p95' $valkey_file)
    
    # パフォーマンス差の計算
    ops_diff=$(echo "scale=2; ($valkey_ops - $redis_ops) / $redis_ops * 100" | bc)
    latency_diff=$(echo "scale=2; ($redis_avg - $valkey_avg) / $redis_avg * 100" | bc)
    
    echo -e "${CYAN}スループット (ops/sec):${NC}"
    echo -e "  Redis:  ${redis_ops}"
    echo -e "  Valkey: ${valkey_ops}"
    echo -e "  差異:   ${ops_diff}% (正の値はValkeyが高速)"
    echo ""
    
    echo -e "${CYAN}平均レイテンシ (ms):${NC}"
    echo -e "  Redis:  ${redis_avg}"
    echo -e "  Valkey: ${valkey_avg}"
    echo -e "  差異:   ${latency_diff}% (正の値はValkeyが低レイテンシ)"
    echo ""
    
    echo -e "${CYAN}95パーセンタイルレイテンシ (ms):${NC}"
    echo -e "  Redis:  ${redis_p95}"
    echo -e "  Valkey: ${valkey_p95}"
    echo ""
    
    # データ構造別の統計（データ構造ベンチマークの場合）
    if [ "$test_type" = "データ構造" ] && [ -f "$redis_file" ] && [ -f "$valkey_file" ]; then
        echo -e "${CYAN}データ構造別のパフォーマンス:${NC}"
        
        # データ構造タイプを取得
        ds_types=$(jq -r '.stats.structure_stats | keys[]' $redis_file 2>/dev/null)
        
        for ds_type in $ds_types; do
            echo -e "${PURPLE}$ds_type:${NC}"
            
            # Redisの統計
            redis_ds_ops=$(jq ".stats.structure_stats.\"$ds_type\".throughput" $redis_file 2>/dev/null)
            redis_ds_avg=$(jq ".stats.structure_stats.\"$ds_type\".avg" $redis_file 2>/dev/null)
            
            # Valkeyの統計
            valkey_ds_ops=$(jq ".stats.structure_stats.\"$ds_type\".throughput" $valkey_file 2>/dev/null)
            valkey_ds_avg=$(jq ".stats.structure_stats.\"$ds_type\".avg" $valkey_file 2>/dev/null)
            
            # 差異の計算
            if [ "$redis_ds_ops" != "null" ] && [ "$valkey_ds_ops" != "null" ]; then
                ds_ops_diff=$(echo "scale=2; ($valkey_ds_ops - $redis_ds_ops) / $redis_ds_ops * 100" | bc)
                ds_latency_diff=$(echo "scale=2; ($redis_ds_avg - $valkey_ds_avg) / $redis_ds_avg * 100" | bc)
                
                echo -e "  スループット (ops/sec):"
                echo -e "    Redis:  ${redis_ds_ops}"
                echo -e "    Valkey: ${valkey_ds_ops}"
                echo -e "    差異:   ${ds_ops_diff}% (正の値はValkeyが高速)"
                
                echo -e "  平均レイテンシ (ms):"
                echo -e "    Redis:  ${redis_ds_avg}"
                echo -e "    Valkey: ${valkey_ds_avg}"
                echo -e "    差異:   ${ds_latency_diff}% (正の値はValkeyが低レイテンシ)"
                echo ""
            fi
        done
    fi
}

# メイン処理
echo -e "${BLUE}===== AWS Elasticache Redis vs Valkey 性能比較ベンチマーク =====${NC}"
echo ""
echo -e "${CYAN}設定:${NC}"
if [ "$AWS_MODE" = true ]; then
    echo "モード = AWS Elasticache"
else
    echo "モード = スタンドアロン"
fi
echo "Redis ホスト:ポート = ${REDIS_HOST}:${REDIS_PORT}"
echo "Valkey ホスト:ポート = ${VALKEY_HOST}:${VALKEY_PORT}"
echo "テストタイプ = ${TEST_TYPE}"
echo "値サイズ = ${VALUE_SIZE} バイト"
echo "キー数 = ${NUM_KEYS}"
echo "スレッドあたりの操作数 = ${OPERATIONS}"
echo "スレッド数 = ${THREADS}"
if [ "$TEST_TYPE" = "ds" ] || [ "$TEST_TYPE" = "all" ]; then
    echo "データ構造 = ${DATA_STRUCTURE}"
    echo "要素数 = ${ELEMENTS}"
fi
echo ""

# ベンチマーク実行
if [ "$TEST_TYPE" = "kv" ] || [ "$TEST_TYPE" = "all" ]; then
    run_kv_benchmark "redis" "${REDIS_HOST}" "${REDIS_PORT}" "${KV_REDIS_RESULT}"
    run_kv_benchmark "valkey" "${VALKEY_HOST}" "${VALKEY_PORT}" "${KV_VALKEY_RESULT}"
    
    if [ "$COMPARE" = true ]; then
        compare_results "${KV_REDIS_RESULT}" "${KV_VALKEY_RESULT}" "キー/バリュー"
    fi
fi

if [ "$TEST_TYPE" = "ds" ] || [ "$TEST_TYPE" = "all" ]; then
    run_ds_benchmark "redis" "${REDIS_HOST}" "${REDIS_PORT}" "${DS_REDIS_RESULT}"
    run_ds_benchmark "valkey" "${VALKEY_HOST}" "${VALKEY_PORT}" "${DS_VALKEY_RESULT}"
    
    if [ "$COMPARE" = true ]; then
        compare_results "${DS_REDIS_RESULT}" "${DS_VALKEY_RESULT}" "データ構造"
    fi
fi

echo -e "${GREEN}ベンチマーク完了！${NC}"
echo -e "結果は ${RESULTS_DIR} ディレクトリに保存されています。"
echo ""
echo -e "${YELLOW}結果を比較するには:${NC}"
echo "$0 --compare -t kv"
echo "$0 --compare -t ds"
echo "$0 --compare -t all"
