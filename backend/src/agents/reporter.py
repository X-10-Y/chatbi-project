"""
Reporter Agent：报告组装
把 Analyst 结论 + 各任务数据组装成前端可渲染的 JSON
"""
from logger import logger
# ==================== 字段识别 ====================
# 时间字段关键词
TIME_KEYWORDS = ["month", "date", "year", "quarter", "week", "time"]
# 维度字段关键词（即使值是数字，也应作为 X 轴）
DIMENSION_KEYWORDS = [
    "month", "date", "year", "quarter", "week", "time",
    "id", "code", "no", "num", "seq", "index", "rank",
    "category", "type", "name", "city", "state", "status",
    "product", "customer", "seller", "payment", "quarter",
]
# 量纲识别关键词
RATE_KEYWORDS = ["rate", "ratio", "pct", "percent"]
COUNT_KEYWORDS = ["count", "cnt", "num", "qty", "quantity"]
AMOUNT_KEYWORDS = ["sales", "amount", "value", "price", "total", "revenue", "growth_amount"]
def is_time_field(field_name: str) -> bool:
    """判断字段是否是时间维度"""
    name = field_name.lower()
    return any(kw in name for kw in TIME_KEYWORDS)
def is_dimension_field(field_name: str) -> bool:
    """判断字段是否是维度（做 X 轴），而不是指标（做 Y 轴）"""
    name = field_name.lower()
    return any(kw in name for kw in DIMENSION_KEYWORDS)
def classify_field(field_name: str) -> str:
    """
    判断字段量纲
    返回：'rate' / 'count' / 'amount' / 'other'
    """
    name = field_name.lower()
    if any(kw in name for kw in RATE_KEYWORDS):
        return "rate"
    if any(kw in name for kw in COUNT_KEYWORDS):
        return "count"
    if any(kw in name for kw in AMOUNT_KEYWORDS):
        return "amount"
    return "other"
def analyze_columns(data: list, columns: list) -> tuple:
    """
    分析列的类型，返回 (维度列列表, 指标列列表)
    维度列：用来做 X 轴（时间、品类、地区等）
    指标列：用来做 Y 轴（金额、数量、比率等）
    """
    if not data:
        return [], []
    dim_cols = []
    metric_cols = []
    first_row = data[0]
    for col in columns:
        val = first_row.get(col)
        # 如果字段名看起来是维度 → 归为维度列
        if is_dimension_field(col):
            dim_cols.append(col)
        # 值是字符串 → 维度列
        elif isinstance(val, str):
            dim_cols.append(col)
        # 值是数字 → 指标列
        elif isinstance(val, (int, float)):
            metric_cols.append(col)
        else:
            dim_cols.append(col)
    return dim_cols, metric_cols
# ==================== 图表配置 ====================
# 字段名 → 中文标签
FIELD_NAME_MAP = {
    "product_category_name": "品类",
    "region": "大区",
    "province": "省份",
    "city": "城市",
    "payment_type": "支付方式",
    "order_year_month": "月份",
    "order_month": "月份",
    "order_quarter": "季度",
    "review_score": "评分",
    "state": "州",
}
# 分组 → 中文后缀
GROUP_LABEL = {
    "amount": "金额对比",
    "rate": "增长率",
    "count": "数量对比",
    "other": "",
}
def short_title(description: str, x_field: str, y_fields: list, group_type: str) -> str:
    """生成简短图表标题"""
    x_label = FIELD_NAME_MAP.get(x_field, x_field)
    y_labels = [FIELD_NAME_MAP.get(f, f) for f in y_fields[:2]]
    y_str = "、".join(y_labels)
    if len(y_fields) > 2:
        y_str += "等"
    return f"按{x_label}的{y_str}"
def build_chart_configs(task_id: int, description: str, data: list, columns: list) -> list:
    """
    为单个任务生成图表配置（可能返回多张图）
    按量纲分组：金额、百分比、计数各自一张图
    """
    if not data or not columns:
        return []
    # 只有 1 行 1 列 → 不画图
    if len(data) == 1 and len(columns) == 1:
        return []
    dim_cols, metric_cols = analyze_columns(data, columns)
    if not dim_cols or not metric_cols:
        return []
    x_field = dim_cols[0]
    # 按量纲分组
    groups = {"amount": [], "rate": [], "count": [], "other": []}
    for col in metric_cols:
        groups[classify_field(col)].append(col)
    # 图表太密看不清，只取前 20 行
    chart_data = data[:20]
    # 如果 X 轴是时间字段，所有图都用折线图
    is_time = is_time_field(x_field)
    bar_or_line = "line" if is_time else "bar"
    charts = []
    # 金额组
    if groups["amount"]:
        charts.append({
            "task_id": task_id,
            "chart_type": bar_or_line,
            "title": short_title(description, x_field, groups["amount"], "amount"),
            "x_field": x_field,
            "y_fields": groups["amount"],
            "data": chart_data
        })
    # 百分比组 → 永远用折线图
    if groups["rate"]:
        charts.append({
            "task_id": task_id,
            "chart_type": "line",
            "title": short_title(description, x_field, groups["rate"], "rate"),
            "x_field": x_field,
            "y_fields": groups["rate"],
            "data": chart_data
        })
    # 计数组
    if groups["count"]:
        charts.append({
            "task_id": task_id,
            "chart_type": bar_or_line,
            "title": short_title(description, x_field, groups["count"], "count"),
            "x_field": x_field,
            "y_fields": groups["count"],
            "data": chart_data
        })
    # 其他数值字段
    if groups["other"]:
        charts.append({
            "task_id": task_id,
            "chart_type": bar_or_line,
            "title": short_title(description, x_field, groups["other"], "other"),
            "x_field": x_field,
            "y_fields": groups["other"],
            "data": chart_data
        })
    return charts
# =================== 报告组装 ====================
def generate_report(question: str, analysis: str, results: list, warning: str = "") -> dict:
    """
    组装完整报告
    """
    charts = []
    tables = []
    for r in results:
        if not r.get("success"):
            continue
        data = r.get("data", [])
        columns = r.get("columns", [])
        task_id = r.get("task_id", 0)
        desc = r.get("description", "")
        # 生成图表配置（可能返回多个）
        task_charts = build_chart_configs(task_id, desc, data, columns)
        charts.extend(task_charts)
        # 表格数据
        tables.append({
            "task_id": task_id,
            "description": desc,
            "sql": r.get("sql", ""),
            "columns": columns,
            "data": data
        })
    report = {
        "title": question,
        "analysis": analysis,
        "warning": warning,
        "charts": charts,
        "tables": tables,
        "task_count": len(results)
    }
    logger.info(f"[Reporter] 报告生成完成: {len(charts)} 个图表, {len(tables)} 个表格")
    return report