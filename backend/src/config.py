import os
from dotenv import load_dotenv
load_dotenv()
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
DB_PATH = os.path.join(CURRENT_DIR, "db", "chatbi.db")
LLM_MODEL = "deepseek-chat"
LLM_BASE_URL = "https://api.deepseek.com"
LLM_API_KEY = os.getenv("DEEPSEEK_API_KEY")
LLM_TIMEOUT = 60        # 单次请求超时（秒），SDK 默认值长达数百秒
LLM_MAX_RETRIES = 2     # SDK 层自动重试次数
MAX_PLAN_TASKS = 6      # Planner 拆解任务数上限，超过则降级为单任务
def get_llm_client():
    """统一创建 LLM 客户端：显式超时 + 有限重试，避免请求长期挂起"""
    from openai import OpenAI
    return OpenAI(
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL,
        timeout=LLM_TIMEOUT,
        max_retries=LLM_MAX_RETRIES
    )
MAX_SQL_RETRY = 3
MAX_CRITIC_RETRY = 2
MAX_RESULT_ROWS = 100
REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = 0
CACHE_TTL = 3600
DB_TYPE = "mysql"
MYSQL_URL = os.getenv("MYSQL_URL")