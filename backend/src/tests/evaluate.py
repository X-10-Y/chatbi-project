"""
ChatBI 评估脚本
用法：
    cd backend/src
    python ../../tests/evaluate.py
"""
import json
import os
import sys
import time

# 当前脚本在 backend/src/tests/ 下，需要加入 backend/src 到路径
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))       # backend/src/tests
SRC_DIR = os.path.dirname(CURRENT_DIR)                          # backend/src
sys.path.insert(0, SRC_DIR)

from agents.orchestrator import run


DATASET_PATH = os.path.join(os.path.dirname(__file__), "test_dataset.json")
RESULT_PATH = os.path.join(os.path.dirname(__file__), "eval_result.json")


def load_dataset():
    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def check_hit(expected_key: str, expected_type: str, task_results: list, all_data: list) -> bool:
    """
    检查系统结果里有没有预期的关键值
    task_results: 任务列表（每个任务有 success / data）
    all_data: 所有任务的数据行展开
    """
    # 把所有数据拼成一个字符串
    text = json.dumps(all_data, ensure_ascii=False)
    if expected_type == "text":
        return expected_key in text
    elif expected_type == "value":
        try:
            expected_num = float(expected_key)
            import re
            # 找所有数字（包括负数、小数）
            numbers = re.findall(r'-?\d+\.?\d*', text)
            for num_str in numbers:
                try:
                    num = float(num_str)
                    if expected_num == 0:
                        continue
                    # 允许 5% 误差
                    if abs(num - expected_num) / abs(expected_num) < 0.05:
                        return True
                    # 兼容百分比 vs 小数（43 vs 0.43）
                    if abs(num * 100 - expected_num) / abs(expected_num) < 0.05:
                        return True
                    if abs(num / 100 - expected_num) / abs(expected_num) < 0.05:
                        return True
                except:
                    continue
            return False
        except:
            return expected_key in text
    elif expected_type == "row_count":
        try:
            expected_count = int(expected_key)
            # ★ 从任务列表里找，看哪个任务返回了期望行数
            for r in task_results:
                if r.get("success"):
                    if len(r.get("data", [])) == expected_count:
                        return True
            return False
        except:
            return False
    return False


def evaluate_one(item: dict) -> dict:
    """评估单个问题"""
    question = item["question"]
    expected_key = item["expected_key"]
    expected_type = item["expected_type"]

    try:
        start = time.time()
        result = run(question)
        elapsed = time.time() - start

        # 收集所有任务的结果
        all_results = []
        for r in result.get("results", []):
            if r.get("success"):
                all_results.extend(r.get("data", []))

        # 检查是否命中
        hit = check_hit(expected_key, expected_type, result.get("results", []), all_results)

        # 统计 SQL 成功率
        total_tasks = len(result.get("results", []))
        success_tasks = sum(1 for r in result.get("results", []) if r.get("success"))

        return {
            "id": item["id"],
            "question": question,
            "category": item.get("category", ""),
            "hit": hit,
            "elapsed": round(elapsed, 2),
            "task_count": result.get("task_count", 0),
            "sql_success": f"{success_tasks}/{total_tasks}",
            "sql_retry": sum(r.get("sql_retry", 0) for r in result.get("results", [])),
            "critic_retry": sum(r.get("critic_retry", 0) for r in result.get("results", [])),
            "status": "成功"
        }

    except Exception as e:
        return {
            "id": item["id"],
            "question": question,
            "category": item.get("category", ""),
            "hit": False,
            "elapsed": 0,
            "status": f"失败: {str(e)[:100]}"
        }


def main():
    dataset = load_dataset()
    print(f"📊 开始评估，共 {len(dataset)} 个问题\n")
    print("=" * 80)

    results = []
    for item in dataset:
        r = evaluate_one(item)
        results.append(r)

        status_icon = "✅" if r["hit"] else "❌"
        print(f"{status_icon} [{r['id']}] {r['question'][:50]}")
        print(f"   类别: {r['category']} | 命中: {r['hit']} | 耗时: {r['elapsed']}s | SQL: {r.get('sql_success', '-')} | 状态: {r.get('status', '')}")
        print("-" * 80)

    # 汇总
    total = len(results)
    hit_count = sum(1 for r in results if r["hit"])
    total_time = sum(r["elapsed"] for r in results)
    avg_time = total_time / total if total > 0 else 0

    # 按类别统计
    categories = {}
    for r in results:
        cat = r["category"]
        if cat not in categories:
            categories[cat] = {"total": 0, "hit": 0}
        categories[cat]["total"] += 1
        if r["hit"]:
            categories[cat]["hit"] += 1

    print("\n" + "=" * 80)
    print("📈 评估结果")
    print("=" * 80)
    print(f"总体命中率: {hit_count}/{total} = {hit_count / total * 100:.1f}%")
    print(f"平均响应时间: {avg_time:.2f}s")
    print()
    print("按类别统计:")
    for cat, stat in categories.items():
        rate = stat["hit"] / stat["total"] * 100 if stat["total"] > 0 else 0
        print(f"  {cat}: {stat['hit']}/{stat['total']} = {rate:.1f}%")

    # 保存结果
    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "overall_hit_rate": round(hit_count / total * 100, 2),
            "total": total,
            "hit_count": hit_count,
            "avg_time": round(avg_time, 2),
            "by_category": categories,
            "details": results
        }, f, ensure_ascii=False, indent=2)
    print(f"\n📁 结果已保存: {RESULT_PATH}")


if __name__ == "__main__":
    main()