# Z-ChatBI · 多智能体数据分析系统

用自然语言提问，自动完成任务拆解、SQL 生成与执行、归因分析和图表报告。

面向的业务场景：运营/业务同学不会写 SQL，但需要快速回答"Q4 为什么增长""哪个品类贡献最大""各区域销售分布"这类问题。

## 效果

评测集 30 条问题，覆盖 5 类题型，命中 29 条，平均响应 13.29 秒：

| 题型 | 命中 | 说明 |
|------|------|------|
| 单点 | 9/10 | 单一指标查询 |
| 趋势 | 5/5 | 按时间维度聚合 |
| 分布 | 5/5 | 按品类/地区等维度拆分 |
| 归因 | 5/5 | 多任务拆解后综合解释 |
| 多跳 | 5/5 | 前一个查询结果作为后一个查询条件 |

> 指标口径：把系统返回的所有数据行拼成文本，检查期望值是否出现（数值允许 5% 误差，兼容百分数/小数写法）。该指标只验证"答案是否出现在结果中"，**不校验 SQL 逻辑是否正确**，详见[已知局限](#已知局限)。

## 架构

```
用户问题
   │
   ▼
Query Rewriter ── 多轮对话中指代消解（"那 Q3 呢" → 完整问句）
   │
   ▼
Planner ── 判断复杂度，输出子任务列表 + depends_on
   │
   ▼
Orchestrator ── 按依赖关系做 DAG 分层，ThreadPoolExecutor 并行
   │
   ├─▶ Schema Router ── 选择相关表
   │        │
   │        ▼
   │   Executor ── 生成 SQL → 只读校验 → 执行
   │        │            ▲
   │        │            └── 报错重写（最多 3 次）
   │        ▼
   │   Critic ── 校验结果是否回答原问题（最多重写 2 次）
   │
   ▼
Analyst ── 跨任务综合归因
   │
   ▼
Reporter ── 图表配置 + 报告
```

配套能力：Redis 缓存分析结果与会话历史；Celery 异步任务与状态轮询；SSE 按子任务粒度推送执行进度。

## 核心设计

1. **拆分原则**：单条 SQL 能回答的问题不拆。"趋势""分布"直接生成一条带 GROUP BY 的 SQL；"归因""多跳"才拆成多任务。目的是控制调用次数和延迟，而不是为了多智能体而多智能体。
2. **Schema 三档注入**：Planner 只看轻量表名/字段名；Executor 只看路由选中表的完整 schema + 2 行样例；全量 schema 仅在前两步失败时兜底。以此控制 prompt 体积。
3. **双层重试**：SQL 执行报错 → 带错误信息重写（最多 3 次）；执行成功但答非所问 → Critic 语义校验后重写（最多 2 次）。两层解决的是不同问题，不能合并。
4. **失败可降级**：Planner 的 JSON 解析失败时退化为单任务执行，保证接口可用；单个子任务失败不会中断整体流程，失败原因写入报告 warning。
5. **工程化**：同步接口、流式接口、异步任务三种调用方式共用同一套编排逻辑；缓存命中直接返回并更新会话历史。

## 技术栈

| 层 | 选型 |
|----|------|
| Web 框架 | FastAPI + Pydantic |
| Agent 编排 | 自研 Orchestrator（DAG 分层 + 线程池），LLM 使用 DeepSeek Chat |
| 数据访问 | SQLAlchemy（SQLite / MySQL 双后端） |
| 缓存 / 会话 | Redis |
| 异步任务 | Celery（broker/backend 均用 Redis） |
| 前端 | Streamlit |
| 数据处理 | pandas |

## 目录结构

```
Z-ChatBI/
├── backend/src/
│   ├── main.py                # FastAPI 入口（同步 / 流式 / 异步 / 上传）
│   ├── config.py              # 模型、重试次数、Redis、数据库配置
│   ├── celery_app.py          # Celery 应用与任务定义
│   ├── agents/
│   │   ├── planner.py         # 任务拆解
│   │   ├── schema_router.py   # 表路由
│   │   ├── executor.py        # SQL 生成、执行、重试
│   │   ├── critic.py          # 结果语义校验
│   │   ├── analyst.py         # 跨任务归因
│   │   ├── reporter.py        # 图表与报告
│   │   ├── query_rewriter.py  # 多轮指代改写
│   │   └── orchestrator.py    # DAG 分层与并行调度
│   ├── tools/
│   │   ├── sql_runner.py      # SQL 执行与只读防火墙
│   │   ├── data_loader.py     # CSV/Excel 清洗入库
│   │   ├── cache.py           # Redis 结果缓存
│   │   └── session.py         # 会话历史
│   ├── db/import_data.py      # Olist 数据集清洗入库脚本
│   └── tests/evaluate.py      # 评测脚本
├── frontend/app.py            # Streamlit 前端
├── download_data.py           # 下载 Olist 数据集
└── requirements.txt
```

## 快速开始

### 1. 环境

- Python 3.10+
- Redis（缓存、会话、Celery 均依赖；本机可用 `redis-server` 或 Docker 启动）
- 可选：MySQL 8（默认配置走 MySQL；没有 MySQL 时改用 SQLite）

### 2. 安装依赖

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. 配置环境变量

在项目根目录创建 `.env`：

```ini
DEEPSEEK_API_KEY=sk-你的密钥

# 可选：使用 MySQL 时填写；使用 SQLite 可留空
MYSQL_URL=mysql+pymysql://root:密码@localhost:3306/chatbi?charset=utf8mb4
```

数据库后端在 `backend/src/config.py` 中切换：

```python
DB_TYPE = "mysql"   # 改成 "sqlite" 即使用 backend/src/db/chatbi.db
```

### 4. 准备数据

仓库不包含数据集（`data/` 与 `*.db` 已在 `.gitignore` 中忽略）。二选一：

```bash
# 方式 A：下载 Olist 巴西电商数据集（需要 Kaggle 账号，kagglehub 首次使用需配置凭证）
python download_data.py

# 清洗并导入数据库
cd backend/src
python -m db.import_data
```

方式 B：直接使用前端"上传数据"，传任意 CSV/Excel，系统会自动建表并导入。

### 5. 启动

```bash
# 后端（端口 8001）
cd backend/src
python main.py

# Celery Worker（使用异步接口时需要，Windows 必须加 -P solo）
cd backend/src
celery -A celery_app worker -l info -P solo

# 前端（新终端）
cd frontend
streamlit run app.py
```

访问：

- 接口文档：http://127.0.0.1:8001/docs
- 前端：http://127.0.0.1:8501

### 6. 调用示例

```bash
# 同步分析
curl -X POST http://127.0.0.1:8001/chatbi \
  -H "Content-Type: application/json" \
  -d '{"question":"2017年Q4的销售额是多少？"}'

# 异步分析
curl -X POST http://127.0.0.1:8001/chatbi/async \
  -H "Content-Type: application/json" \
  -d '{"question":"为什么Q4比Q3增长这么多？"}'

# 查询异步任务状态
curl http://127.0.0.1:8001/chatbi/status/{task_id}
```

## 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/chatbi` | 同步分析，支持 session_id 多轮对话 |
| POST | `/chatbi/stream` | SSE 流式分析，按子任务推送进度 |
| POST | `/chatbi/async` | 提交异步任务，返回 task_id |
| GET | `/chatbi/status/{task_id}` | 查询异步任务状态（pending/running/done/failed） |
| POST | `/upload_data` | 上传 CSV/Excel，自动建表导入 |

## 评测

```bash
cd backend/src
python tests/evaluate.py
```

结果写入 `backend/src/tests/eval_result.json`，包含总体命中率、分类别命中率、每条问题的耗时、任务数、SQL 成功数、重试次数。

## 已知局限

- **评测口径偏宽**：命中判定为"结果中出现期望值"，无法排除数值恰好出现在无关列的情况，也未校验 SQL 语义是否正确。改进方向是用 golden SQL 的结果集做对比。
- **缓存版本签名对 MySQL 只覆盖表名**：SQLite 下用数据库文件的 mtime + 大小做版本，表内数据变化不会触发失效（仍依赖上传接口清缓存）；生产环境建议由数据同步任务显式递增 `DATASET_ID` 或版本号。
- **SQL 防火墙仍有边界**：已用 sqlglot 做 AST 校验（仅单语句、仅 SELECT/UNION），并拦截 `INTO OUTFILE`、`INFORMATION_SCHEMA` 等模式；未安装 sqlglot 时退回关键字黑名单 + 多语句拦截。生产环境仍应叠加只读账号、只读副本和查询超时。
- **未设置查询超时**：已把 `LIMIT` 下推到数据库侧并用 `fetchmany` 限制拉取行数，但慢查询仍可能长期占用连接，建议在连接层设置 statement timeout。
- **会话与任务无鉴权、无租户隔离**：当前为单机演示形态，未做登录、权限和多租户。
- **异步任务无心跳与超时**：Worker 崩溃后任务可能长时间停留在 running。

## Roadmap

- 用 golden SQL 结果集重做评测，补充 SQL 正确率与幻觉率
- 引入语义层（指标口径、状态枚举、join 关系）替代 prompt 中的硬编码规则
- 增加查询超时、行数下推与 EXPLAIN 预检
- 增加 trace_id 串联的全链路日志与成本统计
