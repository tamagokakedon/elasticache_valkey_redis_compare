# AWS Elasticache Redis vs Valkey 性能比較

このプロジェクトは、AWS Elasticacheサービスにおける従来のRedisエンジンと新しいValkeyエンジンの性能差を客観的に検証し、様々なワークロードパターンに対する最適なエンジン選択の指針を提供することを目的としています。

## 概要

AWS Elasticacheは、クラウド環境でのインメモリキャッシュサービスとして広く利用されています。従来はRedisエンジンが主に使用されてきましたが、最近AWSはValkeyエンジンを導入しました。Valkeyは、Redisとの互換性を保ちながらも、パフォーマンスや効率性の向上を謳っています。

このプロジェクトでは、両エンジンの性能特性を客観的に比較し、ユーザーが自身のワークロードに最適なエンジンを選択するための判断材料を提供します。

## 検証範囲

1. **基本的なキー/バリュー操作**: GET/SET操作のスループットとレイテンシ
2. **データ構造操作**: 各種データ構造（リスト、ハッシュ、セット、ソート済みセット）の操作性能
3. **高負荷テスト**: 持続的な高負荷およびバースト負荷下での性能
4. **耐久性テスト**: 障害復旧とデータ永続化の性能への影響

## プロジェクト構成

```
elasticache_valkey_redis_compare/
├── cloudformation/                  # AWS環境構築用CloudFormationテンプレート
│   └── elasticache-benchmark-env.yaml  # ElastiCacheクラスター構築用テンプレート
├── config/                          # 設定ファイル
│   └── aws_endpoints.json           # AWS ElastiCacheエンドポイント設定
├── docs/                            # ドキュメント
│   └── test_plan.md                 # テスト計画書
├── memory-bank/                     # プロジェクト情報
│   ├── activeContext.md             # 現在の作業コンテキスト
│   ├── productContext.md            # 製品コンテキスト
│   ├── progress.md                  # 進捗状況
│   ├── projectbrief.md              # プロジェクト概要
│   ├── systemPatterns.md            # システムパターン
│   └── techContext.md               # 技術コンテキスト
├── results/                         # ベンチマーク結果
├── src/                             # ソースコード
│   ├── analyze_results.ipynb        # 結果分析用Jupyter Notebook
│   ├── aws_config.py                # AWS設定ファイル読み込みモジュール
│   ├── benchmarks/                  # ベンチマークスクリプト
│   │   ├── data_structure_benchmark.py  # データ構造操作ベンチマーク
│   │   └── simple_kv_benchmark.py       # キー/バリュー操作ベンチマーク
│   └── run_benchmarks.sh            # ベンチマーク実行スクリプト
└── README.md                        # このファイル
```

## 前提条件

### ローカル環境での実行

- Python 3.9以上
- 必要なPythonパッケージ: `redis`, `pandas`, `matplotlib`, `seaborn`, `numpy`, `jupyter`
- Docker（ローカルでValkeyを実行する場合）
- Redis（ローカルでRedisを実行する場合）

### AWS環境での実行

- AWSアカウント
- AWS CLI（設定済み）
- CloudFormationテンプレートをデプロイするための権限

## セットアップ

### 1. リポジトリのクローン

```bash
git clone https://github.com/yourusername/elasticache_valkey_redis_compare.git
cd elasticache_valkey_redis_compare
```

### 2. 必要なパッケージのインストール

```bash
pip install -r requirements.txt
```

### 3. AWS環境のセットアップ

CloudFormationテンプレートを使用して、AWS Elasticacheクラスター（RedisとValkey）を作成します。テンプレートは必要なVPCとサブネットも自動的に作成します。

```bash
aws cloudformation create-stack \
  --stack-name elasticache-benchmark \
  --template-body file://cloudformation/elasticache-benchmark-env.yaml \
  --parameters \
    ParameterKey=EC2KeyName,ParameterValue=your-key-pair \
    ParameterKey=VpcCidr,ParameterValue=10.0.0.0/16 \
    ParameterKey=PublicSubnet1Cidr,ParameterValue=10.0.1.0/24 \
    ParameterKey=PublicSubnet2Cidr,ParameterValue=10.0.2.0/24
```

または、AWS Management Consoleからテンプレートをアップロードしてスタックを作成することもできます。

**注意**: スタックの作成には約15〜20分かかります。ElastiCacheクラスターのプロビジョニングには時間がかかります。

### 4. 設定ファイルの作成

AWS Elasticacheエンドポイント情報を設定ファイルに保存します。

```bash
mkdir -p config
cat > config/aws_endpoints.json << EOF
{
  "redis": {
    "host": "your-redis-cluster-endpoint.amazonaws.com",
    "port": 6379
  },
  "valkey": {
    "host": "your-valkey-cluster-endpoint.amazonaws.com",
    "port": 6379
  }
}
EOF
```

