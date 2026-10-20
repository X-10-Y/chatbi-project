"""
会话历史存储：用 Redis 存多轮对话历史
key = chatbi:session:{session_id}
value = JSON 列表，每项 {question, rewritten, answer}
"""
import json
from tools.cache import get_client
from logger import logger
SESSION_PREFIX = "chatbi:session:"
SESSION_TTL = 3600      # 会话保留 1 小时
MAX_TURNS = 3           # 只保留最近 3 轮
def get_history(session_id: str) -> list:
    """读会话历史，不存在返回空列表"""
    if not session_id:
        return []
    try:
        raw = get_client().get(f"{SESSION_PREFIX}{session_id}")
        return json.loads(raw) if raw else []
    except Exception as e:
        logger.warning(f"[Session] 读取失败: {e}")
        return []
def append_turn(session_id: str, question: str, rewritten: str, answer: str):
    """追加一轮对话，只保留最近 MAX_TURNS 轮"""
    if not session_id:
        return
    try:
        history = get_history(session_id)
        history.append({
            "question": question,
            "rewritten": rewritten,
            "answer": answer[:500]    # 答案截断，避免占太多空间
        })
        history = history[-MAX_TURNS:]
        get_client().setex(
            f"{SESSION_PREFIX}{session_id}",
            SESSION_TTL,
            json.dumps(history, ensure_ascii=False)
        )
    except Exception as e:
        logger.warning(f"[Session] 写入失败: {e}")
def clear_session(session_id: str):
    """清空会话历史"""
    if not session_id:
        return
    try:
        get_client().delete(f"{SESSION_PREFIX}{session_id}")
    except Exception as e:
        logger.warning(f"[Session] 清空失败: {e}")
def clear_all_sessions():
    """清空所有会话（谨慎使用）"""
    try:
        client = get_client()
        count = 0
        for key in client.scan_iter(match=f"{SESSION_PREFIX}*", count=100):
            client.delete(key)
            count += 1
        logger.info(f"[Session] 已清空 {count} 个会话")
    except Exception as e:
        logger.warning(f"[Session] 清空失败: {e}")