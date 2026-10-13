# Procure · 采购询价与比价 Agent

刘正享的全栈 / AI Agent 项目。面向电子元器件采购，提供报价导入、条件核验、规格检索、人工澄清、证据报告与审批流程。

## v0.2 自主采购寻源

默认进入“自主寻源”：输入型号、数量、全部预算与到货期限，点击“开始自主寻源”。四个预设切换的是模拟供应商市场与示例目标；工具行动由真实模型选择。

- 正常采购：搜索供应商、获取报价、检索规格、比较成本。
- 库存不足：有限库存无法由单家供货，尝试把数量分配给多家；每份订单分别计入运费。
- 预算紧张：尝试模拟阶梯议价，失败时寻找候选型号；替代型号必须有模拟等价资料和该型号的人工工程确认。
- 约束冲突：无法满足时保留障碍，报告本轮未找到可执行方案，不编造结果。明确固定的预算和交期不能请求放宽。

新 LangGraph：目标理解 → 必要信息澄清 → 制定计划 → 模型选择工具 / 观察返回 / 继续决策 → 人工决定（可恢复） → 方案报告 → 审核。工具包括 `search_suppliers`、`request_quote`、`inspect_offer`、`negotiate_quote`、`find_alternatives`、`evaluate_plan`、`ask_user`、`finish_sourcing`。每轮决策保存检查点，最多14轮；最多3次关键决策询问。

方案由工具强制核验数量、库存、起订量、交期、规格、工程确认、税费运费与全部预算；模型不能自行改写这些判定。当前市场仅支持 DEMO-MCU 模拟系列，未知型号不会虚构供应商。价格、库存、阶梯价与替代资料均为模拟数据，没有真实询价发送或订单交易。

真实模式启动：`.\.venv\Scripts\python.exe -m scripts.serve_live`，在隐藏提示输入密钥，打开 http://127.0.0.1:8011 。保留旧“工作台”用于导入报价核验。服务不保存密钥，重启需重新提供。

新功能真实测试：`python -m scripts.sourcing_validation`。详细结果见 `SOURCING_TEST_REPORT.md` 与脱敏的 `SOURCING_TEST_RESULTS.json`。

## 运行（Windows PowerShell）

```powershell
# 首次准备
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd frontend
npm install
npm run build
cd ..

# 启动，默认规则演示模式，不需要密钥
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8010
```

打开 http://127.0.0.1:8010 。也可以运行 `start.ps1`，它会检查前端构建并启动后端。开发时后端 8010、Vite 前端 5174，Vite 代理 `/api`。

## 演示步骤

1. 点击“运行演示案例”。三个供应商均为模拟数据。
2. LangGraph 在缺少运费的位置 interrupt，状态落盘。
3. 将远川科技运费补充为 15，流程恢复。
4. 报价 A 总价 1195.00；报价 B 为 1201.50；报价 C 因封装与温度不符不能推荐。
5. 查看证据与计算过程，审核或退回报告，导出 Markdown。
6. 刷新页面或重启服务后，可在历史任务中继续待补充或待审核任务。

报价可通过 CSV/XLSX 导入（模板在 frontend/public/samples/quotes.csv）。知识库支持文本型 PDF、TXT、Markdown，保留页码与块 ID。扫描 PDF 暂不支持 OCR。

## 真实模型模式

```powershell
$env:AGENT_MODE = 'live'
$env:ANTHROPIC_API_KEY = '<你的密钥>'
$env:AGENT_MODEL = '<账号支持的模型 ID>'
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8010
```

密钥只在服务端环境变量中，不进入前端或数据库。`.env.example` 是配置说明，程序不会自动读取 `.env`。真实模式使用 LangChain ChatAnthropic + bind_tools，由模型选择读取任务、检索规格和计算成本，最多 8 轮；业务规则最后强制覆盖所有报价的核验。默认模型仅为可替换示例，是否可用取决于账号权限。

### 阿里云 GLM / OpenAI 兼容接口

已增加 `langchain.chat_models.init_chat_model` 适配，`model_provider='openai'` 仅表示协议适配，不表示模型由 OpenAI 提供。

```powershell
$env:AGENT_MODE = 'live'
$env:AGENT_PROVIDER = 'openai'
$env:AGENT_MODEL = 'glm-5.2'
$env:MODEL_BASE_URL = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
$env:MODEL_API_KEY = '<你的密钥>'
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8010
```

可运行 `.\.venv\Scripts\python.exe -m scripts.live_validation --serve`，通过隐藏输入提供密钥。脚本先测试基础调用，成功后测试真实工具调用与人工恢复，结果写入脱敏的 `LIVE_TEST_RESULTS.json`；基础调用失败时跳过依赖真实模型的测试。若启用服务，测试界面位于 8011，避免覆盖原先的演示服务。它不会自动把密钥写入配置文件，也不会自动修改提供的模型或接入地址。

无密钥时明确标为“规则演示”，不会声称大模型已执行；真实 API 调用需要用户自己的服务配置。上传资料会在真实模型模式中作为工具结果发送给模型供应商。

## 架构

- React + Vite 工作台（当前 JSX）；FastAPI API；单 Worker 后台执行。
- LangGraph StateGraph：读取 → 校验 → 澄清 interrupt → 检索 / 模型工具循环 → 报告 → 审核 interrupt → 完成。
- SQLite 业务记录与 SQLite LangGraph checkpointer：不是内存假恢复。单机单进程运行，不适合多实例共享。
- LangChain Document / tool / ChatAnthropic。RAG 采用精确型号过滤 + BM25 + TF-IDF 余弦检索；**不是远程 embedding 或 pgvector**。
- Decimal 确定性金额计算。币种仅支持 CNY；其他币种拒绝而非隐式换汇。
- SSE 步骤事件 + 状态轮询；断开页面不会取消后台任务。
- 审批带检查点版本校验与服务端状态占用；不执行邮件或采购交易。

## 证据与限制

模拟规格书具有人工设定的结构化规格，便于评估。用户上传的真实手册只进入检索，不会自动成为可信结构化规格。无可靠规格依据或候选型号需要电气等价性判断时，报告保留“待确认”；模型说明只是辅助解释，不能覆盖硬性规则。

第一版尚无真实报价 PDF 自动提取、OCR、外部供应商连接、向量模型、PostgreSQL、账户权限和真实行业准确率验证。它是本地单用户原型；勿直接公开后端（API 没有登录保护）。需要公开部署时先加入身份验证、租户隔离、队列和用量限制。

## 验证

GLM-5.2 已完成真实接口测试：6 项检查通过、0 失败，回归测试 12 项通过。详细结果与已发现问题见 `TEST_RESULTS.md`。测试使用模拟价格与规格，尚不代表真实业务准确率。

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

测试覆盖金额 / 计价单位、未知费用、硬性约束、型号检索过滤、未知规格、CSV 来源、上传知识来源、检查点重启恢复和报告审批。
