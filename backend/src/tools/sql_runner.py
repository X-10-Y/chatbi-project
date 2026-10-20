"""
SQL 执行器 + 安全防火墙
支持 SQLite / MySQL 双后端，通过 config.DB_TYPE 切换
"""
import re
from sqlalchemy import create_engine, text, inspect
from config import DB_PATH, MYSQL_URL, DB_TYPE, MAX_RESULT_ROWS
from logger import logger
# ==================== 引擎初始化 ====================
if DB_TYPE == "mysql":
    _engine = create_engine(MYSQL_URL, pool_size=5, max_overflow=10, pool_pre_ping=True)
    logger.info("[DB] 使用 MySQL")
else:
    _engine = create_engine(f"sqlite:///{DB_PATH}")
    logger.info("[DB] 使用 SQLite")
# ==================== 表名 / 字段 ====================
def get_table_names() -> list:
    inspector = inspect(_engine)
    return inspector.get_table_names()
def get_table_columns(table_name: str) -> list:
    """返回 [(列名, 类型), ...]"""
    inspector = inspect(_engine)
    return [(c["name"], str(c["type"])) for c in inspector.get_columns(table_name)]
# ==================== 防火墙 ====================
def is_safe_sql(sql: str):
    if not sql or not sql.strip():
        return False, "SQL 为空"
    sql_upper = sql.strip().upper()
    if not (sql_upper.startswith("SELECT") or sql_upper.startswith("WITH")):
        return False, "只允许 SELECT 或 WITH 查询"
    forbidden = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "CREATE", "TRUNCATE", "REPLACE"]
    for kw in forbidden:
        if re.search(rf'\b{kw}\b', sql_upper):
            return False, f"禁止使用 {kw}"
    return True, ""
# ==================== 统一执行入口 ====================
def run_sql(sql: str) -> dict:
    safe, reason = is_safe_sql(sql)
    if not safe:
        logger.warning(f"[SQL] 被防火墙拦截: {reason}")
        return {"success": False, "error": f"SQL 被拦截: {reason}", "data": [], "columns": []}
    try:
        logger.info(f"[SQL] 执行: {sql[:200]}")
        with _engine.connect() as conn:
            result = conn.execute(text(sql))
            columns = list(result.keys())
            rows = result.fetchall()[:MAX_RESULT_ROWS]
            data = [dict(zip(columns, row)) for row in rows]
        logger.info(f"[SQL] 成功，返回 {len(data)} 行")
        return {"success": True, "data": data, "columns": columns, "error": ""}
    except Exception as e:
        logger.error(f"[SQL] 执行失败: {str(e)}")
        return {"success": False, "error": str(e), "data": [], "columns": []}
# ==================== Schema 提供者 ====================
def _sample_rows(table: str):
    """取 2 行示例数据"""
    try:
        with _engine.connect() as conn:
            result = conn.execute(text(f"SELECT * FROM {table} LIMIT 2"))
            cols = list(result.keys())
            rows = [tuple(r) for r in result.fetchall()]
        return cols, rows
    except Exception:
        return [], []
def get_db_schema() -> str:
    """全量 schema（含示例数据），给 Executor 用"""
    inspector = inspect(_engine)
    lines = []
    for table in inspector.get_table_names():
        lines.append(f"\n表名: {table}")
        for c in inspector.get_columns(table):
            lines.append(f"  - {c['name']} ({c['type']})")
        cols, rows = _sample_rows(table)
        if cols:
            lines.append(f"  示例列: {cols}")
            for row in rows:
                lines.append(f"    {row}")
    return "\n".join(lines)
def get_db_schema_light() -> str:
    """轻量 schema（只表名和字段名），给 Planner 用"""
    inspector = inspect(_engine)
    lines = []
    for table in inspector.get_table_names():
        cols = [c["name"] for c in inspector.get_columns(table)]
        lines.append(f"表名: {table}")
        lines.append(f"  字段: {', '.join(cols)}")
    return "\n".join(lines)
def get_table_summaries() -> str:
    """所有表的简要信息，给 SchemaRouter 用"""
    inspector = inspect(_engine)
    lines = []
    for table in inspector.get_table_names():
        cols = [c["name"] for c in inspector.get_columns(table)]
        lines.append(f"- {table}: {', '.join(cols)}")
    return "\n".join(lines)
def get_db_schema_for_tables(table_names: list) -> str:
    """指定表的完整 schema"""
    if not table_names:
        return get_db_schema()
    inspector = inspect(_engine)
    all_tables = set(inspector.get_table_names())
    lines = []
    for table in table_names:
        if table not in all_tables:
            continue
        lines.append(f"\n表名: {table}")
        for c in inspector.get_columns(table):
            lines.append(f"  - {c['name']} ({c['type']})")
        cols, rows = _sample_rows(table)
        if cols:
            lines.append(f"  示例列: {cols}")
            for row in rows:
                lines.append(f"    {row}")
    return "\n".join(lines)