# 外部触发采编服务：运行边界

## 权限与持久化

运行时只接受日期和幂等键，不接受远程指令文本、路径、URL模板、模型名或发送标志。operator 在服务器修改 Markdown 目录；每个新run保存排序后的原文与hash。相同请求重复提交复用旧快照。HTTP POST /v1/runs 使用editor角色，独立send角色不会隐式出现在pipeline中。

SQLite是业务状态的权威来源；Notion是单向后台投影。新选题DAG先保存逐题证据与独立审核版本，Notion暂时失败不阻止编排和发送；旧冻结刊期保留原投影确认门槛。写Notion前保存submitting，未知结果不自动重试。未找到任何已核实内容仍blocked，不冒充成功。详见 [选题级DAG](workflow.md)。

run与edition分别有幂等记录，防止在创建edition后、回写run关联前崩溃而重复生成。收集时中断标记failed，不重发模型请求；Notion提交中断变unknown；发送中断同样unknown。需要人工核对供应商状态后决定新的操作，不提供无条件重试按钮。

## 调度与资源

服务没有cron，不根据时间自动创建run，也不依赖Codex app routine。worker的Event只等待外部请求唤醒。默认单进程串行，最多8个pending collection run、8个直接编稿任务。新DAG总研究预算5400秒，节点另有限额；逐题先保存简版再深读，截止/中断时本地拼版可恢复。旧legacy/mock仍使用每方向独立预算。不能把202接受当成完成。

已排队刊期优先；新选题研究优先于Notion后台投影，防止镜像故障耗尽研究期限。低频私人服务不提供多租户公平性/SLA；不要通过增加uvicorn进程绕过目录锁。

## 启动检查

lifespan在启动worker、提供health之前执行preflight；没有环境开关跳过：

| 依赖 | 实际检查 | 不代表什么 |
| --- | --- | --- |
| 本地运行环境 | Python、应用直接依赖pin、SQLite WAL/读写/quick_check | 不是远程数据库或备份验收 |
| 资源 | public proto py/pyi/descriptor hash、policy、模板、真实CJK PNG渲染 | 不证明收件客户端显示 |
| Codex | 固定SDK和二进制RECORD校验、host启动、专用账号refresh、禁用skills、model/list | 未执行生成；不保证后续额度或搜索工具可用 |
| Notion | HTTPS固定origin的数据源只读GET、权限及title schema | 不制造测试页；不证明Insert content权限 |
| Todofy | origin/凭据语法及无副作用public /health | 不证明BasicAuth有效、Gemini可用或推荐质量 |
| Resend | 发送配置合法性 | sending-only key无通用读接口；未发送测试邮件、未证明域名/投递 |

只检查已启用的供应商；核心条件、授权与schema错误拒绝启动。Notion/Todofy的临时网络、限流或服务端故障允许degraded启动并记录稳定安全warning；不把该降级用于Codex运行时或本地证据。网络检查有限时、不跟随重定向、不使用继承代理，错误不泄露供应商响应。正式任务仍须处理过期登录、网络中断和配额错误。不能用付费生成或发邮件来伪装安全的启动检查。

Codex uses isolated ChatGPT auth and the pinned Python SDK/runtime; account/read can refresh managed tokens and model/list lists available models. These checks do not initiate a thread or model turn. [Official app-server documentation](https://learn.chatgpt.com/docs/app-server)

## 镜像与本机文件

Docker构建只输入源码与唯一uv.lock；依赖构建层可缓存，最终层只复制安装环境，不复制个人配置/缓存/构建工具。不在启动时下载或升级Codex。默认非root；Compose有init、只读根fs、no-new-privileges、cap_drop、内存/CPU/pids限制。

live部署需单独配置本地持久data目录与专用可写Codex auth目录；初始化登录由运营者正规登录完成。新主机不直接复制个人~/.codex或共享同一份刷新缓存。自定义指令目录用只读挂载，auth/data用最小权限可写挂载。示例Compose是mock，不能只设一个MODE就声称live部署完成。

开发产物统一到.artifacts/，.venv保留为唯一当前开发环境。过去的.demo目录、旧Node/Go构建残留、废弃Python环境与过时多服务设计已移到仓库外可恢复归档；真实预览和私人数据仍只在私有临时目录，不能提交。

## 外部触发器迁移

源码中的daily workflow改为手动或repository_dispatch，仅运行trigger_run.py，且不持有发送权限；无schedule。GitHub线上旧工作流只有在这次修改经用户同意推送后才变化，本地修改不会自动关闭旧schedule。切换前确认旧sender已停，避免新旧重复；当前任务没有推送或替用户改线上配置。
## Current live workflow

Live deployments now default to the versioned DAG described in [workflow.md](workflow.md).
The per-direction serial flow remains the explicit legacy/mock path. DAG
collection has a 5400-second total budget, a 7200-second external trigger wait,
and topic-level durable approval checkpoints. New publications do not wait for
Notion; old immutable bindings keep their original gate. Consult the DAG guide
for candidate preparation, deadline publication and token usage.
