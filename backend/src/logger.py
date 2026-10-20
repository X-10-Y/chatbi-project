import logging
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
logger = logging.getLogger("chatbi")
logger.setLevel(logging.INFO)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
logger.addHandler(console_handler)
file_handler = logging.FileHandler("chatbi.log", encoding="utf-8")
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
logger.addHandler(file_handler)
def log_tokens(agent_name: str, resp):
    """
    记录 LLM 调用的 token 消耗
    resp: OpenAI API 的响应对象
    """
    try:
        if hasattr(resp, 'usage') and resp.usage:
            prompt = resp.usage.prompt_tokens
            completion = resp.usage.completion_tokens
            total = resp.usage.total_tokens
            logger.info(f"[{agent_name}] Token 消耗: 输入 {prompt} + 输出 {completion} = 总计 {total}")
    except Exception as e:
        logger.warning(f"[{agent_name}] Token 统计失败: {e}")