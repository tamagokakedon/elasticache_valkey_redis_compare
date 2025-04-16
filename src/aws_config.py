#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AWS Elasticache Redis vs Valkey 性能比較
AWS設定ファイル読み込みモジュール
"""

import os
import json
from typing import Dict, Any, Optional


def load_aws_endpoints() -> Dict[str, Dict[str, Any]]:
    """
    AWS Elasticacheエンドポイント設定を読み込む

    Returns:
        Dict[str, Dict[str, Any]]: エンジンタイプごとのエンドポイント情報
    """
    # 設定ファイルのパスを決定
    config_paths = [
        # カレントディレクトリの設定ファイル
        os.path.join(os.getcwd(), 'config', 'aws_endpoints.json'),
        # スクリプトディレクトリの設定ファイル
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config', 'aws_endpoints.json'),
        # ホームディレクトリの設定ファイル
        os.path.join(os.path.expanduser('~'), '.aws', 'elasticache_endpoints.json')
    ]
    
    # 設定ファイルを探索
    for config_path in config_paths:
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    endpoints = json.load(f)
                    print(f"AWS Elasticacheエンドポイント設定を読み込みました: {config_path}")
                    return endpoints
            except Exception as e:
                print(f"設定ファイルの読み込みに失敗しました: {config_path} - {e}")
    
    # デフォルト設定
    print("AWS Elasticacheエンドポイント設定が見つからないため、デフォルト設定を使用します")
    return {
        "redis": {
            "host": "localhost",
            "port": 6379
        },
        "valkey": {
            "host": "localhost",
            "port": 6380
        }
    }


def get_endpoint(engine_type: str) -> Dict[str, Any]:
    """
    指定されたエンジンタイプのエンドポイント情報を取得する

    Args:
        engine_type (str): エンジンタイプ ('redis' または 'valkey')

    Returns:
        Dict[str, Any]: エンドポイント情報
    """
    endpoints = load_aws_endpoints()
    
    if engine_type.lower() in endpoints:
        return endpoints[engine_type.lower()]
    else:
        raise ValueError(f"不明なエンジンタイプです: {engine_type}")


if __name__ == "__main__":
    # テスト用コード
    print("Redis エンドポイント:", get_endpoint("redis"))
    print("Valkey エンドポイント:", get_endpoint("valkey"))
