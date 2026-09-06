# GitHub Python proto 依赖迁移 · 2026-09-05

范围：公共源/生成/发布归 protos，newsletter 只消费版本化 Python wheel；不使用 PyPI，不变更业务字段、HTTP 或内容策略。纯依赖迁移验证完成后，真实 E2E 发现既有 ID 格式说明缺口，另作下述小范围修复。

## 已发布与锁定

- proto 源已提交、推送到 `protobuf`：[`08318a20a86648efa45371b3b52dcdf92c698d3d`](https://github.com/ziyixi/protos/commit/08318a20a86648efa45371b3b52dcdf92c698d3d)。
- [Python Actions](https://github.com/ziyixi/protos/actions/runs/34010167782) 与 [Go Actions](https://github.com/ziyixi/protos/actions/runs/34010167642) 均成功；Go 产物发布到 `main` 的 `d56ec665887222690eb1b79e112b0c1219e09c8c`。Todofy 消费者的依赖版本未改。
- GitHub Release：[python-v0.1.0.dev1](https://github.com/ziyixi/protos/releases/tag/python-v0.1.0.dev1)，对应 `ziyixi-protos==0.1.0.dev1`，wheel 8,029 bytes。
- wheel SHA256：`7d4fe875dde4738bd725a8f29701ee36b9c83bf8409b7a3c35876f2e26aa9157`；GitHub asset digest 与 newsletter `uv.lock` 一致。
- 首个 Python variant 只包含 newsletter 消息、stub、`py.typed` 和 provenance，不包含 gRPC 或业务代码；既有 Go 生成和消费路径保留。

newsletter 的 `tool.uv.sources` 指定 release wheel，普通依赖固定版本；安装使用 `uv sync --locked`。本机临时 dev0 包只用于发布前验证，已由真正的 Actions dev1 产物替换。没有最终本地 path/editable proto 依赖，也没有假冒本地 wheel 为 GitHub 产物。

## 行为与构建验证

- 纯依赖迁移阶段：626 项离线测试通过，0 failed/0 skipped；Ruff、mypy（26 个手写源）、锁检查、proto 完整性检查和 diff-check 通过。两条原有 Starlette/httpx/AnyIO 弃用警告未顺带处理。
- 纯依赖迁移阶段：归一化 descriptor（仅移除虚拟文件名）、schema 字段顺序、OpenAPI、提示词/内容资源/SDK 配置，以及 9 类 HTML/text/PNG/hash/preview 与迁移前一致。
- Python 模块现在是 `ziyixi_protos.newsletter.editorial_pb2`；虚拟 proto 文件名改变，但业务包名仍为 `newsletter.v1`。包的普通 import、pickle、ProtoJSON、oneof 和 optional presence 均有回归。
- 删除了 newsletter 本地生成代码/stub/provenance 副本及生成脚本；来源生成校验归公共仓库，消费者的 `make proto-check` 验证已安装 wheel。旧快照可恢复，未删除实际业务数据。
- sdist/wheel 构建和源码外独立安装、fake demo 通过。首次完全离线安装缺少 `--require-hashes` 所需的原始 wheel 缓存；明确下载同一固定公开 release 后通过，并再次完全离线复验。URL 与导出哈希始终正确，没有退回本地路径或放宽哈希校验。
- 两项格式修复后的最终本地 Docker：`personal-newsletter:github-proto-20260905`，ID `sha256:445a82fd2ee7675b5353d47c4e1dd2886fbe85a722bd50408d91f296c0db80b5`，251,668,549 bytes（约 240 MiB），Linux/ARM64。
- 固定 ID 容器断网、非 root、只读 rootfs、仅临时 tmpfs、无 host/凭据挂载。33 个应用文件及 6 个 proto 文件一致，无本地 generated 副本及开发工具。实际 mock preflight、后台采集→ready→预览通过，0 EML；容器 HTTP 使用 ASGI transport，不宣称容器 TCP/真实账号已验。镜像未推送或部署。

## 真实、无邮件 E2E

使用新独立 DB 与 request key；真实三方向指令、Codex、Notion、Todofy，不手工投稿或混入假材料。发送路由、邮件适配器、发送预约和数据库发送插入均硬禁止，邮件凭据不进入服务环境。

### 第一次运行及格式缺口

- Run `06ffab60-5f24-4c62-b645-41cb387099f5`：真实启动检查通过。AI/ML 方向完成 2 份材料并写入 Notion；自然科学方向输出中的 `source.id` 使用了含 `/` 的 DOI，被既有严格校验拒绝，运行以 `collection_invalid_result` 停止。世界新闻、总编及 Todofy 抓取尚未执行。
- 2 次研究 execute；已写的 2 份 Notion 材料均独立只读回查成功。邮件调用 0、发送预约 0、EML 0。失败记录及 Notion 页面保留，没有人工修正模型 JSON 或重放同一请求。
- 原因是源 ID 在模型 JSON Schema 中仅标为 string，而服务要求 1–128 个 ASCII 字符、首位字母/数字、余下只允许字母/数字/`_.:-`。`/` 是引用中 packet/source 的分隔符，不应通过放宽 validator 接受 DOI。
- 修复：复用原有 ID grammar，在 Source.id / 总编临时补充材料 id 的输出 schema 中补充 pattern 和解释，研究提示明确短 ID 与 URL 的区别；服务 validator 的接受集合未变。OpenAI 的 [Structured Outputs 支持 pattern 约束](https://developers.openai.com/api/docs/guides/structured-outputs#supported-schemas)；各正则引擎的末尾换行语义不同，最终仍使用应用的严格全串校验。
- 修复后检查原始、未更新的迁移 baseline：只有 schema 和研究 ID 格式提示两项发生预期变化，其余 API、业务 descriptor、模型配置、内容策略与 9 类渲染均一致。仅在诊断进程内移除新增 ID 说明后，原始全量 baseline 也完全匹配。
- 新增 17 项 ID 回归：模型采集/总编 schema 的 Source.id 与补充材料 id 约束、合法边界、斜杠/URL/DOI/非 ASCII/超长 ID、后端末尾换行严格拒绝。此阶段 **643 项测试通过**；Ruff/format、mypy、锁、proto 完整性和 diff-check 全通过。两项格式修复完成后，Docker 已重新构建并按上面的最终固定 ID 完成同样隔离验收。

### 独立重新运行

- 第二次 Run `0d89bbe3-9aa4-469f-8ba9-22c712a3e2f8`：316.2 秒，三方向完成 4 份材料，4 次真实 execute（3 采集 + 1 总编），4 份 Notion 投影全部只读回查成功。总编完成真实检索和补查，但一处引用的 packet UUID 写错，最终被 `INVALID_CITATION` 拒绝，run 为 `editor_invalid_result`。模型 review 承认该处错误却仍 passed，服务没有信任这项自检。Todofy 尚未抓取，0 邮件/发送预约/EML。
- 第二个格式修复：总编 schema 按本次输入材料生成精确 packet/source 配对约束，逐项转义 ID；补查材料限定 `supplement-1` 至 `supplement-6` 临时命名空间，其来源仍须由后端检查实际存在。prompt 显式提供 `available_citations`，要求逐字复制，不能把修正留给管线。没有新增模型重试、外部写入重放或自动修正引用。对第二轮原始模型产物进行只读复验，新 schema 正好拒绝那一条错误引用。
- 新增 35 项引用格式/SDK 接线回归；最终完整测试 **678 项通过**，Ruff/format、mypy、uv lock、proto-check 和 diff-check 均通过。引用字段覆盖正文、两类图表观测值及推荐阅读；即使 review.passed=true，后端仍拒绝未知引用，不会修正后放行。
- 引用修复后再次对原始 baseline 比较：只有模型 schema、研究 ID 提示及总编引用提示发生预期变化；公开 descriptor、OpenAPI、内容策略/研究指令/模板、runtime 及全部 9 类渲染样例保持一致。
- 两轮失败记录均保留；后续使用新 DB / request key，不改失败状态，也不向失败稿注入人工或 mock 材料。

### 最终独立运行

- **通过**：Run `a987b886-5e57-4ab6-87e2-f4d3f7826d49`，Edition `e5e639f0-5679-4ec1-9de2-589308c6fad8`，状态 `ready`，采编等待 326.4 秒。
- 实际加载 GitHub 发布的 `ziyixi-protos==0.1.0.dev1`，source commit `08318a20a86648efa45371b3b52dcdf92c698d3d`；真实模型 `gpt-5.6-sol`，4 次 execute（3 采集 + 1 总编），每次都有 search/open 证据。execute 保留原有一次有界来源打开纠正，不能把 execute 数等同于供应商 turn 数。
- 4 份指令采集材料 + 1 份总编补查材料，共 5 份真实材料成功写入 Notion。停 worker 后独立分页只读回查，5 份内容、来源及 packet/hash 标记全部与本地持久化匹配，未发现重复投影。三轮共新增 11 份草稿投影（2 + 4 + 5），失败轮的 6 份未擅自删除。
- Todofy 真实鉴权抓取 1 次，`current`，最终展示 5 条事件，位于正文、推荐阅读与来源之后。私人事项未进入研究/总编提示、公共材料或 Notion；预览内容不等同于对上游私人摘要的原文核验。
- 真实 loopback HTTP 的重复 request key 仍返回同一 run；渲染哈希和预览字节一致。新进程仅以只读方式重新打开冻结 DB/产物验证通过；**不是带真实供应商预检的服务重启测试**。
- `delivery_state=not_requested`；邮件调用 0、发送预约 0、EML 0，发送 API/适配器/预约/DB 插入均被阻止。真实采编无 mock 材料；邮件投递与真实收件箱兼容性因明确禁发而未测试。
- 本期 HTML 36,460 bytes，render hash `b5e1cdca5862554552d2be4155c10aa9903765b42d24f8d37b6706d4bad711d6`。模型未生成图表，并在本期说明中解释厄尔尼诺观测点时间口径不一致、不宜强行绘制；图表功能仍由 9 类渲染回归覆盖，**本次真实 E2E 未覆盖实数 PNG 生成**。
- 预览已在 Codex 内置浏览器打开：[本期预览](http://127.0.0.1:53166/preview.html)。该临时服务只监听 loopback，只提供已冻结的 HTML，不暴露目录、业务 API 或发信入口。
- 本地验收证据：`/private/tmp/newsletter-proto-live.lOoIAi/citation-check/`，包含 report、run、edition、原始公共模型输出、Notion 回查及冻结重载报告。包含真实私人事件的 edition/HTML/text 保持本机私有权限，不进入仓库。
- 测试结束后删除了本次生成的临时凭据副本；原始 `.env` 与专用 Codex 登录目录未改动。真实服务/worker 已关闭，仅保留上面的只读预览服务。

### 内容验收边界

公开材料及最终稿已做独立、主信源抽查，未见严重中心事实错误，但工程通过不等于全面事实认证；预览是未发送的审阅稿。以下问题保留在真实产物中，没有人工修改测试输出：

- 表格学习论文的“三至四成耗时”未充分限定实验策略；SAINT 有 5 个数据集因内存不足未完成，不能推断所有模型/数据集组合都成功。119%/123% 已正确说明为相对 AUPRC 比值。
- 量子研究的核验仅到摘要；最终稿对同行评议元数据仍过于保守，这不意味着论文未经同行评议。
- WHO 补查材料 `excerpt` 含未标省略的删节拼接，不应当逐字引语展示。最终正文是中文概述，中心数字已对照官方页；当前邮件模板不展示来源 excerpt。
- Todofy 内容仍是上游概述经过本地保守筛选，不代表已核实银行原文、联系电话、实际自动还款状态或当前 Todoist 任务。本次没有根据这些内容执行任何操作。

newsletter 本地修改尚未提交或推送；此轮只发布了公共 proto 仓库。没有部署服务、启用定时任务或变更线上 newsletter 调度。
