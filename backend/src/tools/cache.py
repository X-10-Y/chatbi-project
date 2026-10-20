"""
Redis 缓存层：缓存高频查询的分析结果
key = 问题的 MD5
value = 完整分析结果 JSON
"""
import json
import hashlib
import redis
from config import REDIS_HOST, REDIS_PORT, REDIS_DB, CACHE_TTL
from logger import logger
_client = None
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
def _make_key(question: str) -> str:
    """把问题转成缓存 key"""
    return "chatbi:" + hashlib.md5(question.encode("utf-8")).hexdigest()
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