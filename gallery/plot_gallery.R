# Original R plotting code. Only reads released aggregate history tables.
# Usage: Rscript gallery/plot_gallery.R [R_library_1] [R_library_2]
# No numerical model runs, no synthetic observations, no donor-level output.
args <- commandArgs(trailingOnly = TRUE)
if (length(args)) .libPaths(c(args, .libPaths()))
script <- normalizePath(sub("^--file=", "", grep("^--file=", commandArgs(), value = TRUE)[1]), winslash = "/")
root <- dirname(script)
needed <- c("ggplot2", "patchwork", "ragg", "svglite", "jsonlite")
missing <- needed[!vapply(needed, requireNamespace, logical(1), quietly = TRUE)]
if (length(missing)) stop("Missing R packages; no substitute renderer: ", paste(missing, collapse = ", "))
library(ggplot2)
library(patchwork)
font <- "Microsoft YaHei" # Chinese sans-serif; editable vector text.
width_mm <- 210
dpi <- 300
meta <- jsonlite::fromJSON(file.path(root, "data/historical_summary.json"), simplifyVector = FALSE)
table_in <- function(name) read.csv(file.path(root, "data", name), stringsAsFactors = FALSE, check.names = FALSE, fileEncoding = "UTF-8")
scores <- table_in("pooled_fixed_program_scores.csv")
edges <- table_in("pooled_top12_associations.csv")
seed <- table_in("seed_stability.csv")
baseline <- table_in("baseline_comparison.csv")
signs <- table_in("donor_sign_aggregate.csv")
targets <- unlist(meta$targets)
palette <- c(JUND = "#31688E", STAT4 = "#9B6547")
accent <- "#A95844"
theme_set(theme_classic(base_family = font, base_size = 9) +
    theme(plot.title = element_text(size = 10, face = "bold"),
          plot.subtitle = element_text(size = 8, lineheight = 1.2),
          plot.caption = element_text(size = 7, hjust = 0, lineheight = 1.2),
          axis.text = element_text(size = 8), axis.title = element_text(size = 9),
          legend.text = element_text(size = 8), legend.title = element_text(size = 8),
          strip.text = element_text(size = 9, face = "bold"),
          plot.margin = margin(6, 8, 6, 8)))
dir.create(file.path(root, "figures"), showWarnings = FALSE)
exports <- list()
save_figure <- function(plot, name, height_mm) {
    path <- file.path(root, "figures", name)
    ragg::agg_png(paste0(path, ".png"), width = width_mm, height = height_mm, units = "mm", res = dpi, background = "white")
    print(plot); dev.off()
    grDevices::cairo_pdf(paste0(path, ".pdf"), width = width_mm / 25.4, height = height_mm / 25.4, family = font)
    print(plot); dev.off()
    svglite::svglite(paste0(path, ".svg"), width = width_mm / 25.4, height = height_mm / 25.4, bg = "white")
    print(plot); dev.off()
    exports[[name]] <<- list(height_mm = height_mm, files = paste0(name, c(".png", ".pdf", ".svg")))
}
footer <- "来源：Lin, Weimin · Zenodo 19697597 · CC-BY-4.0；已生成去标识聚合摘要。\n元数据 publication_date 异常未解决；无匹配真实 KO/KD 实验，不作治疗靶点结论。"
text_panel <- function(title, label, fill = "#EDF1F3") {
    ggplot() + annotate("rect", xmin = 0, xmax = 1, ymin = 0, ymax = 1, fill = fill, color = NA) +
        annotate("text", x = .06, y = .91, label = title, family = font, fontface = "bold", size = 10 / .pt, hjust = 0, vjust = 1) +
        annotate("text", x = .06, y = .68, label = label, family = font, size = 9 / .pt, hjust = 0, vjust = 1, lineheight = 1.5) +
        coord_cartesian(xlim = c(0, 1), ylim = c(0, 1), expand = FALSE, clip = "off") + theme_void()
}

# A. Observed input audit: only overall dimensions and definition, no identities.
dimensions <- data.frame(x = 1:3, n = c(meta$n_cells, meta$n_independent_donors, meta$n_genes),
    label = c("输入细胞 / cells", "独立供者 / donors", "固定面板 / genes"))
pa <- ggplot(dimensions, aes(x, 1)) + geom_tile(fill = "#EDF1F3", width = .94, height = 1) +
    geom_text(aes(label = n), size = 23 / .pt, family = font, color = palette[1], nudge_y = .12) +
    geom_text(aes(label = label), size = 9 / .pt, family = font, nudge_y = -.25) +
    coord_cartesian(ylim = c(.45, 1.55), clip = "off") + theme_void()
