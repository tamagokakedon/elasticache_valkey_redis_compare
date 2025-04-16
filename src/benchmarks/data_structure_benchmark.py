#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AWS Elasticache Redis vs Valkey 性能比較
複雑なデータ構造操作のベンチマークスクリプト

このスクリプトは、RedisとValkeyエンジンに対して複雑なデータ構造操作
（リスト、セット、ハッシュ、ソート済みセットなど）のパフォーマンスを測定し、
比較するためのものです。
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
from typing import Dict, List, Tuple, Any, Optional, Callable
from enum import Enum

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


class DataStructureType(Enum):
    """ベンチマーク対象のデータ構造タイプ"""
    STRING = "string"
    LIST = "list"
    HASH = "hash"
    SET = "set"
    ZSET = "zset"
    ALL = "all"  # すべてのデータ構造をテスト


class BenchmarkConfig:
    """ベンチマーク設定を管理するクラス"""
    
    def __init__(self, 
                 host: str,
                 port: int,
                 password: Optional[str] = None,
                 db: int = 0,
                 key_prefix: str = 'benchmark:ds:',
                 data_structure: DataStructureType = DataStructureType.ALL,
                 num_keys: int = 1000,
                 elements_per_key: int = 100,
                 element_size: int = 100,
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
            data_structure: テスト対象のデータ構造タイプ
            num_keys: 使用するキーの総数
            elements_per_key: キーごとの要素数（リスト、セット、ハッシュなど）
            element_size: 要素のサイズ（バイト）
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
        self.data_structure = data_structure
        self.num_keys = num_keys
        self.elements_per_key = elements_per_key
        self.element_size = element_size
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
            'data_structure': self.data_structure.value,
            'num_keys': self.num_keys,
            'elements_per_key': self.elements_per_key,
            'element_size': self.element_size,
            'num_threads': self.num_threads,
            'operations_per_thread': self.operations_per_thread,
            'read_write_ratio': self.read_write_ratio,
            'random_values': self.random_values,
            'pipeline_size': self.pipeline_size,
            'total_operations': self.num_threads * self.operations_per_thread
        }


class OperationResult:
    """操作の結果を保持するクラス"""
    
    def __init__(self, 
                 operation_type: str,
                 data_structure: str,
                 duration_ms: float,
                 success: bool = True,
                 error: Optional[str] = None):
        """
        Args:
            operation_type: 操作タイプ（例: 'LPUSH', 'HGET'など）
            data_structure: データ構造タイプ（例: 'list', 'hash'など）
            duration_ms: 操作の実行時間（ミリ秒）
            success: 操作が成功したかどうか
            error: エラーメッセージ（失敗した場合）
        """
        self.operation_type = operation_type
        self.data_structure = data_structure
        self.duration_ms = duration_ms
        self.success = success
        self.error = error


