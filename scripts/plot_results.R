# R-only figures from audited inputs and actual engine results; no synthetic data.
# Usage: Rscript plot_results.R output_dir font width_mm dpi R_library
args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 5) stop("Usage: plot_results.R output_dir font width_mm dpi R_library")
root <- normalizePath(args[1], winslash = "/", mustWork = TRUE)
font <- args[2]; width_mm <- as.numeric(args[3]); dpi <- as.numeric(args[4])
toolkit_root <- dirname(dirname(normalizePath(sub("^--file=", "", grep("^--file=", commandArgs(), value = TRUE)[1]), winslash = "/")))
.libPaths(c(file.path(toolkit_root, "environment/r_library"), args[5], .libPaths()))
needed <- c("ggplot2", "patchwork", "ragg", "jsonlite", "svglite")
missing <- needed[!vapply(needed, requireNamespace, logical(1), quietly = TRUE)]
if (length(missing)) stop("Missing R dependencies; no substitute renderer: ", paste(missing, collapse = ", "))
stopifnot(is.finite(width_mm), width_mm >= 183, is.finite(dpi), dpi >= 300)
library(ggplot2); library(patchwork)
outdir <- file.path(root, "figures")
dir.create(outdir, recursive = TRUE, showWarnings = FALSE)
inputs <- character(); notes <- character(); captions <- list(); files <- character()
table_in <- function(name, fields) {
  p <- file.path(root, "results", name)
  if (!file.exists(p)) stop("Actual result missing: ", p)
  z <- read.csv(p, check.names = FALSE, stringsAsFactors = FALSE, fileEncoding = "UTF-8-BOM")
  if (!all(fields %in% names(z))) stop("Invalid schema in ", name, ": ", paste(setdiff(fields, names(z)), collapse = ", "))
  inputs <<- unique(c(inputs, p)); z
}
json_in <- function(p) {
  p <- file.path(root, p)
  if (!file.exists(p)) stop("Required manifest missing: ", p)
  inputs <<- unique(c(inputs, p)); jsonlite::fromJSON(p, simplifyVector = FALSE)
}
cfg <- json_in("config_resolved.json")
status <- json_in("results/status.json")
summary <- json_in("results/input_summary.json")
cells <- table_in("cell_metadata.csv", c("cell_id", "donor_id", "vpt_state"))
coverage <- table_in("gene_coverage.csv", c("target", "gene", "detection_rate", "mean_raw"))
edges <- table_in("target_edges.csv", c("target", "gene", "weight", "run_index"))
pred <- table_in("predictions.csv", c("target", "scope", "gene", "effect_mean", "effect_ci_low", "effect_ci_high", "delta_mean", "direction"))
seed <- table_in("seed_stability.csv", c("target", "metric", "pair", "spearman", "top_k_jaccard"))
donor <- table_in("donor_predictions.csv", c("target", "donor_id", "gene", "delta", "pooled_delta", "conflict"))
baseline <- table_in("baseline_comparison.csv", c("target", "run_index", "delta_vs_direct_spearman", "effect_vs_expression_spearman", "effect_vs_degree_spearman"))
stopifnot(nrow(cells) > 0, !anyDuplicated(cells$cell_id), all(nzchar(cells$donor_id)))
pooled <- pred[pred$scope == "pooled", , drop = FALSE]
if (!nrow(pooled)) stop("No actual pooled prediction available")
targets <- unique(pooled$target)
donors <- sort(unique(cells$donor_id))
known_donors <- donors[!tolower(donors) %in% c("unknown", "donor_unknown", "missing", "na")]
colors <- setNames(grDevices::hcl.colors(max(3, length(targets)), "Dark 3")[seq_along(targets)], targets)
program_names <- c(Inflammatory = "炎症", Matrix = "基质", Myofibroblast = "肌成纤维", Stress = "应激", Cell_cycle = "细胞周期", Immune_contamination = "免疫谱系审查", Epithelial_contamination = "上皮谱系审查", Endothelial_contamination = "内皮谱系审查")
programs <- cfg$programs
if (is.null(programs)) programs <- list()
program_map <- if (length(programs)) do.call(rbind, lapply(names(programs), function(p) data.frame(program = p, gene = unlist(programs[[p]]), stringsAsFactors = FALSE))) else data.frame(program = character(), gene = character())
label_program <- function(z) ifelse(z %in% names(program_names), program_names[z], z)
num <- function(x) ifelse(is.finite(x), formatC(x, format = "g", digits = 2), "×")
wrap_cn <- function(text, width = 108) {
  chars <- strsplit(text, "", fixed = TRUE)[[1]]; lines <- character(); line <- ""; columns <- 0
  for (ch in chars) {
    n <- nchar(ch, type = "width")
    if (ch == "\n" || columns + n > width) {lines <- c(lines, line); line <- ""; columns <- 0}
    if (ch != "\n") {line <- paste0(line, ch); columns <- columns + n}
  }
  wrapped <- paste(c(lines, line), collapse = "\n")
  gsub("(?<=[A-Za-z_])\\n(?=[A-Za-z_/])", "", wrapped, perl = TRUE)
}
theme_set(theme_classic(base_family = font, base_size = 8) + theme(
  axis.text = element_text(size = 7), axis.title = element_text(size = 8),
  plot.title = element_text(size = 9, face = "bold"), plot.subtitle = element_text(size = 7),
  strip.text = element_text(size = 8, face = "bold"), plot.tag = element_text(size = 10, face = "bold"),
  legend.text = element_text(size = 7), legend.title = element_text(size = 7), legend.position = "bottom",
  plot.caption = element_text(size = 7, hjust = 0, lineheight = 1.2), plot.margin = margin(6, 6, 6, 6),
  axis.line = element_line(linewidth = .3)))