definition <- text_panel("Observed / 细胞定义审查", "多基因炎症程序富集的操作性集合。\n基础 QC 与 counts 核验支持探索性输入。\n正式成纤维细胞细分状态仍 provisional。\n本图不展示单细胞坐标或供者身份。")
scope <- text_panel("历史锁定 / 无重新选取", "JUND、STAT4；网络 KD alpha = 0.5。\n只整理已完成的历史结果。\n未重新进行 QC、筛选、建模或调参。\n460 genes 分支跳过 CP；不能称 CP 成功。")
fig_a <- (pa / (definition | scope)) + plot_layout(heights = c(1, 2)) +
    plot_annotation(title = "A  Target Cell / Input · 输入与细胞定义", caption = footer,
        theme = theme(plot.title = element_text(size = 12, face = "bold", family = font), plot.caption = element_text(size = 7, family = font)))
save_figure(fig_a, "A_Target_Cell_Input", 105)

# B. Weight range is variability of 3 algorithm runs, not a donor confidence interval.
edges$key <- paste(edges$target, edges$gene, sep = "::")
edges$key <- factor(edges$key, levels = unique(edges$key[order(edges$target, abs(edges$mean_weight))]))
network <- ggplot(edges, aes(mean_weight, key, color = target)) +
    geom_vline(xintercept = 0, linewidth = .35, color = "#AAAAAA") +
    geom_linerange(aes(xmin = minimum_weight, xmax = maximum_weight), linewidth = .6) +
    geom_point(size = 2) + facet_wrap(~ target, scales = "free_y", ncol = 2) +
    scale_y_discrete(labels = function(x) sub(".*::", "", x)) +
    scale_color_manual(values = palette, guide = "none") +
    labs(title = "Model-predicted / 目标关联网络摘要", subtitle = "每靶点按平均绝对权重固定取前 12 条；点为 3 次均值，线为最小–最大范围", x = "PCR association weight（模型尺度）", y = NULL)
fig_b <- network + plot_annotation(title = "B  Regulatory Target · 模型关联边", caption = paste("无因果箭头；正负权重不是已证实激活/抑制。完整网络与 checkpoint 仅本地保留。\n", footer, sep = ""),
    theme = theme(plot.title = element_text(size = 12, face = "bold", family = font), plot.caption = element_text(size = 7, family = font)))
save_figure(fig_b, "B_Regulatory_Target", 140)

# C. Complete fixed program genes; no filtering by favorable donor agreement.
inflammation <- scores[scores$program == "Inflammatory", , drop = FALSE]
inflammation$gene <- factor(inflammation$gene, levels = rev(unlist(meta$programs$Inflammatory)))
pc_effect <- ggplot(inflammation, aes(effect_mean, gene, color = target)) +
    geom_linerange(aes(xmin = effect_ci_low, xmax = effect_ci_high), linewidth = .6) +
    geom_point(size = 2) + facet_wrap(~ target, ncol = 1) + scale_color_manual(values = palette, guide = "none") +
    labs(title = "固定炎症基因 / effect", subtitle = "非负网络嵌入距离；区间是算法分位范围", x = "effect（非 log2FC）", y = NULL)
program_order <- names(meta$programs)
gene_order <- unique(unlist(meta$programs))
scores$gene <- factor(scores$gene, levels = rev(gene_order))
scores$target <- factor(scores$target, levels = targets)
scores$display_label <- ifelse(is.na(scores$delta_mean), "缺失",
    paste0(ifelse(scores$direction == "ambiguous", "? ", ""), formatC(scores$delta_mean, format = "g", digits = 2)))
pc_delta <- ggplot(scores, aes(target, gene, fill = delta_mean)) + geom_tile(color = "white", linewidth = .4) +
    geom_text(aes(label = display_label), size = 7 / .pt, family = font) +
    scale_fill_gradient2(low = "#3A6B91", mid = "white", high = "#A95844", midpoint = 0, na.value = "#DDDDDD", name = "delta") +
    labs(title = "完整固定程序 / delta", subtitle = "signed propagation；? = ambiguous\n方向未确定，不作可靠定向解释", x = NULL, y = NULL) +
    theme(axis.line = element_blank(), axis.ticks = element_blank(), legend.position = "bottom")
fig_c <- (pc_effect | pc_delta) + plot_layout(widths = c(1.15, 1)) +
    plot_annotation(title = "C  Virtual Perturbation · 历史实际预测", caption = paste("Model-predicted。alpha=0.5 为网络行缩放，非已校准的 50% RNA/protein KD。\neffect 与 delta 数值尺度不同；不能解释为真实表达量变化或生物学置信区间。\n", footer, sep = ""),
        theme = theme(plot.title = element_text(size = 12, face = "bold", family = font), plot.caption = element_text(size = 7, family = font)))
save_figure(fig_c, "C_Virtual_Perturbation", 195)

