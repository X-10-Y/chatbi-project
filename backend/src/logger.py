import os
import logging
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
logger = logging.getLogger("chatbi")
logger.setLevel(logging.INFO)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
logger.addHandler(console_handler)
# 日志文件路径可配，默认临时目录避免写死到源码目录触发沙箱限制
_log_dir = os.getenv("LOG_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "logs"))
os.makedirs(_log_dir, exist_ok=True)
_log_path = os.path.join(_log_dir, "chatbi.log")
file_handler = logging.FileHandler(_log_path, encoding="utf-8")
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
logger.addHandler(file_handler)

def fmt_trace(trace_id: str | None) -> str:
    """给日志加 trace_id 前缀；None 时返回空串，保持向后兼容"""
    return f"[trace={trace_id}] " if trace_id else ""

def log_tokens(agent_name: str, resp, trace_id: str = None):
    """
    记录 LLM 调用的 token 消耗
    resp: OpenAI API 的响应对象
    """
    try:
        if hasattr(resp, 'usage') and resp.usage:
            prompt = resp.usage.prompt_tokens
            completion = resp.usage.completion_tokens
            total = resp.usage.total_tokens
            logger.info(f"{fmt_trace(trace_id)}[{agent_name}] Token 消耗: 输入 {prompt} + 输出 {completion} = 总计 {total}")
    except Exception as e:
        logger.warning(f"{fmt_trace(trace_id)}[{agent_name}] Token 统计失败: {e}")