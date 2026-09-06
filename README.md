# Personal Newsletter

一个由外部调用驱动的私人采编服务。Python 3.12.14、FastAPI、SQLite、Codex Python SDK；不用 Codex routine、自身 cron、Redis 或多个业务进程。

```text
外部 scheduler / HTTP caller
          │ POST /v1/runs（日期 + 幂等键）
          ▼
指令目录快照 → Codex逐方向调查 → SQLite材料 + Notion持久投影
                                              │ 确认写入后
                                              ▼
                               Codex总编：补查、取舍、写稿、自审
                                              │
                          Todofy私有事件筛选 → 冻结JSON / HTML / PNG
                                              │
                              独立 send token + 冻结 hash 才能发信
```

默认 mock 模式只做离线演示；live 没有假稿或 API key 自动兜底。技术 ready 不等于事实或发布审批已通过。真实投递必须另外验收。

## 修改你希望收集什么

直接维护 [src/newsletter/instructions/](src/newsletter/instructions/)：

- [01-ai-ml.md](src/newsletter/instructions/01-ai-ml.md)：AI/ML论文、顶会、优秀研究组及公司的实质技术报告；允许 arXiv，但检查证据、对照和评议状态。
- [02-science.md](src/newsletter/instructions/02-science.md)：跨学科研究，与 AI/ML **可以同时展示**，不再二选一。
- [03-world.md](src/newsletter/instructions/03-world.md)：兴趣之外的重要世界变化、来源交叉核对和可追溯图表数据。

服务在**每次新触发**扫描所有顶层 Markdown，按文件名排序并保存不可变快照/hash。README.md、_开头的说明不执行；符号链接、空文件、过大内容或非法名称会失败。文件是题材指令，不是可执行 skill，不提供 shell/API/文件权限。可用 NEWSLETTER_INSTRUCTIONS_DIR 指定服务器上的独立只读目录；镜像已携带默认指令，无须重新安装 Codex。

最多8个方向、每方向2份材料。找不到合格材料应报告缺口，不能凑新闻。总编仍会自己补查，并按 [编辑准则](src/newsletter/policy/editorial.md) 和 [读者偏好](src/newsletter/policy/reader-profile.md) 写作；不依赖聊天 memory。“研究介绍”在邮件内直接讲清问题、方法、结果和限制，链接只是可选延伸。

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

运行状态为 queued → collecting → projecting → editing → ready / blocked / failed。每方向默认最多600秒，总编900秒；不是整期600秒。当前单进程串行工作，适合私人简报，不承诺并发采编SLA。中断模型任务标记失败，不自动重跑；Notion结果不明必须人工核对，不盲目重建页面。部分成功材料仍可查到。

新材料的引用必须对应工具实际打开的地址。地址不匹配时，在同一模型上下文和原超时预算内最多纠正一次：真正打开来源或删去未支持内容；再次不合格就失败。不会把摘要链接自动当成已读PDF，也不会自动重试供应商写入。

