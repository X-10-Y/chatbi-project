"""
Schema Router：从所有表里选出和问题相关的表
避免把全量 schema 塞给 SQL 生成，省 token 且提高准确率
"""
from openai import OpenAI
from config import LLM_MODEL, LLM_BASE_URL, LLM_API_KEY
from tools.sql_runner import get_table_summaries
from logger import logger, log_tokens, fmt_trace
def select_tables(question: str, trace_id: str = None) -> list:
    """让 LLM 从所有表里选出相关表，返回表名列表"""
    summaries = get_table_summaries()
    prompt = f"""你是一个数据库专家。根据用户问题，从下面的表里选出需要用到的表。
【可用的表】
{summaries}
【用户问题】
{question}
【要求】
1. 只输出表名，用逗号分隔，比如：orders, order_items, products
2. 只选真正需要用到的表，不要多选
3. 如果判断不了，输出所有表名
4. 只输出表名，不要任何其他文字
相关表："""
    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=200
    )
    log_tokens("SchemaRouter", resp, trace_id=trace_id)
    raw = resp.choices[0].message.content.strip()
    # 清洗：去掉可能的 markdown 或换行
    raw = raw.replace("\n", "").replace("`", "")
    tables = [t.strip() for t in raw.split(",") if t.strip()]
    logger.info(f"{fmt_trace(trace_id)}[SchemaRouter] 选出表: {tables}")
    return tables