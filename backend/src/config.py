import os
from dotenv import load_dotenv
load_dotenv()
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
DB_PATH = os.path.join(CURRENT_DIR, "db", "chatbi.db")
LLM_MODEL = "deepseek-chat"
LLM_BASE_URL = "https://api.deepseek.com"
LLM_API_KEY = os.getenv("DEEPSEEK_API_KEY")
MAX_SQL_RETRY = 3
MAX_CRITIC_RETRY = 2
MAX_RESULT_ROWS = 100
REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = 0
CACHE_TTL = 3600
DB_TYPE = "mysql"
MYSQL_URL = os.getenv("MYSQL_URL")