#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AWS Elasticache Redis vs Valkey 性能比較
単純なキー/バリュー操作のベンチマークスクリプト

このスクリプトは、RedisとValkeyエンジンに対して基本的なキー/バリュー操作（GET/SET）の
パフォーマンスを測定し、比較するためのものです。
"""

import argparse
import time
import random
import string
import statistics
import json
import redis
import concurrent.futures
import os
import sys
from datetime import datetime
from typing import Dict, List, Tuple, Any, Optional

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


class BenchmarkConfig:
    """ベンチマーク設定を管理するクラス"""
    
    def __init__(self, 
                 host: str,
                 port: int,
                 password: Optional[str] = None,
                 db: int = 0,
                 key_prefix: str = 'benchmark:',
                 num_keys: int = 10000,
                 value_size: int = 1024,
                 num_threads: int = 10,
                 operations_per_thread: int = 1000,
                 read_write_ratio: float = 0.8,  # 0.8 = 80% reads, 20% writes
                 random_values: bool = False,
                 pipeline_size: int = 0):  # 0 = no pipelining
        """
        Args:
            host: Redisサーバーのホスト名
            port: Redisサーバーのポート番号
            password: 認証パスワード（必要な場合）
            db: 使用するデータベース番号
            key_prefix: ベンチマークで使用するキーのプレフィックス
            num_keys: 使用するキーの総数
            value_size: 値のサイズ（バイト）
            num_threads: 並列実行するスレッド数
            operations_per_thread: スレッドごとの操作数
            read_write_ratio: 読み取り/書き込み比率（0.8 = 80%読み取り、20%書き込み）
            random_values: 値をランダム生成するかどうか
            pipeline_size: パイプライン処理のバッチサイズ（0=パイプラインなし）
        """
        self.host = host
        self.port = port
        self.password = password
        self.db = db
        self.key_prefix = key_prefix
        self.num_keys = num_keys
        self.value_size = value_size
        self.num_threads = num_threads
        self.operations_per_thread = operations_per_thread
        self.read_write_ratio = read_write_ratio
        self.random_values = random_values
        self.pipeline_size = pipeline_size
        
    def to_dict(self) -> Dict[str, Any]:
        """設定を辞書形式で返す"""
        return {
            'host': self.host,
            'port': self.port,
            'password': '***' if self.password else None,
            'db': self.db,
            'key_prefix': self.key_prefix,
            'num_keys': self.num_keys,
            'value_size': self.value_size,
            'num_threads': self.num_threads,
            'operations_per_thread': self.operations_per_thread,
            'read_write_ratio': self.read_write_ratio,
            'random_values': self.random_values,
            'pipeline_size': self.pipeline_size,
            'total_operations': self.num_threads * self.operations_per_thread
        }


class BenchmarkResult:
    """ベンチマーク結果を管理するクラス"""
    
    def __init__(self, 
                 config: BenchmarkConfig,
                 engine_type: str,
                 start_time: datetime,
                 end_time: datetime,
                 operation_times: List[float],
                 operation_types: List[str],
                 errors: int = 0):
        """
        Args:
            config: ベンチマーク設定
            engine_type: エンジンタイプ（'Redis' または 'Valkey'）
            start_time: 開始時刻
            end_time: 終了時刻
            operation_times: 各操作の実行時間（ミリ秒）
            operation_types: 各操作のタイプ（'GET' または 'SET'）
            errors: エラー数
        """
        self.config = config
        self.engine_type = engine_type
        self.start_time = start_time
        self.end_time = end_time
        self.operation_times = operation_times
        self.operation_types = operation_types
        self.errors = errors
        
    def calculate_stats(self) -> Dict[str, Any]:
        """統計情報を計算して返す"""
        duration_sec = (self.end_time - self.start_time).total_seconds()
        total_operations = len(self.operation_times)
        
        if not self.operation_times:
            return {
                'error': 'No operations recorded'
            }
        
        # 全体の統計
        all_times = self.operation_times
        all_stats = {
            'min': min(all_times),
            'max': max(all_times),
            'avg': statistics.mean(all_times),
            'median': statistics.median(all_times),
            'p95': sorted(all_times)[int(len(all_times) * 0.95)],
            'p99': sorted(all_times)[int(len(all_times) * 0.99)],
            'throughput': total_operations / duration_sec
        }
        
        # 操作タイプ別の統計
        get_times = [t for t, op in zip(self.operation_times, self.operation_types) if op == 'GET']
        set_times = [t for t, op in zip(self.operation_times, self.operation_types) if op == 'SET']
        
        get_stats = {}
        if get_times:
            get_stats = {
                'min': min(get_times),
                'max': max(get_times),
                'avg': statistics.mean(get_times),
                'median': statistics.median(get_times),
                'p95': sorted(get_times)[int(len(get_times) * 0.95)],
                'p99': sorted(get_times)[int(len(get_times) * 0.99)],
                'throughput': len(get_times) / duration_sec
            }
            
        set_stats = {}
        if set_times:
            set_stats = {
                'min': min(set_times),
                'max': max(set_times),
                'avg': statistics.mean(set_times),
                'median': statistics.median(set_times),
                'p95': sorted(set_times)[int(len(set_times) * 0.95)],
                'p99': sorted(set_times)[int(len(set_times) * 0.99)],
                'throughput': len(set_times) / duration_sec
            }
            
        return {
            'engine_type': self.engine_type,
            'duration_sec': duration_sec,
            'total_operations': total_operations,
            'operations_per_sec': total_operations / duration_sec,
            'errors': self.errors,
            'all_stats': all_stats,
            'get_stats': get_stats,
            'set_stats': set_stats
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """結果を辞書形式で返す"""
        return {
            'config': self.config.to_dict(),
            'engine_type': self.engine_type,
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat(),
            'stats': self.calculate_stats()
        }
    
    def save_to_file(self, filename: str) -> None:
        """結果をJSONファイルに保存する"""
        with open(filename, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
    
    def print_summary(self) -> None:
        """結果のサマリーを表示する"""
        stats = self.calculate_stats()
        duration_sec = stats['duration_sec']
        
        print(f"\n===== {self.engine_type} ベンチマーク結果 =====")
        print(f"実行時間: {duration_sec:.2f}秒")
        print(f"総操作数: {stats['total_operations']}")
        print(f"スループット: {stats['operations_per_sec']:.2f} ops/sec")
        print(f"エラー数: {stats['errors']}")
        
        print("\n--- 全体統計 ---")
        print(f"最小レイテンシ: {stats['all_stats']['min']:.3f} ms")
        print(f"最大レイテンシ: {stats['all_stats']['max']:.3f} ms")
        print(f"平均レイテンシ: {stats['all_stats']['avg']:.3f} ms")
        print(f"中央値レイテンシ: {stats['all_stats']['median']:.3f} ms")
        print(f"95パーセンタイルレイテンシ: {stats['all_stats']['p95']:.3f} ms")
        print(f"99パーセンタイルレイテンシ: {stats['all_stats']['p99']:.3f} ms")
        
        if stats['get_stats']:
            print("\n--- GET操作統計 ---")
            print(f"操作数: {len([op for op in self.operation_types if op == 'GET'])}")
            print(f"スループット: {stats['get_stats']['throughput']:.2f} ops/sec")
            print(f"平均レイテンシ: {stats['get_stats']['avg']:.3f} ms")
            print(f"95パーセンタイルレイテンシ: {stats['get_stats']['p95']:.3f} ms")
            
        if stats['set_stats']:
            print("\n--- SET操作統計 ---")
            print(f"操作数: {len([op for op in self.operation_types if op == 'SET'])}")
            print(f"スループット: {stats['set_stats']['throughput']:.2f} ops/sec")
            print(f"平均レイテンシ: {stats['set_stats']['avg']:.3f} ms")
            print(f"95パーセンタイルレイテンシ: {stats['set_stats']['p95']:.3f} ms")


class KeyValueBenchmark:
    """キー/バリュー操作のベンチマークを実行するクラス"""
    
    def __init__(self, config: BenchmarkConfig, engine_type: str):
        """
        Args:
            config: ベンチマーク設定
            engine_type: エンジンタイプ（'Redis' または 'Valkey'）
        """
        self.config = config
        self.engine_type = engine_type
        self.client = self._create_client()
        self.operation_times = []
        self.operation_types = []
        self.errors = 0
        
    def _create_client(self) -> redis.Redis:
        """Redisクライアントを作成する"""
        return redis.Redis(
            host=self.config.host,
            port=self.config.port,
            password=self.config.password,
            db=self.config.db,
            decode_responses=True
        )
    
    def _generate_random_value(self, size: int) -> str:
        """指定されたサイズのランダムな文字列を生成する"""
        return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(size))
    
    def _get_key(self, index: int) -> str:
        """キー名を生成する"""
        return f"{self.config.key_prefix}{index}"
    
    def _get_value(self, size: int) -> str:
        """値を生成する"""
        if self.config.random_values:
            return self._generate_random_value(size)
        else:
            # 固定パターンの値（サイズ分だけ繰り返し）
            pattern = "abcdefghij"
            repeats = size // len(pattern) + 1
            return (pattern * repeats)[:size]
    
    def prepare_data(self) -> None:
        """ベンチマーク用のデータを準備する"""
        print(f"データ準備中: {self.config.num_keys}キーを作成...")
        
        # パイプラインを使用してデータをバッチ処理
        batch_size = 1000
        for i in range(0, self.config.num_keys, batch_size):
            pipe = self.client.pipeline()
            end = min(i + batch_size, self.config.num_keys)
            for j in range(i, end):
                key = self._get_key(j)
                value = self._get_value(self.config.value_size)
                pipe.set(key, value)
            pipe.execute()
            
            # 進捗表示
            progress = min(100, int((end / self.config.num_keys) * 100))
            print(f"\r進捗: {progress}% ({end}/{self.config.num_keys})", end='')
            
        print("\nデータ準備完了")
    
    def cleanup_data(self) -> None:
        """ベンチマークで使用したデータを削除する"""
        print(f"データクリーンアップ中: {self.config.key_prefix}* のキーを削除...")
        keys = self.client.keys(f"{self.config.key_prefix}*")
        if keys:
            self.client.delete(*keys)
        print("クリーンアップ完了")
    
    def _perform_operation(self, thread_id: int) -> Tuple[List[float], List[str], int]:
        """スレッドごとの操作を実行する"""
        local_times = []
        local_op_types = []
        local_errors = 0
        
        # スレッド固有のクライアントを作成
        client = self._create_client()
        
        # パイプライン処理の準備
        use_pipeline = self.config.pipeline_size > 0
        if use_pipeline:
            pipe = client.pipeline(transaction=False)
            pipe_count = 0
            pipe_times = []
            pipe_op_types = []
        
        for i in range(self.config.operations_per_thread):
            # ランダムなキーを選択
            key_index = random.randint(0, self.config.num_keys - 1)
            key = self._get_key(key_index)
            
            # 読み取り/書き込み比率に基づいて操作を決定
            is_read = random.random() < self.config.read_write_ratio
            
            try:
                if use_pipeline:
                    # パイプライン処理
                    start_time = time.time()
                    if is_read:
                        pipe.get(key)
                        pipe_op_types.append('GET')
                    else:
                        value = self._get_value(self.config.value_size)
                        pipe.set(key, value)
                        pipe_op_types.append('SET')
                    
                    pipe_count += 1
                    
                    # パイプラインサイズに達したら実行
                    if pipe_count >= self.config.pipeline_size:
                        pipe.execute()
                        end_time = time.time()
                        elapsed = (end_time - start_time) * 1000  # ミリ秒に変換
                        
                        # 各操作に時間を分配
                        op_time = elapsed / pipe_count
                        pipe_times.extend([op_time] * pipe_count)
                        
                        # リセット
                        pipe = client.pipeline(transaction=False)
                        pipe_count = 0
                else:
                    # 通常の操作
                    start_time = time.time()
                    if is_read:
                        client.get(key)
                        local_op_types.append('GET')
                    else:
                        value = self._get_value(self.config.value_size)
                        client.set(key, value)
                        local_op_types.append('SET')
                    end_time = time.time()
                    
                    elapsed = (end_time - start_time) * 1000  # ミリ秒に変換
                    local_times.append(elapsed)
            except Exception as e:
                local_errors += 1
                print(f"エラー: {e}")
        
        # 残りのパイプライン操作を実行
        if use_pipeline and pipe_count > 0:
            start_time = time.time()
            pipe.execute()
            end_time = time.time()
            elapsed = (end_time - start_time) * 1000  # ミリ秒に変換
            
            # 各操作に時間を分配
            op_time = elapsed / pipe_count
            pipe_times.extend([op_time] * pipe_count)
            
            # パイプラインの結果を統合
            local_times.extend(pipe_times)
            local_op_types.extend(pipe_op_types)
        
        return local_times, local_op_types, local_errors
    
    def run(self) -> BenchmarkResult:
        """ベンチマークを実行する"""
        print(f"\n===== {self.engine_type} ベンチマーク開始 =====")
        print(f"設定: {json.dumps(self.config.to_dict(), indent=2)}")
        
        # データ準備
        self.prepare_data()
        
        # ウォームアップ
        print("ウォームアップ中...")
        warmup_ops = min(1000, self.config.num_keys)
        for i in range(warmup_ops):
            key = self._get_key(i % self.config.num_keys)
            self.client.get(key)
        
        # ベンチマーク実行
        print(f"ベンチマーク実行中: {self.config.num_threads}スレッド, "
              f"スレッドあたり{self.config.operations_per_thread}操作...")
        
        start_time = datetime.now()
        
        # スレッドプールを使用して並列実行
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.config.num_threads) as executor:
            futures = [executor.submit(self._perform_operation, i) for i in range(self.config.num_threads)]
            
            # 結果を収集
            for future in concurrent.futures.as_completed(futures):
                times, op_types, errors = future.result()
                self.operation_times.extend(times)
                self.operation_types.extend(op_types)
                self.errors += errors
        
        end_time = datetime.now()
        
        # 結果を作成
        result = BenchmarkResult(
            config=self.config,
            engine_type=self.engine_type,
            start_time=start_time,
            end_time=end_time,
            operation_times=self.operation_times,
            operation_types=self.operation_types,
            errors=self.errors
        )
        
        # クリーンアップ
        self.cleanup_data()
        
        return result


def parse_arguments():
    """コマンドライン引数をパースする"""
    parser = argparse.ArgumentParser(description='Redis/Valkey キー/バリュー操作ベンチマーク')
    
    parser.add_argument('--host', type=str, default=None,
                        help='Redisサーバーのホスト名 (デフォルト: AWS設定またはlocalhost)')
    parser.add_argument('--port', type=int, default=None,
                        help='Redisサーバーのポート番号 (デフォルト: AWS設定または6379/6380)')
    parser.add_argument('--password', type=str, default=None,
                        help='Redisサーバーの認証パスワード (デフォルト: なし)')
    parser.add_argument('--db', type=int, default=0,
                        help='使用するデータベース番号 (デフォルト: 0)')
    
    parser.add_argument('--engine', type=str, choices=['redis', 'valkey'], required=True,
                        help='テスト対象のエンジン (redis または valkey)')
    
    parser.add_argument('--aws', action='store_true',
                        help='AWS Elasticacheモードを有効化（設定ファイルから接続情報を読み込み）')
    
    parser.add_argument('--key-prefix', type=str, default='benchmark:',
                        help='ベンチマークで使用するキーのプレフィックス (デフォルト: benchmark:)')
    parser.add_argument('--num-keys', type=int, default=10000,
                        help='使用するキーの総数 (デフォルト: 10000)')
    parser.add_argument('--value-size', type=int, default=1024,
                        help='値のサイズ（バイト） (デフォルト: 1024)')
    
    parser.add_argument('--num-threads', type=int, default=10,
                        help='並列実行するスレッド数 (デフォルト: 10)')
    parser.add_argument('--operations', type=int, default=1000,
                        help='スレッドごとの操作数 (デフォルト: 1000)')
    
    parser.add_argument('--read-ratio', type=float, default=0.8,
                        help='読み取り操作の比率 (0.0-1.0, デフォルト: 0.8)')
    parser.add_argument('--random-values', action='store_true',
                        help='ランダムな値を使用する (デフォルト: 固定パターン)')
    
    parser.add_argument('--pipeline', type=int, default=0,
                        help='パイプライン処理のバッチサイズ (0=パイプラインなし, デフォルト: 0)')
    
    parser.add_argument('--output', type=str, default=None,
                        help='結果を保存するJSONファイル (デフォルト: なし)')
    
    return parser.parse_args()


def main():
    """メイン関数"""
    args = parse_arguments()
    
    # ホストとポートの設定
    host = args.host
    port = args.port
    
    # AWS Elasticacheモードが有効な場合、設定ファイルからエンドポイント情報を取得
    if args.aws or (host is None and port is None):
        try:
            endpoint = get_endpoint(args.engine)
            if host is None:
                host = endpoint.get("host", "localhost")
            if port is None:
                port = endpoint.get("port", 6379 if args.engine == "redis" else 6380)
            print(f"AWS Elasticacheエンドポイント設定を使用: {host}:{port}")
        except Exception as e:
            print(f"AWS設定の読み込みに失敗しました: {e}")
            print("デフォルト設定を使用します")
            if host is None:
                host = "localhost"
            if port is None:
                port = 6379 if args.engine == "redis" else 6380
    else:
        # コマンドライン引数で指定されたホストとポートを使用
        if host is None:
            host = "localhost"
        if port is None:
            port = 6379 if args.engine == "redis" else 6380
    
    # 設定を作成
    config = BenchmarkConfig(
        host=host,
        port=port,
        password=args.password,
        db=args.db,
        key_prefix=args.key_prefix,
        num_keys=args.num_keys,
        value_size=args.value_size,
        num_threads=args.num_threads,
        operations_per_thread=args.operations,
        read_write_ratio=args.read_ratio,
        random_values=args.random_values,
        pipeline_size=args.pipeline
    )
    
    # エンジンタイプを設定
    engine_type = args.engine.capitalize()  # 'redis' -> 'Redis', 'valkey' -> 'Valkey'
    
    # ベンチマークを実行
    benchmark = KeyValueBenchmark(config, engine_type)
    result = benchmark.run()
    
    # 結果を表示
    result.print_summary()
    
    # 結果をファイルに保存（指定されている場合）
    if args.output:
        result.save_to_file(args.output)
        print(f"\n結果を {args.output} に保存しました")


if __name__ == "__main__":
    main()
