#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AWS Elasticache Redis から Valkey へのエンジン変更時のモニタリングと解析

このスクリプトは、AWS Elasticacheのエンジン変更（RedisからValkey）時に、
読み書きの切断やパフォーマンス低下を検証するためのモニタリングと解析を行います。
"""

import os
import sys
import time
import json
import argparse
import datetime
import threading
import concurrent.futures
import signal
import queue
import statistics
from typing import Dict, List, Any, Optional, Tuple

import boto3
import redis
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from botocore.exceptions import ClientError

# AWS設定モジュールのインポート
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from aws_config import get_endpoint
except ImportError:
    # aws_config.pyが見つからない場合のフォールバック関数
    def get_endpoint(engine_type: str) -> Dict[str, Any]:
        return {
            "host": "localhost",
            "port": 6379 if engine_type.lower() == "redis" else 6380
        }


class ElasticacheMigrationMonitor:
    """Elasticacheエンジン変更時のモニタリングを行うクラス"""
    
    def __init__(self, 
                 cluster_id: str,
                 region: str = 'ap-northeast-1',
                 host: Optional[str] = None,
                 port: Optional[int] = None,
                 password: Optional[str] = None,
                 db: int = 0,
                 key_prefix: str = 'migration-test:',
                 monitoring_interval: int = 1,
                 test_interval: float = 0.1,
                 value_size: int = 1024,
                 num_keys: int = 1000,
                 output_dir: str = '../results/migration'):
        """
        Args:
            cluster_id: ElasticacheクラスターID
            region: AWSリージョン
            host: Redisサーバーのホスト名（指定しない場合はクラスターIDから自動取得）
            port: Redisサーバーのポート番号（指定しない場合はデフォルト6379）
            password: 認証パスワード（必要な場合）
            db: 使用するデータベース番号
            key_prefix: テストで使用するキーのプレフィックス
            monitoring_interval: CloudWatchメトリクスの取得間隔（秒）
            test_interval: 読み書きテストの間隔（秒）
            value_size: テスト値のサイズ（バイト）
            num_keys: テストで使用するキーの数
            output_dir: 結果の出力ディレクトリ
        """
        self.cluster_id = cluster_id
        self.region = region
        self.password = password
        self.db = db
        self.key_prefix = key_prefix
        self.monitoring_interval = monitoring_interval
        self.test_interval = test_interval
        self.value_size = value_size
        self.num_keys = num_keys
        self.output_dir = output_dir
        
        # AWSクライアントの初期化
        self.cloudwatch = boto3.client('cloudwatch', region_name=region)
        self.elasticache = boto3.client('elasticache', region_name=region)
        
        # ホストとポートの設定
        if host is None or port is None:
            # クラスターIDからエンドポイント情報を取得
            cluster_info = self._get_cluster_info()
            if cluster_info:
                self.host = cluster_info.get('host', 'localhost')
                self.port = cluster_info.get('port', 6379)
            else:
                self.host = 'localhost'
                self.port = 6379
        else:
            self.host = host
            self.port = port
        
        # Redisクライアントの初期化
        self.client = self._create_client()
        
        # モニタリング結果の保存用
        self.cloudwatch_metrics = []
        self.latency_metrics = []
        self.connection_status = []
        
        # 実行制御用
        self.running = False
        self.monitoring_thread = None
        self.test_thread = None
        self.metrics_queue = queue.Queue()
        
        # 出力ディレクトリの作成
        os.makedirs(self.output_dir, exist_ok=True)
    
    def _create_client(self) -> redis.Redis:
        """Redisクライアントを作成する"""
        return redis.Redis(
            host=self.host,
            port=self.port,
            password=self.password,
            db=self.db,
            socket_timeout=5.0,  # タイムアウト設定
            socket_connect_timeout=5.0,
            socket_keepalive=True,
            retry_on_timeout=True,
            decode_responses=True
        )
    
    def _get_cluster_info(self) -> Dict[str, Any]:
        """Elasticacheクラスターのエンドポイントとポートを取得する"""
        try:
            response = self.elasticache.describe_replication_groups(
                ReplicationGroupId=self.cluster_id
            )
            
            if 'ReplicationGroups' in response and response['ReplicationGroups']:
                group = response['ReplicationGroups'][0]
                
                # プライマリエンドポイントを取得
                if 'NodeGroups' in group and group['NodeGroups']:
                    primary_endpoint = group['NodeGroups'][0].get('PrimaryEndpoint', {})
                    return {
                        'host': primary_endpoint.get('Address'),
                        'port': primary_endpoint.get('Port', 6379)
                    }
            
            print(f"警告: クラスター {self.cluster_id} の情報を取得できませんでした。")
            return {}
            
        except ClientError as e:
            print(f"エラー: クラスター情報の取得に失敗しました: {e}")
            return {}
    
    def _generate_test_value(self, size: int) -> str:
        """テスト用の値を生成する"""
        pattern = "abcdefghij"
        repeats = size // len(pattern) + 1
        return (pattern * repeats)[:size]
    
    def _get_cloudwatch_metrics(self) -> List[Dict[str, Any]]:
        """CloudWatchからElasticacheメトリクスを取得する"""
        end_time = datetime.datetime.utcnow()
        start_time = end_time - datetime.timedelta(minutes=5)
        
        metrics = []
        
        # 取得するメトリクス
        metric_names = [
            'CurrConnections',
            'NewConnections',
            'BytesUsedForCache',
            'CacheHits',
            'CacheMisses',
            'CPUUtilization',
            'NetworkBytesIn',
            'NetworkBytesOut',
            'EngineCPUUtilization',
            'ReplicationLag',
            'CommandLatency'
        ]
        
        for metric_name in metric_names:
            try:
                response = self.cloudwatch.get_metric_data(
                    MetricDataQueries=[
                        {
                            'Id': 'metric',
                            'MetricStat': {
                                'Metric': {
                                    'Namespace': 'AWS/ElastiCache',
                                    'MetricName': metric_name,
                                    'Dimensions': [
                                        {
                                            'Name': 'ReplicationGroupId',
                                            'Value': self.cluster_id
                                        }
                                    ]
                                },
                                'Period': 60,
                                'Stat': 'Average'
                            },
                            'ReturnData': True
                        }
                    ],
                    StartTime=start_time,
                    EndTime=end_time
                )
                
                if 'MetricDataResults' in response and response['MetricDataResults']:
                    result = response['MetricDataResults'][0]
                    if result['Values']:
                        metrics.append({
                            'timestamp': datetime.datetime.utcnow().isoformat(),
                            'metric_name': metric_name,
                            'value': result['Values'][-1]  # 最新の値を取得
                        })
            except Exception as e:
                print(f"メトリクス {metric_name} の取得中にエラーが発生しました: {e}")
        
        return metrics
    
    def _test_connection(self) -> Tuple[bool, float, float]:
        """接続テストと読み書きレイテンシを測定する"""
        connected = False
        read_latency = 0.0
        write_latency = 0.0
        
        try:
            # 接続テスト
            start_time = time.time()
            self.client.ping()
            connected = True
            
            # 書き込みテスト
            key = f"{self.key_prefix}{int(time.time())}"
            value = self._generate_test_value(self.value_size)
            
            write_start = time.time()
            self.client.set(key, value)
            write_latency = (time.time() - write_start) * 1000  # ミリ秒に変換
            
            # 読み取りテスト
            read_start = time.time()
            self.client.get(key)
            read_latency = (time.time() - read_start) * 1000  # ミリ秒に変換
            
        except Exception as e:
            print(f"接続テスト中にエラーが発生しました: {e}")
            connected = False
        
        return connected, read_latency, write_latency
    
    def _monitor_cloudwatch(self):
        """CloudWatchメトリクスのモニタリングを行うスレッド"""
        while self.running:
            try:
                metrics = self._get_cloudwatch_metrics()
                self.cloudwatch_metrics.extend(metrics)
                
                # キューにメトリクスを追加（リアルタイム表示用）
                self.metrics_queue.put({
                    'type': 'cloudwatch',
                    'data': metrics,
                    'timestamp': datetime.datetime.utcnow().isoformat()
                })
                
                # 指定された間隔で実行
                time.sleep(self.monitoring_interval)
                
            except Exception as e:
                print(f"CloudWatchモニタリング中にエラーが発生しました: {e}")
                time.sleep(self.monitoring_interval)
    
    def _run_connection_tests(self):
        """接続テストと読み書きレイテンシの測定を行うスレッド"""
        while self.running:
            try:
                connected, read_latency, write_latency = self._test_connection()
                
                timestamp = datetime.datetime.utcnow().isoformat()
                
                # 接続状態を記録
                self.connection_status.append({
                    'timestamp': timestamp,
                    'connected': connected
                })
                
                # レイテンシを記録
                if connected:
                    self.latency_metrics.append({
                        'timestamp': timestamp,
                        'read_latency': read_latency,
                        'write_latency': write_latency
                    })
                
                # キューにデータを追加（リアルタイム表示用）
                self.metrics_queue.put({
                    'type': 'latency',
                    'data': {
                        'timestamp': timestamp,
                        'connected': connected,
                        'read_latency': read_latency,
                        'write_latency': write_latency
                    }
                })
                
                # 指定された間隔で実行
                time.sleep(self.test_interval)
                
            except Exception as e:
                print(f"接続テスト中にエラーが発生しました: {e}")
                
                # 接続エラーを記録
                self.connection_status.append({
                    'timestamp': datetime.datetime.utcnow().isoformat(),
                    'connected': False
                })
                
                time.sleep(self.test_interval)
    
    def _print_status_update(self):
        """ステータス更新を表示するスレッド"""
        last_print_time = time.time()
        
        while self.running:
            try:
                # キューからデータを取得（タイムアウト付き）
                try:
                    data = self.metrics_queue.get(timeout=1.0)
                    
                    # 前回の表示から1秒以上経過している場合のみ表示
                    current_time = time.time()
                    if current_time - last_print_time >= 1.0:
                        if data['type'] == 'latency':
                            latency_data = data['data']
                            status = "接続中" if latency_data['connected'] else "切断"
                            print(f"[{latency_data['timestamp']}] 状態: {status}, "
                                  f"読取: {latency_data['read_latency']:.2f}ms, "
                                  f"書込: {latency_data['write_latency']:.2f}ms")
                        
                        last_print_time = current_time
                    
                    self.metrics_queue.task_done()
                    
                except queue.Empty:
                    pass
                
            except Exception as e:
                print(f"ステータス表示中にエラーが発生しました: {e}")
            
            time.sleep(0.1)
    
    def start_monitoring(self):
        """モニタリングを開始する"""
        if self.running:
            print("モニタリングは既に実行中です。")
            return
        
        self.running = True
        
        # CloudWatchモニタリングスレッドを開始
        self.monitoring_thread = threading.Thread(target=self._monitor_cloudwatch)
        self.monitoring_thread.daemon = True
        self.monitoring_thread.start()
        
        # 接続テストスレッドを開始
        self.test_thread = threading.Thread(target=self._run_connection_tests)
        self.test_thread.daemon = True
        self.test_thread.start()
        
        # ステータス表示スレッドを開始
        self.status_thread = threading.Thread(target=self._print_status_update)
        self.status_thread.daemon = True
        self.status_thread.start()
        
        print(f"モニタリングを開始しました。Ctrl+Cで終了します。")
        print(f"クラスター: {self.cluster_id}")
        print(f"エンドポイント: {self.host}:{self.port}")
    
    def stop_monitoring(self):
        """モニタリングを停止する"""
        if not self.running:
            return
        
        self.running = False
        
        # スレッドの終了を待機
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=2.0)
        
        if self.test_thread:
            self.test_thread.join(timeout=2.0)
        
        if self.status_thread:
            self.status_thread.join(timeout=2.0)
        
        print("モニタリングを停止しました。")
    
    def save_results(self):
        """モニタリング結果を保存する"""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # CloudWatchメトリクスを保存
        if self.cloudwatch_metrics:
            cloudwatch_file = os.path.join(self.output_dir, f"cloudwatch_{timestamp}.json")
            with open(cloudwatch_file, 'w') as f:
                json.dump(self.cloudwatch_metrics, f, indent=2)
            print(f"CloudWatchメトリクスを {cloudwatch_file} に保存しました。")
        
        # レイテンシメトリクスを保存
        if self.latency_metrics:
            latency_file = os.path.join(self.output_dir, f"latency_{timestamp}.json")
            with open(latency_file, 'w') as f:
                json.dump(self.latency_metrics, f, indent=2)
            print(f"レイテンシメトリクスを {latency_file} に保存しました。")
        
        # 接続状態を保存
        if self.connection_status:
            connection_file = os.path.join(self.output_dir, f"connection_{timestamp}.json")
            with open(connection_file, 'w') as f:
                json.dump(self.connection_status, f, indent=2)
            print(f"接続状態を {connection_file} に保存しました。")
        
        # 結果をまとめたレポートを作成
        self.generate_report(timestamp)
    
    def generate_report(self, timestamp: str):
        """モニタリング結果のレポートを生成する"""
        report_file = os.path.join(self.output_dir, f"report_{timestamp}.md")
        
        # 接続状態の分析
        disconnections = []
        current_disconnection = None
        
        for status in self.connection_status:
            if not status['connected'] and current_disconnection is None:
                # 切断開始
                current_disconnection = {
                    'start': status['timestamp'],
                    'end': None
                }
            elif status['connected'] and current_disconnection is not None:
                # 切断終了
                current_disconnection['end'] = status['timestamp']
                disconnections.append(current_disconnection)
                current_disconnection = None
        
        # 最後の切断が終了していない場合
        if current_disconnection is not None:
            current_disconnection['end'] = "モニタリング終了時点"
            disconnections.append(current_disconnection)
        
        # レイテンシの分析
        read_latencies = [m['read_latency'] for m in self.latency_metrics]
        write_latencies = [m['write_latency'] for m in self.latency_metrics]
        
        read_stats = {
            'min': min(read_latencies) if read_latencies else 0,
            'max': max(read_latencies) if read_latencies else 0,
            'avg': statistics.mean(read_latencies) if read_latencies else 0,
            'median': statistics.median(read_latencies) if read_latencies else 0,
            'p95': sorted(read_latencies)[int(len(read_latencies) * 0.95)] if len(read_latencies) > 20 else 0,
            'p99': sorted(read_latencies)[int(len(read_latencies) * 0.99)] if len(read_latencies) > 100 else 0
        }
        
        write_stats = {
            'min': min(write_latencies) if write_latencies else 0,
            'max': max(write_latencies) if write_latencies else 0,
            'avg': statistics.mean(write_latencies) if write_latencies else 0,
            'median': statistics.median(write_latencies) if write_latencies else 0,
            'p95': sorted(write_latencies)[int(len(write_latencies) * 0.95)] if len(write_latencies) > 20 else 0,
            'p99': sorted(write_latencies)[int(len(write_latencies) * 0.99)] if len(write_latencies) > 100 else 0
        }
        
        # レポートの作成
        with open(report_file, 'w') as f:
            f.write(f"# AWS Elasticache エンジン変更モニタリングレポート\n\n")
            f.write(f"実行日時: {timestamp}\n")
            f.write(f"クラスターID: {self.cluster_id}\n")
            f.write(f"エンドポイント: {self.host}:{self.port}\n\n")
            
            f.write(f"## 接続状態\n\n")
            f.write(f"総テスト回数: {len(self.connection_status)}\n")
            
            connected_count = sum(1 for s in self.connection_status if s['connected'])
            disconnected_count = len(self.connection_status) - connected_count
            
            f.write(f"接続成功: {connected_count} ({connected_count/len(self.connection_status)*100:.2f}%)\n")
            f.write(f"接続失敗: {disconnected_count} ({disconnected_count/len(self.connection_status)*100:.2f}%)\n\n")
            
            if disconnections:
                f.write(f"### 切断イベント\n\n")
                f.write(f"切断回数: {len(disconnections)}\n\n")
                f.write(f"| 開始時刻 | 終了時刻 | 期間 |\n")
                f.write(f"|---------|---------|------|\n")
                
                for d in disconnections:
                    start = datetime.datetime.fromisoformat(d['start'])
                    
                    if d['end'] == "モニタリング終了時点":
                        duration = "不明（モニタリング終了）"
                        f.write(f"| {start.strftime('%Y-%m-%d %H:%M:%S')} | {d['end']} | {duration} |\n")
                    else:
                        end = datetime.datetime.fromisoformat(d['end'])
                        duration = end - start
                        duration_str = str(duration)
                        f.write(f"| {start.strftime('%Y-%m-%d %H:%M:%S')} | {end.strftime('%Y-%m-%d %H:%M:%S')} | {duration_str} |\n")
            else:
                f.write(f"切断イベントはありませんでした。\n\n")
            
            f.write(f"\n## レイテンシ統計\n\n")
            f.write(f"### 読み取りレイテンシ (ms)\n\n")
            f.write(f"- 最小値: {read_stats['min']:.2f}\n")
            f.write(f"- 最大値: {read_stats['max']:.2f}\n")
            f.write(f"- 平均値: {read_stats['avg']:.2f}\n")
            f.write(f"- 中央値: {read_stats['median']:.2f}\n")
            f.write(f"- 95パーセンタイル: {read_stats['p95']:.2f}\n")
            f.write(f"- 99パーセンタイル: {read_stats['p99']:.2f}\n\n")
            
            f.write(f"### 書き込みレイテンシ (ms)\n\n")
            f.write(f"- 最小値: {write_stats['min']:.2f}\n")
            f.write(f"- 最大値: {write_stats['max']:.2f}\n")
            f.write(f"- 平均値: {write_stats['avg']:.2f}\n")
            f.write(f"- 中央値: {write_stats['median']:.2f}\n")
            f.write(f"- 95パーセンタイル: {write_stats['p95']:.2f}\n")
            f.write(f"- 99パーセンタイル: {write_stats['p99']:.2f}\n\n")
            
            f.write(f"\n## 結論\n\n")
            
            if disconnected_count > 0:
                f.write(f"モニタリング期間中に **{len(disconnections)}回の切断** が検出されました。\n")
                if len(disconnections) > 0:
                    max_duration = max([datetime.datetime.fromisoformat(d['end']) - datetime.datetime.fromisoformat(d['start']) 
                                       for d in disconnections if d['end'] != "モニタリング終了時点"], 
                                       default=datetime.timedelta(0))
                    f.write(f"最長の切断時間は **{max_duration}** でした。\n\n")
            else:
                f.write(f"モニタリング期間中に **切断は検出されませんでした**。\n\n")
            
            # レイテンシの変化を分析
            if len(self.latency_metrics) > 10:
                # データを前半と後半に分割して比較
                mid_point = len(self.latency_metrics) // 2
                
                first_half_read = [m['read_latency'] for m in self.latency_metrics[:mid_point]]
                second_half_read = [m['read_latency'] for m in self.latency_metrics[mid_point:]]
                
                first_half_write = [m['write_latency'] for m in self.latency_metrics[:mid_point]]
                second_half_write = [m['write_latency'] for m in self.latency_metrics[mid_point:]]
                
                read_change = statistics.mean(second_half_read) - statistics.mean(first_half_read)
                write_change = statistics.mean(second_half_write) - statistics.mean(first_half_write)
                
                f.write(f"### パフォーマンスの変化\n\n")
                
                if abs(read_change) < 1.0 and abs(write_change) < 1.0:
                    f.write(f"モニタリング期間中のレイテンシに **顕著な変化は見られませんでした**。\n")
                else:
                    if read_change > 0:
                        f.write(f"読み取りレイテンシは **{read_change:.2f}ms 増加** しました。\n")
                    else:
                        f.write(f"読み取りレイテンシは **{abs(read_change):.2f}ms 減少** しました。\n")
                    
                    if write_change > 0:
                        f.write(f"書き込みレイテンシは **{write_change:.2f}ms 増加** しました。\n")
                    else:
                        f.write(f"書き込みレイテンシは **{abs(write_change):.2f}ms 減少** しました。\n")
        
        print(f"レポートを {report_file} に保存しました。")
        
        # グラフの生成
        self.generate_graphs(timestamp)
    
    def generate_graphs(self, timestamp: str):
        """モニタリング結果のグラフを生成する"""
        if not self.latency_metrics:
            return
        
        # データフレームの作成
        df = pd.DataFrame(self.latency_metrics)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # グラフのスタイル設定
        plt.style.use('ggplot')
        sns.set(style="whitegrid")
        
        # レイテンシの時系列グラフ
        plt.figure(figsize=(12, 6))
        plt.plot(df['timestamp'], df['read_latency'], label='読み取りレイテンシ')
        plt.plot(df['timestamp'], df['write_latency'], label='書き込みレイテンシ')
        plt.xlabel('時間')
        plt.ylabel('レイテンシ (ms)')
        plt.title('Elasticacheエンジン変更中のレイテンシ変化')
        plt.legend()
        plt.grid(True)
        
        # x軸の日付フォーマットを設定
        plt.gcf().autofmt_xdate()
        
        # グラフを保存
        graph_file = os.path.join(self.output_dir, f"latency_graph_{timestamp}.png")
        plt.savefig(graph_file, dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"レイテンシグラフを {graph_file} に保存しました。")
        
        # 接続状態のヒートマップ
        if self.connection_status:
            conn_df = pd.DataFrame(self.connection_status)
            conn_df['timestamp'] = pd.to_datetime(conn_df['timestamp'])
            conn_df['connected_int'] = conn_df['connected'].astype(int)
            
            plt.figure(figsize=(12, 3))
            plt.scatter(conn_df['timestamp'], [1] * len(conn_df), c=conn_df['connected_int'], 
                       cmap='RdYlGn', s=50, marker='s')
            plt.yticks([])
            plt.xlabel('時間')
            plt.title('接続状態 (緑=接続中, 赤=切断)')
            plt.grid(False)
            
            # x軸の日付フォーマットを設定
            plt.gcf().autofmt_xdate()
            
            # グラフを保存
            conn_graph_file = os.path.join(self.output_dir, f"connection_status_{timestamp}.png")
            plt.savefig(conn_graph_file, dpi=300, bbox_inches='tight')
            plt.close()
            
            print(f"接続状態グラフを {conn_graph_file} に保存しました。")


def parse_arguments():
    """コマンドライン引数をパースする"""
    parser = argparse.ArgumentParser(description='AWS Elasticache エンジン変更モニタリングツール')
    
    parser.add_argument('--cluster-id', type=str, required=True,
                        help='モニタリング対象のElasticacheクラスターID')
    parser.add_argument('--region', type=str, default='ap-northeast-1',
                        help='AWSリージョン (デフォルト: ap-northeast-1)')
    parser.add_argument('--host', type=str, default=None,
                        help='Redisサーバーのホスト名 (指定しない場合はクラスターIDから自動取得)')
    parser.add_argument('--port', type=int, default=None,
                        help='Redisサーバーのポート番号 (指定しない場合はデフォルト6379)')
    parser.add_argument('--password', type=str, default=None,
                        help='Redisサーバーの認証パスワード (必要な場合)')
    parser.add_argument('--db', type=int, default=0,
                        help='使用するデータベース番号 (デフォルト: 0)')
    
    parser.add_argument('--key-prefix', type=str, default='migration-test:',
                        help='テストで使用するキーのプレフィックス (デフォルト: migration-test:)')
    parser.add_argument('--monitoring-interval', type=int, default=60,
                        help='CloudWatchメトリクスの取得間隔（秒） (デフォルト: 60)')
    parser.add_argument('--test-interval', type=float, default=0.1,
                        help='読み書きテストの間隔（秒） (デフォルト: 0.1)')
    parser.add_argument('--value-size', type=int, default=1024,
                        help='テスト値のサイズ（バイト） (デフォルト: 1024)')
    parser.add_argument('--num-keys', type=int, default=1000,
                        help='テストで使用するキーの数 (デフォルト: 1000)')
    
    parser.add_argument('--output-dir', type=str, default='../results/migration',
                        help='結果の出力ディレクトリ (デフォルト: ../results/migration)')
    
    return parser.parse_args()


def signal_handler(sig, frame):
    """シグナルハンドラ（Ctrl+C）"""
    print("\nモニタリングを停止しています...")
    if monitor:
        monitor.stop_monitoring()
        monitor.save_results()
    sys.exit(0)


def main():
    """メイン関数"""
    args = parse_arguments()
    
    global monitor
    monitor = ElasticacheMigrationMonitor(
        cluster_id=args.cluster_id,
        region=args.region,
        host=args.host,
        port=args.port,
        password=args.password,
        db=args.db,
        key_prefix=args.key_prefix,
        monitoring_interval=args.monitoring_interval,
        test_interval=args.test_interval,
        value_size=args.value_size,
        num_keys=args.num_keys,
        output_dir=args.output_dir
    )
    
    # シグナルハンドラを設定（Ctrl+Cで終了）
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        # モニタリングを開始
        monitor.start_monitoring()
        
        # メインスレッドを維持
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nモニタリングを停止しています...")
        monitor.stop_monitoring()
        monitor.save_results()
    
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        if monitor:
            monitor.stop_monitoring()
            monitor.save_results()


if __name__ == "__main__":
    monitor = None
    main()
