"""Export only aggregate historical results; never run DoseDirKO or copy raw data."""
import argparse
import csv
import hashlib
import json
import statistics
from pathlib import Path


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows):
    if not rows:
        raise ValueError(f"No observed rows for {path.name}")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export(source, destination):
    destination.mkdir(parents=True, exist_ok=True)
    config = json.loads((source / "config_resolved.json").read_text(encoding="utf-8-sig"))
    status = json.loads((source / "results/status.json").read_text(encoding="utf-8-sig"))
    files = ["predictions.csv", "target_edges.csv", "donor_predictions.csv",
             "seed_stability.csv", "baseline_comparison.csv", "network_diagnostics.csv"]
    tables = {name: read_csv(source / "results" / name) for name in files}
    programs = config["programs"]
    target_order = config["targets"]
    pooled = [r for r in tables["predictions.csv"] if r["scope"] == "pooled"]
    by_gene = {(r["target"], r["gene"]): r for r in pooled}
    fields = ["target", "gene", "effect_mean", "effect_ci_low", "effect_ci_high",
              "delta_mean", "direction", "p_up", "p_down", "topk_freq"]
    program_scores = []
    top_effect = []
    signs = []
    for target in target_order:
        ordered = sorted((r for r in pooled if r["target"] == target),
                         key=lambda r: (-float(r["effect_mean"]), r["gene"]))
        top_effect.extend({k: r[k] for k in fields} for r in ordered[:20])
        for program, genes in programs.items():
            for gene in genes:
                row = by_gene.get((target, gene))
                if row is None:
                    program_scores.append(dict(target=target, program=program, gene=gene,
                        **{k: "" for k in fields if k not in ["target", "gene"]}, present=False))
                else:
                    program_scores.append(dict(target=target, program=program, gene=gene,
                        **{k: row[k] for k in fields if k not in ["target", "gene"]}, present=True))
                donors = [r for r in tables["donor_predictions.csv"]
                          if r["target"] == target and r["gene"] == gene]
                values = [float(r["delta"]) for r in donors]
                signs.append(dict(target=target, program=program, gene=gene,
                    n_donor_models=len(values), n_positive=sum(v > 0 for v in values),
                    n_negative=sum(v < 0 for v in values), n_zero=sum(v == 0 for v in values),
                    pooled_direction=row["direction"] if row else "unavailable",
                    n_pooled_donor_sign_conflicts=sum(r["conflict"].lower() == "true" for r in donors)))
    write_csv(destination / "pooled_fixed_program_scores.csv", program_scores)
    write_csv(destination / "pooled_top20_effect.csv", top_effect)
    write_csv(destination / "donor_sign_aggregate.csv", signs)
    write_csv(destination / "seed_stability.csv", tables["seed_stability.csv"])
    write_csv(destination / "baseline_comparison.csv", tables["baseline_comparison.csv"])
    associations = []
    for target in target_order:
        gene_weights = {}
        for row in tables["target_edges.csv"]:
            if row["target"] == target and row["scope"] == "pooled":
                gene_weights.setdefault(row["gene"], []).append(float(row["weight"]))
        means = {g: statistics.mean(w) for g, w in gene_weights.items()}
        selected = sorted(means, key=lambda g: (-abs(means[g]), g))[:12]
        associations.extend(dict(target=target, gene=g, mean_weight=means[g],
                            minimum_weight=min(gene_weights[g]), maximum_weight=max(gene_weights[g]),
                            n_algorithm_runs=len(gene_weights[g])) for g in selected)
    write_csv(destination / "pooled_top12_associations.csv", associations)
    diagnostics = [r for r in tables["network_diagnostics.csv"] if r["scope"] == "pooled"]
    write_csv(destination / "pooled_network_diagnostics.csv", diagnostics)
    model = json.loads((source / "models/pooled_JUND_alpha0.5/run_manifest.json").read_text(encoding="utf-8-sig"))
    cell_table = read_csv(source / "results/cell_metadata.csv")
    independent_donors = len({r["donor_id"] for r in cell_table})
    share_status = {layer: {"state": status[layer]["state"], "reason": status[layer]["reason"]}
                    for layer in ["INPUT_OK", "RUN_OK", "PREDICTION_STABLE", "BIO_VALIDATED"]}
    share_status.update(scientific_decision=status["scientific_decision"],
        historical_replay=status["historical_replay"],
        independent_true_KO=status["independent_true_KO"],
        baseline_superiority=status["baseline_superiority"])
    metadata = dict(schema_version=1, evidence="Historical aggregate; NOT new analysis",
        n_cells=model["n_cells"], n_independent_donors=independent_donors, n_genes=len(model["genes"]),
        cell_definition="Operational multigene enrichment; fine subtype provisional",
        raw_counts_audit="PASS for exploratory subset only", targets=target_order,
        perturbation=config["perturbation"], engine=dict(id=config["engine"]["id"],
            official_commit=config["engine"]["official_commit"], params=model["params"]),
        programs=programs, stability_criteria=config["stability_criteria"], status=share_status,
        data_attribution=dict(creator="Lin, Weimin", source="https://zenodo.org/records/19697597",
            license="CC-BY-4.0", license_source="Zenodo record API, accessed 2026-10-10",
            caveat="API publication_date=2028-04-22 conflicts with audit date 2026-10-10; unresolved metadata anomaly"),
        excluded=["raw counts", "cell identifiers", "donor identifiers", "library identifiers",
                  "per-cell coordinates", "per-donor scores", "complete network and checkpoints",
                  "private absolute paths", "third-party engine source"],
        selection_rules=dict(associations="Top12 absolute mean pooled WT association weights per target",
            predictions="All fixed historical program genes; top20 effect table separately supplied",
            donor_summary="Aggregate signs/counts only; no donor IDs or individual numerical scores",
            seed_results="All 3 pairwise comparisons per score per target; no seed selection"))
    (destination / "historical_summary.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    source_paths = [source / "results" / name for name in files] + [
        source / "config_resolved.json", source / "results/status.json", source / "results/cell_metadata.csv",
        source / "models/pooled_JUND_alpha0.5/run_manifest.json"]
    manifest = dict(source_label="Local historical replay; original records excluded from repository",
        source_sha256={str(p.relative_to(source)).replace("\\", "/"): sha(p) for p in source_paths},
        exported_sha256={p.name: sha(p) for p in sorted(destination.iterdir()) if p.is_file()},
        exporter_sha256=sha(Path(__file__)), independent_validation=False)
    (destination.parent / "source_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--historical-output", type=Path, required=True)
    parser.add_argument("--destination", type=Path, default=Path(__file__).parent / "data")
    args = parser.parse_args()
    export(args.historical_output, args.destination)
    print("Exported aggregate historical tables; no numerical engine was run.")
