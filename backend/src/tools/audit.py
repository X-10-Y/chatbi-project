"""
查询审计与结果反馈

- 审计：谁在什么时候问了什么、生成了哪些 SQL、返回几行、耗时、是否缓存命中、成败
- 反馈：用户标记「口径不对 / 答非所问 / SQL 有误」，用于 bad case 复盘

单机演示形态，落盘为追加写 JSONL（默认 data/audit、data/feedback，已在 .gitignore 中）。
审计写入失败不影响主流程，只记日志。
"""
import json
import os
import threading
import uuid
from datetime import datetime

from config import PROJECT_ROOT
from logger import logger

# 可用 AUDIT_DIR 覆盖落盘目录（测试时指到临时目录，避免污染运行数据）
_DATA_ROOT = os.getenv("AUDIT_DIR", os.path.join(PROJECT_ROOT, "data"))
AUDIT_PATH = os.path.join(_DATA_ROOT, "audit", "queries.jsonl")
FEEDBACK_PATH = os.path.join(_DATA_ROOT, "feedback", "feedback.jsonl")

_WRITE_LOCK = threading.Lock()
_MAX_SQL_LEN = 2000
_MAX_TEXT_LEN = 4000

# 反馈类型白名单，和前端下拉选项保持一致
REASON_TYPES = ("口径不对", "答非所问", "SQL 有误", "数据不对", "其他")


def _now() -> str:
    """带时区的本地时间，便于和日志对照"""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _append(path: str, record: dict):
    """追加一行 JSON；失败只记日志，不影响业务"""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with _WRITE_LOCK:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error(f"[Audit] 写入失败 {path}: {e}")


def _summarize(item: dict) -> dict:
    """统一裁剪单个 SQL 任务，失败任务也保留错误信息"""
    return {
        "task_id": item.get("task_id"),
        "description": (item.get("description") or "")[:200],
        "sql": (item.get("sql") or "")[:_MAX_SQL_LEN],
        "success": bool(item.get("success")),
        "rows": len(item.get("data") or []),
        "sql_retry": item.get("sql_retry", 0),
        "critic_retry": item.get("critic_retry", 0),
        "error": (item.get("error") or "")[:200],
    }


def summarize_results(results: list) -> list:
    """把 orchestrator.run() 的 results 压成审计字段"""
    return [_summarize(r) for r in (results or [])]


def summarize_tables(tables: list) -> list:
    """缓存命中时只有 report.tables，没有重试信息，缺省为 0"""
    return [_summarize(t) for t in (tables or [])]


def record_query(*, trace_id: str, question: str, effective_question: str = "",
                 session_id: str = "", cache_hit: bool = False, success: bool = True,
                 elapsed: float = 0.0, task_count: int = 0, layers: int = 0,
                 sqls: list = None, client_ip: str = "", error: str = ""):
    """记录一次查询。sqls 由 summarize_results / summarize_tables 生成"""
    _append(AUDIT_PATH, {
        "ts": _now(),
        "trace_id": trace_id,
        "session_id": session_id,
        "client_ip": client_ip,
        "question": question,
        "effective_question": effective_question,
        "cache_hit": cache_hit,
        "success": success,
        "elapsed": round(elapsed, 2),
        "task_count": task_count,
        "layers": layers,
        "sqls": sqls or [],
        "error": error[:500],
    })


def record_feedback(*, question: str, reason_type: str, answer: str = "", note: str = "",
                    sql: str = "", trace_id: str = "", session_id: str = "",
                    client_ip: str = "") -> str:
    """记录一条判错反馈，返回反馈编号"""
    feedback_id = uuid.uuid4().hex[:8]
    _append(FEEDBACK_PATH, {
        "feedback_id": feedback_id,
        "ts": _now(),
        "trace_id": trace_id,
        "session_id": session_id,
        "client_ip": client_ip,
        "question": question,
        "answer": (answer or "")[:_MAX_TEXT_LEN],
        "reason_type": reason_type,
        "note": note[:1000],
        "sql": (sql or "")[:_MAX_SQL_LEN],
    })
    return feedback_id


def recent_queries(limit: int = 20) -> dict:
    """读取最近 N 条查询审计（倒序），用于排查和演示"""
    limit = max(1, min(int(limit), 100))
    if not os.path.exists(AUDIT_PATH):
        return {"total": 0, "items": []}
    try:
        with _WRITE_LOCK:
            with open(AUDIT_PATH, "r", encoding="utf-8") as f:
                lines = [ln for ln in f.readlines() if ln.strip()]
        items = [json.loads(ln) for ln in lines[-limit:]]
        items.reverse()
        return {"total": len(lines), "items": items}
    except Exception as e:
        logger.error(f"[Audit] 读取失败 {AUDIT_PATH}: {e}")
        return {"total": 0, "items": []}
