"""
ChatBI FastAPI 服务
- 同步接口：POST /chatbi
- 异步接口：POST /chatbi/async + GET /chatbi/status/{task_id}
"""
import os
import uuid
import time
from celery_app import celery_app, _save_task, _load_task
from tools.cache import get_cached, set_cached, clear_cache, get_client
from tools.session import get_history, append_turn, clear_session, clear_all_sessions
from agents.query_rewriter import rewrite_query
from typing import Optional
from fastapi import FastAPI, HTTPException
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
class AsyncResponse(BaseModel):
    task_id: str
    status: str
class StatusResponse(BaseModel):
    task_id: str
    status: str  # pending / running / done / failed
    result: Optional[dict] = None
    error: Optional[str] = None
    elapsed: Optional[float] = None
# ==================== 同步接口 ====================
@app.post("/chatbi", response_model=AskResponse)
def chatbi_sync(req: AskRequest):
    """同步分析：支持多轮对话"""
    trace_id = uuid.uuid4().hex[:8]
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
        return AskResponse(**cached)
    try:
        result = run(effective_question, trace_id=trace_id)
    except Exception as e:
        logger.error(f"[API] 分析失败 [trace={trace_id}]: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    elapsed = time.time() - start
    response_data = {
        "question": result["question"],
        "analysis": result["analysis"],
        "task_count": result["task_count"],
        "layers": result["layers"],
        "report": result["report"],
    }
    set_cached(effective_question, response_data)
    if req.session_id:
        append_turn(req.session_id, req.question, effective_question, result["analysis"])
    return AskResponse(**response_data, elapsed=round(elapsed, 2))
# ==================== 异步接口 ====================
@app.post("/chatbi/stream")
def chatbi_stream(req: AskRequest):
    trace_id = uuid.uuid4().hex[:8]
    logger.info(f"[API] 流式请求 [trace={trace_id}]: {req.question} | session: {req.session_id}")
    history = get_history(req.session_id) if req.session_id else []
    effective_question = rewrite_query(req.question, history, trace_id=trace_id)
    cached = get_cached(effective_question)
    if cached:
        if req.session_id:
            append_turn(req.session_id, req.question, effective_question, cached["analysis"])
        def _cached_stream():
            yield sse_event("cached", cached)
            yield sse_event("done", {})
        return StreamingResponse(_cached_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
    def _stream_with_session():
        analysis_text = ""
        for event in run_stream(effective_question, trace_id=trace_id):
            # 从 analysis_done 事件里提取答案，用于存历史
            if '"type": "analysis_done"' in event or '"type":"analysis_done"' in event:
                try:
                    import json as _json
                    data = _json.loads(event[6:].strip())
                    analysis_text = data.get("analysis", "")
                except Exception:
                    pass
            yield event
        if req.session_id and analysis_text:
            append_turn(req.session_id, req.question, effective_question, analysis_text)
    return StreamingResponse(
        _stream_with_session(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )
@app.post("/chatbi/async", response_model=AsyncResponse)
def chatbi_async(req: AskRequest):
    """异步分析：立即返回 task_id，丢进 Celery 队列"""
    task_id = str(uuid.uuid4())
    trace_id = uuid.uuid4().hex[:8]
    _save_task(task_id, {
        "status": "pending",
        "question": req.question,
        "result": None,
        "error": None,
        "trace_id": trace_id,
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
# ==================== 根路径 ====================
@app.get("/")
def root():
    return {
        "service": "ChatBI 多智能体数据分析系统",
        "endpoints": ["/chatbi", "/chatbi/async", "/chatbi/status/{task_id}","/chatbi/stream","/upload_data"]
    }
# ==================== 启动 ====================
if __name__ == "__main__":
    import uvicorn
    print("🚀 启动 ChatBI 服务...")
    print("📡 访问地址: http://127.0.0.1:8001")
    print("📖 接口文档: http://127.0.0.1:8001/docs")
    uvicorn.run(app, host="0.0.0.0", port=8001)