not_evaluated <- function(title, reason) {
  notes <<- c(notes, paste(title, reason, sep = ": "))
  ggplot(data.frame(x = 0, y = 0, label = wrap_cn(reason, 45)), aes(x, y, label = label)) +
    geom_text(size = 8 / .pt, family = font, lineheight = 1.25) +
    labs(title = title, subtitle = "NOT_EVALUATED / 未评价") + theme_void(base_family = font, base_size = 8) +
    theme(plot.title = element_text(size = 9, face = "bold"), plot.subtitle = element_text(size = 7))
}
save_figure <- function(p, stem, height_mm, caption) {
  p <- p + plot_annotation(caption = wrap_cn(caption), tag_levels = "a", theme = theme(plot.caption = element_text(size = 7, family = font, hjust = 0)))
  prefix <- file.path(outdir, stem)
  ragg::agg_png(paste0(prefix, ".png"), width = width_mm, height = height_mm, units = "mm", res = dpi, background = "white")
  print(p); grDevices::dev.off()
  grDevices::cairo_pdf(paste0(prefix, ".pdf"), width = width_mm / 25.4, height = height_mm / 25.4, family = font, onefile = TRUE)
  print(p); grDevices::dev.off()
  svglite::svglite(paste0(prefix, ".svg"), width = width_mm / 25.4, height = height_mm / 25.4, system_fonts = list(sans = font))
  print(p); grDevices::dev.off()
  files <<- c(files, paste0(stem, c(".png", ".pdf", ".svg")))
  captions[[stem]] <<- caption
}

# A: selected inputs and frozen marker coverage; no new cell clustering or naming.
cell_n <- aggregate(list(n = rep(1, nrow(cells))), cells[c("donor_id", "vpt_state")], sum)
pa <- ggplot(cell_n, aes(donor_id, n, fill = vpt_state)) + geom_col(width = .68) +
  geom_text(aes(label = n), vjust = -.3, size = 7 / .pt, family = font) +
  scale_y_continuous(expand = expansion(mult = c(0, .15))) +
  labs(title = "输入细胞与供者信息 | Observed", subtitle = paste0(nrow(cells), "个选中细胞；", length(known_donors), "个已知供者ID；unknown不计独立n"), x = "供者ID（依原课题标注）", y = "细胞数", fill = "原课题状态标签")
