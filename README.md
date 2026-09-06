# Personal Newsletter

一个由外部调用驱动的私人采编服务。Python 3.12.14、FastAPI、SQLite、Codex Python SDK；不用 Codex routine、自身 cron、Redis 或多个业务进程。

```text
外部 scheduler / HTTP caller
          │ POST /v1/runs（日期 + 幂等键）
          ▼
冻结 YAML/指令/日期 → 六方向发现 + API/RSS + 历史观察
          │
去重候选池 → 全局选题 → 每题简版独立核验/保存 → 重点题独立深读/核验
          │                                       │
SQLite证据/已审版本 → Notion后台镜像        已审完整版本确定性拼版
                                                  │
                             Todofy私有事件 → 冻结JSON / HTML / PNG
                                                  │
                                 独立send token + 冻结hash + 同日防重
```

默认 mock 模式只做离线演示；live 没有假稿或 API key 自动兜底。技术 ready 不等于事实或发布审批已通过。真实投递必须另外验收。

## 修改你希望收集什么

Live 默认使用 [可编辑 DAG](src/newsletter/workflows/daily.yaml) 和
[六个发现方向](src/newsletter/instructions/discovery/)。流程、预算和依赖写 YAML；
题材要求写 Markdown；数据契约仍在公共 proto。详细说明见 [DAG 与用量](docs/workflow.md)。

默认最多30条候选，选最多8个问题（可配置到12）；每题先核实简版，再对最多4题深入调查、展示最多2篇深读；
不是必须填满的配额。Crossref/Nature RSS 只提供元数据线索，不冒充已读论文。
AI/ML与其他学科可同时入选，历史候选帮助去重；总编仍需调查、解释和核对反证。

服务在每次新触发冻结 DAG、方向指令、编辑政策、历史和模型配置。README.md、_开头的说明不执行；符号链接、空文件、过大内容或非法名称会失败。配置只能调用注册节点，不能执行 shell、展开密钥或获得发信权限。镜像包含默认资源，也可只读挂载 NEWSLETTER_WORKFLOW_FILE / NEWSLETTER_DISCOVERY_DIR。

旧顶层 [instructions/](src/newsletter/instructions/) 和串行采集器仅用于显式 NEWSLETTER_WORKFLOW=legacy、旧运行恢复与离线 mock；不是 live 失败的回退。新采编遵循 [选题级编辑准则](src/newsletter/policy/story-editorial.md) 和 [读者偏好](src/newsletter/policy/reader-profile.md)，不依赖聊天 memory。“研究介绍”不点链接也应自足，支持主阅读链接之外的补充证据引用。

## 开发

先安装 uv 0.12.10，再运行：

```sh
make setup
make check
make build
make smoke-codex
```

uv.lock 是唯一依赖锁；安装用 --locked，构建不重新生成 protobuf，启动不下载依赖。make demo 是显式假稿演示，会生成本地模拟 EML；不访问任何供应商。产物统一放在 .artifacts/（缓存、dist、demo），真实数据与凭据必须使用仓库/同步盘之外的目录。

| 位置 | 职责 |
| --- | --- |
| src/newsletter/app.py、lifecycle.py | HTTP鉴权/路由；独立的资源创建、预检和关闭 |
| src/newsletter/collection/ | 指令快照、采集、持久运行记录和整期编排 |
| src/newsletter/workflow/、workflows/ | 受限DAG定义、逐节点持久化、候选/研究/审校、运行账本 |
| src/newsletter/usage.py | 供应商用量累计快照、缺失标记和低调页脚 |
| src/newsletter/editor.py | 总编、模型结果/引用验证 |
| src/newsletter/preflight.py | 启动依赖与账号检查，失败即拒绝启动 |
| src/newsletter/codex_runtime.py、model_schema.py | 隔离 SDK 启动与 proto 派生的结构化输出约束 |
| src/newsletter/model_io.py | 研究员与总编共用的严格JSON解析和工作目录校验 |
| src/newsletter/store.py、worker.py | SQLite事务、串行工作队列、崩溃恢复 |
| src/newsletter/todofy.py、adapters.py | 私人事件、Notion、邮件供应商边界 |
| src/newsletter/rendering.py、templates/、charts.py | 邮件正文与预览；独立的PNG绘图 |
| ziyixi-protos 依赖包 | 公共 protobuf 代码、类型及来源清单；由 GitHub Release wheel 分发 |
| tests/、scripts/ | 离线回归、runtime/HTTP/安装包验证、外部触发客户端 |

