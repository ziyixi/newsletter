# 指令驱动采编验收 · 2026-09-05

实现阶段的验收快照；后续不改变行为的整理见 [重构记录](refactoring-2026-09-05.md)。

范围：实现外部 HTTP 触发 → 指令快照 → 真实研究 → Notion 材料持久化 → 总编补查/写稿 → Todofy 私人事件 → 冻结预览。没有发真实邮件、提交、推送、部署或改变线上调度。测试凭据和私有预览未进入仓库。

## 已验证

| 项目 | 结果 | 证据/边界 |
| --- | --- | --- |
| 离线回归 | PASS | 540 项 pytest；包含鉴权、指令快照、原子保存、去重、Notion 不确定结果、崩溃恢复、来源纠正、事件筛选和邮件兼容边界 |
| 代码与契约 | PASS | Ruff check/format、mypy 23 个源文件、公共 proto 逐字生成/provenance 校验、uv 锁检查 |
| 发布包 | PASS | 锁定依赖安装到仓库外，校验所有源码资源一致性，包含三份指令、模板、中文资源与 Codex runtime |
| 本机 HTTP | PASS | loopback 工作队列与冻结预览；显式离线模拟投递另测，不是向真实收件人发信 |
| Todofy 修改 | PASS | `TestRecommendationPrompt` 与 `TestHandleRecommendation_DoesNotPadBelowLimit` 的 Go 定向回归通过；上游新 prompt 未部署 |
| 生产镜像 | PASS | 251,660,635 bytes（约 240 MiB），arm64，23 个生产 distributions；不包含 uv/pytest/ruff/mypy/build 或旧 Node/Go 依赖 |
| 镜像隔离启动 | PASS | 无网络、只读根文件系统、UID 10001、无 host 挂载、降权；SQLite/CJK/PNG/proto/policy 真预检，3 指令的 mock 流程 ready，预览 HTTP 200，无 EML |
| 镜像缺登录 | PASS | 空 Codex auth 使用真实配套 SDK/runtime，0.65 秒内以 `CODEX_CHATGPT_AUTH_REQUIRED` 拒绝启动 |
| 真实整期 | PASS（技术链路） | 单次 `POST /v1/runs`，同键重复返回同 run；3 个方向真实 search/open，5 份材料写入 Notion 后编稿，约 294 秒 ready；Todofy current，5 条事件 |
| Notion 回读 | PASS | 创建后的 5 页逐一确认 packet ID、hash、正文、来源和非 fixture 标记；初次只读核对连接超时，第二次只读核对通过，未重建页面 |
| 真实投递 | NOT TESTED | 邮件凭据未加载，发送接口硬禁用，send reservation=0，真实流程无 EML；未宣称 Gmail/Outlook 实际收件验收 |

最终镜像：`personal-newsletter:collection-test`，固定 ID `sha256:8db64fc8ef2b62ccf66ef6fbb75ef3dfc2af0d0bd382b70f3b338aef939753ce`。仅本机构建，没有推送 registry。

## 真实运行暴露的问题

第一次采集的模型实际打开 arXiv 摘要页，却返回 PDF 来源地址。业务校验拒绝，没有写 Notion。共享 SDK 执行层现提供一次同上下文来源纠正，仍在原超时预算内；必须真实打开新地址或删去未支持的内容，再次不合格则失败。没有自动把摘要地址当作全文，也不自动重试供应商写入。第二次完整采集通过。

技术 ready 不等于出版质量通过：独立阅读 [SLR 官方元数据](https://aclanthology.org/2026.acl-long.16/) 和 [论文全文 Table 2–3、Appendix C](https://aclanthology.org/2026.acl-long.16.pdf) 发现，采集 note 将 7 月论文描述为六周内；精确发表日无法由会议首日确定。论文正文的增幅百分比也与表格原值不一致，原自动稿照搬了正文。原材料另有把改写句放进 excerpt 的问题。

通用编辑规则现要求：以刊期自行核算时间窗口、窗口外标回看、未知精确日期不编造；百分比按同口径原值复算，原文内部矛盾要披露；注明价格基期和缓存假设。它们是提高质量的约束，不是事实正确性的形式证明。

5 份原始材料和旧冻结刊期保留不改；真实原文复核记录通过材料接口追加到同一测试 inbox，供总编生成单独修订刊期。这是有外部复核输入的修订测试，不混称为一次全自动采集就自主发现了所有错误。

## 修订验收

PASS（本轮修订目标）：通过真实 HTTP 材料接口加入 1 份原文核对材料，确认 Notion 后用已有材料编稿接口生成新刊期；Codex 真实搜索并打开 6 个来源，另补充 2 份经济/公共健康扫描材料。新增 3 页均确认 Notion 写入和回读，约 151 秒完成。总计本轮完整采集与修订留下 8 份材料，不清空测试 inbox。新旧刊期分开保存，原冻结 hash 未变，邮件调用和发送记录仍为零。

最终修订版同时包含 AI/ML 回看与近期生态研究，研究介绍卡为 3 段自足概述。独立复核确认了日期、原值/倍数、2025 年价格基期和忽略缓存的说明。仍有可打磨的措辞，例如“hard 层未解决”应结合紧邻的 45% 正确率理解，不能读成完全不会做；本次没有修改冻结稿来伪装模型原始输出。

浏览器验证：最终 HTML 在默认桌面宽度 1679px 与手机 390×844px 下无横向溢出；新介绍卡标签存在，旧点击诱导栏目名已消失，私人事件位于所有公共内容与来源之后。已恢复默认 viewport。不是实际邮件客户端测试，也没有本期真实图表产物。

本机最终预览：`http://127.0.0.1:51404/preview.html`（仅 loopback，服务只暴露这一个冻结 HTML，不提供目录或业务接口）。它含私人事件，不应对外部署。服务进程关闭后，该地址不再可用；冻结文件保存在私有临时测试目录。

## 仍需明确的运行边界

- live 启动检查账号可刷新、模型目录和配套 runtime，但不执行模型，不能保证后续额度/工具永不失效。
- Notion 只读预检不能证明 Insert content 权限；真实写入已另验。
- Todofy public health 不能证明 Basic Auth 或 Gemini 可用；本次真实摘要读取另验。新上游 prompt 尚未部署，真实结果只验证已部署 Todofy + 新本地筛选。
- 私人事件不进入公开研究、模型提示或 Notion；本地筛选仍依赖上游摘要，不是银行或 Todoist 实时事实查询。正常账单/确认自动处理的通知降权，异常付款、安全及实际行动优先，不要求凑满。
- 图表仍须有可靠、可比数据。首次自动稿选择不画图，已如实说明；不能把 PNG/离线渲染测试当成本期真实图表验收。
- 服务无 cron；本地 GitHub daily 改为外部/手动 dispatch。未推送前，GitHub 旧 schedule 不会自动消失。
- 仅验本机 arm64 镜像；amd64 CI 和真实部署/长期登录刷新仍待实际环境验收。

## 清理与可恢复性

旧 `.demo-*`、Node/Go 构建残留、废弃 Python 环境、历史缓存及过时多服务设计稿约 560 MB 已移到 `/private/tmp/newsletter-cleanup.dYAY3f`，不是永久删除。当前 `.env`、`.venv`、专用登录和真实测试数据保留。新开发产物归到 `.artifacts/`；系统临时目录可能被系统清理，需长期保留的历史文件应由用户另行归档。