class BenchmarkResult:
    """ベンチマーク結果を管理するクラス"""
    
    def __init__(self, 
                 config: BenchmarkConfig,
                 engine_type: str,
                 start_time: datetime,
                 end_time: datetime,
                 operation_results: List[OperationResult]):
        """
        Args:
            config: ベンチマーク設定
            engine_type: エンジンタイプ（'Redis' または 'Valkey'）
            start_time: 開始時刻
            end_time: 終了時刻
            operation_results: 各操作の結果
        """
        self.config = config
        self.engine_type = engine_type
        self.start_time = start_time
        self.end_time = end_time
        self.operation_results = operation_results
        
    def calculate_stats(self) -> Dict[str, Any]:
        """統計情報を計算して返す"""
        duration_sec = (self.end_time - self.start_time).total_seconds()
        total_operations = len(self.operation_results)
        successful_operations = sum(1 for r in self.operation_results if r.success)
        errors = total_operations - successful_operations
        
        if not self.operation_results:
            return {
                'error': 'No operations recorded'
            }
        
        # 全体の統計
        all_times = [r.duration_ms for r in self.operation_results if r.success]
        if not all_times:
            return {
                'error': 'No successful operations recorded'
            }
            
        all_stats = {
            'min': min(all_times),
            'max': max(all_times),
            'avg': statistics.mean(all_times),
            'median': statistics.median(all_times),
            'p95': sorted(all_times)[int(len(all_times) * 0.95)],
            'p99': sorted(all_times)[int(len(all_times) * 0.99)],
            'throughput': successful_operations / duration_sec
        }
        
        # データ構造別の統計
        structure_stats = {}
        for ds_type in DataStructureType:
            if ds_type == DataStructureType.ALL:
                continue
                
            ds_times = [r.duration_ms for r in self.operation_results 
                        if r.success and r.data_structure == ds_type.value]
            
            if ds_times:
                structure_stats[ds_type.value] = {
                    'operations': len(ds_times),
                    'min': min(ds_times),
                    'max': max(ds_times),
                    'avg': statistics.mean(ds_times),
                    'median': statistics.median(ds_times),
                    'p95': sorted(ds_times)[int(len(ds_times) * 0.95)],
                    'p99': sorted(ds_times)[int(len(ds_times) * 0.99)],
                    'throughput': len(ds_times) / duration_sec
                }
                
                # 操作タイプ別の統計
                op_stats = {}
                for op_type in set(r.operation_type for r in self.operation_results 
                                  if r.success and r.data_structure == ds_type.value):
                    op_times = [r.duration_ms for r in self.operation_results 
                               if r.success and r.data_structure == ds_type.value and r.operation_type == op_type]
                    
                    if op_times:
                        op_stats[op_type] = {
                            'operations': len(op_times),
                            'min': min(op_times),
                            'max': max(op_times),
                            'avg': statistics.mean(op_times),
                            'median': statistics.median(op_times),
                            'p95': sorted(op_times)[int(len(op_times) * 0.95)],
                            'p99': sorted(op_times)[int(len(op_times) * 0.99)],
                            'throughput': len(op_times) / duration_sec
                        }
                
                structure_stats[ds_type.value]['operations_by_type'] = op_stats
            
        return {
            'engine_type': self.engine_type,
            'duration_sec': duration_sec,
            'total_operations': total_operations,
            'successful_operations': successful_operations,
            'operations_per_sec': successful_operations / duration_sec,
            'errors': errors,
            'all_stats': all_stats,
            'structure_stats': structure_stats
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
        
        print(f"\n===== {self.engine_type} データ構造ベンチマーク結果 =====")
        print(f"実行時間: {duration_sec:.2f}秒")
        print(f"総操作数: {stats['total_operations']}")
        print(f"成功操作数: {stats['successful_operations']}")
        print(f"スループット: {stats['operations_per_sec']:.2f} ops/sec")
        print(f"エラー数: {stats['errors']}")
        
        print("\n--- 全体統計 ---")
        print(f"最小レイテンシ: {stats['all_stats']['min']:.3f} ms")
        print(f"最大レイテンシ: {stats['all_stats']['max']:.3f} ms")
        print(f"平均レイテンシ: {stats['all_stats']['avg']:.3f} ms")
        print(f"中央値レイテンシ: {stats['all_stats']['median']:.3f} ms")
        print(f"95パーセンタイルレイテンシ: {stats['all_stats']['p95']:.3f} ms")
        print(f"99パーセンタイルレイテンシ: {stats['all_stats']['p99']:.3f} ms")
        
        # データ構造別の統計
        for ds_type, ds_stats in stats.get('structure_stats', {}).items():
            print(f"\n--- {ds_type.upper()} 操作統計 ---")
            print(f"操作数: {ds_stats['operations']}")
            print(f"スループット: {ds_stats['throughput']:.2f} ops/sec")
            print(f"平均レイテンシ: {ds_stats['avg']:.3f} ms")
            print(f"95パーセンタイルレイテンシ: {ds_stats['p95']:.3f} ms")
            
            # 主要な操作タイプの統計を表示
            for op_type, op_stats in ds_stats.get('operations_by_type', {}).items():
                if op_stats['operations'] > 0:
                    print(f"  {op_type}: {op_stats['operations']} 操作, "
                          f"平均 {op_stats['avg']:.3f} ms, "
                          f"スループット {op_stats['throughput']:.2f} ops/sec")


class DataStructureBenchmark:
    """データ構造操作のベンチマークを実行するクラス"""
    
    def __init__(self, config: BenchmarkConfig, engine_type: str):
        """
        Args:
            config: ベンチマーク設定
            engine_type: エンジンタイプ（'Redis' または 'Valkey'）
        """
        self.config = config
        self.engine_type = engine_type
        self.client = self._create_client()
        self.operation_results = []
        
        # テスト対象のデータ構造を決定
        if self.config.data_structure == DataStructureType.ALL:
            self.data_structures = [ds for ds in DataStructureType if ds != DataStructureType.ALL]
        else:
            self.data_structures = [self.config.data_structure]
        
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
    
    def _get_key(self, ds_type: DataStructureType, index: int) -> str:
        """キー名を生成する"""
        return f"{self.config.key_prefix}{ds_type.value}:{index}"
    
    def _get_value(self, size: int) -> str:
        """値を生成する"""
        if self.config.random_values:
            return self._generate_random_value(size)
        else:
            # 固定パターンの値（サイズ分だけ繰り返し）
            pattern = "abcdefghij"
            repeats = size // len(pattern) + 1
            return (pattern * repeats)[:size]
    
    def _get_field_name(self, index: int) -> str:
        """ハッシュフィールド名を生成する"""
        return f"field:{index}"
    
    def _get_member_name(self, index: int) -> str:
        """セットメンバー名を生成する"""
        return f"member:{index}"
    
    def _get_score(self, index: int) -> float:
        """ソート済みセットのスコアを生成する"""
        return float(index)
    
    def prepare_data(self) -> None:
        """ベンチマーク用のデータを準備する"""
        print(f"データ準備中...")
        
        for ds_type in self.data_structures:
            print(f"{ds_type.value.upper()} データ構造の準備: {self.config.num_keys}キーを作成...")
            
            # パイプラインを使用してデータをバッチ処理
            batch_size = 100
            for i in range(0, self.config.num_keys, batch_size):
                pipe = self.client.pipeline()
                end = min(i + batch_size, self.config.num_keys)
                
                for j in range(i, end):
                    key = self._get_key(ds_type, j)
                    
                    if ds_type == DataStructureType.STRING:
                        # 文字列
                        value = self._get_value(self.config.element_size)
                        pipe.set(key, value)
                        
                    elif ds_type == DataStructureType.LIST:
                        # リスト
                        pipe.delete(key)  # 既存のリストをクリア
                        for k in range(self.config.elements_per_key):
                            value = self._get_value(self.config.element_size)
                            pipe.rpush(key, value)
                            
                    elif ds_type == DataStructureType.HASH:
                        # ハッシュ
                        pipe.delete(key)  # 既存のハッシュをクリア
                        hash_data = {}
                        for k in range(self.config.elements_per_key):
                            field = self._get_field_name(k)
                            value = self._get_value(self.config.element_size)
                            hash_data[field] = value
                        pipe.hset(key, mapping=hash_data)
                        
                    elif ds_type == DataStructureType.SET:
                        # セット
                        pipe.delete(key)  # 既存のセットをクリア
                        for k in range(self.config.elements_per_key):
                            member = self._get_member_name(k)
                            pipe.sadd(key, member)
                            
                    elif ds_type == DataStructureType.ZSET:
                        # ソート済みセット
                        pipe.delete(key)  # 既存のソート済みセットをクリア
                        for k in range(self.config.elements_per_key):
                            member = self._get_member_name(k)
                            score = self._get_score(k)
                            pipe.zadd(key, {member: score})
                
                pipe.execute()
                
                # 進捗表示
                progress = min(100, int((end / self.config.num_keys) * 100))
                print(f"\r進捗: {progress}% ({end}/{self.config.num_keys})", end='')
                
            print("\n完了")
    
    def cleanup_data(self) -> None:
        """ベンチマークで使用したデータを削除する"""
        print(f"データクリーンアップ中: {self.config.key_prefix}* のキーを削除...")
        keys = self.client.keys(f"{self.config.key_prefix}*")
        if keys:
            self.client.delete(*keys)
        print("クリーンアップ完了")
    
    def _perform_string_operation(self, is_read: bool, key: str) -> OperationResult:
        """文字列操作を実行する"""
        try:
            start_time = time.time()
            
            if is_read:
                # GET操作
                self.client.get(key)
                operation_type = "GET"
            else:
                # SET操作
                value = self._get_value(self.config.element_size)
                self.client.set(key, value)
                operation_type = "SET"
                
            end_time = time.time()
            elapsed = (end_time - start_time) * 1000  # ミリ秒に変換
            
            return OperationResult(
                operation_type=operation_type,
                data_structure=DataStructureType.STRING.value,
                duration_ms=elapsed,
                success=True
            )
        except Exception as e:
            return OperationResult(
                operation_type=operation_type if 'operation_type' in locals() else "UNKNOWN",
                data_structure=DataStructureType.STRING.value,
                duration_ms=0,
                success=False,
                error=str(e)
            )
    
    def _perform_list_operation(self, is_read: bool, key: str) -> OperationResult:
        """リスト操作を実行する"""
        try:
            start_time = time.time()
            
            if is_read:
                # ランダムに読み取り操作を選択
                op_choice = random.choice(["LRANGE", "LINDEX", "LLEN"])
                
                if op_choice == "LRANGE":
                    # リストの範囲を取得
                    start_idx = random.randint(0, max(0, self.config.elements_per_key - 10))
                    end_idx = min(start_idx + 9, self.config.elements_per_key - 1)
                    self.client.lrange(key, start_idx, end_idx)
                    operation_type = "LRANGE"
                elif op_choice == "LINDEX":
                    # リストの特定位置の要素を取得
                    index = random.randint(0, self.config.elements_per_key - 1)
                    self.client.lindex(key, index)
                    operation_type = "LINDEX"
                else:  # LLEN
                    # リストの長さを取得
                    self.client.llen(key)
                    operation_type = "LLEN"
            else:
                # ランダムに書き込み操作を選択
                op_choice = random.choice(["LPUSH", "RPUSH", "LPOP", "RPOP"])
                
                if op_choice == "LPUSH":
                    # リストの先頭に追加
                    value = self._get_value(self.config.element_size)
                    self.client.lpush(key, value)
                    operation_type = "LPUSH"
                elif op_choice == "RPUSH":
                    # リストの末尾に追加
                    value = self._get_value(self.config.element_size)
                    self.client.rpush(key, value)
                    operation_type = "RPUSH"
                elif op_choice == "LPOP":
                    # リストの先頭から削除
                    self.client.lpop(key)
                    operation_type = "LPOP"
                else:  # RPOP
                    # リストの末尾から削除
                    self.client.rpop(key)
                    operation_type = "RPOP"
                
            end_time = time.time()
            elapsed = (end_time - start_time) * 1000  # ミリ秒に変換
            
            return OperationResult(
                operation_type=operation_type,
                data_structure=DataStructureType.LIST.value,
                duration_ms=elapsed,
                success=True
            )
        except Exception as e:
            return OperationResult(
                operation_type=operation_type if 'operation_type' in locals() else "UNKNOWN",
                data_structure=DataStructureType.LIST.value,
                duration_ms=0,
                success=False,
                error=str(e)
            )
    
    def _perform_hash_operation(self, is_read: bool, key: str) -> OperationResult:
        """ハッシュ操作を実行する"""
        try:
            start_time = time.time()
            
            if is_read:
                # ランダムに読み取り操作を選択
                op_choice = random.choice(["HGET", "HMGET", "HGETALL", "HLEN"])
                
                if op_choice == "HGET":
                    # 単一フィールドの取得
                    field_idx = random.randint(0, self.config.elements_per_key - 1)
                    field = self._get_field_name(field_idx)
                    self.client.hget(key, field)
                    operation_type = "HGET"
                elif op_choice == "HMGET":
                    # 複数フィールドの取得
                    num_fields = min(10, self.config.elements_per_key)
                    fields = [self._get_field_name(random.randint(0, self.config.elements_per_key - 1)) 
                              for _ in range(num_fields)]
                    self.client.hmget(key, fields)
                    operation_type = "HMGET"
                elif op_choice == "HGETALL":
                    # すべてのフィールドと値を取得
                    self.client.hgetall(key)
                    operation_type = "HGETALL"
                else:  # HLEN
                    # フィールド数を取得
                    self.client.hlen(key)
                    operation_type = "HLEN"
            else:
                # ランダムに書き込み操作を選択
                op_choice = random.choice(["HSET", "HMSET", "HDEL"])
                
                if op_choice == "HSET":
                    # 単一フィールドの設定
                    field_idx = random.randint(0, self.config.elements_per_key - 1)
                    field = self._get_field_name(field_idx)
                    value = self._get_value(self.config.element_size)
                    self.client.hset(key, field, value)
                    operation_type = "HSET"
                elif op_choice == "HMSET":
                    # 複数フィールドの設定
                    num_fields = min(5, self.config.elements_per_key)
                    mapping = {}
                    for _ in range(num_fields):
                        field_idx = random.randint(0, self.config.elements_per_key - 1)
                        field = self._get_field_name(field_idx)
                        value = self._get_value(self.config.element_size)
                        mapping[field] = value
                    self.client.hset(key, mapping=mapping)  # redis-py 3.x では hmset の代わりに hset(mapping=) を使用
                    operation_type = "HMSET"
                else:  # HDEL
                    # フィールドの削除
                    field_idx = random.randint(0, self.config.elements_per_key - 1)
                    field = self._get_field_name(field_idx)
                    self.client.hdel(key, field)
                    operation_type = "HDEL"
                
            end_time = time.time()
            elapsed = (end_time - start_time) * 1000  # ミリ秒に変換
            
            return OperationResult(
                operation_type=operation_type,
                data_structure=DataStructureType.HASH.value,
                duration_ms=elapsed,
                success=True
            )
        except Exception as e:
            return OperationResult(
                operation_type=operation_type if 'operation_type' in locals() else "UNKNOWN",
                data_structure=DataStructureType.HASH.value,
                duration_ms=0,
                success=False,
                error=str(e)
            )
    
    def _perform_set_operation(self, is_read: bool, key: str) -> OperationResult:
        """セット操作を実行する"""
        try:
            start_time = time.time()
            
            if is_read:
                # ランダムに読み取り操作を選択
                op_choice = random.choice(["SMEMBERS", "SISMEMBER", "SCARD"])
                
                if op_choice == "SMEMBERS":
                    # すべてのメンバーを取得
                    self.client.smembers(key)
                    operation_type = "SMEMBERS"
                elif op_choice == "SISMEMBER":
                    # メンバーの存在確認
                    member_idx = random.randint(0, self.config.elements_per_key * 2 - 1)  # 存在しない可能性も含める
                    member = self._get_member_name(member_idx)
                    self.client.sismember(key, member)
                    operation_type = "SISMEMBER"
                else:  # SCARD
                    # メンバー数を取得
                    self.client.scard(key)
                    operation_type = "SCARD"
            else:
                # ランダムに書き込み操作を選択
                op_choice = random.choice(["SADD", "SREM"])
                
                if op_choice == "SADD":
                    # メンバーの追加
                    member_idx = random.randint(0, self.config.elements_per_key * 2 - 1)  # 既存メンバーの可能性も含める
                    member = self._get_member_name(member_idx)
                    self.client.sadd(key, member)
                    operation_type = "SADD"
                else:  # SREM
                    # メンバーの削除
                    member_idx = random.randint(0, self.config.elements_per_key - 1)
                    member = self._get_member_name(member_idx)
                    self.client.srem(key, member)
                    operation_type = "SREM"
                
            end_time = time.time()
            elapsed = (end_time - start_time) * 1000  # ミリ秒に変換
            
            return OperationResult(
                operation_type=operation_type,
                data_structure=DataStructureType.SET.value,
                duration_ms=elapsed,
                success=True
            )
        except Exception as e:
            return OperationResult(
                operation_type=operation_type if 'operation_type' in locals() else "UNKNOWN",
                data_structure=DataStructureType.SET.value,
                duration_ms=0,
                success=False,
                error=str(e)
            )
    
    def _perform_zset_operation(self, is_read: bool, key: str) -> OperationResult:
        """ソート済みセット操作を実行する"""
        try:
            start_time = time.time()
            
            if is_read:
                # ランダムに読み取り操作を選択
                op_choice = random.choice(["ZRANGE", "ZREVRANGE", "ZCARD", "ZSCORE"])
                
                if op_choice == "ZRANGE":
                    # 範囲を取得（スコア順）
                    start_idx = random.randint(0, max(0, self.config.elements_per_key - 10))
                    end_idx = min(start_idx + 9, self.config.elements_per_key - 1)
                    self.client.zrange(key, start_idx, end_idx)
                    operation_type = "ZRANGE"
                elif op_choice == "ZREVRANGE":
                    # 範囲を取得（逆スコア順）
                    start_idx = random.randint(0, max(0, self.config.elements_per_key - 10))
                    end_idx = min(start_idx + 9, self.config.elements_per_key - 1)
                    self.client.zrevrange(key, start_idx, end_idx)
                    operation_type = "ZREVRANGE"
                elif op_choice == "ZCARD":
                    # メンバー数を取得
                    self.client.zcard(key)
                    operation_type = "ZCARD"
                else:  # ZSCORE
                    # メンバーのスコアを取得
                    member_idx = random.randint(0, self.config.elements_per_key - 1)
                    member = self._get_member_name(member_idx)
                    self.client.zscore(key, member)
                    operation_type = "ZSCORE"
            else:
                # ランダムに書き込み操作を選択
                op_choice = random.choice(["ZADD", "ZREM", "ZINCRBY"])
                
                if op_choice == "ZADD":
                    # メンバーの追加
                    member_idx = random.randint(0, self.config.elements_per_key * 2 - 1)  # 既存メンバーの可能性も含める
                    member = self._get_member_name(member_idx)
                    score = random.uniform(0, 1000)
                    self.client.zadd(key, {member: score})
                    operation_type = "ZADD"
                elif op_choice == "ZREM":
                    # メンバーの削除
                    member_idx = random.randint(0, self.config.elements_per_key - 1)
                    member = self._get_member_name(member_idx)
                    self.client.zrem(key, member)
                    operation_type = "ZREM"
                else:  # ZINCRBY
                    # スコアの増加
                    member_idx = random.randint(0, self.config.elements_per_key - 1)
                    member = self._get_member_name(member_idx)
                    increment = random.uniform(-10, 10)
                    self.client.zincrby(key, increment, member)
                    operation_type = "ZINCRBY"
                
            end_time = time.time()
            elapsed = (end_time - start_time) * 1000  # ミリ秒に変換
            
            return OperationResult(
                operation_type=operation_type,
                data_structure=DataStructureType.ZSET.value,
                duration_ms=elapsed,
                success=True
            )
        except Exception as e:
            return OperationResult(
                operation_type=operation_type if 'operation_type' in locals() else "UNKNOWN",
                data_structure=DataStructureType.ZSET.value,
                duration_ms=0,
                success=False,
                error=str(e)
            )
    
    def _perform_operation(self, thread_id: int) -> List[OperationResult]:
        """スレッドごとの操作を実行する"""
        local_results = []
        
        # スレッド固有のクライアントを作成
        client = self._create_client()
        
        # パイプライン処理の準備
        use_pipeline = self.config.pipeline_size > 0
        if use_pipeline:
            pipe = client.pipeline(transaction=False)
            pipe_count = 0
            pipe_ops = []
        
        for i in range(self.config.operations_per_thread):
            # テスト対象のデータ構造をランダムに選択
            ds_type = random.choice(self.data_structures)
            
            # ランダムなキーを選択
            key_index = random.randint(0, self.config.num_keys - 1)
            key = self._get_key(ds_type, key_index)
            
            # 読み取り/書き込み比率に基づいて操作を決定
            is_read = random.random() < self.config.read_write_ratio
            
            # データ構造に応じた操作を実行
            if ds_type == DataStructureType.STRING:
                result = self._perform_string_operation(is_read, key)
            elif ds_type == DataStructureType.LIST:
                result = self._perform_list_operation(is_read, key)
            elif ds_type == DataStructureType.HASH:
                result = self._perform_hash_operation(is_read, key)
            elif ds_type == DataStructureType.SET:
                result = self._perform_set_operation(is_read, key)
            elif ds_type == DataStructureType.ZSET:
                result = self._perform_zset_operation(is_read, key)
            
            local_results.append(result)
        
        return local_results
    
    def run(self) -> BenchmarkResult:
        """ベンチマークを実行する"""
        print(f"\n===== {self.engine_type} データ構造ベンチマーク開始 =====")
        print(f"設定: {json.dumps(self.config.to_dict(), indent=2)}")
        
        # データ準備
        self.prepare_data()
        
        # ウォームアップ
        print("ウォームアップ中...")
        warmup_ops = min(1000, self.config.num_keys)
        for ds_type in self.data_structures:
            for i in range(min(100, warmup_ops)):
                key = self._get_key(ds_type, i % self.config.num_keys)
                
                if ds_type == DataStructureType.STRING:
                    self.client.get(key)
                elif ds_type == DataStructureType.LIST:
                    self.client.llen(key)
                elif ds_type == DataStructureType.HASH:
                    self.client.hlen(key)
                elif ds_type == DataStructureType.SET:
                    self.client.scard(key)
                elif ds_type == DataStructureType.ZSET:
                    self.client.zcard(key)
        
        # ベンチマーク実行
        print(f"ベンチマーク実行中: {self.config.num_threads}スレッド, "
              f"スレッドあたり{self.config.operations_per_thread}操作...")
        
        start_time = datetime.now()
        
        # スレッドプールを使用して並列実行
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.config.num_threads) as executor:
            futures = [executor.submit(self._perform_operation, i) for i in range(self.config.num_threads)]
            
            # 結果を収集
            for future in concurrent.futures.as_completed(futures):
                results = future.result()
                self.operation_results.extend(results)
        
        end_time = datetime.now()
        
        # 結果を作成
        result = BenchmarkResult(
            config=self.config,
            engine_type=self.engine_type,
            start_time=start_time,
            end_time=end_time,
            operation_results=self.operation_results
        )
        
        # クリーンアップ
        self.cleanup_data()
        
        return result


