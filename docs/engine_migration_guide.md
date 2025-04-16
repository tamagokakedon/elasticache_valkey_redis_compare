# AWS Elasticache エンジン変更（Redis → Valkey）モニタリングガイド

このドキュメントでは、AWS Elasticacheのエンジン変更（RedisからValkey）時に、読み書きの切断やパフォーマンス低下を検証するためのモニタリング方法について説明します。

## 概要

AWS Elasticacheでは、RedisエンジンからValkeyエンジンへの変更が可能になりました。この変更は、クラスターの再起動を伴わずに行われるとされていますが、実際の運用環境では以下の点を検証することが重要です：

1. **接続の切断有無**: エンジン変更中にクライアント接続が切断されるかどうか
2. **パフォーマンスへの影響**: 変更前後でレイテンシやスループットに変化があるかどうか
3. **CloudWatchメトリクス**: CPU使用率、メモリ使用量、接続数などの変化

このプロジェクトでは、これらの点を検証するためのモニタリングツールを提供しています。

## 前提条件

- AWS CLI がインストールされ、適切な権限で設定されていること
- Python 3.6以上がインストールされていること
- 以下のPythonパッケージがインストールされていること:
  - boto3
  - redis
  - pandas
  - numpy
  - matplotlib
  - seaborn

## モニタリングツールの使用方法

### 1. 実行権限の付与

```bash
chmod +x src/run_migration_monitor.sh
```

### 2. モニタリングの開始

クラスターIDを指定してモニタリングを開始します：

```bash
./src/run_migration_monitor.sh --cluster-id your-elasticache-cluster-id
```

または、ホスト名とポートを直接指定することもできます：

```bash
./src/run_migration_monitor.sh --host your-elasticache-endpoint.amazonaws.com --port 6379
```

### 3. AWS コンソールでのエンジン変更

モニタリングを開始した後、AWS Management Consoleにログインし、以下の手順でエンジン変更を行います：

1. Elasticacheダッシュボードを開く
2. 対象のクラスターを選択
3. 「アクション」→「変更」を選択
4. 「エンジンバージョンの互換性」セクションで「Valkey」を選択
5. 「変更をすぐに適用」を選択
6. 「変更を適用」をクリック

### 4. モニタリングの終了

エンジン変更が完了し、十分なデータが収集できたら、`Ctrl+C`でモニタリングを終了します。終了時に自動的に結果が保存され、レポートが生成されます。

## 出力ファイル

モニタリングツールは以下のファイルを生成します（デフォルトでは`results/migration`ディレクトリに保存）：

- `latency_YYYYMMDD_HHMMSS.json`: 読み書きレイテンシのデータ
- `connection_YYYYMMDD_HHMMSS.json`: 接続状態のデータ
- `cloudwatch_YYYYMMDD_HHMMSS.json`: CloudWatchメトリクスのデータ
- `report_YYYYMMDD_HHMMSS.md`: 分析レポート（Markdown形式）
- `latency_graph_YYYYMMDD_HHMMSS.png`: レイテンシの時系列グラフ
- `connection_status_YYYYMMDD_HHMMSS.png`: 接続状態のヒートマップ

## レポートの解釈

生成されるレポートには以下の情報が含まれます：

### 接続状態

- 総テスト回数
- 接続成功率
- 切断イベントの詳細（発生時刻、期間）

### レイテンシ統計

- 読み取り/書き込みレイテンシの最小値、最大値、平均値、中央値、95パーセンタイル、99パーセンタイル

### 結論

- 切断の有無と期間
- レイテンシの変化（前半と後半の比較）

## 詳細なオプション

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

## 注意事項

- モニタリングツールは、テスト用のキー/バリューペアを継続的に書き込みます。本番環境で使用する場合は、`--key-prefix`オプションで適切なプレフィックスを設定してください。
- CloudWatchメトリクスの取得には、適切なIAM権限が必要です。
- 長時間のモニタリングを行う場合は、`--test-interval`の値を大きくして、Elasticacheへの負荷を軽減することを検討してください。

## トラブルシューティング

### 接続エラー

```
接続テスト中にエラーが発生しました: Error 111 connecting to your-endpoint.amazonaws.com:6379. Connection refused
```

- エンドポイントとポートが正しいか確認してください
- セキュリティグループの設定を確認してください
- VPC内からアクセスしている場合は、適切なサブネットにいることを確認してください

### 権限エラー

```
CloudWatchモニタリング中にエラーが発生しました: An error occurred (AccessDenied) when calling the GetMetricData operation: User is not authorized to perform cloudwatch:GetMetricData
```

- AWS CLIの設定を確認し、適切な権限を持つIAMユーザーまたはロールを使用してください
- 必要なIAM権限: `cloudwatch:GetMetricData`, `elasticache:DescribeReplicationGroups`

## まとめ

このモニタリングツールを使用することで、AWS ElasticacheのRedisからValkeyへのエンジン変更時の影響を客観的に評価できます。特に、接続の切断有無とパフォーマンスへの影響を詳細に分析することで、本番環境での変更計画に役立てることができます。
