"""Tiny software fixtures only; these tests provide no biological validation."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from scipy import io, sparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vpt.inputs import load_input


class InputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.x = np.array([[1, 0, 3], [0, 2, 1], [4, 2, 0]], dtype=np.int32)
        self.meta = pd.DataFrame({"cell_id": ["c3", "c1", "c2"], "sample": ["s2", "s1", "s1"],
                                  "donor": ["d2", "d1", "d1"], "state_origin": ["b", "a", "a"],
                                  "retained_note": ["third", "first", "second"]})
        self._write_10x()
        self.spec = {"format": "10x", "path": "tenx", "cell_metadata": "metadata.csv",
                     "columns": {"cell_id": "cell_id", "sample_id": "sample", "donor_id": "donor", "state": "state_origin"},
                     "species": "human", "accession": "SOFTWARE_FIXTURE", "counts_origin": "software fixture counts",
                     "qc_status": "software fixture only", "annotation": {"kind": "operational", "label": "fixture", "source": "unit test"}}

    def tearDown(self):
        self.temp.cleanup()

    def _write_10x(self, x=None, genes=None):
        directory = self.root / "tenx"
        directory.mkdir(exist_ok=True)
        io.mmwrite(directory / "matrix.mtx", sparse.coo_matrix((self.x if x is None else x).T))
        pd.DataFrame({0: ["id1", "id2", "id3"], 1: genes or ["G1", "G2", "G3"], 2: ["Gene Expression"] * 3}).to_csv(directory / "features.tsv", sep="\t", index=False, header=False)
        (directory / "barcodes.tsv").write_text("c1\nc2\nc3\n", encoding="utf-8")
        self.meta.to_csv(self.root / "metadata.csv", index=False)

    def test_barcode_alignment_and_retained_metadata(self):
        x, genes, meta, prov = load_input(self.spec, self.root)
        np.testing.assert_array_equal(x.toarray(), self.x)
        self.assertEqual(genes, ["G1", "G2", "G3"])
        self.assertEqual(meta.index.tolist(), ["c1", "c2", "c3"])
        self.assertEqual(meta["retained_note"].tolist(), ["first", "second", "third"])
        self.assertEqual(meta["vpt_state"].tolist(), ["a", "a", "b"])
        self.assertTrue(prov["donor_stratification_allowed"])

    def test_invalid_counts_rejected(self):
        for invalid in (-1.0, 0.5, np.nan):
            x = self.x.astype(float)
            x[0, 0] = invalid
            self._write_10x(x=x)
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, "Raw counts"):
                load_input(self.spec, self.root)

    def test_10x_budget_blocks_before_matrix_is_loaded(self):
        with patch("vpt.inputs.io.mmread") as reader:
            with self.assertRaisesRegex(MemoryError, "10x counts estimate"):
                load_input(dict(self.spec, max_counts_bytes=1), self.root)
            reader.assert_not_called()

    def test_duplicate_symbols_rejected(self):
        self._write_10x(genes=["G1", "G1", "G3"])
        with self.assertRaisesRegex(ValueError, "Gene symbols"):
            load_input(self.spec, self.root)

    def test_missing_and_duplicate_cell_metadata_rejected(self):
        for metadata in (self.meta.iloc[:2], pd.concat([self.meta, self.meta.iloc[:1]])):
            metadata.to_csv(self.root / "metadata.csv", index=False)
            with self.assertRaises(ValueError):
                load_input(self.spec, self.root)

    def test_unknown_donor_blocks_stratification_without_fabrication(self):
        self.meta.loc[self.meta.cell_id == "c1", "donor"] = "UNKNOWN"
        self.meta.to_csv(self.root / "metadata.csv", index=False)
        _, _, meta, prov = load_input(self.spec, self.root)
        self.assertFalse(prov["donor_stratification_allowed"])
        self.assertEqual(meta.loc["c1", "donor_id"], "UNKNOWN")

    def test_gene_metadata_identity_cannot_be_guessed_by_position(self):
        pd.DataFrame({"feature_id": ["id3", "id1", "id2"], "gene_symbol": ["G3", "G1", "WRONG"]}).to_csv(self.root / "genes.csv", index=False)
        self.spec["gene_metadata"] = "genes.csv"
        with self.assertRaisesRegex(ValueError, "symbols disagree"):
            load_input(self.spec, self.root)

    def test_h5ad_missing_counts_and_inconsistent_symbol_rejected(self):
        import anndata as ad
        obs = self.meta.set_index("cell_id").loc[["c1", "c2", "c3"]]
        data = ad.AnnData(X=sparse.csr_matrix(np.log1p(self.x)), obs=obs,
                          var=pd.DataFrame({"symbol": ["G1", "G2", "G3"]}, index=["id1", "id2", "id3"]))
        data.write_h5ad(self.root / "fixture.h5ad")
        spec = dict(self.spec, format="h5ad", path="fixture.h5ad", counts_layer="counts", gene_symbol_column="symbol")
        spec.pop("cell_metadata")
        with self.assertRaisesRegex(ValueError, "no declared counts layer"):
            load_input(spec, self.root)
        for layer in ("X", "raw", "raw.X"):
            with self.assertRaisesRegex(ValueError, "explicit named"):
                load_input(dict(spec, counts_layer=layer), self.root)
        data.layers["counts"] = sparse.csr_matrix(self.x)
        data.var["symbol"] = ["G1", "G1", "G3"]
        data.write_h5ad(self.root / "fixture.h5ad")
        with self.assertRaisesRegex(ValueError, "Gene symbols"):
            load_input(spec, self.root)

    def test_10x_and_h5ad_subset_values_are_identical(self):
        import anndata as ad
        obs = self.meta.set_index("cell_id").loc[["c1", "c2", "c3"]]
        data = ad.AnnData(X=sparse.csr_matrix(np.log1p(self.x)), obs=obs,
                          var=pd.DataFrame({"symbol": ["G1", "G2", "G3"]}, index=["id1", "id2", "id3"]))
        data.layers["counts"] = sparse.csr_matrix(self.x)
        data.write_h5ad(self.root / "fixture.h5ad")
        self.spec["selection"] = {"column": "state_origin", "values": ["a"]}
        tenx = load_input(self.spec, self.root)
        spec = dict(self.spec, format="h5ad", path="fixture.h5ad", counts_layer="counts", gene_symbol_column="symbol")
        spec.pop("cell_metadata")
        h5ad = load_input(spec, self.root)
        np.testing.assert_array_equal(tenx[0].toarray(), h5ad[0].toarray())
        self.assertEqual(tenx[1], h5ad[1])
        self.assertEqual(tenx[2].index.tolist(), h5ad[2].index.tolist())
        self.assertEqual(h5ad[3]["source_shape_cells_genes"], [3, 3])
        with self.assertRaises(MemoryError):
            load_input(dict(spec, max_counts_bytes=1), self.root)

    def test_missing_source_declaration_and_unexported_rds_rejected(self):
        spec = self.spec.copy()
        spec.pop("counts_origin")
        with self.assertRaisesRegex(ValueError, "counts_origin"):
            load_input(spec, self.root)
        with self.assertRaisesRegex(ValueError, "export_path"):
            load_input(dict(self.spec, format="seurat_rds", path="source.rds"), self.root)

    def test_h5ad_cell_column_cannot_reverse_matrix_row_identity(self):
        import anndata as ad
        obs = self.meta.set_index("cell_id").loc[["c1", "c2", "c3"]]
        obs["cell_id"] = ["c2", "c1", "c3"]
        obs.index.name = None
        data = ad.AnnData(X=sparse.csr_matrix(self.x), obs=obs,
                          var=pd.DataFrame(index=["G1", "G2", "G3"]))
        data.layers["counts"] = sparse.csr_matrix(self.x)
        data.write_h5ad(self.root / "fixture.h5ad")
        spec = dict(self.spec, format="h5ad", path="fixture.h5ad", counts_layer="counts")
        spec.pop("cell_metadata")
        with self.assertRaisesRegex(ValueError, "contradicts obs_names"):
            load_input(spec, self.root)


if __name__ == "__main__":
    unittest.main()