[开发说明](docs/development.md)说明依赖方向、扩展入口与回归边界。当前操作文档留在 docs/；旧验收和迁移记录归档在 docs/history/，不要把历史“下一步”当成现行部署指令。

## 外部触发

仅准备内容的外部服务只持有 **editor token**。经用户明确授权的自动投递触发器可另外持有独立 **send token**；不持有供应商密钥或 Codex 登录。调用：

```http
POST /v1/runs
Authorization: Bearer <editor-token>
Content-Type: application/json

{"request_key":"daily-2026-09-05","issue_date":"2026-09-05"}
```

立即返回202和运行ID。GET /v1/runs/{id} 查询进度，完成后取得 edition_id，再查询刊期和预览。相同键和日期重试返回原运行，不重复搜索或写 Notion；修改指令后想重新采集需用新键。请求结果不明时只重试同一键。整期流程**不调用发送接口**。

外层运行状态保留 queued / collecting / editing / ready / blocked / failed；workflow 字段展示各节点状态、候选/研究数量及定义hash。默认DAG总预算5400秒，节点另有上限；外部触发器应等候7200秒，不能仍沿用一小时客户端超时。当前单进程保守串行执行模型，动态任务数不等于物理并发。完成节点不会重跑；中断中的模型任务标unknown并阻止自动重试。Notion结果不明必须核对，不盲目重建页面。

新流程不再由整期二次 HOLD 决定所有选题的命运：正文/推荐卡/图表/观察短讯分别审校，正文最多一次定向修订。已核实简版立即保存，深读失败、截止或中断时用已审核的完整版本拼版；没有任何已核实内容仍拒绝发信。`publication` 字段逐题记录 deep/brief/watch/deferred 及原因，未完成的问题作为后续线索；明确发现事实错误只能按精确版本和独立证据撤回。旧冻结图和门槛不改。外部 cron 负责触发和发送，人工查看日志不是运行依赖。

新材料的引用必须对应工具实际打开的地址。地址不匹配时，在同一模型上下文和原超时预算内最多纠正一次：真正打开来源或删去未支持内容；再次不合格就失败。不会把摘要链接自动当成已读PDF，也不会自动重试供应商写入。

