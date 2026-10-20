"""
数据上传工具：读取 CSV / Excel，清洗列名，建表，导入数据库
支持 SQLite / MySQL 双后端
"""
import os
import re
import pandas as pd
from tools.sql_runner import _engine
from logger import logger
def import_dataframe(df: pd.DataFrame, table_name: str) -> dict:
    """把 DataFrame 导入当前数据库（SQLite 或 MySQL）"""
    df.to_sql(table_name, _engine, if_exists="replace", index=False)
    return {
        "table_name": table_name,
        "rows": len(df),
        "columns": list(df.columns)
    }
def clean_column_name(name: str) -> str:
    """清洗列名：去空格、去特殊字符、中文保留"""
    name = str(name).strip()
    name = re.sub(r'[（(].*?[)）]', '', name)
    name = re.sub(r'[^\w\u4e00-\u9fff]', '_', name)
    name = re.sub(r'_+', '_', name).strip('_')
    return name or "col"
def safe_read_csv(path: str) -> pd.DataFrame:
    """自动尝试多种编码读取 CSV"""
    if not os.path.exists(path):
        raise FileNotFoundError(f"文件不存在: {path}")
    for encoding in ["utf-8", "gbk", "gb2312", "utf-8-sig"]:
        try:
            return pd.read_csv(path, encoding=encoding)
        except UnicodeDecodeError:
            continue
        except Exception:
            continue
    raise ValueError("无法识别文件编码，请另存为 UTF-8 或 GBK 格式")
def safe_read_excel(path: str, sheet_name=None) -> pd.DataFrame:
    """读取 Excel，支持指定 sheet"""
    return pd.read_excel(path, sheet_name=sheet_name)
def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """清洗 DataFrame"""
    df.columns = [clean_column_name(c) for c in df.columns]
    cols = []
    seen = {}
    for c in df.columns:
        if c in seen:
            seen[c] += 1
            cols.append(f"{c}_{seen[c]}")
        else:
            seen[c] = 0
            cols.append(c)
    df.columns = cols
    df = df.dropna(how="all").reset_index(drop=True)
    for col in df.columns:
        if df[col].dtype == object:
            try:
                converted = df[col].astype(str).str.replace(",", "", regex=False)
                df[col] = pd.to_numeric(converted, errors="ignore")
            except Exception:
                pass
    return df
def infer_table_name(filename: str) -> str:
    """从文件名推断表名"""
    name = os.path.splitext(os.path.basename(filename))[0]
    name = re.sub(r'[^\w\u4e00-\u9fff]', '_', name)
    name = re.sub(r'_+', '_', name).strip('_')
    return name or "uploaded_data"
def load_file(file_path: str, original_filename: str = None) -> dict:
    """
    统一入口：读取文件 → 清洗 → 导入当前数据库
    返回：{"table_name": ..., "rows": ..., "columns": [...], "sheets": [...]}
    """
    ext = os.path.splitext(file_path)[1].lower()
    filename = original_filename or os.path.basename(file_path)
    if ext == ".csv":
        df = safe_read_csv(file_path)
        df = clean_dataframe(df)
        table_name = infer_table_name(filename)
        result = import_dataframe(df, table_name)
        result["sheets"] = [table_name]
        logger.info(f"[DataLoader] CSV 导入成功: {table_name}, {len(df)} 行")
        return result
    elif ext in [".xlsx", ".xls"]:
        xl = pd.ExcelFile(file_path)
        sheets = []
        results = []
        for i, sheet_name in enumerate(xl.sheet_names):
            df = safe_read_excel(file_path, sheet_name=sheet_name)
            df = clean_dataframe(df)
            if len(xl.sheet_names) == 1:
                table_name = infer_table_name(filename)
            else:
                table_name = f"{infer_table_name(filename)}_{clean_column_name(sheet_name)}"
            result = import_dataframe(df, table_name)
            results.append(result)
            sheets.append(table_name)
            logger.info(f"[DataLoader] Sheet '{sheet_name}' 导入成功: {table_name}, {len(df)} 行")
        return {
            "table_name": results[0]["table_name"],
            "rows": sum(r["rows"] for r in results),
            "columns": results[0]["columns"],
            "sheets": sheets,
            "all_results": results
        }
    else:
        raise ValueError(f"不支持的文件格式: {ext}，只支持 .csv / .xlsx / .xls")