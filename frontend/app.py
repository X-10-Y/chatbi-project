import streamlit as st
import requests
import pandas as pd

API_BASE = "http://127.0.0.1:8001"
# 与后端 tools/audit.py 的 REASON_TYPES 保持一致
REASON_TYPES = ["口径不对", "答非所问", "SQL 有误", "数据不对", "其他"]

st.set_page_config(page_title="ChatBI 数据分析", page_icon="📊", layout="wide")
st.title("📊 ChatBI 多智能体数据分析")
with st.sidebar:
    st.markdown("### 📁 上传数据")
    uploaded = st.file_uploader("支持 CSV / Excel", type=["csv", "xlsx", "xls"])
    if uploaded:
        with st.spinner("上传中..."):
            try:
                resp = requests.post(
                    f"{API_BASE}/upload_data",
                    files={"file": (uploaded.name, uploaded.getvalue())},
                    timeout=120
                )
                data = resp.json()
                if data.get("success"):
                    st.success(f"✅ {data['message']}")
                    st.caption(f"表名: `{data['table_name']}`")
                    if len(data.get("sheets", [])) > 1:
                        st.caption(f"包含 {len(data['sheets'])} 个 sheet")
                    # 数据已变化，清掉上一次分析结果，避免旧结论对照新数据
                    st.session_state.pop("chatbi_last", None)
                else:
                    st.error(f"上传失败: {data.get('detail', '未知错误')}")
            except Exception as e:
                st.error(f"上传失败: {e}")
    st.divider()
    st.caption("每次查询都会写入后端审计日志（问题、SQL、行数、耗时、成败），分析结论可通过下方入口反馈错误。")

st.caption("用自然语言提问，系统自动完成任务规划、SQL 生成、归因分析和报告生成")

question = st.text_input("请输入你的问题", placeholder="例如：为什么Q4比Q3增长这么多？")
if st.button("开始分析", type="primary") and question:
    with st.spinner("Agent 正在分析，约 10-30 秒..."):
        try:
            resp = requests.post(
                f"{API_BASE}/chatbi",
                json={"question": question},
                timeout=120
            )
            if resp.status_code != 200:
                st.error(f"分析失败: {resp.json().get('detail', resp.text)}")
                st.stop()
            # 存进 session_state，反馈表单提交触发 rerun 时结果不会消失
            st.session_state["chatbi_last"] = {"question": question, "result": resp.json()}
        except Exception as e:
            st.error(f"请求失败: {e}")
            st.stop()

last = st.session_state.get("chatbi_last")
if last:
    result = last["result"]
    report = result["report"]

    # 展示分析结论
    st.markdown("## 📝 分析结论")
    st.markdown(result["analysis"])

    # 展示任务概览
    col1, col2, col3 = st.columns(3)
    col1.metric("任务数", result["task_count"])
    col2.metric("执行层数", result["layers"])
    col3.metric("耗时", f"{result['elapsed']}s")

    # 展示图表
    if report["charts"]:
        st.markdown("## 📊 数据图表")
        for chart in report["charts"]:
            st.markdown(f"**{chart['title']}**")
            df = pd.DataFrame(chart["data"])
            if chart["chart_type"] == "bar":
                st.bar_chart(df.set_index(chart["x_field"])[chart["y_fields"]])
            elif chart["chart_type"] == "line":
                st.line_chart(df.set_index(chart["x_field"])[chart["y_fields"]])

    # 展示原始 SQL
    if report["tables"]:
        st.markdown("## 🔍 查询详情")
        for table in report["tables"]:
            with st.expander(f"任务{table['task_id']}: {table['description'][:50]}"):
                st.code(table["sql"], language="sql")
                st.dataframe(pd.DataFrame(table["data"]))

    trace_id = result.get("trace_id") or ""
    if trace_id:
        st.caption(f"trace_id: `{trace_id}`（反馈与审计日志凭此关联）")

    # 判错反馈：答非所问 / 口径错 / SQL 错都能标记，写后端 feedback.jsonl
    with st.expander("🙅 这条答得不对？"):
        with st.form(key=f"feedback_{trace_id or 'latest'}"):
            reason = st.selectbox("问题类型", REASON_TYPES)
            note = st.text_area(
                "补充说明（可选）",
                placeholder="例如：Q4 销售额应为含运费的支付口径；系统答成了订单金额"
            )
            submitted = st.form_submit_button("提交反馈")
        if submitted:
            payload = {
                "question": last["question"],
                "answer": result.get("analysis", ""),
                "reason_type": reason,
                "note": note,
                "trace_id": trace_id,
                "sql": "\n\n".join(t.get("sql", "") for t in report.get("tables", []))[:2000],
            }
            try:
                resp = requests.post(f"{API_BASE}/feedback", json=payload, timeout=10)
                data = resp.json()
                if resp.ok:
                    st.success(f"已记录，反馈编号 {data['feedback_id']}")
                else:
                    st.error(f"提交失败: {data.get('detail', resp.text)}")
            except Exception as e:
                st.error(f"提交失败: {e}")