`newsletter-trigger` 提供随包发布的标准库客户端；[scripts/trigger_run.py](scripts/trigger_run.py) 是源码目录中的同一入口。从进程环境读取 NEWSLETTER_SERVICE_URL、NEWSLETTER_EDITOR_TOKEN，另可传 NEWSLETTER_ISSUE_DATE / NEWSLETTER_REQUEST_KEY。默认只提交，`--wait` 等待准备完成，`--send` 等待并用 NEWSLETTER_SEND_TOKEN 按冻结 hash 请求一次发送。不把 token 放进 URL、参数或输出。生产调度在 [self-host-on-vultr](https://github.com/ziyixi/self-host-on-vultr) 的独立 cron 容器中，每日 **15:00 UTC** 触发；newsletter 服务本身仍没有 cron。

公网调用必须使用固定 HTTPS origin。私有 Docker 网络可显式设置 NEWSLETTER_ALLOW_INTERNAL_HTTP=1，仅放行 `http://newsletter:8080`；不开宿主机端口，不跟随跳转。日期默认按 America/Los_Angeles 生成，同一天使用稳定的 daily 幂等键。失败或结果不明不会换键重投；先查运行与刊期状态。切换部署必须检查旧 GitHub scheduled workflow 已停用且无遗留发送运行。

| 操作 | HTTP | 权限 |
| --- | --- | --- |
| 用户明确要求的修订验证邮件（默认每日期额外至多一次，保留原投递记录） | POST /v1/editions/{id}/send-verification | send |
| 启动/查询整期 | POST /v1/runs；GET /v1/runs/{id} | editor |
| 可选外部材料补充 | POST /v1/packets | ingest |
| 查材料 | POST /v1/inbox/query | editor |
| 用已有材料直接编稿 | POST /v1/editions | editor |
| 刊期/冻结预览 | GET /v1/editions/{id}；GET /v1/editions/{id}/preview | editor / send |
| 纯渲染 | POST /v1/render | editor |
| 单独批准发送 | POST /v1/editions/{id}/send | send |

所有消息是公共 protobuf 的 snake_case ProtoJSON。旧材料接口保留作为可选入口，不再需要外部 routine。collection: 前缀是内部幂等键空间，外部直接编稿不能占用。

同一天已成功发过验证邮件后，只有用户再次明确要求，操作员才能对**新的 ready 刊期**调用 `send-verification`：请求体仍为 `id`、稳定的 `request_key` 和该刊期的 `expected_render_hash`，另加 `X-Newsletter-Verification-After: <上一封已确认接受的验证刊期 UUID>`。该 UUID 必须是同日期验证链的最新末端；每个末端只允许一个后继，旧 UUID、未确认/失败投递都不能授权新邮件。调用仍需要 send token，发送目标仍绑定原数据库；不自动启用此能力，不改 cron 或普通每日发送。重复请求只返回既有投递结果，结果未知时不会重投。

升级时 SQLite 在单一事务内迁移验证台账，保留旧记录并改用唯一刊期、请求键和前序刊期约束；普通 `sends` 每日唯一约束不变。部署前备份数据库；一旦存在同日多条验证记录，**不要回退到旧的一日一行数据库结构**，它无法表示完整台账。回退代码也须保留新台账及幂等检查，不能删除投递记录来重试。已有新投递后也不能恢复投递前的数据库备份，否则会丢失幂等凭据、造成重复发送风险。

## 私人事件

Todofy 位于全部公共内容之后。推荐模式一次读取最多10条候选，本地按行动价值筛选，NEWSLETTER_TODOFY_TOP 只控制最多显示几条，不要求凑满。安全/付款失败/逾期等异常优先；例行对账单、明确已自动处理的通知不凭空变成还款任务。没有证据时不假设自动还款开启或任务已经完成。

上游仍只提供最近24小时摘要，并非实时 Todoist 状态；本地规则不等于独立核查银行、邮件或账户。Todofy读取可能触发上游Gemini，不能当成免费数据库查询。内容永远不进入公开采编、Notion或公开搜索；失败在文末说明，不拖垮公共稿件。

## 启动与部署

配置样例见 [.env.example](.env.example)，完整凭据说明见 [联调清单](docs/live-acceptance.md)。应用不自动读取旧 .env。

启动在发布健康状态前检查：SQLite读写/WAL、锁定依赖、proto/resource、中文字体；live还检查配套Codex二进制、专用ChatGPT登录、禁用技能、模型目录；启用Notion则只读验证数据源；启用Todofy则检查无副作用health。核心运行条件或授权/配置错误失败即退出；Notion/Todofy暂时网络不可用以degraded安全日志启动，不能拖垮本地公共内容。检查边界见 [运行说明](docs/collection-service.md)：账户可读不等于生成工具永久可用，公开health不能证明Todofy密码有效，也不会为检测邮件key而发信。

Docker为锁定多阶段构建，最终镜像不带uv/dev工具、旧Node/Go依赖或源码工作树。非root运行；示例Compose为只读根文件系统、有限tmpfs、本机端口和独立持久卷。Codex登录缓存需专用可写卷，不能烘焙进镜像。默认Compose仍是安全的mock配置，不是生产live部署。

GitHub Actions 在原生 Linux/amd64 runner 上先跑回归，再构建、验证最终镜像，成功后才发布 `ghcr.io/ziyixi/newsletter:service-<commit>` 与 `:service`。生产 Compose 固定通过验收的 digest，不依赖可变标签；CI 不加载任何真实账号密钥。发布前检查待提交内容及 Docker 构建上下文，`.env` 变体、登录文件和真实数据不得进入公开仓库或镜像。

一次只允许一个进程占有SQLite目录；不要放同步盘或启动多个uvicorn worker。Notion是材料的单向后台镜像，不反向同步手工修改。新选题DAG先本地持久化证据和审核版本，不等待Notion投影；旧冻结刊期仍保留原采用材料投影门槛。发送按冻结render hash单独审批，每日最多一次尝试；结果不明不自动重投。

邮件最底角显示本期已记录的 Codex tokens，覆盖发现、选题、深读、拟稿、补查、定稿与审校，包括有用量事件的失败尝试。缓存输入是子集，不重复加总；无用量事件不是零。Todofy接口没有返回Gemini usage，因此明确未计入，不把上下文日志当用量或费用。统计也包含在冻结render hash里。

## 契约与验收

内容质量与结构验收分开：[prompt 评测标准与本地运行方法](evals/README.md)
记录选题、解释深度、事实校准、阅读收益和成本。实验必须显式授权真实模型调用，
结果保存在仓库与同步目录之外；不加载 `.env`，不连接 Notion、不触发邮件。
`evals/prompts/` 是待比较版本，不会被生产 DAG 自动扫描或替换默认政策。

2026-09-06 的上线选择：将 v3 选题与 v1 CS／金融发现要求显式复制到生产
`workflow/content.py` 和 `instructions/discovery/`；选题同时接收本次任务冻结的
`reader-profile.md`。v3 摘要在留出集上的提升不足，未替换正文写作政策。
这是一轮有限材料上的改进，不代表事实准确率或跨日期质量已获得保证；
独立审校、失败记录、原始来源核对和真实邮件验收仍须保留。

公共源：[protos 仓库](https://github.com/ziyixi/protos) protobuf 分支的 `proto/newsletter/editorial.proto`。公共仓库生成并验证 Python 代码、类型 stub 和 provenance，作为 **GitHub Release wheel** 发布 `ziyixi-protos`，不发布到 PyPI。newsletter 不再维护生成副本，不需要 sibling checkout 或 protoc。

导入使用 `from ziyixi_protos.newsletter import editorial_pb2`。`pyproject.toml` 固定版本并通过 `tool.uv.sources` 指向对应 release wheel，`uv.lock` 固定 URL 和 SHA-256；不会从本地路径或 `latest` 浮动下载。`make proto-check` 只检查已安装包的 descriptor/code/stub hash、来源仓库/路径/commit 与发行版本，不重新生成。新增字段须先在公共仓库发布，再更新 newsletter 的版本、wheel URL 和锁并运行回归。

离线测试显式模拟供应商与故障；真实试验单独记录，不混称“全部线上通过”。[首次真实联调](docs/history/real-e2e-2026-09-05.md)曾发现模型自审漏过统计口径误述；本轮准则已补强，但任何结构检查都不能保证事实正确。Gmail/Apple Mail/Outlook真实收件尚需用户批准后验收。

[指令驱动采编验收](docs/history/collection-acceptance-2026-09-05.md)记录真实链路、来源校验失败与修复、内容复核问题、镜像指标及未验边界。[后续重构记录](docs/history/refactoring-2026-09-05.md)记录保持行为不变的多轮整理与验证。

旧代码和迁移前的设计稿可从 Git 或本机清理归档恢复；旧天气/股价/HN 固定 fetcher 没有全部迁移。部署、投递与客户端验收结果应分别记录，不将代码支持等同于线上验证通过。
