# Skill 安装与同步 / Skill synchronization

GitHub 仓库及其本地 checkout 是唯一维护源。Codex 安装目录只保存根 `SKILL.md`、`scripts/run_toolkit.py`、UI 元数据和两个自动生成的本机映射/同步文件；不复制 `src/`、数据、外部 DoseDirKO 或图件。安装目录中的 launcher 始终调用 checkout 的 `Run.ps1`。

## 安装 / Install

在仓库目录执行（launcher 和同步工具仅需 Python 标准库）：

```powershell
python scripts/skill_sync.py install
python scripts/skill_sync.py status
python scripts/skill_sync.py version
```

默认安装位置为 `$CODEX_HOME/skills/virtual-perturbation-toolkit`；未设置 CODEX_HOME 时为用户目录的 `.codex/skills/virtual-perturbation-toolkit`。也可指定 `--skill-dir "<directory>"` 测试隔离安装。安装不会修改 Python/R 环境，也不会下载官方核心。

旧版未跟踪安装或手动修改会触发拒绝覆盖；审阅后明确指定备份位置：

```powershell
python scripts/skill_sync.py install --backup "<local_backup_directory>"
```

脚本先完整复制旧 Skill 到带时间戳的备份子目录，成功后再同步管理的文件。未管理的其他文件保留原位；备份目录不得放在待更新 Skill 内。没有 `--backup` 时不能覆盖修改；`--backup` 是实际备份动作，不是跳过检查的 force 开关。

## 更新 / Update

先检查当前 checkout 和已安装 Skill：

```powershell
python scripts/skill_sync.py check-update
python scripts/skill_sync.py status
```

`check-update` 只比较本地 checkout 与安装哈希，不查询远程。要取得 GitHub 新版，先在 checkout 通过正常 Git 工作流获取并审查新版；不要覆盖未提交的本地修改。确认版本后执行：

```powershell
python scripts/skill_sync.py update
# 如检测到手动修改：
python scripts/skill_sync.py update --backup "<local_backup_directory>"
```

`status` 区分 NOT_INSTALLED、UNTRACKED_INSTALL、CLEAN、MODIFIED，并报告 `update_available`。即使版本号不变，管理文件哈希变化也会显示可更新。`version` 同时显示仓库版本和安装快照版本。

核心代码始终从当前 checkout 读取，Skill 安装快照只保存说明与 launcher；因此更新仓库核心后，不应把旧安装版本当成冻结完整数值实现。每次实际分析仍需保留工具源码哈希、外部组件哈希和参数。需要严格复现实验时使用对应 Git tag/commit 的独立 checkout，再把 Skill 映射到该 checkout。

## 检查依赖与诊断 / Doctor

```powershell
python scripts/skill_sync.py doctor
python scripts/skill_sync.py doctor --config "<local_job.json>"
```

不提供配置时仅检查安装与仓库入口，不能据此声称模型可运行。提供配置后查询指定数值 Python 和监控 Python 的依赖版本、R 版本及绘图依赖、外部 DoseDirKO 文件集合与 SHA。版本不同于历史测试环境会产生警告，缺依赖、运行时或外部核心则 BLOCKED。查询不导入数值算法、不安装依赖、不训练；资源预检和实际运行验收仍由 `Run.ps1` 执行。

常见处理：

- NOT_INSTALLED：运行 `install`。
- UNTRACKED_INSTALL / MODIFIED：先查看修改，再指定备份目录同步。
- 仓库入口不存在：checkout 已移动；在新 checkout 执行 `update` 重建映射。
- 外部源码 SHA 不一致：核对官方版本，禁止直接去掉 SHA 检查。
- 缺 Python/R 依赖：在课题隔离环境解决，再运行软件测试；不要把安装成功视为生物学验证。

## Codex 最简调用 / Minimal invocation

```text
使用 $virtual-perturbation-toolkit，按 <job.json> 执行 DoseDirKO，输出到 <new_output>；保留方向冲突和四层验证状态，生成中文解释及科研图件。
```

Skill 中的入口可直接使用：

```powershell
python "<installed_skill>/scripts/run_toolkit.py" --version
python "<installed_skill>/scripts/run_toolkit.py" --doctor --config "<job.json>"
python "<installed_skill>/scripts/run_toolkit.py" --config "<job.json>" --output "<new_output>"
```

配置统一承载输入数据、原注释目标细胞、目标基因、KO/KD、引擎、输出和随机种子；以 `examples/new_project.template.json` 及输入规范补全。历史 JUND 冻结配置只在本机 `examples/jund_history.local.json`；远程仓库仅展示经审查的汇总，不包含供者级原始材料。