## 使用方法

### AWS環境でのベンチマーク実行

AWS環境でベンチマークを実行するには、以下の手順に従います：

#### 1. EC2インスタンスへの接続

CloudFormationスタックのデプロイが完了したら、出力セクションに表示されるSSHコマンドを使用してEC2インスタンスに接続します：

```bash
# CloudFormationスタックの出力からSSHコマンドを取得
aws cloudformation describe-stacks --stack-name elasticache-benchmark --query "Stacks[0].Outputs[?OutputKey=='SSHCommand'].OutputValue" --output text

# 表示されたコマンドを実行（例）
ssh -i your-key-pair.pem ec2-user@ec2-xx-xx-xx-xx.compute-1.amazonaws.com
```

#### 2. プロジェクトコードの転送

EC2インスタンスにプロジェクトコードを転送する方法は2つあります：

**方法1: SCPを使用してローカルからコードを転送**

```bash
# プロジェクトディレクトリ全体を転送
scp -i your-key-pair.pem -r ./elasticache_valkey_redis_compare ec2-user@ec2-xx-xx-xx-xx.compute-1.amazonaws.com:~

# または必要なファイルのみを転送
scp -i your-key-pair.pem -r ./src ./config ./docs ec2-user@ec2-xx-xx-xx-xx.compute-1.amazonaws.com:~/elasticache_valkey_redis_compare/
```

**方法2: GitHubからクローン（EC2インスタンス上で実行）**

EC2インスタンスのUserDataスクリプトでは既にリポジトリのクローンを試みていますが、手動で行う場合：

```bash
# EC2インスタンス上で実行
cd ~
git clone https://github.com/yourusername/elasticache_valkey_redis_compare.git
cd elasticache_valkey_redis_compare
```

#### 3. 設定ファイルの確認

EC2インスタンス上で、AWS Elasticacheエンドポイント情報が正しく設定されているか確認します：

```bash
cat ~/elasticache_valkey_redis_compare/config/aws_endpoints.json
```

必要に応じて、CloudFormationスタックの出力から取得したエンドポイント情報で更新します：

```bash
# CloudFormationスタックの出力からエンドポイント情報を取得
REDIS_ENDPOINT=$(aws cloudformation describe-stacks --stack-name elasticache-benchmark --query "Stacks[0].Outputs[?OutputKey=='RedisEndpoint'].OutputValue" --output text)
VALKEY_ENDPOINT=$(aws cloudformation describe-stacks --stack-name elasticache-benchmark --query "Stacks[0].Outputs[?OutputKey=='ValkeyEndpoint'].OutputValue" --output text)

# エンドポイント情報をJSONファイルに書き込む
mkdir -p ~/elasticache_valkey_redis_compare/config
cat > ~/elasticache_valkey_redis_compare/config/aws_endpoints.json << EOF
{
  "redis": {
    "host": "$(echo $REDIS_ENDPOINT | cut -d: -f1)",
    "port": $(echo $REDIS_ENDPOINT | cut -d: -f2)
  },
  "valkey": {
    "host": "$(echo $VALKEY_ENDPOINT | cut -d: -f1)",
    "port": $(echo $VALKEY_ENDPOINT | cut -d: -f2)
  }
}
EOF
```

#### 4. ベンチマークの実行

EC2インスタンス上でベンチマークを実行します：

```bash
# 実行権限を付与
chmod +x ~/elasticache_valkey_redis_compare/src/run_benchmarks.sh

# 基本的な使用方法（AWS Elasticacheを使用）
cd ~/elasticache_valkey_redis_compare
./src/run_benchmarks.sh --aws

# キー/バリュー操作のみをテスト
./src/run_benchmarks.sh --aws -t kv

# データ構造操作のみをテスト
./src/run_benchmarks.sh --aws -t ds

# 特定のデータ構造（例：ハッシュ）のみをテスト
./src/run_benchmarks.sh --aws -t ds -d hash

# カスタムパラメータでテスト
./src/run_benchmarks.sh --aws -s 1024 -n 10000 -o 10000 -j 10

# 結果を比較
./src/run_benchmarks.sh --aws --compare
```

#### 5. 結果の取得

ベンチマーク結果をEC2インスタンスからローカルマシンに転送します：

```bash
# ローカルマシンで実行
mkdir -p ./results
scp -i your-key-pair.pem -r ec2-user@ec2-xx-xx-xx-xx.compute-1.amazonaws.com:~/elasticache_valkey_redis_compare/results/* ./results/
```

### 結果の分析

#### 仮想環境のセットアップ

プロジェクトフォルダ以外の環境を汚さないように、Python仮想環境（venv）を作成して必要なライブラリをインストールします：