cov_genes <- unique(c(targets, unlist(programs$Inflammatory), unlist(programs$Matrix)))
if (!length(cov_genes)) cov_genes <- unique(program_map$gene)
grid_cov <- expand.grid(target = targets, gene = cov_genes, stringsAsFactors = FALSE)
cov <- merge(grid_cov, coverage, by = c("target", "gene"), all.x = TRUE, sort = FALSE)
stopifnot(all(is.na(cov$detection_rate) | (cov$detection_rate >= 0 & cov$detection_rate <= 1)))
cov$gene <- factor(cov$gene, levels = rev(cov_genes))
pc <- ggplot(cov, aes(target, gene, fill = detection_rate)) + geom_tile(color = "white", linewidth = .25) +
  geom_text(aes(label = ifelse(is.na(detection_rate), "×", paste0(round(100 * detection_rate), "%"))), size = 7 / .pt, family = font) +
  scale_fill_gradient(low = "#F2F5F7", high = "#4477AA", limits = c(0, 1), na.value = "#E1E1E1") +
  labs(title = "靶点及固定炎症/基质程序覆盖 | Observed", subtitle = "检测率来自原始counts；×为缺失，不是0表达", x = "引擎任务", y = NULL, fill = "检测比例")
if (all(c("UMAP1", "UMAP2") %in% names(cells)) && all(is.finite(cells$UMAP1)) && all(is.finite(cells$UMAP2))) {
  pu <- ggplot(cells, aes(UMAP1, UMAP2, color = donor_id)) + geom_point(size = .7, alpha = .8) +
    labs(title = "已提供的参考坐标 | Observed", subtitle = "仅显示原坐标切片；未重建UMAP或证明新亚群", color = "供者") + theme(axis.ticks = element_blank(), axis.text = element_blank())
  fig_a <- (pa / pu) | pc
} else {fig_a <- pa | pc; notes <- c(notes, "A: 未提供完整有限的UMAP1/UMAP2，未绘制坐标面板。")}
save_figure(fig_a, "Figure_A_Input_and_State", 178,
  "A图仅审查选中输入与预定义程序覆盖；状态名称由原课题提供，工具不重新聚类或创造亚群。炎症程序富集标签不能直接升级为正式炎症性成纤维细胞亚型。图中所有原始供者与选定基因均保留。")

# B: frozen selection by absolute mean association weight, never causal arrows.
if ("scope" %in% names(edges)) edges <- edges[edges$scope == "pooled", , drop = FALSE]
edges <- edges[edges$gene != edges$target, , drop = FALSE]
stopifnot(all(is.finite(edges$weight)))
em <- aggregate(weight ~ target + gene, edges, mean)
selected <- do.call(rbind, lapply(targets, function(tf) {
  z <- em[em$target == tf, ]; z <- z[order(-abs(z$weight), z$gene), ]; head(z, 12)
}))
if (!nrow(selected)) stop("No effective target-associated network edges for panel B")
nodes <- do.call(rbind, lapply(targets, function(tf) {
  z <- selected[selected$target == tf, ]; angle <- seq(0, 2 * pi, length.out = nrow(z) + 1)[-(nrow(z) + 1)]
  z$x <- cos(angle); z$y <- sin(angle); z$sign <- ifelse(z$weight >= 0, "正权重", "负权重")
  z
}))
pn <- ggplot(nodes) + geom_segment(aes(x = 0, y = 0, xend = x, yend = y, color = sign, linewidth = abs(weight)), alpha = .6) +
  geom_point(aes(x, y), size = 1.3, color = "#5C6770") +
  geom_text(aes(1.08 * x, 1.12 * y, label = gene,
                hjust = ifelse(x > .3, 0, ifelse(x < -.3, 1, .5))), size = 7 / .pt, family = font) +
  geom_point(data = data.frame(target = targets), aes(x = 0, y = 0), size = 6, color = "#F1F3F4") +
  geom_text(data = data.frame(target = targets), aes(x = 0, y = 0, label = target), size = 8 / .pt, family = font, fontface = "bold") +
  facet_wrap(~target, ncol = 2) + coord_equal(xlim = c(-1.9, 1.9), ylim = c(-1.4, 1.4)) +
  scale_color_manual(values = c("正权重" = "#4477AA", "负权重" = "#CC8866")) + scale_linewidth_continuous(range = c(.3, 1.1), guide = "none") +
  labs(title = "合并WT靶点关联网络 | Model-predicted", subtitle = "仅pooled；绝对平均权重前12条；无因果箭头", color = "网络权重符号") +
  theme_void(base_family = font, base_size = 8) + theme(strip.text = element_text(size = 8, face = "bold"), plot.title = element_text(size = 9, face = "bold"), plot.subtitle = element_text(size = 7), legend.position = "bottom", legend.text = element_text(size = 7), legend.title = element_text(size = 7))