def parse_arguments():
    """コマンドライン引数をパースする"""
    parser = argparse.ArgumentParser(description='Redis/Valkey データ構造操作ベンチマーク')
    
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
    
    parser.add_argument('--data-structure', type=str, 
                        choices=['string', 'list', 'hash', 'set', 'zset', 'all'],
                        default='all',
                        help='テスト対象のデータ構造 (デフォルト: all)')
    
    parser.add_argument('--key-prefix', type=str, default='benchmark:ds:',
                        help='ベンチマークで使用するキーのプレフィックス (デフォルト: benchmark:ds:)')
    parser.add_argument('--num-keys', type=int, default=1000,
                        help='使用するキーの総数 (デフォルト: 1000)')
    parser.add_argument('--elements', type=int, default=100,
                        help='キーごとの要素数 (デフォルト: 100)')
    parser.add_argument('--element-size', type=int, default=100,
                        help='要素のサイズ（バイト） (デフォルト: 100)')
    
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
    
    # データ構造タイプを設定
    data_structure = DataStructureType(args.data_structure)
    
    # 設定を作成
    config = BenchmarkConfig(
        host=host,
        port=port,
        password=args.password,
        db=args.db,
        key_prefix=args.key_prefix,
        data_structure=data_structure,
        num_keys=args.num_keys,
        elements_per_key=args.elements,
        element_size=args.element_size,
        num_threads=args.num_threads,
        operations_per_thread=args.operations,
        read_write_ratio=args.read_ratio,
        random_values=args.random_values,
        pipeline_size=args.pipeline
    )
    
    # エンジンタイプを設定
    engine_type = args.engine.capitalize()  # 'redis' -> 'Redis', 'valkey' -> 'Valkey'
    
    # ベンチマークを実行
    benchmark = DataStructureBenchmark(config, engine_type)
    result = benchmark.run()
    
    # 結果を表示
    result.print_summary()
    
    # 結果をファイルに保存（指定されている場合）
    if args.output:
        result.save_to_file(args.output)
        print(f"\n結果を {args.output} に保存しました")


if __name__ == "__main__":
    main()
