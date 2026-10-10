# Explicit Seurat counts export. No package installation or annotation changes.
args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2L || length(args) > 3L) {
  stop("Usage: Rscript export_seurat.R input.rds output_directory [assay=RNA]")
}
for (pkg in c("SeuratObject", "Matrix", "jsonlite")) {
  if (!requireNamespace(pkg, quietly = TRUE)) stop("Not installed: ", pkg, "; use an existing supported Seurat environment")
}
input <- normalizePath(args[[1]], mustWork = TRUE)
output <- args[[2]]
assay <- if (length(args) == 3L) args[[3]] else "RNA"
if (dir.exists(output) && length(list.files(output, all.files = TRUE, no.. = TRUE))) {
  stop("Output directory must be empty; existing exports are never overwritten")
}
obj <- readRDS(input)
if (!inherits(obj, "Seurat")) stop("Input is not a Seurat object")
if (!assay %in% names(obj@assays)) stop("Assay not found: ", assay)
if (utils::packageVersion("SeuratObject") >= "5.0.0") {
  layers <- SeuratObject::Layers(obj[[assay]])
  if (!"counts" %in% layers || any(grepl("^counts\\.", layers))) {
    stop("A single explicit counts layer is required; split layers must be resolved in the source project")
  }
  counts <- SeuratObject::LayerData(obj, assay = assay, layer = "counts")
  location <- paste0(assay, "/layers/counts")
} else {
  counts <- SeuratObject::GetAssayData(obj, assay = assay, slot = "counts")
  location <- paste0(assay, "/slot/counts")
}
if (!inherits(counts, "sparseMatrix")) stop("Counts must be sparse; export a small sparse subset upstream")
if (!nrow(counts) || !ncol(counts) || anyDuplicated(rownames(counts)) || anyDuplicated(colnames(counts))) {
  stop("Counts must have nonempty unique row and column IDs")
}
if (any(!is.finite(counts@x)) || any(counts@x < 0) || any(counts@x != floor(counts@x))) {
  stop("Counts must contain finite nonnegative integers")
}
metadata <- obj[[]]
if (!all(colnames(counts) %in% rownames(metadata))) stop("Missing cell metadata")
metadata <- metadata[colnames(counts), , drop = FALSE]
if ("cell_id" %in% colnames(metadata) && !identical(as.character(metadata$cell_id), colnames(counts))) {
  stop("Existing cell_id disagrees with counts; no identifier remapping is guessed")
}
metadata$cell_id <- colnames(counts)
dir.create(output, recursive = TRUE, showWarnings = FALSE)
Matrix::writeMM(counts, file.path(output, "matrix.mtx"))
utils::write.table(data.frame(rownames(counts), rownames(counts), "Gene Expression"),
                   file.path(output, "features.tsv"), sep = "\t", quote = FALSE,
                   row.names = FALSE, col.names = FALSE)
utils::write.table(colnames(counts), file.path(output, "barcodes.tsv"), sep = "\t",
                   quote = FALSE, row.names = FALSE, col.names = FALSE)
utils::write.csv(metadata, file.path(output, "cell_metadata.csv"), row.names = FALSE,
                 fileEncoding = "UTF-8", na = "")
files <- c("matrix.mtx", "features.tsv", "barcodes.tsv", "cell_metadata.csv")
md5 <- as.list(unname(tools::md5sum(file.path(output, files))))
names(md5) <- files
manifest <- list(source_rds = input, source_rds_md5 = unname(tools::md5sum(input)),
                 counts_location = location, export_md5 = md5,
                 shape_genes_cells = dim(counts), gene_id_note = "Original Seurat row names; no Ensembl mapping invented",
                 R = R.version.string,
                 packages = lapply(c("SeuratObject", "Matrix", "jsonlite"), function(x) as.character(utils::packageVersion(x))))
names(manifest$packages) <- c("SeuratObject", "Matrix", "jsonlite")
jsonlite::write_json(manifest, file.path(output, "seurat_export_manifest.json"), auto_unbox = TRUE, pretty = TRUE)
message("Exported explicit raw counts. Supply biological sample/donor/state mappings in toolkit config.")
