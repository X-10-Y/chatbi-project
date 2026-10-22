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
try:
    import sqlglot
    from sqlglot import exp
    _HAS_SQLGLOT = True
except ImportError:  # 未安装 sqlglot 时退回关键字黑名单
    _HAS_SQLGLOT = False
_FORBIDDEN_KEYWORDS = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "CREATE", "TRUNCATE", "REPLACE"]
_FORBIDDEN_PATTERNS = ["INTO OUTFILE", "INTO DUMPFILE", "LOAD_FILE", "INFORMATION_SCHEMA"]
def _validate_with_sqlglot(sql: str):
    """用 AST 校验语句类型，避免注释混淆、多语句、子查询包裹 DML 等绕过"""
    dialect = "mysql" if DB_TYPE == "mysql" else "sqlite"
    try:
        statements = [s for s in sqlglot.parse(sql, read=dialect) if s is not None]
    except Exception as e:
        return False, f"SQL 解析失败: {e}"
    if len(statements) != 1:
        return False, "只允许单条 SQL 语句"
    if not isinstance(statements[0], (exp.Select, exp.Union)):
        return False, "只允许 SELECT 或 WITH 查询"
    return True, ""
def is_safe_sql(sql: str):
    if not sql or not sql.strip():
        return False, "SQL 为空"
    stripped = sql.strip().rstrip(";").strip()
    sql_upper = stripped.upper()
    if not (sql_upper.startswith("SELECT") or sql_upper.startswith("WITH")):
        return False, "只允许 SELECT 或 WITH 查询"
    for kw in _FORBIDDEN_KEYWORDS:
        if re.search(rf'\b{kw}\b', sql_upper):
            return False, f"禁止使用 {kw}"
    for pattern in _FORBIDDEN_PATTERNS:
        if pattern in sql_upper:
            return False, f"禁止使用 {pattern}"
    if _HAS_SQLGLOT:
        return _validate_with_sqlglot(stripped)
    # 没有 sqlglot 时至少拦住多语句拼接
    if ";" in stripped:
        return False, "只允许单条 SQL 语句"
    return True, ""
# ==================== 统一执行入口 ====================
def run_sql(sql: str, max_rows: int = None) -> dict:
    """执行只读 SQL，最多返回 max_rows 行（在数据库侧用 LIMIT 限制，避免全量拉取）"""
    if max_rows is None:
        max_rows = MAX_RESULT_ROWS
    safe, reason = is_safe_sql(sql)
    if not safe:
        logger.warning(f"[SQL] 被防火墙拦截: {reason}")
        return {"success": False, "error": f"SQL 被拦截: {reason}", "data": [], "columns": [], "truncated": False}
    query = sql.strip().rstrip(";").strip()
    limited = f"SELECT * FROM ({query}) AS _chatbi_result LIMIT {max_rows + 1}"
    try:
        logger.info(f"[SQL] 执行: {query[:200]}")
        with _engine.connect() as conn:
            try:
                result = conn.execute(text(limited))
            except Exception:
                # 少数方言不支持子查询包裹时退回原 SQL，用 fetchmany 控制拉取量
                result = conn.execute(text(query))
            columns = list(result.keys())
            rows = result.fetchmany(max_rows + 1)
        truncated = len(rows) > max_rows
        data = [dict(zip(columns, row)) for row in rows[:max_rows]]
        logger.info(f"[SQL] 成功，返回 {len(data)} 行（截断={truncated}）")
        return {"success": True, "data": data, "columns": columns, "error": "", "truncated": truncated}
    except Exception as e:
        logger.error(f"[SQL] 执行失败: {str(e)}")
        return {"success": False, "error": str(e), "data": [], "columns": [], "truncated": False}
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
    """指定表的完整 schema；路由结果全部无效时回退全量 schema，避免模型无 schema 可依"""
    if not table_names:
        return get_db_schema()
    inspector = inspect(_engine)
    all_tables = set(inspector.get_table_names())
    matched = [t for t in table_names if t in all_tables]
    if not matched:
        logger.warning(f"[Schema] 路由表 {table_names} 均不存在，回退全量 schema")
        return get_db_schema()
    lines = []
    for table in matched:
        lines.append(f"\n表名: {table}")
        for c in inspector.get_columns(table):
            lines.append(f"  - {c['name']} ({c['type']})")
        cols, rows = _sample_rows(table)
        if cols:
            lines.append(f"  示例列: {cols}")
            for row in rows:
                lines.append(f"    {row}")
    return "\n".join(lines)