ph <- ggplot(em, aes(weight, fill = target)) + geom_histogram(bins = 30, color = "white", linewidth = .2) +
  facet_wrap(~target, ncol = 2, scales = "free_y") + scale_fill_manual(values = colors, guide = "none") +
  labs(title = "完整靶点关联权重分布", subtitle = paste0(nrow(em), "条目标-基因关系，未按方向筛选"), x = "算法重复平均网络权重", y = "基因数")
save_figure(pn / ph + plot_layout(heights = c(1.3, 1)), "Figure_B_Target_and_Network", 192,
  "B图仅显示合并WT模型的算法重复平均关联网络，未混合供者网络。边权不是经过实验确认的调控关系。子网络为可读性显示绝对平均权重前12条，完整分布与源表保留所有边。正负权重不能直接解释为生物学激活/抑制。")

# C: official effect intervals plus every frozen program output, including failure.
top <- do.call(rbind, lapply(targets, function(tf) {
  z <- pooled[pooled$target == tf, ]; z <- z[order(-z$effect_mean, z$gene), ]; head(z, 20)
}))
top$key <- paste(top$gene, top$target, sep = "___")
top$key <- factor(top$key, levels = rev(top$key))
pe <- ggplot(top, aes(effect_mean, key, color = target)) +
  geom_errorbar(aes(xmin = effect_ci_low, xmax = effect_ci_high), orientation = "y", width = .28, linewidth = .35) +
  geom_point(size = 1.5) + facet_wrap(~target, scales = "free_y", ncol = 2) +
  scale_y_discrete(labels = function(z) sub("___.*$", "", z)) + scale_color_manual(values = colors, guide = "none") +
  labs(title = "差异调控effect排序 | Model-predicted", subtitle = "每靶点按官方effect_mean前20；区间为算法重复区间", x = "官方effect；不是log2FC", y = NULL)
