"""
查询改写：把带指代词的问题改写成完整独立的问句
比如 "那上个月呢" → "上个月销售额是多少"
只在检测到指代词时才调 LLM，省一次调用
"""
from openai import OpenAI
from config import LLM_MODEL, LLM_BASE_URL, LLM_API_KEY
from logger import logger, log_tokens, fmt_trace
REFERENCE_WORDS = [
    "那", "这个", "那个", "它", "该", "上述", "前面", "刚才",
    "再", "还有", "呢", "那么", "然后", "接着", "换", "改成",
]
def _has_reference(question: str) -> bool:
    """检测问题里有没有指代词"""
    return any(w in question for w in REFERENCE_WORDS)
def rewrite_query(question: str, history: list, trace_id: str = None) -> str:
    """
    把问题改写成完整独立的问句
    - 没有历史 → 直接返回原问题
    - 没有指代词 → 直接返回原问题
    - 有历史 + 有指代词 → 调 LLM 改写
    """
    if not history:
        return question
    if not _has_reference(question):
        logger.info(f"{fmt_trace(trace_id)}[Rewriter] 无指代词，跳过改写: {question}")
        return question
    history_text = "\n".join([
        f"用户：{h.get('question', '')}\n助手：{h.get('answer', '')[:100]}..."
        for h in history
    ])
    prompt = f"""你是一个查询改写助手。用户正在进行多轮对话，请根据对话历史，把当前问题改写成完整、独立的问句。
【对话历史】
{history_text}
【当前问题】
{question}
【要求】
1. 把指代词（"那""它""这个""上述"等）替换成具体的对象
2. 改写成能单独理解的完整问句
3. 只输出改写后的问题，不要任何解释
4. 如果无法判断指代对象，直接输出原问题
改写后的问题："""
    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=100
    )
    log_tokens("Rewriter", resp, trace_id=trace_id)
    rewritten = resp.choices[0].message.content.strip()
    logger.info(f"{fmt_trace(trace_id)}[Rewriter] 原问题: {question}")
    logger.info(f"{fmt_trace(trace_id)}[Rewriter] 改写后: {rewritten}")
    return rewritten or question