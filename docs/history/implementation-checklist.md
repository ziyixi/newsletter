# 单服务实现与验收 · 2026-09-05

历史快照，不是当前操作清单；架构和运行方式以 [README](../../README.md) 为准。

## 本地已验证

- 一个 Python 服务，六个 ProtoJSON HTTP 操作；SQLite + 单后台总编 worker。
- 全套离线单元/集成测试；普通测试禁止外网 socket，供应商请求仅 MockTransport。
- 实际 uvicorn loopback 投稿 → 后台编稿 → 冻结预览 → 一次模拟发送，包括重复请求。
- 公共源与生成代码/provenance 的 `--check`、Ruff lint/format，以及已安装依赖一致性检查。
- 构建 Python wheel、核对模板/policy/fixture/provenance 随包打入，在源码目录外运行 wheel demo。
- 中文 PNG 已目视检查；HTML、纯文本、带 CID 图片的模拟 EML 已生成。
- 2026-09-05 邮件改版：293 项离线测试通过；Todofy 私有栏目、故障降级、独立超时、冻结 hash、重复请求不重取均有覆盖。
- 1000px 桌面、390px / 320px 手机已截图检查，无横向溢出；移除 head 样式后仍可读，无图版本仍保留原始数据表及来源链接。
- 已恢复旧 Todofy Basic Auth 接口的适配器，但本轮只使用 fake；私人事件不交给公共总编，也不写入 Notion。
- 后续位置调整：Todofy 移至来源/本期说明之后、品牌页脚之前，纯文本同样最后；新增有图/无图顺序回归后共 295 项测试通过。最新样稿为 `.demo-personal-last/preview.html`，此前改版截图仅作历史对照。
- 用空白临时 Codex home 核对 pinned runtime 功能开关，不启动真实模型、不读个人登录。
- 后续只读预检确认 Docker CLI / daemon 29.7.2、Compose v5.5.0 可用（desktop-linux）；版本查询不等于镜像构建或容器验收通过。

## uv 与类型检查迁移

- 工具链固定为 Python 3.12.14、uv 0.12.10；`uv.lock` 是唯一依赖锁，开发工具使用 dev dependency group，Codex 保留为 extra。
- 本地与 CI 使用 `make setup` 的 `--locked` 安装；`make check` 统一执行锁检查、Ruff、Mypy 与 pytest。`make build` 构建 Python 包；`make smoke` 仍只做 fake/loopback 验证。
- Mypy 检查手写服务，生成 protobuf 的 `.pyi` 与 `.py` 由同一公共源生成、随包分发并记录 hash；`make proto-check` 做逐字核对，不重新定义契约。
- Docker 多阶段构建只安装锁定的运行依赖与 Codex extra，最终环境非 editable、无 dev 工具和 uv；服务启动直接运行已安装的命令。
- 最终源码的 Linux/ARM64 和 Linux/AMD64 镜像均已构建并通过断网、非 root、只读根目录下的 HTTP smoke；镜像内源码指纹与工作区一致，中文字体及配套 Codex runtime 版本检查通过。
- CI 增加独立 wheel 验证：临时导出同一锁的带 hash 生产依赖，在源码外安装发布包、检查资源与 runtime，并运行 fake demo；源码包包含同一锁和 Python 版本文件。
- 新增 8 项离线工具链回归已通过：依赖锁/直接版本、分组、Python/uv 跨入口版本、类型 stub 打包、Make 质量门禁、Docker 上下文 allowlist/生产安装/直接启动、CI 质量门禁。
- 最终 `make check`：305 项测试通过，Mypy 检查全部 12 个手写源无错误，Ruff 检查及 29 文件格式检查通过。公共 proto 逐字校验、源码包和 wheel 独立安装均已验证；详见 [uv 迁移验收](uv-migration.md)。

## 尚未验证 / 尚未切换

- 账号允许模型、额度刷新、SDK hosted search/打开原文，以及实际成稿质量；用户已完成专用登录，但登录状态不等于模型调用验收。
- 真实 Notion 数据源权限与创建结果、Resend 和各邮件客户端的实际显示/投递。
- 本轮只在本机验证容器，没有推送或运行远端 GitHub Actions，也未验证服务器持久化、TLS、账号刷新或部署。
- 浏览器截图仅验证布局，不代表 Gmail / Apple Mail / 经典或新版 Outlook 的实际收件效果；深色模式尚未在真实邮件客户端验收。
- 没有发布公共 proto 产物、commit/push、部署服务、创建定时 routine 或变更 GitHub 定时发送。

## 下一次联调顺序

1. 使用 `make setup` 的锁定环境，运行 `make check`、`make build`、`make smoke` 和公共 proto `--check`；先确认假稿版式与 API。
2. 在专用登录目录、专用 live DB、fake mail 模式下，用少量真实材料跑 SDK；检查补查能力及文章质量，不发信。
3. 按需接 Notion；它只是单向 inbox 投影，不是必须组件。
4. 明确批准一次精确预览后再验收真实邮件。启用新发送前先停旧 daily，防重复。
5. 最后再建立采编 routines：只配 ingest/editor 所需权限，不给发送 token。真实投递的历史才进入去重上下文。

## 邮件视觉复核记录

本地假稿：`.demo-redesign-final/preview.html`。截图位于被 Git 忽略的 `.demo-design-review/`：

- `06-final-desktop.png`：新版刊头、导读和个人事件层次。
- `07-before-desktop-matched.png`：同为 1000 × 1000 的旧版对照。
- `08-final-mobile.png`、`09-final-mobile-chart.png`、`10-final-narrow.png`：手机首屏、图表和窄屏。
- `11-inline-only-mobile.png`、`12-no-images-mobile.png`：样式表与图片被移除的降级检查。

采用邮件表格布局、内联关键样式、系统字体、CID PNG、可读的数据表和文末外链；没有依赖 JavaScript、折叠组件或邮件页内锚点。选择更清晰的刊头/正文层级，减少重复测试前缀，同时保留明确的模拟内容标识。这些样张不含真实新闻或账户记录。
