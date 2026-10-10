"""Explicit raw-count adapters; no clustering, annotation, or automatic QC."""
from pathlib import Path
import gzip
import hashlib
import json

import numpy as np
import pandas as pd
from scipy import io, sparse


def _path(value, base_dir):
    path = Path(value)
    return path if path.is_absolute() else (Path(base_dir) / path).resolve()


def _digest(path, algorithm="sha256"):
    digest = hashlib.new(algorithm)
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _file(directory, stem):
    found = [directory / name for name in (stem, stem + ".gz") if (directory / name).is_file()]
    if len(found) != 1:
        raise ValueError(f"Exactly one {stem} or {stem}.gz is required: {directory}")
    return found[0]


def _table(path, **kwargs):
    return pd.read_csv(path, dtype=str, keep_default_na=False, **kwargs)


def _matrix_market_preflight(path, budget):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="ascii") as handle:
        header = handle.readline().strip().lower().split()
        if len(header) != 5 or header[:3] != ["%%matrixmarket", "matrix", "coordinate"] or header[3] not in ("integer", "real") or header[4] != "general":
            raise ValueError("10x requires a general sparse integer/real MatrixMarket count matrix")
        line = next((line for line in handle if line.strip() and not line.lstrip().startswith("%")), "")
        fields = line.split()
        if len(fields) != 3:
            raise ValueError("Malformed MatrixMarket dimensions/nnz")
        genes, cells, nnz = map(int, fields)
        if genes <= 0 or cells <= 0 or nnz < 0:
            raise ValueError("Invalid MatrixMarket dimensions/nnz")
    # Allow for COO, CSR and conversion/validation temporary arrays.
    estimated = 64 * nnz + 16 * (genes + cells)
    if estimated > budget:
        raise MemoryError(f"10x counts estimate {estimated} bytes exceeds max_counts_bytes={budget}; export a smaller upstream subset")
    return genes, cells, nnz


def _unique(values, label):
    values = [str(value) for value in values]
    if not values or any(not value.strip() for value in values) or len(values) != len(set(values)):
        raise ValueError(f"{label} must be nonempty and unique; identifiers are never invented or collapsed")
    return values


def _counts(matrix):
    values = np.asarray(matrix.data if sparse.issparse(matrix) else matrix).ravel()
    if not np.all(np.isfinite(values)) or np.any(values < 0) or np.any(values != np.floor(values)):
        raise ValueError("Raw counts must be finite, nonnegative integers; normalized/log expression is rejected")
    result = sparse.csr_matrix(matrix)
    result.sum_duplicates()
    result.eliminate_zeros()
    return result


def _metadata(frame, cells, columns):
    mapping = {key: columns.get(key, key) for key in ("cell_id", "sample_id", "donor_id")}
    mapping["vpt_state"] = columns.get("state", "state")
    if mapping["cell_id"] not in frame:
        raise ValueError(f"Missing cell identifier column: {mapping['cell_id']}")
    frame = frame.copy()
    frame.index = _unique(frame[mapping["cell_id"]], "Metadata cell IDs")
    missing = set(cells) - set(frame.index)
    if missing:
        raise ValueError(f"Metadata is missing {len(missing)} count-matrix cell IDs")
    frame = frame.loc[cells].copy()
    for key, source in mapping.items():
        if source not in frame:
            raise ValueError(f"Missing required metadata column for {key}: {source}")
        if key in frame and key != source and not frame[key].astype(str).equals(frame[source].astype(str)):
            raise ValueError(f"Column mapping would overwrite different metadata: {key}")
        frame[key] = frame[source].astype(str)
    frame.index.name = "cell_id"
    if any(not value.strip() for value in frame["sample_id"]):
        raise ValueError("sample_id cannot be empty; do not invent sample identities")
    return frame


def _subset(metadata, selection):
    if not selection:
        return np.arange(len(metadata)), metadata
    if selection["column"] not in metadata:
        raise ValueError(f"Unknown selection column: {selection['column']}")
    rows = np.flatnonzero(metadata[selection["column"]].isin(selection["values"]).to_numpy())
    if not len(rows):
        raise ValueError("Requested cell subset is empty; no state is invented")
    return rows, metadata.iloc[rows].copy()


