# 示例 / Examples

- `new_project.template.json`：新任务配置。填入已有counts、来源、注释、目标、外部引擎、运行时；默认QC未确认，不能直接当成功示例。
- `jund_history.json`：历史参数模板，不含本机路径或数据。须另有合法的本地历史输入和官方组件才可回放；不能用重新筛选的细胞代替原冻结输入。
- `jund_history.local.json`：仅原工作站存在、被Git忽略的原始运行配置。本次发布不再运行JUND科研分析。
- [图库](../gallery/README.md)：可分享的真实历史摘要，可以从图库小表格重绘，不需官方核心或原始矩阵。

从仓库根目录运行：

```powershell
python scripts/run_toolkit.py --config examples/my_job.local.json --output outputs/my_job
```

配置统一接受输入、目标细胞/既有状态、目标基因、KO/KD、引擎、输出路径和 `engine.params.random_state`。路径相对于配置文件。请保留默认资源门槛或根据有证据的预检收紧。
