"""
Celery 应用配置 + 任务定义
task 和 app 在同一个模块，避免跨模块绑定到默认 app 的问题
"""
import os
import sys
_PROJECT_SRC = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_SRC not in sys.path:
    sys.path.insert(0, _PROJECT_SRC)
os.environ.setdefault("FORKED_BY_MULTIPROCESSING", "1")   # Windows 必需
import json
import time
from celery import Celery
from config import REDIS_HOST, REDIS_PORT
celery_app = Celery(
    "chatbi",
    broker=f"redis://{REDIS_HOST}:{REDIS_PORT}/1",
    backend=f"redis://{REDIS_HOST}:{REDIS_PORT}/2",
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    # 单任务软/硬超时，避免 worker 卡死时任务永远停在 running
    # 注意：时间限制依赖 SIGUSR1，Windows 下不生效，仅 Linux 生产环境有效
    task_soft_time_limit=300,
    task_time_limit=360,
)
# ==================== 任务状态 Redis 辅助 ====================
TASK_PREFIX = "chatbi:task:"
TASK_TTL = 3600
def _save_task(task_id: str, data: dict):
    from tools.cache import get_client
    from logger import logger
    try:
        get_client().setex(
            f"{TASK_PREFIX}{task_id}", TASK_TTL,
            json.dumps(data, ensure_ascii=False)
        )
    except Exception as e:
        logger.error(f"[Task] 写入失败: {e}")
def _load_task(task_id: str) -> dict:
    from tools.cache import get_client
    from logger import logger
    try:
        raw = get_client().get(f"{TASK_PREFIX}{task_id}")
        return json.loads(raw) if raw else None
    except Exception as e:
        logger.error(f"[Task] 读取失败: {e}")
        return None
# ==================== 任务定义 ====================
@celery_app.task(
    bind=True,
    name="chatbi.run_analysis",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=2
)
def _run_task(self, task_id: str, question: str, trace_id: str = None):
    from agents.orchestrator import run
    from logger import logger, fmt_trace
    from tools.audit import record_query, summarize_results
    task = _load_task(task_id) or {}
    # 兼容旧版本投递的任务（args 里没有 trace_id 时从任务记录里补）
    trace_id = trace_id or task.get("trace_id")
    task["status"] = "running"
    _save_task(task_id, task)
    start = time.time()
    logger.info(f"[API] {fmt_trace(trace_id)}异步任务 {task_id} 开始: {question}")
    try:
        result = run(question, trace_id=trace_id)
        task["status"] = "done"
        task["finished_at"] = time.time()
        created_at = task.get("created_at", start)
        task["elapsed"] = round(task["finished_at"] - created_at, 2)
        task["result"] = {
            "question": result["question"],
            "analysis": result["analysis"],
            "task_count": result["task_count"],
            "layers": result["layers"],
            "report": result["report"],
            "elapsed": round(time.time() - start, 2)
        }
        _save_task(task_id, task)
        # Worker 进程内写审计，trace_id 与接口返回一致，便于跨进程复盘
        record_query(
            trace_id=trace_id or "", question=question, effective_question=question,
            session_id="", cache_hit=False, success=True,
            elapsed=task["elapsed"], task_count=result["task_count"], layers=result["layers"],
            sqls=summarize_results(result["results"]),
            client_ip=task.get("client_ip", "")
        )
        logger.info(f"[API] {fmt_trace(trace_id)}异步任务 {task_id} 完成")
    except Exception as e:
        task["status"] = "failed"
        task["error"] = str(e)
        _save_task(task_id, task)
        record_query(
            trace_id=trace_id or "", question=question, effective_question=question,
            session_id="", cache_hit=False, success=False,
            elapsed=time.time() - start, client_ip=task.get("client_ip", ""),
            error=f"{type(e).__name__}: {e}"
        )
        logger.error(f"[API] {fmt_trace(trace_id)}异步任务 {task_id} 失败: {e}")
        # 抛出以触发 autoretry（最多 2 次，指数退避）
        raise