```bash
# EC2インスタンス上で実行
cd ~/elasticache_valkey_redis_compare
chmod +x setup_jupyter_env.sh
./setup_jupyter_env.sh
```

このスクリプトは以下の処理を行います：
1. Python仮想環境（venv）を作成
2. 必要なライブラリ（pandas, numpy, matplotlib, seaborn, jupyter）をインストール
3. Jupyter Notebookのカーネルを設定
4. Jupyter Notebookを起動するためのスクリプトを作成

#### Jupyter Notebookの実行

セットアップ後、以下のコマンドでJupyter Notebookを起動できます：

```bash
# EC2インスタンス上で実行
cd ~/elasticache_valkey_redis_compare
./run_jupyter.sh
```

Jupyter Notebookが起動したら、表示されるURLをブラウザで開いてアクセスします。`src/analyze_results.ipynb`または`src/analyze_results_part2.ipynb`を開いて結果を分析できます。

**注意**: EC2インスタンス上でJupyter Notebookを実行する場合は、セキュリティグループで8888ポートを開放する必要があります。

#### ローカルマシンでの分析

結果ファイルをローカルマシンに転送した場合は、ローカル環境でJupyter Notebookを実行することもできます：

```bash
# ローカルマシンで実行（必要なライブラリがインストールされていることを確認）
jupyter notebook src/analyze_results.ipynb
```

## 主要なコマンドラインオプション

### run_benchmarks.sh

```
使用方法: ./src/run_benchmarks.sh [オプション]

オプション:
  -h, --help                このヘルプメッセージを表示
  --aws                     AWS Elasticacheモードを有効化（設定ファイルから接続情報を読み込み）
  -r, --redis-host HOST     Redisホスト (デフォルト: AWS設定またはlocalhost)
  -p, --redis-port PORT     Redisポート (デフォルト: AWS設定または6379)
  -v, --valkey-host HOST    Valkeyホスト (デフォルト: AWS設定またはlocalhost)
  -q, --valkey-port PORT    Valkeyポート (デフォルト: AWS設定または6380)
  -a, --password PASS       認証パスワード (デフォルト: なし)
  -t, --test TYPE           実行するテストタイプ (kv, ds, all) (デフォルト: all)
                            kv: キー/バリュー操作のみ
                            ds: データ構造操作のみ
                            all: すべてのテスト
  -s, --size SIZE           値のサイズ (デフォルト: 1024)
  -n, --num-keys NUM        キー数 (デフォルト: 10000)
  -o, --operations NUM      スレッドあたりの操作数 (デフォルト: 10000)
  -j, --threads NUM         スレッド数 (デフォルト: 10)
  -d, --data-structure TYPE テスト対象のデータ構造 (string, list, hash, set, zset, all) (デフォルト: all)
  -e, --elements NUM        データ構造あたりの要素数 (デフォルト: 100)
  -c, --compare             結果の比較を表示
```

### run_migration_monitor.sh

```
使用方法: ./src/run_migration_monitor.sh [オプション]

オプション:
  -h, --help                このヘルプメッセージを表示
  -c, --cluster-id ID       モニタリング対象のElasticacheクラスターID (必須)
  -r, --region REGION       AWSリージョン (デフォルト: ap-northeast-1)
  --host HOST               Redisサーバーのホスト名 (指定しない場合はクラスターIDから自動取得)
  --port PORT               Redisサーバーのポート番号 (指定しない場合はデフォルト6379)
  --password PASS           Redisサーバーの認証パスワード (必要な場合)
  -o, --output-dir DIR      結果の出力ディレクトリ (デフォルト: ../results/migration)
  -t, --test-interval SEC   読み書きテストの間隔（秒） (デフォルト: 0.1)
  -m, --monitor-interval SEC CloudWatchメトリクスの取得間隔（秒） (デフォルト: 60)
```

## 結果の解釈

ベンチマーク結果は以下の指標を含みます：

1. **スループット**: 1秒あたりの操作数（ops/sec）
2. **レイテンシ**: 操作あたりの実行時間（ミリ秒）
   - 平均レイテンシ
   - 中央値レイテンシ
   - 95パーセンタイルレイテンシ
   - 99パーセンタイルレイテンシ
3. **エラー率**: 失敗した操作の割合

これらの指標を使用して、RedisとValkeyの性能を比較し、特定のワークロードパターンに対する最適なエンジン選択を判断できます。

## 貢献

プロジェクトへの貢献は大歓迎です。以下の方法で貢献できます：

1. バグの報告
2. 新機能の提案
3. コードの改善
4. ドキュメントの改善

## ライセンス

このプロジェクトはMITライセンスの下で公開されています。詳細はLICENSEファイルを参照してください。