`newsletter-trigger` 提供随包发布的标准库客户端；[scripts/trigger_run.py](scripts/trigger_run.py) 是源码目录中的同一入口。从进程环境读取 NEWSLETTER_SERVICE_URL、NEWSLETTER_EDITOR_TOKEN，另可传 NEWSLETTER_ISSUE_DATE / NEWSLETTER_REQUEST_KEY。默认只提交，`--wait` 等待准备完成，`--send` 等待并用 NEWSLETTER_SEND_TOKEN 按冻结 hash 请求一次发送。不把 token 放进 URL、参数或输出。生产调度在 [self-host-on-vultr](https://github.com/ziyixi/self-host-on-vultr) 的独立 cron 容器中，每日 **15:00 UTC** 触发；newsletter 服务本身仍没有 cron。

公网调用必须使用固定 HTTPS origin。私有 Docker 网络可显式设置 NEWSLETTER_ALLOW_INTERNAL_HTTP=1，仅放行 `http://newsletter:8080`；不开宿主机端口，不跟随跳转。日期默认按 America/Los_Angeles 生成，同一天使用稳定的 daily 幂等键。失败或结果不明不会换键重投；先查运行与刊期状态。切换部署必须检查旧 GitHub scheduled workflow 已停用且无遗留发送运行。

| 操作 | HTTP | 权限 |
| --- | --- | --- |
| 启动/查询整期 | POST /v1/runs；GET /v1/runs/{id} | editor |
| 可选外部材料补充 | POST /v1/packets | ingest |
| 查材料 | POST /v1/inbox/query | editor |
| 用已有材料直接编稿 | POST /v1/editions | editor |
| 刊期/冻结预览 | GET /v1/editions/{id}；GET /v1/editions/{id}/preview | editor / send |
| 纯渲染 | POST /v1/render | editor |
| 单独批准发送 | POST /v1/editions/{id}/send | send |

所有消息是公共 protobuf 的 snake_case ProtoJSON。旧材料接口保留作为可选入口，不再需要外部 routine。collection: 前缀是内部幂等键空间，外部直接编稿不能占用。

## 私人事件

Todofy 位于全部公共内容之后。推荐模式一次读取最多10条候选，本地按行动价值筛选，NEWSLETTER_TODOFY_TOP 只控制最多显示几条，不要求凑满。安全/付款失败/逾期等异常优先；例行对账单、明确已自动处理的通知不凭空变成还款任务。没有证据时不假设自动还款开启或任务已经完成。

上游仍只提供最近24小时摘要，并非实时 Todoist 状态；本地规则不等于独立核查银行、邮件或账户。Todofy读取可能触发上游Gemini，不能当成免费数据库查询。内容永远不进入公开采编、Notion或公开搜索；失败在文末说明，不拖垮公共稿件。

## 启动与部署

配置样例见 [.env.example](.env.example)，完整凭据说明见 [联调清单](docs/live-acceptance.md)。应用不自动读取旧 .env。

启动在发布健康状态前检查：SQLite读写/WAL、锁定依赖、proto/resource、中文字体；live还检查配套Codex二进制、专用ChatGPT登录、禁用技能、模型目录；启用Notion则只读验证数据源；启用Todofy则检查无副作用health。失败即退出，不等到用户触发才发现。检查边界见 [运行说明](docs/collection-service.md)：账户可读不等于生成工具永久可用，公开health不能证明Todofy密码有效，也不会为检测邮件key而发信。

Docker为锁定多阶段构建，最终镜像不带uv/dev工具、旧Node/Go依赖或源码工作树。非root运行；示例Compose为只读根文件系统、有限tmpfs、本机端口和独立持久卷。Codex登录缓存需专用可写卷，不能烘焙进镜像。默认Compose仍是安全的mock配置，不是生产live部署。

GitHub Actions 在原生 Linux/amd64 runner 上先跑回归，再构建、验证最终镜像，成功后才发布 `ghcr.io/ziyixi/newsletter:service-<commit>` 与 `:service`。生产 Compose 固定通过验收的 digest，不依赖可变标签；CI 不加载任何真实账号密钥。发布前检查待提交内容及 Docker 构建上下文，`.env` 变体、登录文件和真实数据不得进入公开仓库或镜像。

一次只允许一个进程占有SQLite目录；不要放同步盘或启动多个uvicorn worker。Notion是材料的单向持久投影，不反向同步手工修改。新整期live入口要求Notion配置且确认投影后才编稿。发送按冻结render hash单独审批，每刊期最多一次尝试；结果不明不自动重投。

## 契约与验收

公共源：[protos 仓库](https://github.com/ziyixi/protos) protobuf 分支的 `proto/newsletter/editorial.proto`。公共仓库生成并验证 Python 代码、类型 stub 和 provenance，作为 **GitHub Release wheel** 发布 `ziyixi-protos`，不发布到 PyPI。newsletter 不再维护生成副本，不需要 sibling checkout 或 protoc。

导入使用 `from ziyixi_protos.newsletter import editorial_pb2`。`pyproject.toml` 固定版本并通过 `tool.uv.sources` 指向对应 release wheel，`uv.lock` 固定 URL 和 SHA-256；不会从本地路径或 `latest` 浮动下载。`make proto-check` 只检查已安装包的 descriptor/code/stub hash、来源仓库/路径/commit 与发行版本，不重新生成。新增字段须先在公共仓库发布，再更新 newsletter 的版本、wheel URL 和锁并运行回归。

离线测试显式模拟供应商与故障；真实试验单独记录，不混称“全部线上通过”。[首次真实联调](docs/history/real-e2e-2026-09-05.md)曾发现模型自审漏过统计口径误述；本轮准则已补强，但任何结构检查都不能保证事实正确。Gmail/Apple Mail/Outlook真实收件尚需用户批准后验收。

[指令驱动采编验收](docs/history/collection-acceptance-2026-09-05.md)记录真实链路、来源校验失败与修复、内容复核问题、镜像指标及未验边界。[后续重构记录](docs/history/refactoring-2026-09-05.md)记录保持行为不变的多轮整理与验证。

旧代码和迁移前的设计稿可从 Git 或本机清理归档恢复；旧天气/股价/HN 固定 fetcher 没有全部迁移。部署、投递与客户端验收结果应分别记录，不将代码支持等同于线上验证通过。