core <- intersect(c("Inflammatory", "Matrix", "Myofibroblast", "Stress", "Cell_cycle"), names(programs))
if (!length(core)) core <- names(programs)
pm <- program_map[program_map$program %in% core, , drop = FALSE]
if (nrow(pm)) {
pg <- merge(expand.grid(target = targets, gene = unique(pm$gene), stringsAsFactors = FALSE), pooled, by = c("target", "gene"), all.x = TRUE, sort = FALSE)
pg <- merge(pm, pg, by = "gene", all.x = TRUE, sort = FALSE)
pg$program <- factor(label_program(pg$program), levels = label_program(core))
pg$gene <- factor(pg$gene, levels = rev(unique(pm$gene)))
pg$display <- paste0(num(pg$delta_mean), ifelse(!is.na(pg$direction) & tolower(pg$direction) == "ambiguous", " ?", ""))
bound <- max(abs(pg$delta_mean), na.rm = TRUE); if (!is.finite(bound) || bound == 0) bound <- 1
pd <- ggplot(pg, aes(target, gene, fill = delta_mean)) + geom_tile(color = "white", linewidth = .25) +
  geom_text(aes(label = display), size = 7 / .pt, family = font) + facet_grid(program ~ ., scales = "free_y", space = "free_y") +
  scale_fill_gradient2(low = "#4477AA", mid = "#F8F8F8", high = "#CC8866", limits = c(-bound, bound), na.value = "#E1E1E1") +
  labs(title = "固定程序候选方向 | Model-predicted", subtitle = "完整预设程序；?为官方ambiguous，×为缺失", x = "靶点", y = NULL, fill = "模型delta") +
  theme(strip.text.y = element_text(angle = 0, size = 7))
fig_c <- pe | pd
} else {
  fig_c <- pe
  notes <- c(notes, "C: 未提供冻结基因程序，只绘制实际effect；不事后发明程序。")
}
save_figure(fig_c, "Figure_C_Actual_Predictions", max(205, 90 + 4 * length(unique(pm$gene))),
  "C图effect为模型差异调控尺度；delta是官方候选方向值，均非实测表达log2FC。横线保留官方算法区间，不是供者生物学置信区间。有冻结程序时完整保留其基因，包括不支持、方向不明确及缺失基因；未据预测方向挑选基因。")

# D: actual numerical stability, donor conflicts, baseline similarity, four layers.
ps <- if (nrow(seed)) ggplot(seed, aes(pair, spearman, color = metric, shape = metric)) + geom_point(size = 2) +
  facet_wrap(~target, ncol = 2) + scale_y_continuous(limits = c(-1, 1), breaks = c(-1, 0, .5, 1)) +
  scale_color_manual(values = c(delta = "#4477AA", effect = "#CC8866")) +
  labs(title = "随机种子排名稳定性 | Model-predicted", subtitle = "所有算法运行两两比较；算法种子不是生物学重复", x = "算法运行配对", y = "Spearman", color = "模型尺度", shape = "模型尺度") else not_evaluated("随机种子稳定性", "少于两次算法运行或没有可定义排名配对；不补造相关系数。")
