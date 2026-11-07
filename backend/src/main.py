"""
ChatBI FastAPI 服务
- 同步接口：POST /chatbi
- 异步接口：POST /chatbi/async + GET /chatbi/status/{task_id}
"""
import os
import json
import uuid
import time
from celery_app import celery_app, _save_task, _load_task
from tools.cache import get_cached, set_cached, clear_cache, get_client
from tools.session import get_history, append_turn, clear_session, clear_all_sessions
from tools.audit import (
    record_query, record_feedback, recent_queries, summarize_results, summarize_tables, REASON_TYPES
)
from agents.query_rewriter import rewrite_query
from typing import Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from logger import logger, fmt_trace
from fastapi import File, UploadFile
from tools.data_loader import load_file
from fastapi.responses import StreamingResponse
from agents.orchestrator import run, run_stream, sse_event
import shutil
import tempfile
app = FastAPI(title="ChatBI 多智能体数据分析系统", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# ==================== 请求/响应模型 ====================
class AskRequest(BaseModel):
    question: str
    session_id: Optional[str] = None
class AskResponse(BaseModel):
    question: str
    analysis: str
    task_count: int
    layers: int
    report: dict
    elapsed: float
    trace_id: Optional[str] = None  # 与审计日志关联，前端反馈时回传
class AsyncResponse(BaseModel):
    task_id: str
    status: str
class StatusResponse(BaseModel):
    task_id: str
    status: str  # pending / running / done / failed
    result: Optional[dict] = None
    error: Optional[str] = None
    elapsed: Optional[float] = None
class FeedbackRequest(BaseModel):
    question: str
    reason_type: str            # 口径不对 / 答非所问 / SQL 有误 / 数据不对 / 其他
    answer: Optional[str] = ""
    note: Optional[str] = ""
    sql: Optional[str] = ""
    trace_id: Optional[str] = None
    session_id: Optional[str] = None
# ==================== 同步接口 ====================
@app.post("/chatbi", response_model=AskResponse)
def chatbi_sync(req: AskRequest, request: Request):
    """同步分析：支持多轮对话"""
    trace_id = uuid.uuid4().hex[:8]
    client_ip = request.client.host if request.client else ""
    logger.info(f"[API] 同步请求 [trace={trace_id}]: {req.question} | session: {req.session_id}")
    start = time.time()
    history = get_history(req.session_id) if req.session_id else []
    effective_question = rewrite_query(req.question, history, trace_id=trace_id)
    cached = get_cached(effective_question)
    if cached:
        cached["elapsed"] = round(time.time() - start, 2)
        # 缓存命中也要更新会话历史
        if req.session_id:
            append_turn(req.session_id, req.question, effective_question, cached["analysis"])
        cached["trace_id"] = trace_id
        record_query(
            trace_id=trace_id, question=req.question, effective_question=effective_question,
            session_id=req.session_id or "", cache_hit=True, success=True,
            elapsed=cached["elapsed"], task_count=cached.get("task_count", 0),
            layers=cached.get("layers", 0),
            sqls=summarize_tables(cached.get("report", {}).get("tables", [])),
            client_ip=client_ip
        )
        return AskResponse(**cached)
    try:
        result = run(effective_question, trace_id=trace_id)
    except Exception as e:
        record_query(
            trace_id=trace_id, question=req.question, effective_question=effective_question,
            session_id=req.session_id or "", success=False,
            elapsed=time.time() - start, client_ip=client_ip,
            error=f"{type(e).__name__}: {e}"
        )
        logger.error(f"[API] 分析失败 [trace={trace_id}]: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    elapsed = time.time() - start
    response_data = {
        "question": result["question"],
        "analysis": result["analysis"],
        "task_count": result["task_count"],
        "layers": result["layers"],
        "report": result["report"],
        "trace_id": trace_id,
    }
    record_query(
        trace_id=trace_id, question=req.question, effective_question=effective_question,
        session_id=req.session_id or "", cache_hit=False, success=True,
        elapsed=elapsed, task_count=result["task_count"], layers=result["layers"],
        sqls=summarize_results(result["results"]), client_ip=client_ip
    )
    set_cached(effective_question, response_data)
    if req.session_id:
        append_turn(req.session_id, req.question, effective_question, result["analysis"])
    return AskResponse(**response_data, elapsed=round(elapsed, 2))
# ==================== 异步接口 ====================
@app.post("/chatbi/stream")
def chatbi_stream(req: AskRequest, request: Request):
    trace_id = uuid.uuid4().hex[:8]
    client_ip = request.client.host if request.client else ""
    logger.info(f"[API] 流式请求 [trace={trace_id}]: {req.question} | session: {req.session_id}")
    start = time.time()
    history = get_history(req.session_id) if req.session_id else []
    effective_question = rewrite_query(req.question, history, trace_id=trace_id)
    cached = get_cached(effective_question)
    if cached:
        if req.session_id:
            append_turn(req.session_id, req.question, effective_question, cached["analysis"])
        cached["trace_id"] = trace_id
        record_query(
            trace_id=trace_id, question=req.question, effective_question=effective_question,
            session_id=req.session_id or "", cache_hit=True, success=True,
            elapsed=time.time() - start, task_count=cached.get("task_count", 0),
            layers=cached.get("layers", 0),
            sqls=summarize_tables(cached.get("report", {}).get("tables", [])),
            client_ip=client_ip
        )
        def _cached_stream():
            yield sse_event("cached", cached)
            yield sse_event("done", {})
        return StreamingResponse(_cached_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
    def _stream_with_session():
        analysis_text = ""
        report = {}
        task_count = 0
        layer_count = 0
        ok = True
        error_text = ""
        try:
            for event in run_stream(effective_question, trace_id=trace_id):
                payload = event[6:].strip() if event.startswith("data:") else ""
                parsed = None
                if payload:
                    try:
                        parsed = json.loads(payload)
                    except Exception:
                        parsed = None
                if parsed:
                    etype = parsed.get("type")
                    if etype == "analysis_done":
                        analysis_text = parsed.get("analysis", "")
                    elif etype == "report_done":
                        report = parsed.get("report") or {}
                        task_count = report.get("task_count", 0) or 0
                    elif etype == "layers_done":
                        layer_count = parsed.get("layer_count", 0) or 0
                yield event
        except Exception as e:
            ok = False
            error_text = f"{type(e).__name__}: {e}"
            raise
        finally:
            record_query(
                trace_id=trace_id, question=req.question, effective_question=effective_question,
                session_id=req.session_id or "", cache_hit=False, success=ok,
                elapsed=time.time() - start, task_count=task_count, layers=layer_count,
                sqls=summarize_tables(report.get("tables", [])),
                client_ip=client_ip, error=error_text
            )
            if req.session_id and analysis_text:
                append_turn(req.session_id, req.question, effective_question, analysis_text)
    return StreamingResponse(
        _stream_with_session(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )
@app.post("/chatbi/async", response_model=AsyncResponse)
def chatbi_async(req: AskRequest, request: Request):
    """异步分析：立即返回 task_id，丢进 Celery 队列"""
    task_id = str(uuid.uuid4())
    trace_id = uuid.uuid4().hex[:8]
    client_ip = request.client.host if request.client else ""
    _save_task(task_id, {
        "status": "pending",
        "question": req.question,
        "result": None,
        "error": None,
        "trace_id": trace_id,
        "client_ip": client_ip,
        "created_at": time.time()
    })
    try:
        # trace_id 跨进程无法靠 contextvars 传递，只能作为任务参数显式带过去
        celery_app.send_task("chatbi.run_analysis", args=[task_id, req.question, trace_id])
    except Exception as e:
        import traceback
        logger.error(f"[API] {fmt_trace(trace_id)}Celery 投递失败: {type(e).__name__}: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Celery 投递失败: {type(e).__name__}: {e}")
    logger.info(f"[API] {fmt_trace(trace_id)}异步请求 {task_id}: {req.question}")
    return AsyncResponse(task_id=task_id, status="pending")
@app.get("/chatbi/status/{task_id}", response_model=StatusResponse)
def chatbi_status(task_id: str):
    """查询异步任务状态"""
    task = _load_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    elapsed = task.get("elapsed") if task["status"] == "done" else None
    return StatusResponse(
        task_id=task_id,
        status=task["status"],
        result=task.get("result"),
        error=task.get("error"),
        elapsed=elapsed
    )
@app.post("/upload_data")
async def upload_data(file: UploadFile = File(...), session_id: str = None):
    """上传 CSV/Excel，自动建表并导入"""
    suffix = os.path.splitext(file.filename)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name
    try:
        result = load_file(tmp_path, original_filename=file.filename)
        clear_cache()
        if session_id:
            clear_session(session_id)
            logger.info(f"[API] 上传后清空会话: {session_id}")
        else:
            clear_all_sessions()
            logger.info(f"[API] 上传后清空所有会话")
        return {
            "success": True,
            "message": f"上传成功，共 {result['rows']} 行",
            **result
        }
    except Exception as e:
        logger.error(f"[API] 上传失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        os.unlink(tmp_path)
# ==================== 审计与反馈 ====================
@app.post("/feedback")
def submit_feedback(req: FeedbackRequest, request: Request):
    """记录一条判错反馈，返回反馈编号（前端「这条答得不对」用）"""
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="question 不能为空")
    if req.reason_type not in REASON_TYPES:
        raise HTTPException(status_code=400, detail=f"reason_type 必须是 {list(REASON_TYPES)} 之一")
    client_ip = request.client.host if request.client else ""
    feedback_id = record_feedback(
        question=req.question.strip(), reason_type=req.reason_type,
        answer=req.answer or "", note=req.note or "", sql=req.sql or "",
        trace_id=req.trace_id or "", session_id=req.session_id or "",
        client_ip=client_ip
    )
    logger.info(f"[API] 收到反馈 {feedback_id} [{req.reason_type}]: {req.question}")
    return {"success": True, "feedback_id": feedback_id}
@app.get("/audit/queries")
def audit_queries(limit: int = 20):
    """最近的查询审计（倒序），用于排查 bad case"""
    return recent_queries(limit)
# ==================== 根路径 ====================
@app.get("/")
def root():
    return {
        "service": "ChatBI 多智能体数据分析系统",
        "endpoints": [
            "/chatbi", "/chatbi/async", "/chatbi/status/{task_id}", "/chatbi/stream",
            "/upload_data", "/feedback", "/audit/queries"
        ]
    }
# ==================== 启动 ====================
if __name__ == "__main__":
    import uvicorn
    print("🚀 启动 ChatBI 服务...")
    print("📡 访问地址: http://127.0.0.1:8001")
    print("📖 接口文档: http://127.0.0.1:8001/docs")
    uvicorn.run(app, host="0.0.0.0", port=8001)