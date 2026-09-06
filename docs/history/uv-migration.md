# uv 与内部类型迁移验收 · 2026-09-05

历史快照；当前开发入口见 [开发说明](../development.md)。

## 改动范围

- 保持一个 Python 服务。固定 Python 3.12.14、uv 0.12.10；`uv.lock` 替换原 `requirements.lock`，开发、CI 和 Docker 共用它。
- 迁移时核对原 31 个依赖版本无漂移；随后删除已被 uv 替代的 `build` 及其专用依赖 `pyproject-hooks`。业务依赖及 Codex SDK/runtime 0.147.0 没有升级。
- 开发工具移至 dev dependency group，新增 Mypy 2.3.1 与 protobuf 类型 stub；Codex 保持 optional extra。构建后端固定 setuptools 84.0.0。
- 补充刊期/投递/投影状态 Literal、内部记录和结果 TypedDict、适配器 Protocol、任务更新的带类型参数。手写代码全部纳入 Mypy，没有忽略整个业务模块。
- 外部 ProtoJSON 仍由公共 protobuf 定义并做运行时校验；动态 payload 是明确保留的边界，不宣称全部 JSON 已获静态类型保证。
- 同一公共 proto 生成 `.py` 和 `.pyi`，provenance 新增 stub hash；没有更改公共消息定义、数据库 schema、SDK 调用参数、模型选择或邮件版式。
- CI 运行统一 Make 质量检查与源码外 wheel 验证；Docker 多阶段安装锁定的非 editable 生产环境，固定 Python/uv 多架构镜像 digest，运行阶段没有 uv 或开发工具。

## 本机实际执行结果

| 验证项 | 结果 |
| --- | --- |
| `make setup` / 锁一致性 / 已安装依赖兼容性 | PASS |
| `make check`：pytest | PASS：305 passed，0 failed，0 skipped |
| Mypy：全部 12 个手写源 | PASS：0 errors |
| Ruff lint / format | PASS：29 files |
| `make proto-check` | PASS：公共源、生成 Python、类型 stub、provenance 一致 |
| 静态正负测试 | PASS：合法用法通过；拼错状态、非法投递状态、缺失渲染 hash 等被拒绝 |
| sdist + wheel 构建 | PASS；源码包包含当前锁、Python pin 和 manifest，不附带半套测试目录 |
| wheel 与当前源码/资源逐字核对 | PASS；过期 wheel 会明确失败 |
| 源码外新环境安装 wheel | PASS：同锁带 hash 依赖、资源与 runtime 检查、fake demo、一次本地 EML |
| 本机真实 loopback HTTP | PASS：投稿→后台编稿→冻结预览→模拟投递；重复请求仍只有一次投递 |
| Linux/ARM64 与 Linux/AMD64 镜像构建 | PASS：两种架构分别构建，未推送多架构远端镜像 |
| 两种架构镜像内 HTTP smoke | PASS：断网、非 root、只读根目录、仅临时 `/tmp` 可写、无用户目录挂载 |
| 两种架构镜像资源/runtime | PASS：源码指纹与工作区一致、有中文字体、无开发工具/uv、配套 CLI `--version` 成功 |
| `git diff --check` | PASS |

保留两项既有 Starlette/httpx/AnyIO 弃用警告；本次没有顺带升级这些业务依赖。

本机 uv 位于 `/Users/ziyixi/.local/bin/uv`。如终端 PATH 未包含它，可运行 `make UV=/Users/ziyixi/.local/bin/uv check`；没有为此修改全局 shell 配置。

## 未执行与限制

- 真实模型请求、Notion 写入、Todofy 查询、真实邮件均为 0；没有读取/改动 `.env` 或登录凭据。
- 没有 commit/push、远端 GitHub Actions、部署、定时 routine 或旧 daily 调度变更。
- 镜像中的字体通过系统包安装；依赖锁与基础镜像 digest 不是所有系统包永久可复现的保证。
- 容器内 CLI 版本检查不等于 ChatGPT 登录刷新、模型额度或搜索/内容质量验收。实际账号联调、持久化/TLS 与一次真实收件仍按 [真实联调清单](../live-acceptance.md) 分阶段执行。
- 所有测试容器使用 `--rm`，退出即移除。两个本地验收镜像标签保留：`personal-newsletter:uv-preflight-20260905`、`personal-newsletter:uv-preflight-amd64-20260905`；没有覆盖生产镜像标签。