# D. All seed comparisons, all fixed inflammatory signs, explicit failure states.
seed$key <- factor(paste(seed$target, seed$metric), levels = rev(c("JUND effect", "JUND delta", "STAT4 effect", "STAT4 delta")))
seed$pair <- factor(seed$pair)
ps <- ggplot(seed, aes(spearman, key, color = target, shape = pair)) +
    geom_vline(xintercept = .8, linewidth = .4, linetype = 2, color = "#888888") + geom_point(size = 2.3) +
    scale_color_manual(values = palette, guide = "none") + scale_x_continuous(limits = c(0, 1)) +
    labs(title = "全部种子比较", subtitle = "虚线为历史审查阈值 0.8；非前瞻独立验证", x = "Spearman correlation", y = NULL, shape = "算法运行对") +
    theme(legend.position = "bottom")
si <- signs[signs$program == "Inflammatory", , drop = FALSE]
si$label <- paste(si$target, si$gene)
si$label <- factor(si$label, levels = rev(si$label))
pd <- ggplot(si, aes(n_pooled_donor_sign_conflicts, label, fill = target)) + geom_col(width = .65) +
    geom_text(aes(label = paste0(n_pooled_donor_sign_conflicts, "/", n_donor_models)), hjust = -.15, size = 8 / .pt, family = font) +
    scale_fill_manual(values = palette, guide = "none") + scale_x_continuous(limits = c(0, 3.7), breaks = 0:3) +
    labs(title = "供者方向冲突 / 聚合计数", subtitle = "固定炎症程序完整保留；0/3 也不等于真实验证", x = "与 pooled delta 异号的供者模型数", y = NULL)
pb <- ggplot(baseline, aes(delta_vs_direct_spearman, target, color = target, shape = factor(run_index))) +
    geom_point(size = 2.3) + scale_color_manual(values = palette, guide = "none") +
    labs(title = "direct-only 基线关系", subtitle = "高度相似并不证明预测准确或优于基线", x = "Spearman(delta, direct-only)", y = NULL, shape = "算法运行") +
    scale_x_continuous(limits = c(.9985, 1), breaks = c(.9985, .999, .9995, 1)) + theme(legend.position = "bottom")
layers <- c("INPUT_OK", "RUN_OK", "PREDICTION_STABLE", "BIO_VALIDATED")
states <- data.frame(layer = factor(layers, levels = rev(layers)), state = vapply(layers, function(x) meta$status[[x]]$state, character(1)))
states$label <- paste0(as.character(states$layer), "\n", states$state)
pe <- ggplot(states, aes(1, layer, fill = state)) + geom_tile(width = .96, height = .85) +
    geom_text(aes(label = label), size = 8 / .pt, family = font) +
    scale_fill_manual(values = c(PASS = "#E3EDF1", FAIL = "#EACFC6", NOT_EVALUATED = "#E7E7E7"), guide = "none") +
    labs(title = "分层证据状态", subtitle = "PARTIAL：软件成功，预测稳定性失败") + theme_void(base_family = font, base_size = 9) +
    theme(plot.title = element_text(size = 10, face = "bold"), plot.subtitle = element_text(size = 8))
fig_d <- ((ps | pd) / (pb | pe)) + plot_layout(heights = c(1.3, 1)) +
    plot_annotation(title = "D  Robustness / Validation · 保留失败结果", caption = paste("Model-predicted / 科学审查；无 Experimentally validated 面板。\n供者间未生成生物学 CI；种子比较是算法重复，不能增加生物学样本量。\n", footer, sep = ""),
        theme = theme(plot.title = element_text(size = 12, face = "bold", family = font), plot.caption = element_text(size = 7, family = font)))
save_figure(fig_d, "D_Robustness_Validation", 185)

manifest <- list(backend = "R", R_version = R.version.string,
    packages = setNames(lapply(needed, function(x) as.character(utils::packageVersion(x))), needed),
    width_mm = width_mm, dpi = dpi, font = font, minimum_font_pt = 7,
    data_md5 = as.list(setNames(tools::md5sum(list.files(file.path(root, "data"), full.names = TRUE)), list.files(file.path(root, "data")))),
    plot_source_md5 = unname(tools::md5sum(script)), exports = exports,
    simulated_data = FALSE, model_recomputed = FALSE, donor_identifiers_released = FALSE,
    notes = "Three algorithm runs; no biological confidence intervals. Fixed programs unchanged; complete seed comparisons preserved. ? in Figure C retains official direction=ambiguous rather than treating a nonzero delta as a reliable direction.")
jsonlite::write_json(manifest, file.path(root, "figure_manifest.json"), pretty = TRUE, auto_unbox = TRUE)
cat("Rendered 4 aggregate historical figures in PNG/PDF/SVG (12 files).\n")
