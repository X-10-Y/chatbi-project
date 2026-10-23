"""
Orchestrator：多智能体编排器
整合 Planner + Executor + Critic + Analyst + Reporter
支持任务依赖调度（DAG 分层执行）
"""
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI
from config import LLM_MODEL, LLM_BASE_URL, LLM_API_KEY
from agents.planner import plan
from agents.executor import execute
from agents.analyst import analyze
from agents.reporter import generate_report
from logger import logger, log_tokens, fmt_trace
MAX_CONCURRENT = 5
def build_layers(tasks: list) -> list:
    """
    按 depends_on 把任务分成多层
    返回：[[层1任务], [层2任务], ...]
    """
    task_map = {t.id: t for t in tasks}
    completed = set()
    layers = []
    remaining = set(task_map.keys())
    while remaining:
        current_layer = [
            task_map[tid] for tid in remaining
            if all(dep in completed for dep in task_map[tid].depends_on)
        ]
        if not current_layer:
            logger.error(f"[Orchestrator] 检测到循环依赖: {remaining}")
            current_layer = [task_map[tid] for tid in remaining]
        layers.append(current_layer)
        for task in current_layer:
            completed.add(task.id)
            remaining.discard(task.id)
    return layers
# ==================== 综合型任务：文本归纳 ====================
def synthesize(task, dep_results: dict, trace_id: str = None) -> dict:
    """
    综合型任务：直接文本综合，不走 SQL
    把前置任务的数据丢给 LLM，让它归纳结论
    """
    # 收集前置结果
    context_parts = []
    for dep_id, dep_result in dep_results.items():
        if dep_result and dep_result.get("success"):
            data = dep_result.get("data", [])
            context_parts.append(
                f"任务{dep_id}（{dep_result.get('description', '')}）结果：\n"
                f"{json.dumps(data[:20], ensure_ascii=False, indent=2)}"
            )
    if not context_parts:
        logger.warning(f"{fmt_trace(trace_id)}[Orchestrator] 任务 {task.id} 没有可用的前置结果")
        return {
            "task_id": task.id,
            "description": task.description,
            "depends_on": task.depends_on,
            "is_aggregate": True,
            "success": False,
            "error": "没有可用的前置结果",
            "data": [],
            "columns": [],
            "sql": "(综合型任务)",
            "warning": "",
            "sql_retry": 0,
            "critic_retry": 0
        }
    context = "\n\n".join(context_parts)
    prompt = f"""你是一个数据分析专家。请根据以下各维度的查询结果，综合回答用户的任务。
【任务描述】
{task.description}
【各维度数据】
{context}
要求：
1. 用简洁的中文，200-400 字
2. 引用具体数据支撑结论
3. 综合多个维度，不要单独罗列
4. 如果数据不足以回答，明确说明
分析结论："""
    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=800
    )
    log_tokens("综合归纳", resp, trace_id=trace_id)
    analysis = resp.choices[0].message.content.strip()
    logger.info(f"{fmt_trace(trace_id)}[Orchestrator] 任务 {task.id} 文本综合完成，长度 {len(analysis)} 字")
    return {
        "task_id": task.id,
        "description": task.description,
        "depends_on": task.depends_on,
        "is_aggregate": True,
        "success": True,
        "sql": "(综合型任务，直接文本归纳，未生成 SQL)",
        "data": [{"综合结论": analysis}],
        "columns": ["综合结论"],
        "error": "",
        "warning": "",
        "sql_retry": 0,
        "critic_retry": 0
    }
# ==================== 筛选型任务：SQL 流程 ====================
def run_sql_task(task, dep_results: dict, trace_id: str = None) -> dict:
    """筛选型任务：走 SQL 生成 → 执行 → Critic 校验"""
    # 从前置结果提取"已知事实"
    facts_text = ""
    if dep_results:
        facts = []
        for dep_id, dep_result in dep_results.items():
            if dep_result and dep_result.get("success"):
                data = dep_result.get("data", [])
                if data:
                    first_row = data[0]
                    for k, v in first_row.items():
                        if isinstance(v, str) and v and not isinstance(v, bool):
                            facts.append(f"- {k} = '{v}'")
                            break
        if facts:
            facts_text = "\n".join(facts)
            logger.info(f"{fmt_trace(trace_id)}[Orchestrator] 任务 {task.id} 注入 {len(facts)} 个已知事实: {facts_text}")
    if facts_text:
        enriched_question = f"""{task.description}
【已知事实（必须直接使用，绝对禁止写子查询重新计算）】
{facts_text}
请直接使用上述具体值，例如 WHERE product_category_name = '床品浴品'"""
        # ★ 传给 Critic 的是 enriched_question，让 Critic 知道这些值是合法的
        critic_input = enriched_question
    else:
        enriched_question = task.description
        critic_input = task.description
    result = execute(enriched_question, task_description=critic_input, context="", trace_id=trace_id)
    return {
        "task_id": task.id,
        "description": task.description,
        "depends_on": task.depends_on,
        "is_aggregate": False,
        "sql": result["sql"],
        "success": result["success"],
        "data": result["data"],
        "columns": result["columns"],
        "error": result.get("error", ""),
        "warning": result.get("warning", ""),
        "sql_retry": result.get("sql_retry", 0),
        "critic_retry": result.get("critic_retry", 0)
    }
# ==================== 统一入口 ====================
def run_one_task(task, dep_results: dict = None, trace_id: str = None) -> dict:
    """执行单个任务：根据 Planner 标注的 task_type 分流"""
    logger.info(f"{fmt_trace(trace_id)}[Orchestrator] 执行任务 {task.id}: {task.description}")
    if getattr(task, "task_type", "sql") == "aggregate":
        logger.info(f"{fmt_trace(trace_id)}[Orchestrator] 任务 {task.id} 是综合型任务，走文本归纳")
        return synthesize(task, dep_results or {}, trace_id=trace_id)
    else:
        return run_sql_task(task, dep_results or {}, trace_id=trace_id)
