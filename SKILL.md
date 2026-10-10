---
name: virtual-perturbation-toolkit
description: 使用已处理单细胞 subset、既有注释和目标基因调用本地虚拟 KO/KD，审查输入与预测尺度，输出可追溯科研图件和中文解释。当前适配 DoseDirKO 外部核心；不负责完整单细胞 QC、自动亚群命名或真实实验因果验证。
---

# 虚拟干扰工具 / Virtual Perturbation Toolkit

仓库是唯一维护源；安装的 Skill 仅含此说明、薄 launcher 和本机路径映射，不复制数值核心。先执行 `python "<skill>/scripts/run_toolkit.py" --locate` 找到仓库，阅读该目录的 `README.md`、`docs/输入规范.md`。遇到状态定义或证据问题再读 `docs/历史细胞定义与输入审计.md`、`docs/方法与证据层级.md`。安装与更新见仓库 `docs/Skill安装与同步.md`。

## 调用 / Run

获取用户已有数据或 subset、原课题目标细胞/状态、目标基因、KO/KD、引擎和输出目录；沿用既有注释。以仓库 `examples/new_project.template.json` 填写配置。来源、counts 层、样本/供者身份或状态依据不明时记录问题，不能用聚类、列顺序或新亚群名称补造信息。H5AD 必须有明确 raw counts layer；10x 输入需要可核对的 metadata。Seurat RDS 导出适配器尚未实测，不列正式支持。

```powershell
python "<skill>/scripts/run_toolkit.py" --doctor --config "<job.json>"
python "<skill>/scripts/run_toolkit.py" --config "<job.json>" --output "<new_output>"
```

launcher 调用仓库 `Run.ps1`；launcher 仅需 Python 标准库，数值分析和 R 环境由配置指定。DoseDirKO 官方组件在仓库外，通过冻结 SHA 校验后调用；未知再分发许可的官方核心不随仓库上传。没有组件或兼容依赖则报告 BLOCKED，不替换为虚构预测。其他登记引擎目前 `NOT_INTEGRATED`。不调用外部 LLM/API，不训练大型模型。

## 科学边界 / Evidence boundaries

- 保留数据来源与 SHA、cells/genes 顺序、cell/sample/donor ID、物种、基因标识、QC、状态定义、算法版本与参数。此模块复用上游 QC，不重新执行完整单细胞分析。
- `INPUT_OK`、`RUN_OK`、`PREDICTION_STABLE`、`BIO_VALIDATED` 独立记录状态与证据。无适用真实 KO/KD 时 `BIO_VALIDATED=NOT_EVALUATED`，意为 UNVALIDATED；前一层通过不会传递到下一层。算法重复不是生物学重复。
- `effect` 是无方向网络嵌入距离；`delta` 是候选 signed propagation。两者均非实验 log2FC。算法分位数不是供者 CI，`p_up/p_down` 不是 P 值或准确率，不与其他引擎分数混用。
- 输入通过不证明细分状态成立：`celltype_fine` 可能仅复制 broad 注释。状态依据不足时限制或阻断“状态特异性”声明，不自动发明亚群。
- 每图标记 Observed、Model-predicted 或有适用真实证据的 Experimentally validated，保存 PNG/PDF/SVG、绘图代码与中文图注。保留方向冲突、基线相似、失败与缺失；不得挑选种子、靶点或面板制造一致性。
- 历史 JUND 仅为 PARTIAL 演示：120 个操作性程序富集细胞、3 名供者、460 基因； pooled 与供者方向冲突，effect 稳定性有限，delta 与 direct-only 排名近同，没有匹配真实 KO。不能称为抗炎验证、准确靶点预测或“炎症性成纤维细胞特异性”机制。

本机历史冻结配置为 `examples/jund_history.local.json`，不上传私有绝对路径或供者级材料。此前 8 次调用、12 次算法运行的 44 项数值 SHA 回放一致，只证明软件回放。新课题需自己的输入审查、稳定性和真实验证。

交付中文说明：本次输入、实际方法调用、原始预测及数值含义、四层状态、资源/复现检查、失败与限制。必要时生成《本次分析到底做了什么.md》。保持原课题只读；工具版本 `v0.1.0-exploratory` 不代表科学验证通过。
