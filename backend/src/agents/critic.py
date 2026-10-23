"""
Critic Agent：质检员
检查 Executor 生成的结果是否能回答用户问题
"""
import json
from pydantic import BaseModel
from openai import OpenAI
from config import LLM_MODEL, LLM_BASE_URL, LLM_API_KEY
from logger import logger, log_tokens, fmt_trace
class CriticResult(BaseModel):
    pass_: bool = True
    reason: str = ""
def check_result(question: str, sql: str, data: list, columns: list, trace_id: str = None) -> dict:
    """检查 SQL 结果是否能回答用户问题"""
    # 快速检查：空结果
    if not data:
        return {"pass": False, "reason": "查询返回空结果，可能 WHERE 条件有误或数据不存在"}
    data_preview = data[:5]
    prompt = f"""你是一个数据分析质检员。请检查以下查询结果是否能回答用户的问题。
用户问题：{question}
生成的 SQL：
{sql}
查询结果：
- 列名：{columns}
- 总行数：{len(data)}
- 前5行数据：{data_preview}
请判断：
1. 数据的"形状"是否匹配用户问题的意图？
   - 用户问"平均/总数/占比" → 应该返回 1 行或少量汇总行
   - 用户问"每个/各个/分别" → 应该返回多行明细
   - 用户问"最高/最低/Top N" → 应该返回排序后的少量行
2. SQL 的关键字段是否和用户问题的关键实体匹配？
   - 用户问"Q4" → SQL 里应该有 order_quarter = 4 或类似条件
   - 用户问"某品类" → SQL 里应该有 product_category_name 相关条件
   - 用户问"销售额" → SQL 里应该用到 price 或 payment_value 字段
   - 如果 SQL 里完全没有提到用户问题里的关键实体，判不通过
3. 有没有明显的语义不匹配？
只输出 JSON，不要其他内容：
{{"pass": true 或 false, "reason": "不通过时说明原因，通过时留空"}}
"""
    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=200
    )
    log_tokens("Critic", resp, trace_id=trace_id)
    raw = resp.choices[0].message.content.strip()
    # 清洗 markdown
    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0].strip()
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0].strip()
    try:
        raw_dict = json.loads(raw)
        validated = CriticResult(
            pass_=raw_dict.get("pass", True),
            reason=raw_dict.get("reason", "")
        )
        logger.info(f"{fmt_trace(trace_id)}[Critic] 检查结果: pass={validated.pass_}, reason={validated.reason[:50]}")
        return {"pass": validated.pass_, "reason": validated.reason}
    except Exception as e:
        logger.error(f"{fmt_trace(trace_id)}[Critic] 解析失败: {e}")
        return {"pass": True, "reason": ""}