# ==================== 主流程 ====================
def run(question: str, trace_id: str = None) -> dict:
    """完整流程：拆解 → 分层执行 → 归因 → 报告"""
    logger.info(f"{fmt_trace(trace_id)}[Orchestrator] 收到问题: {question}")
    plan_result = plan(question, trace_id=trace_id)
    logger.info(f"{fmt_trace(trace_id)}[Orchestrator] 拆解为 {len(plan_result.tasks)} 个任务")
    layers = build_layers(plan_result.tasks)
    logger.info(f"{fmt_trace(trace_id)}[Orchestrator] 分成 {len(layers)} 层执行")
    results = []
    completed_results = {}
    for layer_idx, layer in enumerate(layers):
        logger.info(f"{fmt_trace(trace_id)}[Orchestrator] 执行第 {layer_idx + 1} 层，共 {len(layer)} 个任务")
        with ThreadPoolExecutor(max_workers=MAX_CONCURRENT) as executor:
            futures = {
                executor.submit(
                    run_one_task,
                    task,
                    {dep: completed_results.get(dep) for dep in task.depends_on},
                    trace_id
                ): task
                for task in layer
            }
            for future in as_completed(futures):
                try:
                    result = future.result()
                    results.append(result)
                    completed_results[result["task_id"]] = result
                except Exception as e:
                    task = futures[future]
                    logger.error(f"{fmt_trace(trace_id)}[Orchestrator] 任务 {task.id} 失败: {e}")
                    error_result = {
                        "task_id": task.id,
                        "description": task.description,
                        "success": False,
                        "error": str(e)
                    }
                    results.append(error_result)
                    completed_results[task.id] = error_result
    results.sort(key=lambda x: x["task_id"])
    # 调 Analyst
    logger.info(f"{fmt_trace(trace_id)}[Orchestrator] 调 Analyst 做归因分析")
    analyst_result = analyze(question, plan_result.reason, results, trace_id=trace_id)
    # 调 Reporter
    logger.info(f"{fmt_trace(trace_id)}[Orchestrator] 调 Reporter 生成报告")
    report = generate_report(
        question=question,
        analysis=analyst_result["analysis"],
        results=results,
        warning=analyst_result["warning"],
        trace_id=trace_id
    )
    return {
        "question": question,
        "is_complex": plan_result.is_complex,
        "reason": plan_result.reason,
        "task_count": len(plan_result.tasks),
        "layers": len(layers),
        "results": results,
        "analysis": analyst_result["analysis"],
        "analysis_warning": analyst_result["warning"],
        "report": report
    }
def sse_event(event_type: str, data: dict) -> str:
    """格式化一条 SSE 事件"""
    payload = {"type": event_type, **data}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
def run_stream(question: str, trace_id: str = None):
    """流式版本：每完成一个任务 yield 一个事件"""
    logger.info(f"{fmt_trace(trace_id)}[Orchestrator-Stream] 收到问题: {question}")
    yield sse_event("plan_start", {"question": question})
    plan_result = plan(question, trace_id=trace_id)
    yield sse_event("plan_done", {
        "is_complex": plan_result.is_complex,
        "reason": plan_result.reason,
        "tasks": [
            {"id": t.id, "description": t.description,
             "depends_on": t.depends_on, "task_type": t.task_type}
            for t in plan_result.tasks
        ]
    })
    layers = build_layers(plan_result.tasks)
    yield sse_event("layers_done", {
        "layer_count": len(layers),
        "task_count": len(plan_result.tasks)
    })
    results = []
    completed_results = {}
    for layer_idx, layer in enumerate(layers):
        yield sse_event("layer_start", {
            "layer_index": layer_idx + 1,
            "tasks": [t.id for t in layer]
        })
        with ThreadPoolExecutor(max_workers=MAX_CONCURRENT) as executor:
            futures = {
                executor.submit(
                    run_one_task, task,
                    {dep: completed_results.get(dep) for dep in task.depends_on},
                    trace_id
                ): task
                for task in layer
            }
            for future in as_completed(futures):
                task = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                    completed_results[result["task_id"]] = result
                    yield sse_event("task_done", {
                        "task_id": result["task_id"],
                        "description": result["description"],
                        "success": result["success"],
                        "row_count": len(result.get("data", [])),
                        "sql": (result.get("sql") or "")[:200],
                        "data_preview": result.get("data", [])[:5]
                    })
                except Exception as e:
                    logger.error(f"{fmt_trace(trace_id)}[Orchestrator-Stream] 任务 {task.id} 失败: {e}")
                    error_result = {
                        "task_id": task.id,
                        "description": task.description,
                        "success": False,
                        "error": str(e)
                    }
                    results.append(error_result)
                    completed_results[task.id] = error_result
                    yield sse_event("task_error", {
                        "task_id": task.id,
                        "error": str(e)
                    })
    results.sort(key=lambda x: x["task_id"])
    yield sse_event("analysis_start", {})
    analyst_result = analyze(question, plan_result.reason, results, trace_id=trace_id)
    yield sse_event("analysis_done", {
        "analysis": analyst_result["analysis"],
        "warning": analyst_result["warning"]
    })
    yield sse_event("report_start", {})
    report = generate_report(
        question=question,
        analysis=analyst_result["analysis"],
        results=results,
        warning=analyst_result["warning"],
        trace_id=trace_id
    )
    yield sse_event("report_done", {"report": report})

    yield sse_event("done", {})