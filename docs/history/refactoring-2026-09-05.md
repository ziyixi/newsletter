# 三轮结构整理 · 2026-09-05

目标：保留功能、内容策略与质量门槛，以小模块和显式依赖改善可读性。没有迁移框架、升级依赖、改 API/proto/数据库 schema、改提示词、降低来源校验或新增后台调度。

## 每轮改动与反思

| 轮次 | 具体问题与处理 | 验证后再审视 |
| --- | --- | --- |
| 1：装配与模型结构 | HTTP factory 的资源生命周期移入 `lifecycle.py`；研究 schema 不再穿过总编 schema 的五层内部结构，共用 proto 派生的 PacketBody | 不以文件变短作为解耦证据：保留 factory 的显式注入；检查实例隔离、目录锁、失败释放、worker 先停再关 DB。schema 独立构造，字段顺序及可变树隔离不变 |
| 2：渲染与模型边界 | PNG/字体移入 `charts.py`；严格 JSON 和工作目录校验移入 54 行的 `model_io.py`，研究员不再借用总编私有函数 | 9 种图表场景逐字对比；保留 JSON 错误、大小上限、日期/符号链接/旧产物检查。不把 editor 上下文和写稿逻辑塞进通用 utils |
| 3：依赖方向与文档 | CLI 的预览直接使用 renderer；HTTP 仍导出原 `preview_html` 以兼容已有调用；启动检查使用公开模板入口；历史记录移入 history，新增当前开发说明 | CLI 不再为离线预览加载服务；预览不改变已冻结邮件。没有新增路由注册器、仓储基类、插件容器或拆散引用编号顺序 |

明确停止继续拆分：现有 adapters 的共享 HTTP 错误处理、worker 的串行调度、store 的事务边界仍清晰。仅为减少单文件行数而新增抽象，会增加阅读跳转且不能解决实际问题。当前三个新生产模块各有具体消费者和独立回归测试，不预建未来框架。

生产源码由 4,700 行变为 4,768 行，净增 68 行（约 1.4%，主要为模块导入、签名和职责说明）。这是小幅代码成本换取明确边界，不宣称总代码量减少；结构审计未发现循环依赖或跨模块私有函数导入。

## 回归证据

- 改动前保留本地源码快照与固定基线；三轮后均通过同一基线，不改期望值以适配重构。
- 策略、指令、模板、生成契约、研究提示、SDK 参数、OpenAPI、schema（含字段顺序）保持一致。
- 同环境下邮件 HTML/text/PNG/render hash 一致；另比较 9 个图表场景。跨字体/系统的 PNG 字节不承诺相同。
- 独立源码复核：生命周期完整执行体、46 个相关函数和移动的 helper 在统一改名、排除新增 docstring 后 AST 等价；SDK、错误类别、数据库、Todofy、Notion/邮件适配器未改。
- 最终 `make check`：613 passed，0 failed，0 skipped（基线 540）；Ruff 61 文件格式通过，mypy 26 个手写源无错误。保留两条原有 Starlette/httpx/AnyIO 弃用警告，未顺带升级依赖。
- 公共 proto/provenance 校验通过；同一 uv 锁离线构建 sdist/wheel，在源码目录外安装并运行显式 fake demo，包内源码和资源逐字一致。
- 本机真实 loopback HTTP 的投稿、后台编稿、冻结预览、幂等模拟投递通过；只生成临时 EML，不发送真实邮件。

- 最终本地 Linux/ARM64 镜像 `personal-newsletter:refactor-20260905`：251,663,320 bytes（约 240.0 MiB），固定 ID `sha256:7440d9a911b2ead27c76464d320117ea8270ab3845c9f5ca68365fe0a55c6de3`；37 个源码/资源文件与工作区一致，无 uv/pytest/ruff/mypy/build 开发包。
- 容器使用非 root 10001、断网、只读根目录、cap-drop/no-new-privileges 和临时 tmpfs，无用户目录或凭据挂载。实际 mock preflight 及后台 worker 完成 `POST /v1/runs → ready → preview`；0 EML，`delivery_state=not_requested`。CLI 帮助可运行；缺 token 启动失败，重复 token 和 mock/真实后端混配均拒绝。
- 容器内 HTTP 验证使用 ASGI transport；不是该镜像 TCP/healthcheck 的端到端证明。本机另有实际 TCP smoke；未重测其他 CPU 架构或真实账号能力。测试容器退出移除，只保留本地验收镜像标签，未推送。

## 清理与范围

四份历史验收/迁移文档移入 `docs/history/`，原内容保留并标注快照身份；没有删除真实数据或旧验收证据。开发缓存、构建包和一次性对比工具放在被忽略的 `.artifacts/`，保持 `.env` 与旧工具链残留的忽略保护；没有用 git clean 或覆盖用户改动。

本次重构没有读取 `.env`/登录凭据，没有真实模型、Notion、Todofy或邮件调用，没有 commit/push、线上 Actions、部署或调度变更。功能/行为一致性证据不等于保证今后每次随机模型输出同样优质，也不代替事实审核或真实邮件客户端验收。
