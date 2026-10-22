"""
Executor Agent：生成 SQL 并执行
"""
from openai import OpenAI
from logger import logger, log_tokens
from tools.sql_runner import run_sql, get_db_schema
from agents.critic import check_result
from config import LLM_MODEL, LLM_BASE_URL, LLM_API_KEY, MAX_SQL_RETRY, MAX_CRITIC_RETRY
# ==================== SQL 清洗 ====================
def clean_sql(raw: str) -> str:
    raw = raw.strip()
    if "```sql" in raw:
        raw = raw.split("```sql")[1].split("```")[0].strip()
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0].strip()
    raw = raw.rstrip(";").strip()
    return raw
# ==================== 通用业务规则 ====================
def build_business_rules() -> str:
    """
    生成通用业务规则。
    不依赖任何特定数据集，规则适用于任何数据库。
    数据集特有的业务知识，由 LLM 从 schema 和示例数据里自行推断。
    """
    rules = [
        "通用规则：",
        "1. 只输出 SQL，不要任何解释文字，不要 markdown 代码块",
        "2. 只允许 SELECT 或 WITH 查询",
        "3. 金额字段通常命名包含 price、amount、value、sales、total、revenue、cost、fee 等，根据字段名和示例数据判断",
        "4. 状态字段通常命名包含 status、state、type 等。状态字段的取值从示例数据里看，不要凭空猜测",
        "5. 表之间的关联字段根据列名判断：同名字段通常是关联字段（如两张表都有 order_id，则通过 order_id 关联）",
        "6. 中文列名直接使用，不需要翻译或转义",
        "7. 时间字段如果是整数类型，条件里用整数（如 quarter = 4）；如果是字符串类型，用字符串",
        "8. 统计金额或数量时，如果表中有状态字段，注意判断是否需要过滤有效状态（比如排除'已取消''已退货'）。具体过滤哪些状态，从状态字段的示例数据里判断，不要凭空假设",
        "9. 不确定字段含义时，从示例数据推断，不要瞎猜",
        "10. 表名和字段名区分大小写，按 schema 里的原样使用",
        "11. 不要使用 FULL OUTER JOIN（MySQL 不支持），改用 LEFT JOIN + UNION 替代",
    ]
    return "\n".join(rules)
# ==================== 生成 SQL ====================
def generate_sql(question: str, context: str = "") -> str:
    from agents.schema_router import select_tables
    from tools.sql_runner import get_db_schema_for_tables
    tables = select_tables(question)
    schema = get_db_schema_for_tables(tables)
    rules = build_business_rules()
    context_section = ""
    if context:
        context_section = f"""
【前置任务的结果】
{context}
请基于以上结果生成 SQL，如果需要用到前置结果中的具体值（比如最高品类名），直接使用具体值。
"""
    prompt = f"""{context_section}你是一个 SQL 专家。请根据用户问题生成查询语句。
数据库结构：
{schema}
{rules}
用户问题：{question}
SQL："""
    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=1500
    )
    log_tokens("Executor-生成", resp)
    raw = resp.choices[0].message.content
    logger.info(f"[Executor] LLM 原始输出: {raw[:200]}")
    sql = clean_sql(raw)
    logger.info(f"[Executor] 清洗后 SQL: {sql}")
    return sql
# ==================== 带报错反馈重写 ====================
def generate_sql_with_feedback(question: str, failed_sql: str, error: str) -> str:
    schema = get_db_schema()
    rules = build_business_rules()
    prompt = f"""你是一个 SQL 专家。上一次生成的 SQL 执行报错了，请根据报错信息重写。
数据库结构：
{schema}
用户问题：{question}
上次生成的 SQL：
{failed_sql}
数据库返回的错误：
{error}
请分析错误原因，重新生成正确的 SQL。
{rules}
正确的 SQL："""
    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=1500
    )
    log_tokens("Executor-报错重写", resp)
    raw = resp.choices[0].message.content
    logger.info(f"[Executor] 重写原始输出: {raw[:200]}")
    sql = clean_sql(raw)
    logger.info(f"[Executor] 重写后 SQL: {sql}")
    return sql
