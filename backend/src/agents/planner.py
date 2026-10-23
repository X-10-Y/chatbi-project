"""
Planner Agent：任务拆解
判断问题是否需要拆分，复杂问题拆成多个子任务
"""
from typing import List
from pydantic import BaseModel, ValidationError
from openai import OpenAI
from config import LLM_MODEL, LLM_BASE_URL, LLM_API_KEY
from logger import logger, log_tokens, fmt_trace
from tools.sql_runner import get_db_schema_light
# ==================== Pydantic 模型 ====================
class Task(BaseModel):
    id: int
    description: str
    depends_on: list[int] = []
    task_type: str = "sql"
class Plan(BaseModel):
    is_complex: bool
    reason: str
    tasks: List[Task]
# =================== JSON 清洗 ====================
def clean_json(raw: str) -> str:
    """去掉 markdown 代码块标记"""
    raw = raw.strip()
    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0].strip()
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0].strip()
    return raw
# ==================== 核心：任务拆解 ====================
def plan(question: str, trace_id: str = None) -> Plan:
    """
    让 LLM 判断问题复杂度，复杂问题拆成多个子任务
    """
    json_example = '''{
    "is_complex": true,
    "reason": "为什么这么拆（或不拆）",
    "tasks": [
        {"id": 1, "description": "子任务描述", "depends_on": [], "task_type": "sql"},
        {"id": 2, "description": "子任务描述", "depends_on": [], "task_type": "sql"},
        {"id": 3, "description": "综合前两个任务的结果", "depends_on": [1, 2], "task_type": "aggregate"}
    ]
}'''
    schema = get_db_schema_light()
    prompt = f"""你是一个数据分析任务规划专家。请判断用户问题是否需要拆分成多个子任务。
【核心原则】
能用 GROUP BY 一次查出来的，不要拆。只有需要多个 SQL 结果综合才能回答的，才拆。
【判断标准】
不拆的类型（1个任务）：
- 单点查询：问一个数字、一个排名、一个占比
  例：某月的销售额是多少、最高的5个是什么、各分类占比
- 趋势查询：按时间维度看变化
  例：每个月的销售趋势 → 一个 GROUP BY 时间字段搞定
- 分布查询：按某个维度分组统计
  例：各分类的销售额分布 → 一个 GROUP BY 分类字段搞定
必须拆的类型（多个任务）：
- 归因查询：为什么 X 发生变化
  例：为什么某季度比上季度增长 → 必须按多个维度分别查
- 多跳查询：先查A，再基于A查B
  例：哪个分类最高？它的客户在哪 → 先查分类，再查客户
- 对比分析多个独立维度
  例：对比两个地区的客单价和复购率 → 客单价和复购率是两个独立查询
【关键区别】
- 趋势/分布：一个维度，一个 SQL 用 GROUP BY 解决 → 不拆
- 归因：多个维度，需要分别查再综合 → 必须拆
- 多跳：任务之间有依赖 → 必须拆
【任务依赖判断】
每个任务可以声明依赖的前置任务 id，判断标准：
1. 如果任务描述里有"该X""上述结果""基于前面的""综合"等指代 → 需要依赖
2. 如果任务描述是独立的查询（按X统计、查询Y）→ 不依赖
3. 无依赖的任务填空列表
【任务描述规则】
- 任务描述是"查询需求"，不是"结果筛选"
- 不要写"找出最大/最高/最多的X"，要写"按X维度统计，返回完整分组"
- 错误写法：找出增长贡献最大的品类（会导致 LLM 加 LIMIT 1）
- 正确写法：按品类统计增长额和增长率，返回所有品类
- 只有用户明确说"Top N""前几名"时，才写"取前N"
【任务类型判断】
每个任务必须标注 task_type：
- "sql"：需要通过查询数据库才能完成的筛选型任务，比如"按品类统计销售额"
- "aggregate"：不需要查数据库，而是综合其他任务的结果做归纳的任务，比如"综合分析增长原因"
只有依赖其他任务且描述里含"综合/归纳/总结/分析原因"等词的，才是 aggregate。
【数据库表结构】
{schema}
【输出格式】
{json_example}
注意：
- 如果不拆，tasks 里只有一个任务，description 就是原问题
- 如果拆，每个任务描述要具体、可独立查询
- 任务描述用中文
用户问题：{question}
只输出 JSON，不要其他内容："""
    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=800
    )
    log_tokens("Planner", resp, trace_id=trace_id)
    raw = resp.choices[0].message.content
    logger.info(f"{fmt_trace(trace_id)}[Planner] LLM 原始输出: {raw[:300]}")
    cleaned = clean_json(raw)
    try:
        plan_result = Plan.model_validate_json(cleaned)
        logger.info(f"{fmt_trace(trace_id)}[Planner] 拆解完成: is_complex={plan_result.is_complex}, tasks={len(plan_result.tasks)}")
        return plan_result
    except Exception as e:
        logger.error(f"{fmt_trace(trace_id)}[Planner] 解析失败: {e}")
        return Plan(
            is_complex=False,
            reason="解析失败，降级为单任务",
            tasks=[Task(id=1, description=question)]
        )