genes_d <- unlist(programs$Inflammatory); if (!length(genes_d)) genes_d <- unique(pm$gene)
if (!length(genes_d)) genes_d <- targets
if (nrow(donor)) {
dd <- merge(expand.grid(target = targets, donor_id = donors, gene = genes_d, stringsAsFactors = FALSE), donor, by = c("target", "donor_id", "gene"), all.x = TRUE, sort = FALSE)
dd$gene <- factor(dd$gene, levels = rev(genes_d))
dd$conflict <- !is.na(dd$conflict) & tolower(as.character(dd$conflict)) %in% c("true", "1")
dd$display <- paste0(num(dd$delta), ifelse(dd$conflict, " !", ""))
db <- max(abs(dd$delta), na.rm = TRUE); if (!is.finite(db) || db == 0) db <- 1
pp <- ggplot(dd, aes(donor_id, gene, fill = delta)) + geom_tile(color = "white", linewidth = .25) +
  geom_text(aes(label = display), size = 7 / .pt, family = font) + facet_wrap(~target, ncol = 2) +
  scale_fill_gradient2(low = "#4477AA", mid = "#F8F8F8", high = "#CC8866", limits = c(-db, db), na.value = "#E1E1E1") +
  labs(title = "供者结果与合并结果冲突", subtitle = "!为与pooled_delta异号；×为缺失；不投票筛除", x = "供者ID", y = NULL, fill = "模型delta")
} else pp <- not_evaluated("供者分层稳定性", "没有已运行供者结果。可能未启用分层、供者ID不足或有效细胞数不足；原因查阅运行状态。")
bm <- c(delta_vs_direct_spearman = "delta vs\ndirect-only", effect_vs_expression_spearman = "effect vs\n表达均值", effect_vs_degree_spearman = "effect vs\n网络度数")
if (nrow(baseline)) {
bl <- do.call(rbind, lapply(names(bm), function(m) data.frame(target = baseline$target, run_index = baseline$run_index, metric = bm[m], rho = baseline[[m]])))
pb <- ggplot(bl, aes(metric, rho, color = target, group = run_index)) + geom_point(size = 1.5, position = position_dodge(width = .45)) +
  facet_wrap(~target, ncol = 2) + scale_y_continuous(limits = c(-1, 1), breaks = c(-1, 0, .5, 1)) + scale_color_manual(values = colors, guide = "none") +
  labs(title = "简单基线的排名相似性", subtitle = "相似性不等于预测准确性；无真实KO误差指标", x = NULL, y = "Spearman")
} else pb <- not_evaluated("简单基线比较", "没有可用的实际基线比较记录；不补造基线性能。")
layers <- c("INPUT_OK", "RUN_OK", "PREDICTION_STABLE", "BIO_VALIDATED")
get_layer <- function(k) {
  item <- status[[k]]; if (is.null(item)) item <- status$layers[[k]]
  if (is.null(item)) return("NOT_EVALUATED")
  if (is.list(item)) as.character(item$state) else as.character(item)
}
states <- data.frame(layer = factor(layers, levels = rev(layers)), state = vapply(layers, get_layer, character(1)), stringsAsFactors = FALSE)
states$label <- paste0(as.character(states$layer), "\n", states$state)
pt <- ggplot(states, aes(1, layer, fill = state)) + geom_tile(width = .94, height = .85) +
  geom_text(aes(label = label), size = 8 / .pt, family = font) +
  scale_fill_manual(values = c(PASS = "#DCE8EF", FAIL = "#ECD8CD", NOT_EVALUATED = "#E8E8E8", NOT_APPLICABLE = "#F0F0F0"), guide = "none") +
  labs(title = "四层证据状态", subtitle = "前一层通过不代表后一层通过") + theme_void(base_family = font, base_size = 8) +
  theme(plot.title = element_text(size = 9, face = "bold"), plot.subtitle = element_text(size = 7))
save_figure((ps | pp) / (pb | pt), "Figure_D_Stability_and_Evidence", 216,
  "D图保留全部种子比较、独立供者和基线关系。合并结果与供者异号以!显示；零或缺失按原结果保留。direct-only高度相似不能作为优于基线的证据。未提供适用真实KO实验时BIO_VALIDATED必须为NOT_EVALUATED，不生成虚构的实验验证图或AUROC/AUPRC。")

manifest <- list(backend = "R", R_version = R.version.string,
  packages = setNames(lapply(needed, function(p) as.character(utils::packageVersion(p))), needed),
  font = font, minimum_font_pt = 7, width_mm = width_mm, dpi = dpi,
  input_md5 = as.list(tools::md5sum(inputs)), script_md5 = as.character(tools::md5sum(file.path(toolkit_root, "scripts/plot_results.R"))),
  output_files = files, selected_cells = nrow(cells), known_donor_ids = known_donors,
  plotted_targets = targets, edge_display_rule = "Pooled WT only; Top12 absolute mean association weight per target; complete distribution retained",
  effect_display_rule = "Top20 official effect_mean per target; complete frozen programs retained",
  exclusions_and_notes = notes, captions = captions)
jsonlite::write_json(manifest, file.path(outdir, "figure_manifest.json"), auto_unbox = TRUE, pretty = TRUE, na = "null")
writeLines(c("# 图注 / Figure captions", unlist(lapply(names(captions), function(k) c("", paste0("## ", k), "", captions[[k]])))), file.path(outdir, "图注.md"), useBytes = TRUE)
cat("Rendered actual results: ", length(files), " files (4 PNG + 4 PDF + 4 SVG)\n", sep = "")