# ==================== 带 Critic 反馈重写 ====================
def generate_sql_with_critic_feedback(question: str, failed_sql: str, critic_reason: str) -> str:
    schema = get_db_schema()
    rules = build_business_rules()
    prompt = f"""你是一个 SQL 专家。上一次生成的 SQL 执行成功了，但质检员认为结果不能回答用户问题，请重写。
数据库结构：
{schema}
用户问题：{question}
上次生成的 SQL：
{failed_sql}
质检员反馈：
{critic_reason}
请根据反馈重新生成 SQL。
{rules}
正确的 SQL："""
    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=1500
    )
    log_tokens("Executor-Critic重写", resp)
    raw = resp.choices[0].message.content
    logger.info(f"[Executor] Critic反馈重写原始输出: {raw[:200]}")
    sql = clean_sql(raw)
    logger.info(f"[Executor] Critic反馈重写后 SQL: {sql}")
    return sql
# ==================== 主流程 ====================
def execute(question: str, max_sql_retry: int = None, max_critic_retry: int = None,
            task_description: str = None, context: str = "") -> dict:
    # 使用配置的默认值
    if max_sql_retry is None:
        max_sql_retry = MAX_SQL_RETRY
    if max_critic_retry is None:
        max_critic_retry = MAX_CRITIC_RETRY
    # 阶段1：生成 + 语法重试
    sql = generate_sql(question, context=context)
    result = run_sql(sql)
    sql_retry = 0
    while not result["success"] and sql_retry < max_sql_retry:
        sql_retry += 1
        logger.info(f"[Executor] SQL 报错，第 {sql_retry} 次重试")
        sql = generate_sql_with_feedback(question, sql, result["error"])
        result = run_sql(sql)
    if not result["success"]:
        return {
            "question": question,
            "sql": sql,
            "success": False,
            "data": [],
            "columns": [],
            "error": result["error"],
            "sql_retry": sql_retry,
            "critic_retry": 0,
            "warning": ""
        }
    # 阶段2：Critic 检查 + 语义重试
    critic_retry = 0
    while critic_retry < max_critic_retry:
        check = check_result(task_description or question, sql, result["data"], result["columns"])
        if check is None:
            logger.warning("[Executor] Critic 返回 None，默认通过")
            break
        if check["pass"]:
            break
        critic_retry += 1
        logger.info(f"[Executor] Critic 不通过，第 {critic_retry} 次语义重写")
        sql = generate_sql_with_critic_feedback(question, sql, check.get("reason", ""))
        result = run_sql(sql)
        if not result["success"]:
            # 语义重写可能引入语法/字段错误，先走报错反馈修复，避免直接返回空结果
            fix_retry = 0
            while not result["success"] and fix_retry < max_sql_retry:
                fix_retry += 1
                logger.info(f"[Executor] 语义重写后执行失败，报错修复第 {fix_retry} 次")
                sql = generate_sql_with_feedback(question, sql, result["error"])
                result = run_sql(sql)
            sql_retry += fix_retry
            if not result["success"]:
                return {
                    "question": question,
                    "sql": sql,
                    "success": False,
                    "data": [],
                    "columns": [],
                    "error": result["error"],
                    "sql_retry": sql_retry,
                    "critic_retry": critic_retry,
                    "warning": "语义重写后的 SQL 执行失败，已尝试修复但仍未成功"
                }
    warning = ""
    if critic_retry >= max_critic_retry:
        warning = "系统对本次结果质量存疑，建议核实后使用"
    return {
        "question": question,
        "sql": sql,
        "success": result["success"],
        "data": result["data"],
        "columns": result["columns"],
        "error": result["error"],
        "sql_retry": sql_retry,
        "critic_retry": critic_retry,
        "warning": warning
    }