def load_input(spec, base_dir):
    """Return cells×genes CSR counts, symbols, cell metadata, and source provenance.

    ``base_dir`` is the directory of the configuration file, not the shell cwd.
    Seurat RDS requires a previously verified export made by export_seurat.R.
    """
    for key in ("species", "accession", "counts_origin", "qc_status"):
        if not spec.get(key):
            raise ValueError(f"Required source declaration is absent: {key}")
    annotation = spec.get("annotation", {})
    if annotation.get("kind") not in ("operational", "author", "validated") or not all(
        annotation.get(key) for key in ("label", "source")
    ):
        raise ValueError("annotation requires kind=operational|author|validated, label, and source")
    source_format = spec.get("format")
    source_path = _path(spec["path"], base_dir)
    columns = spec.get("columns", {})
    source_files = []
    gene_metadata_columns = []
    counts_location = ""
    selection = spec.get("selection")
    original_shape = None
    already_subset = False
    if source_format == "seurat_rds":
        if not spec.get("export_path"):
            raise ValueError("Seurat RDS requires export_path. Run scripts/export_seurat.R in an existing Seurat R environment first")
        export_path = _path(spec["export_path"], base_dir)
        manifest_path = export_path / "seurat_export_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        if _digest(source_path, "md5") != manifest["source_rds_md5"]:
            raise ValueError("Seurat export belongs to different/changed RDS input")
        for name, md5 in manifest["export_md5"].items():
            if _digest(export_path / name, "md5") != md5:
                raise ValueError(f"Seurat export integrity mismatch: {name}")
        source_files = [source_path, manifest_path]
        counts_location = manifest["counts_location"]
        source_path = export_path

    if source_format in ("10x", "seurat_rds"):
        matrix_path = _file(source_path, "matrix.mtx")
        features_path = _file(source_path, "features.tsv")
        barcodes_path = _file(source_path, "barcodes.tsv")
        _matrix_market_preflight(matrix_path, int(spec.get("max_counts_bytes", 256 * 1024 * 1024)))
        opener = gzip.open if matrix_path.suffix == ".gz" else open
        with opener(matrix_path, "rb") as handle:
            matrix = io.mmread(handle)
        features = _table(features_path, sep="\t", header=None)
        barcodes = _table(barcodes_path, sep="\t", header=None)
        if features.shape[1] < 2 or barcodes.shape[1] != 1:
            raise ValueError("10x requires feature ID + gene symbol columns and one-column barcodes")
        if features.shape[1] >= 3 and not features[2].eq("Gene Expression").all():
            raise ValueError("Mixed/non-Gene Expression 10x features require an explicit upstream RNA subset")
        gene_ids = _unique(features[0], "Feature IDs")
        genes = _unique(features[1], "Gene symbols")
        cells = _unique(barcodes[0], "Matrix cell IDs")
        if matrix.shape != (len(genes), len(cells)):
            raise ValueError("10x matrix rows/columns do not match features/barcodes")
        matrix = _counts(matrix).T.tocsr()
        if not spec.get("cell_metadata") and source_format != "seurat_rds":
            raise ValueError("10x input requires cell_metadata; biological IDs cannot be inferred from barcodes")
        metadata_path = _path(spec["cell_metadata"], base_dir) if spec.get("cell_metadata") else source_path / "cell_metadata.csv"
        metadata = _table(metadata_path)
        source_files.extend([matrix_path, features_path, barcodes_path, metadata_path])
        counts_location = counts_location or "10x/matrix.mtx (explicitly declared raw counts)"
    elif source_format == "h5ad":
        layer = spec.get("counts_layer")
        if not layer or layer in ("X", "raw", "raw.X"):
            raise ValueError("H5AD requires an explicit named counts_layer; X/raw are not guessed to be counts")
        import anndata as ad
        import h5py
        # read_h5ad(backed='r') can eagerly load layers; open only obs/var and
        # slice the declared layer through the official sparse_dataset API.
        with h5py.File(source_path, "r") as data:
            if "layers" not in data or layer not in data["layers"]:
                raise ValueError(f"H5AD has no declared counts layer: {layer}")
            metadata = ad.io.read_elem(data["obs"])
            var = ad.io.read_elem(data["var"])
            cells = _unique(metadata.index, "H5AD obs_names")
            gene_ids = _unique(var.index, "H5AD var_names")
            symbol_column = spec.get("gene_symbol_column")
            if symbol_column and symbol_column not in var:
                raise ValueError(f"H5AD var is missing gene symbol column: {symbol_column}")
            genes = _unique(var[symbol_column] if symbol_column else gene_ids, "Gene symbols")
            gene_metadata_columns = list(var.columns)
            declared_cell_column = columns.get("cell_id", "cell_id")
            if declared_cell_column in metadata and metadata[declared_cell_column].astype(str).tolist() != cells:
                raise ValueError("H5AD obs cell-ID column contradicts obs_names order; no remapping is guessed")
            if "cell_id" not in metadata and columns.get("cell_id", "cell_id") == "cell_id":
                metadata["cell_id"] = cells
            if spec.get("cell_metadata"):
                metadata_path = _path(spec["cell_metadata"], base_dir)
                metadata = _table(metadata_path)
                source_files.append(metadata_path)
            metadata = _metadata(metadata, cells, columns)
            rows, metadata = _subset(metadata, selection)
            layer_data = data["layers"][layer]
            budget = int(spec.get("max_counts_bytes", 256 * 1024 * 1024))
            if isinstance(layer_data, h5py.Group):
                dataset = ad.io.sparse_dataset(layer_data)
                if dataset.shape != (len(cells), len(genes)):
                    raise ValueError("Declared H5AD counts layer does not match obs/var order/shape")
                if dataset.format == "csr":
                    ptr = layer_data["indptr"]
                    nnz = sum(int(ptr[row + 1]) - int(ptr[row]) for row in rows)
                else:
                    # CSC row slicing can materialize the full sparse matrix.
                    nnz = len(layer_data["data"])
                estimated = nnz * (layer_data["data"].dtype.itemsize + layer_data["indices"].dtype.itemsize) + (len(rows) + 1) * 8
            else:
                dataset = layer_data
                if dataset.shape != (len(cells), len(genes)):
                    raise ValueError("Declared H5AD counts layer does not match obs/var order/shape")
                estimated = len(rows) * len(genes) * dataset.dtype.itemsize
            if estimated > budget:
                raise MemoryError(f"Counts slice estimate {estimated} bytes exceeds max_counts_bytes={budget}; export a smaller upstream subset")
            matrix = _counts(dataset[rows, :])
            original_shape = [len(cells), len(genes)]
            already_subset = True
            counts_location = f"layers/{layer}"
        source_files.append(source_path)
    else:
        raise ValueError(f"Unsupported input format: {source_format}")

    if spec.get("gene_metadata"):
        gene_metadata_path = _path(spec["gene_metadata"], base_dir)
        gene_metadata = _table(gene_metadata_path)
        id_column = spec.get("gene_id_column", "feature_id")
        symbol_column = spec.get("gene_symbol_column", "gene_symbol")
        if id_column not in gene_metadata or symbol_column not in gene_metadata:
            raise ValueError("gene_metadata requires explicit ID and symbol columns")
        gene_metadata.index = _unique(gene_metadata[id_column], "Gene metadata IDs")
        if set(gene_ids) - set(gene_metadata.index):
            raise ValueError("gene_metadata is missing count-matrix gene IDs")
        if gene_metadata.loc[gene_ids, symbol_column].tolist() != genes:
            raise ValueError("gene_metadata symbols disagree with count-matrix feature order/identities")
        gene_metadata_columns = list(gene_metadata.columns)
        source_files.append(gene_metadata_path)

    if not already_subset:
        metadata = _metadata(metadata, cells, columns)
    original_shape = original_shape or list(matrix.shape)
    if matrix.shape != (len(metadata), len(genes)):
        raise ValueError("Count matrix shape disagrees with cell/gene metadata")
    if not already_subset:
        rows, metadata = _subset(metadata, selection)
        matrix = matrix[rows].tocsr()

    unknown = {"", "unknown", "na", "n/a", "nan", "none", "unavailable", "not reported"}
    missing_donor = metadata["donor_id"].fillna("").str.strip().str.lower().isin(unknown)
    missing_state = metadata["vpt_state"].fillna("").str.strip().str.lower().isin(unknown)
    warnings = []
    if missing_donor.any():
        warnings.append("Unknown donor identity: donor-stratified analysis is blocked; no replacement IDs were created")
    if missing_state.any() or annotation["kind"] == "operational":
        warnings.append("Cell state is unknown or operational: no subtype-specific biological claim is supported by this adapter")
    zero_cells = int(np.count_nonzero(np.asarray(matrix.sum(axis=1)).ravel() == 0))
    if zero_cells:
        warnings.append(f"{zero_cells} zero-count cells were retained; upstream QC must resolve them before modeling")
    provenance = {
        "format": source_format, "species": spec["species"], "accession": spec["accession"],
        "counts_origin": spec["counts_origin"], "counts_location": counts_location,
        "qc_status": spec["qc_status"], "annotation": annotation, "selection": selection,
        "source_shape_cells_genes": original_shape, "selected_shape_cells_genes": list(matrix.shape),
        "source_gene_ids": gene_ids, "gene_metadata_columns": gene_metadata_columns,
        "columns": columns, "raw_counts_nonnegative_integer": True,
        "donor_stratification_allowed": not bool(missing_donor.any()),
        "unknown_donor_cells": int(missing_donor.sum()), "zero_count_cells": zero_cells,
        "warnings": warnings,
        "files": {str(path): {"bytes": path.stat().st_size, "sha256": _digest(path)} for path in source_files},
    }
    return matrix, genes, metadata, provenance
