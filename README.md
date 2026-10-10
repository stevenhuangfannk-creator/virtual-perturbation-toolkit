# Virtual Perturbation Toolkit / 虚拟干扰工具

输入已处理单细胞counts、既有细胞注释和指定基因，调用数值引擎，生成可追溯的虚拟KO/KD结果、科学审查和中文科研图件。当前提供 **DoseDirKO外部核心适配器**，不包含未知许可的官方实现，不重做完整单细胞分析，也不调用外部LLM。

English summary: An auditable local toolkit for exploratory perturbation workflows. DoseDirKO requires an externally supplied, hash-locked official implementation. Software reproducibility does not establish biological predictive validity.

**`v0.1.0-exploratory` 是工具版本。历史JUND科学判断仍为PARTIAL：供者方向冲突，没有真实KO验证，也没有证明治疗靶点预测能力。**

## 快速开始 / Quick start

使用已有兼容Python/R环境，不自动安装大批依赖。维护代码在 `src/vpt/`，根 `vpt/` 仅保留旧导入兼容。

```powershell
git clone https://github.com/stevenhuangfannk-creator/virtual-perturbation-toolkit.git
cd virtual-perturbation-toolkit
python scripts/skill_sync.py version
python scripts/skill_sync.py install
python scripts/skill_sync.py status
```

旧安装或手改文件默认不会覆盖。检查后用 `install --backup <备份目录>` 或 `update --backup <备份目录>` 先完整备份。Skill仅保存说明、launcher和仓库路径，核心始终从checkout调用。详见 [安装与同步](docs/Skill安装与同步.md)。

```powershell
Copy-Item examples/new_project.template.json examples/my_job.local.json
python scripts/skill_sync.py doctor --config examples/my_job.local.json
python scripts/run_toolkit.py --config examples/my_job.local.json --output outputs/my_job
```

填写真实输入、来源、状态依据、目标、外部引擎路径、运行时与种子。模板 `qc_completed=false`，不能为了运行虚报完成。路径相对于配置文件，输出目录必须为空。资源监控只管理本工具启动的子进程，不关闭用户应用。

| 统一输入 | 配置字段 |
|---|---|
| 数据和raw counts | `input.format/path/counts_layer/counts_origin` |
| 目标细胞/既有状态 | 已有subset或 `input.selection`，`input.columns.state`、`input.annotation` |
| 基因、干扰、引擎 | `targets`、`perturbation.type/alpha`、`engine.id` |
| 输出和种子 | `output_dir`、`engine.params.random_state` |
| 来源、供者、文库 | `input.accession/species/columns`、可选 `input.sha256` |

## 可用范围 / Supported scope

| 项目 | 实际状态 |
|---|---|
| 10x MTX | 已测试；历史真实输入及ID映射通过 |
| H5AD明确counts layer | 软件夹具测试通过；不猜测X/raw为counts |
| Seurat RDS | 导出适配器已有，实际RDS尚未验证，**不属正式支持** |
| DoseDirKO | 自有适配器可执行，需合法取得的外部官方源码和依赖 |
| CellOracle、scTenifoldKnk | `NOT_INTEGRATED`，仅候选/历史记录，不可调用 |

观察性counts只支持受限网络假设生成。状态证据不足时只允许探索性subset声明，不自动发明亚群。详见 [输入规范](docs/输入规范.md)、[引擎登记](config/engines.json)。

## 输出含义 / Interpretation

每次保存配置、来源哈希、ID顺序、源码哈希、版本、参数、原始模型产物、覆盖、基线结构比较、种子/供者稳定性、状态和失败。`scripts/plot_results.R` 从实际结果表输出PNG/PDF/SVG与中文图注。

| 数值 | 含义 | 不能当作 |
|---|---|---|
| effect | 无向网络嵌入距离 | 表达方向、log2FC、DE显著性 |
| delta | signed propagation候选分数 | 实测表达响应或跨算法统一分数 |
| alpha | 目标网络行缩放参数 | RNA/蛋白KD率或药物剂量 |
| 算法区间/符号频率 | 重复分位数、正负频率 | 生物学CI、P值、正确概率 |

## 科学验证 / Scientific states

| 层 | 历史状态 | 证据与边界 |
|---|---|---|
| INPUT_OK | PASS，限探索性subset | 120细胞、3供者、460基因，细分状态未确认 |
| RUN_OK | PASS | 原19软件测试；已有两份回放各44数值产物一致 |
| PREDICTION_STABLE | FAIL | effect排名不稳，pooled与供者方向冲突 |
| BIO_VALIDATED | NOT_EVALUATED / UNVALIDATED | 没有匹配真实KO/KD，未证明优于基线 |

`NOT_EVALUATED` 保留旧机器枚举，含义为尚未评价；前层通过不向后传递。JUND pooled CXCL8/IL6为负候选delta，但与供者多数/全部方向冲突。delta与direct-only近同只能说明结构相似。详见 [方法证据](docs/方法与证据层级.md)、[历史身份审计](docs/历史细胞定义与输入审计.md)。

## 方法图鉴 / Figure gallery

以下真实历史的有限脱敏摘要保留不稳定性，不包含逐细胞/逐供者原表。每图的数据、参数、脚本、中文图注和边界见 [图库指南](gallery/README.md)。

![A：输入与状态](gallery/figures/A_Target_Cell_Input.png)

A：Observed。操作性集合与规模；不是正式亚群鉴定。

![B：调控靶点](gallery/figures/B_Regulatory_Target.png)

B：Model-predicted。关联网络摘要；边无已证实因果含义。

![C：虚拟干扰](gallery/figures/C_Virtual_Perturbation.png)

C：Model-predicted。effect与delta分开解释，不是真实表达响应。

![D：稳定性与验证](gallery/figures/D_Robustness_Validation.png)

D：模型与软件审查。保留种子不稳定、聚合方向冲突和未生物验证状态。

## 复现检查 / Verification

```powershell
# 在已有numpy/pandas/scipy/anndata环境中
python -m unittest discover -s tests -v
python scripts/check_delivery.py
# 需要已有本地历史产物，只重算哈希，不运行JUND算法
python scripts/verify_history.py --output outputs/jund_history --history ../PI_Inflammatory_Fibroblast_Virtual_Perturbation
```

历史输入不在仓库中。`examples/jund_history.json` 是冻结参数与迁移路径模板；原工作站 `.local.json` 保留真实路径。克隆不自动取得数据/官方源码/许可。详见 [首版验收](docs/首版发布验收.md)。

## 许可与维护 / Licensing and maintenance

官方审计commit `5254bcfeece32442eee31590fe46bcc4af849181` 未发现源码再分发许可。仓库仅发布自有接口，通过 `engine.source_dir` 外部引用并按SHA锁定；Private不替代授权。论文 [10.1186/s12864-026-13270-0](https://doi.org/10.1186/s12864-026-13270-0) 的CC-BY不等于代码许可。

数据摘要注明 [Lin, Weimin，Zenodo:19697597](https://zenodo.org/records/19697597)，CC-BY-4.0；API未来发布日期异常如实记录。首版不新增统一开源许可，外部资源各依原许可。详见 [第三方审查](docs/第三方许可与上传来源.md)、[发布范围](docs/发布范围与数据管理.md)。

GitHub主线是维护来源；先检查本地修改再 `git pull --ff-only`，然后更新Skill。新增引擎按 [接入规范](docs/新引擎接入规范.md) 独立审查，不继承本方法的验证状态。
