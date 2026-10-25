"""
Analyst Agent：归因分析
综合多个子任务的结果，推理出"为什么"
"""
import json
from pydantic import BaseModel
from openai import OpenAI
from config import LLM_MODEL, LLM_BASE_URL, LLM_API_KEY
from logger import logger, log_tokens, fmt_trace
TOP_N = 5
class AnalystResult(BaseModel):
    analysis: str = ""
    warning: str = ""
def summarize_results(results: list) -> tuple:
    """对每个任务的结果做截断，返回 (摘要文本, 失败任务列表)"""
    summaries = []
    failed = []
    for r in results:
        task_id = r.get("task_id", "?")
        desc = r.get("description", "")
        if not r.get("success"):
            failed.append(f"任务{task_id}（{desc}）")
            continue
        data = r.get("data", [])
        total = len(data)
        top_data = data[:TOP_N]
        stats_text = ""
        if total > TOP_N and data:
            numeric_cols = [
                c for c in data[0].keys()
                if isinstance(data[0].get(c), (int, float)) and not isinstance(data[0].get(c), bool)
            ]
            if numeric_cols:
                stats = {}
                for col in numeric_cols:
                    values = [
                        row[col] for row in data
                        if isinstance(row.get(col), (int, float)) and not isinstance(row.get(col), bool)
                    ]
                    if values:
                        stats[col] = {
                            "sum": round(sum(values), 2),
                            "avg": round(sum(values) / len(values), 2),
                            "max": max(values),
                            "min": min(values),
                        }
                if stats:
                    stats_text = f"\n- 全部 {total} 行的数值统计（避免只看前几行的偏差）:\n{json.dumps(stats, ensure_ascii=False, indent=2)}"
        summaries.append(f"""
任务{task_id}: {desc}
- SQL: {r.get('sql', '')[:200]}
- 结果（共 {total} 行，展示前 {len(top_data)} 行）:
{json.dumps(top_data, ensure_ascii=False, indent=2)}{stats_text}
""")
    return "\n".join(summaries), failed
def analyze(question: str, plan_reason: str, results: list, trace_id: str = None) -> dict:
    """综合所有任务结果做归因分析"""
    summaries, failed = summarize_results(results)
    if not summaries:
        return {
            "analysis": "所有子任务都执行失败，无法进行分析。",
            "warning": f"失败任务：{', '.join(failed)}"
        }
    prompt = f"""你是一个数据分析专家。请根据以下多个查询任务的结果，回答用户的问题并给出归因分析。
【用户问题】
{question}
【拆解原因】
{plan_reason}
【各任务查询结果】
{summaries}
【分析要求】
1. 先用一句话总结核心结论
2. 然后分维度说明原因
3. 引用具体数据支撑结论
4. 不要编造数据，只用上面提供的结果
5. 如果结果超过 5 行，摘要里会提供"全部 N 行的数值统计"。你必须引用这些全局统计数字（总和、均值、最大、最小），不要只根据展示的前 5 行下结论。如果需要提到"最大/最高"的项，检查前 5 行里有没有；如果没有，明确说"完整排名未展示，仅展示前 5 行"
6. 如果数据不足以回答，明确说明缺什么
请输出分析结论（中文，200-600字）："""
    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=800
    )
    log_tokens("Analyst", resp, trace_id=trace_id)
    analysis = resp.choices[0].message.content.strip()
    logger.info(f"{fmt_trace(trace_id)}[Analyst] 分析完成，长度 {len(analysis)} 字")
    warning = ""
    if failed:
        warning = f"以下维度因查询失败未纳入分析：{', '.join(failed)}"
        logger.warning(f"{fmt_trace(trace_id)}[Analyst] {warning}")
    result = AnalystResult(analysis=analysis, warning=warning)
    return result.model_dump()