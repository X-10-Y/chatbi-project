# 🤖 ChatBI - 多角色 Agent 数据分析工作流

基于大模型（LLM）与多智能体（Multi-Agent）架构的自然语言数据分析系统。用户只需使用自然语言提问，系统即可自动完成任务拆解、NL2SQL、数据质检、归因分析与报告生成。

## 🌟 核心特性

*   **多角色 Agent 编排**：采用 Planner / Executor / Critic / Analyst / Reporter 五角色协同，职责分离，独立迭代。
*   **自研 DAG 依赖调度**：按任务 `depends_on` 进行拓扑排序，同层任务并行执行，层间串行，大幅提升分析效率。
*   **两级自我纠错机制**：语法重试（基于数据库报错）+ 语义重试（基于 Critic 质检反馈），极大提升 SQL 生成准确率。
*   **Schema 路由与 Token 优化**：在生成 SQL 前进行元数据召回，仅注入相关表结构，减少 Token 消耗并提高准确率。
*   **Celery 真异步与状态持久化**：Web 进程与 Worker 进程分离，任务状态存入 Redis，重启不丢失。
*   **多轮对话与查询改写**：基于 Redis 存储 Session 历史，仅在检测到指代词时触发大模型 Query Rewriting，节省成本。
*   **高频查询 Redis 缓存**：相同问题秒级返回（实测从 9s 降至 0.1s）。
*   **SSE 流式输出**：子任务完成即推流，首字延迟从 8s 降至 1s，提供打字机式的交互体验。

## 🛠️ 技术栈

*   **后端框架**：Python, FastAPI, Pydantic, Uvicorn
*   **大模型编排**：LangChain, 自研 DAG 调度
*   **数据库与中间件**：MySQL, SQLAlchemy, Redis (Cache & Session)
*   **异步任务队列**：Celery, Redis Broker
*   **大模型 API**：DeepSeek API

## 📂 项目结构

```text
├── backend/
│   ├── src/
│   │   ├── agents/          # 五大 Agent 实现 (Planner, Executor, Critic 等)
│   │   ├── tools/           # 工具库 (缓存、数据库执行器、数据加载)
│   │   ├── tests/           # 评估脚本与测试数据集
│   │   ├── config.py        # 配置管理 (基于环境变量)
│   │   ├── main.py          # FastAPI 服务入口
│   │   └── celery_app.py    # Celery 任务定义
├── frontend/                # Streamlit 前端测试页面
├── requirements.txt         # 依赖清单
└── .gitignore
￼
￼
🚀 快速启动
1. 克隆项目
bash
￼
￼
复制
￼
￼
下载
git clone https://github.com/X-10-Y/chatbi-project.git
cd chatbi-project
￼
￼
2. 安装依赖
bash
￼
￼
复制
￼
￼
下载
pip install -r requirements.txt
￼
￼
3. 配置环境变量
在根目录创建 .env 文件并填入以下配置：
env
￼
￼
复制
￼
￼
下载
DEEPSEEK_API_KEY=你的_API_KEY
MYSQL_URL=mysql+pymysql://root:你的密码@localhost:3306/chatbi?charset=utf8mb4
￼
￼
4. 启动服务
bash
￼
￼
复制
￼
￼
下载
# 启动 Web 服务
cd backend/src
python main.py

# 启动 Celery Worker (Windows 下需加 --pool=solo)
celery -A celery_app worker --loglevel=info --pool=solo
￼
￼
📊 评估结果
• 30 条测试问题，整体准确率 96.7%。
• 归因类与多跳类问题准确率 100%。
• Redis 缓存命中后响应时间 < 0.1s。
