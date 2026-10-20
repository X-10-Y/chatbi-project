import streamlit as st
import requests
import pandas as pd
st.set_page_config(page_title="ChatBI 数据分析", page_icon="📊", layout="wide")
st.title("📊 ChatBI 多智能体数据分析")
with st.sidebar:
    st.markdown("### 📁 上传数据")
    uploaded = st.file_uploader("支持 CSV / Excel", type=["csv", "xlsx", "xls"])
    if uploaded:
        with st.spinner("上传中..."):
            try:
                resp = requests.post(
                    "http://127.0.0.1:8001/upload_data",
                    files={"file": (uploaded.name, uploaded.getvalue())},
                    timeout=120
                )
                data = resp.json()
                if data.get("success"):
                    st.success(f"✅ {data['message']}")
                    st.caption(f"表名: `{data['table_name']}`")
                    if len(data.get("sheets", [])) > 1:
                        st.caption(f"包含 {len(data['sheets'])} 个 sheet")
                else:
                    st.error(f"上传失败: {data.get('detail', '未知错误')}")
            except Exception as e:
                st.error(f"上传失败: {e}")
    st.divider()
st.caption("用自然语言提问，系统自动完成任务规划、SQL 生成、归因分析和报告生成")
# 输入框
question = st.text_input("请输入你的问题", placeholder="例如：为什么Q4比Q3增长这么多？")
if st.button("开始分析", type="primary") and question:
    with st.spinner("Agent 正在分析，约 10-30 秒..."):
        try:
            resp = requests.post(
                "http://127.0.0.1:8001/chatbi",
                json={"question": question},
                timeout=120
            )
            result = resp.json()
        except Exception as e:
            st.error(f"请求失败: {e}")
            st.stop()
    # 展示分析结论
    st.markdown("## 📝 分析结论")
    st.markdown(result["analysis"])
    # 展示任务概览
    col1, col2, col3 = st.columns(3)
    col1.metric("任务数", result["task_count"])
    col2.metric("执行层数", result["layers"])
    col3.metric("耗时", f"{result['elapsed']}s")
    # 展示图表
    report = result["report"]
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