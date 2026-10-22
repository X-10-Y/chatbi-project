"""核心纯函数单元测试：SQL 防火墙、SQL 清洗、DAG 分层"""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.sql_runner import is_safe_sql
from agents.executor import clean_sql
from agents.orchestrator import build_layers


def _task(task_id, depends_on):
    return SimpleNamespace(id=task_id, depends_on=depends_on)


def test_allow_simple_select():
    assert is_safe_sql("SELECT 1")[0] is True


def test_allow_cte():
    assert is_safe_sql("WITH a AS (SELECT 1) SELECT * FROM a")[0] is True


def test_block_multi_statement():
    assert is_safe_sql("SELECT 1; SELECT 2")[0] is False


def test_block_dml():
    assert is_safe_sql("UPDATE t SET a = 1")[0] is False


def test_block_outfile():
    assert is_safe_sql("SELECT * FROM t INTO OUTFILE '/tmp/x'")[0] is False


def test_clean_sql_strips_markdown():
    assert clean_sql("```sql\nSELECT 1;\n```") == "SELECT 1"


def test_build_layers_by_dependency():
    tasks = [_task("a", []), _task("b", []), _task("c", ["a", "b"])]
    layers = build_layers(tasks)
    assert len(layers) == 2
    assert {t.id for t in layers[0]} == {"a", "b"}
    assert {t.id for t in layers[1]} == {"c"}


def test_build_layers_cycle_does_not_hang():
    tasks = [_task("a", ["b"]), _task("b", ["a"])]
    layers = build_layers(tasks)
    assert len(layers) == 1
