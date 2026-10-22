"""
Redis 缓存层：缓存高频查询的分析结果
key = 数据集版本 + 问题的 MD5（换数据集/表结构变化后自动失效）
value = 完整分析结果 JSON
"""
import os
import json
import time
import hashlib
import redis
from config import (REDIS_HOST, REDIS_PORT, REDIS_DB, CACHE_TTL,
                    DB_TYPE, DB_PATH)
from logger import logger
_client = None
_version_cache = {"value": "", "ts": 0.0}
_DATASET_ID = os.getenv("DATASET_ID", "default")
def get_client():
    global _client
    if _client is None:
        _client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            decode_responses=True
        )
    return _client
def _dataset_version() -> str:
    """数据集版本：数据文件或表结构变化时让旧缓存自动失效"""
    now = time.time()
    if _version_cache["value"] and now - _version_cache["ts"] < 60:
        return _version_cache["value"]
    try:
        if DB_TYPE == "mysql":
            from tools.sql_runner import get_table_names
            signature = ",".join(sorted(get_table_names()))
        else:
            stat = os.stat(DB_PATH)
            signature = f"{int(stat.st_mtime)}:{stat.st_size}"
    except Exception:
        signature = "unknown"
    _version_cache["value"] = f"{DB_TYPE}:{_DATASET_ID}:{signature}"
    _version_cache["ts"] = now
    return _version_cache["value"]
def _make_key(question: str) -> str:
    """把数据集版本和问题一起转成缓存 key"""
    raw = f"{_dataset_version()}|{question}"
    return "chatbi:" + hashlib.md5(raw.encode("utf-8")).hexdigest()
def get_cached(question: str) -> dict:
    """查缓存，命中返回 dict，未命中返回 None"""
    try:
        client = get_client()
        raw = client.get(_make_key(question))
        if raw:
            logger.info(f"[Cache] 命中: {question[:30]}")
            return json.loads(raw)
        logger.info(f"[Cache] 未命中: {question[:30]}")
        return None
    except Exception as e:
        logger.warning(f"[Cache] 查询失败，跳过缓存: {e}")
        return None
def set_cached(question: str, result: dict):
    """写入缓存"""
    try:
        client = get_client()
        client.setex(
            _make_key(question),
            CACHE_TTL,
            json.dumps(result, ensure_ascii=False)
        )
        logger.info(f"[Cache] 已写入: {question[:30]}")
    except Exception as e:
        logger.warning(f"[Cache] 写入失败: {e}")
def clear_cache():
    """清空所有 chatbi 缓存"""
    try:
        client = get_client()
        count = 0
        for key in client.scan_iter(match="chatbi:*", count=100):
            client.delete(key)
            count += 1
        logger.info(f"[Cache] 已清空 {count} 条缓存")
    except Exception as e:
        logger.warning(f"[Cache] 清空失败: {e}")