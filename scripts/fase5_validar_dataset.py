#!/usr/bin/env python3
"""
Fase 5 — Validação e Controle de Qualidade do Dataset
======================================================
1. Detecção de duplicatas via Jaccard similarity (threshold 80%)
2. Filtros de exclusão pós-anotação
3. Validação estatística da distribuição de smells
4. Correlação ponto-bisserial (métricas vs has_smell)
5. Geração do dataset final em CSV

Uso:
  python3 fase5_validar_dataset.py [--fase1 FILE] [--fase2 FILE] [--fase3 FILE]
                                    [--annotations FILE] [--output DIR]

Se --annotations for fornecido, usa anotações manuais da Fase 4.
Caso contrário, usa os pré-rótulos da Fase 3.
"""
import json
import csv
import re
import math
import os
import sys
import argparse
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

# ─────────────────────────────────────────────────────────────
# Argumentos
# ─────────────────────────────────────────────────────────────
ap = argparse.ArgumentParser(description="Fase 5 — Validação e Controle de Qualidade")
ap.add_argument("--fase1", help="JSON da Fase 1 (metadados do repositório)")
ap.add_argument("--fase2", help="JSON da Fase 2 (snippets + métricas)")
ap.add_argument("--fase3", help="JSON da Fase 3 (pré-rotulação)")
ap.add_argument("--annotations", help="JSON de anotações manuais da Fase 4 (opcional)")
ap.add_argument("--output", help="Diretório de saída")
args = ap.parse_args()

project_dir = Path(__file__).resolve().parent.parent
output_dir = Path(args.output) if args.output else project_dir / "output" / "fase5"
output_dir.mkdir(parents=True, exist_ok=True)

FASE1 = args.fase1 or str(project_dir / "output" / "fase1" / "repositorio_metadata.json")
FASE2 = args.fase2 or str(project_dir / "output" / "fase2" / "snippets_com_metricas.json")
FASE3 = args.fase3 or str(project_dir / "output" / "fase3" / "pre_rotulacao.json")
ANNOTATIONS = args.annotations  # opcional

OUT_CSV = str(output_dir / "dataset_final.csv")
OUT_REPORT = str(output_dir / "validation_report.json")

# ─────────────────────────────────────────────────────────────
# Carregar dados
# ─────────────────────────────────────────────────────────────
print("=" * 70)
print("FASE 5 — Validação e Controle de Qualidade")
print("=" * 70)

for fpath, desc in [(FASE1, "Fase 1 (metadados)"), (FASE2, "Fase 2 (snippets)"), (FASE3, "Fase 3 (labels)")]:
    if not os.path.exists(fpath):
        print(f"ERRO: Arquivo não encontrado: {fpath} ({desc})")
        print("Execute as fases anteriores primeiro.")
        sys.exit(1)

with open(FASE1) as f:
    metadata_repo = json.load(f)
with open(FASE2) as f:
    fase2 = json.load(f)
with open(FASE3) as f:
    fase3 = json.load(f)

# Carregar anotações manuais se disponíveis
manual_annotations = {}
if ANNOTATIONS and os.path.exists(ANNOTATIONS):
    with open(ANNOTATIONS) as f:
        ann_data = json.load(f)
    manual_annotations = ann_data.get("annotations", {})
    manual_label_dist = Counter(a.get("label", "?") for a in manual_annotations.values())
    print(f"  Anotações manuais carregadas: {len(manual_annotations)}")
    print(f"    Labels: {dict(manual_label_dist)}")
    print(f"    Fonte: {ANNOTATIONS}")
else:
    print("  Nenhuma anotação manual fornecida — usando pré-rótulos automáticos da Fase 3")

snippets_metrics = {s["snippet_id"]: s for s in fase2["snippets"]}
snippets_labels = {s["snippet_id"]: s for s in fase3["snippets"]}

total_initial = len(fase3["snippets"])
print(f"\nSnippets iniciais: {total_initial}")

# ─────────────────────────────────────────────────────────────
# Detecção de Duplicatas — Jaccard Similarity
# ─────────────────────────────────────────────────────────────
print("\n--- 2. Detecção de Duplicatas (Jaccard ≥ 0.80) ---")

JACCARD_THRESHOLD = 0.80


def tokenize_code(code: str) -> set:
    return set(re.findall(r'[a-zA-Z_]\w*|\d+|[^\s\w]', code))


token_sets = {}
for sid, sm in snippets_metrics.items():
    token_sets[sid] = tokenize_code(sm.get("code", ""))

snippet_ids = sorted(token_sets.keys())
duplicate_pairs = []
duplicates_to_remove = set()

for i in range(len(snippet_ids)):
    if snippet_ids[i] in duplicates_to_remove:
        continue
    a_id = snippet_ids[i]
    a_tokens = token_sets[a_id]
    a_len = len(a_tokens)
    if a_len == 0:
        continue
    for j in range(i + 1, len(snippet_ids)):
        b_id = snippet_ids[j]
        if b_id in duplicates_to_remove:
            continue
        b_tokens = token_sets[b_id]
        b_len = len(b_tokens)
        if b_len == 0:
            continue
        ratio = min(a_len, b_len) / max(a_len, b_len)
        if ratio < JACCARD_THRESHOLD:
            continue
        intersection = len(a_tokens & b_tokens)
        union = len(a_tokens | b_tokens)
        jaccard = intersection / union if union > 0 else 0
        if jaccard >= JACCARD_THRESHOLD:
            duplicate_pairs.append((a_id, b_id, round(jaccard, 4)))
            a_smells = snippets_labels.get(a_id, {}).get("total_smells_count", 0)
            b_smells = snippets_labels.get(b_id, {}).get("total_smells_count", 0)
            remove_id = b_id if a_smells >= b_smells else a_id
            duplicates_to_remove.add(remove_id)

print(f"  Pares quase-duplicatas: {len(duplicate_pairs)}")
print(f"  Snippets para remoção: {len(duplicates_to_remove)}")

# ─────────────────────────────────────────────────────────────
# Filtros de Exclusão
# ─────────────────────────────────────────────────────────────
print("\n--- 3. Filtros de Exclusão ---")

exclusion_reasons = defaultdict(list)

for sid, sm in snippets_metrics.items():
    code = sm.get("code", "")

    if sid in duplicates_to_remove:
        exclusion_reasons[sid].append("near_duplicate")

    # Código gerado
    auto_gen = [r'(?i)auto[-\s]?generated', r'(?i)do not (?:edit|modify)', r'(?i)generated by \w+', r'(?i)@generated']
    for pat in auto_gen:
        if re.search(pat, code):
            exclusion_reasons[sid].append("auto_generated")
            break

    # Muito curto
    if len(code.strip()) < 20:
        exclusion_reasons[sid].append("too_short")

    # Braces desbalanceadas
    if abs(code.count("{") - code.count("}")) > 2:
        exclusion_reasons[sid].append("unbalanced_braces")

excluded_ids = set(exclusion_reasons.keys())
reason_counts = Counter()
for reasons in exclusion_reasons.values():
    for r in reasons:
        reason_counts[r] += 1

print(f"  Total excluídos: {len(excluded_ids)}")
for reason, count in reason_counts.most_common():
    print(f"    - {reason}: {count}")

# ─────────────────────────────────────────────────────────────
# Dataset Filtrado
# ─────────────────────────────────────────────────────────────
print("\n--- 4. Dataset Filtrado ---")
kept_ids = [sid for sid in snippet_ids if sid not in excluded_ids]
n_kept = len(kept_ids)
print(f"  Snippets mantidos: {n_kept} / {total_initial}")

# ─────────────────────────────────────────────────────────────
# Validação Estatística
# ─────────────────────────────────────────────────────────────
print("\n--- 5. Validação Estatística ---")

smell_counter = Counter()
label_counter = Counter()
for sid in kept_ids:
    sl = snippets_labels.get(sid, {})
    # Usar anotação manual se disponível
    if sid in manual_annotations:
        ann = manual_annotations[sid]
        label = ann.get("label", sl.get("pre_label", "unknown"))
        cats = ann.get("smells", sl.get("unique_smell_categories", []))
    else:
        label = sl.get("pre_label", "unknown")
        cats = sl.get("unique_smell_categories", [])

    label_counter[label] += 1
    for cat in cats:
        smell_counter[cat] += 1

print(f"\n  Distribuição de Labels:")
for label, count in label_counter.most_common():
    print(f"    {label}: {count} ({count/n_kept*100:.1f}%)")

print(f"\n  Top Categorias de Smell:")
for smell, count in smell_counter.most_common(15):
    print(f"    {smell:<30} {count:>5} ({count/n_kept*100:.1f}%)")

# ── Distribuição de pesos por categoria ──
# Para cada categoria detectada nos snippets mantidos, calcula peso médio
# (nº médio de ferramentas distintas que a apontaram) e peso máximo observado.
weight_per_cat_sum = defaultdict(int)
weight_per_cat_count = defaultdict(int)
weight_per_cat_max = defaultdict(int)
weight_global_dist = Counter()
for sid in kept_ids:
    sl = snippets_labels.get(sid, {})
    for cat, cw in (sl.get("category_weights") or {}).items():
        w = cw.get("weight", 0)
        weight_per_cat_sum[cat] += w
        weight_per_cat_count[cat] += 1
        weight_per_cat_max[cat] = max(weight_per_cat_max[cat], w)
        weight_global_dist[w] += 1

category_weight_stats = {
    cat: {
        "avg_weight": round(weight_per_cat_sum[cat] / weight_per_cat_count[cat], 4),
        "max_weight": weight_per_cat_max[cat],
        "occurrences": weight_per_cat_count[cat],
    }
    for cat in weight_per_cat_count
}

print(f"\n  Peso médio por categoria (top 10 por ocorrência):")
top_cats = sorted(category_weight_stats.items(),
                  key=lambda kv: -kv[1]["occurrences"])[:10]
for cat, st in top_cats:
    print(f"    {cat:<30} avg={st['avg_weight']:.2f}  max={st['max_weight']}  n={st['occurrences']}")

# Correlação ponto-bisserial
print(f"\n  Correlação Ponto-Bisserial:")

def point_biserial(binary_var, continuous_var):
    if len(binary_var) < 3:
        return 0.0, 1.0
    n = len(binary_var)
    g1 = [c for b, c in zip(binary_var, continuous_var) if b == 1]
    g0 = [c for b, c in zip(binary_var, continuous_var) if b == 0]
    if not g1 or not g0:
        return 0.0, 1.0
    m1, m0 = sum(g1)/len(g1), sum(g0)/len(g0)
    mean_all = sum(continuous_var) / n
    var_all = sum((x - mean_all)**2 for x in continuous_var) / n
    if var_all == 0:
        return 0.0, 1.0
    sd_all = math.sqrt(var_all)
    rpb = (m1 - m0) / sd_all * math.sqrt(len(g1) * len(g0) / (n * n))
    if abs(rpb) >= 1.0:
        return rpb, 0.0
    t_stat = rpb * math.sqrt((n - 2) / (1 - rpb**2))
    p_val = 2 * (1 - 0.5 * (1 + math.erf(abs(t_stat) / math.sqrt(2))))
    return round(rpb, 4), round(p_val, 4)


metrics_to_check = ["loc_executable", "cyclomatic_complexity", "nesting_depth",
                     "halstead_volume", "halstead_difficulty", "halstead_effort"]

has_smell = []
metric_arrays = defaultdict(list)
for sid in kept_ids:
    sl = snippets_labels.get(sid, {})
    sm = snippets_metrics.get(sid, {})
    if sid in manual_annotations:
        is_smelly = 1 if manual_annotations[sid].get("label") in ("smelly", "potentially_smelly") else 0
    else:
        is_smelly = 1 if sl.get("pre_label") in ("smelly", "potentially_smelly") else 0
    has_smell.append(is_smelly)
    for m in metrics_to_check:
        try:
            metric_arrays[m].append(float(sm.get(m, 0) or 0))
        except (ValueError, TypeError):
            metric_arrays[m].append(0.0)

print(f"  {'Metric':<28} {'r_pb':>8} {'p-value':>10}")
print(f"  {'-'*50}")
correlations = {}
for m in metrics_to_check:
    rpb, pval = point_biserial(has_smell, metric_arrays[m])
    correlations[m] = {"rpb": rpb, "p_value": pval}
    print(f"  {m:<28} {rpb:>8.4f} {pval:>10.4f}")

# ─────────────────────────────────────────────────────────────
# Gerar Dataset Final CSV
# ─────────────────────────────────────────────────────────────
print(f"\n--- 6. Geração do Dataset Final CSV ---")

csv_fields = [
    "snippet_id", "repo", "file_path", "snippet_type", "snippet_name",
    "start_line", "end_line",
    "loc_total", "loc_blank", "loc_comment", "loc_executable",
    "cyclomatic_complexity", "nesting_depth",
    "halstead_vocabulary", "halstead_length", "halstead_volume",
    "halstead_difficulty", "halstead_effort", "halstead_time", "halstead_bugs",
    "num_methods", "num_properties", "parent_class", "implements", "is_abstract",
    "num_parameters", "return_type",
    "label", "label_confidence", "label_source",
    "annotators_count", "agreement_rate", "resolution",
    "notes",
    "smells_detected", "total_smells_count", "unique_smell_categories",
    "smell_counts", "smell_agreement", "disputed_smells",
    "tools_that_detected", "tool_agreement_count",
    "category_weights", "max_category_weight", "avg_category_weight",
    "repo_stars", "repo_forks", "repo_license", "repo_category",
    "code"
]

rows_written = 0
with open(OUT_CSV, "w", newline="", encoding="utf-8") as csvfile:
    writer = csv.DictWriter(csvfile, fieldnames=csv_fields, extrasaction="ignore")
    writer.writeheader()

    for sid in kept_ids:
        sm = snippets_metrics.get(sid, {})
        sl = snippets_labels.get(sid, {})

        # Determinar label final
        if sid in manual_annotations:
            ann = manual_annotations[sid]
            label = ann.get("label", sl.get("pre_label", ""))
            label_source = "manual"
            smells_cats = ann.get("smells", sl.get("unique_smell_categories", []))
            annotators_count = ann.get("annotators_count", "")
            agreement_rate = ann.get("agreement_rate", "")
            resolution = ann.get("resolution", "")
            notes = ann.get("notes", "")
            smell_counts = json.dumps(ann.get("smell_counts", {}))
            smell_agreement = json.dumps(ann.get("smell_agreement", {}))
            disputed_smells = json.dumps(ann.get("disputed_smells", []))
        else:
            label = sl.get("pre_label", "")
            label_source = "automatic"
            smells_cats = sl.get("unique_smell_categories", [])
            annotators_count = ""
            agreement_rate = ""
            resolution = ""
            notes = ""
            smell_counts = ""
            smell_agreement = ""
            disputed_smells = ""

        row = {
            "snippet_id": sid,
            "repo": sm.get("repo", metadata_repo.get("repo_name", "")),
            "file_path": sm.get("file_path", ""),
            "snippet_type": sm.get("snippet_type", ""),
            "snippet_name": sm.get("snippet_name", ""),
            "start_line": sm.get("start_line", ""),
            "end_line": sm.get("end_line", ""),
            "loc_total": sm.get("loc_total", ""),
            "loc_blank": sm.get("loc_blank", ""),
            "loc_comment": sm.get("loc_comment", ""),
            "loc_executable": sm.get("loc_executable", ""),
            "cyclomatic_complexity": sm.get("cyclomatic_complexity", ""),
            "nesting_depth": sm.get("nesting_depth", ""),
            "halstead_vocabulary": sm.get("halstead_vocabulary", ""),
            "halstead_length": sm.get("halstead_length", ""),
            "halstead_volume": sm.get("halstead_volume", ""),
            "halstead_difficulty": sm.get("halstead_difficulty", ""),
            "halstead_effort": sm.get("halstead_effort", ""),
            "halstead_time": sm.get("halstead_time", ""),
            "halstead_bugs": sm.get("halstead_bugs", ""),
            "num_methods": sm.get("num_methods", ""),
            "num_properties": sm.get("num_properties", ""),
            "parent_class": sm.get("parent_class", ""),
            "implements": sm.get("implements", ""),
            "is_abstract": sm.get("is_abstract", ""),
            "num_parameters": sm.get("num_parameters", ""),
            "return_type": sm.get("return_type", ""),
            "label": label,
            "label_confidence": sl.get("pre_label_confidence", ""),
            "label_source": label_source,
            "annotators_count": annotators_count,
            "agreement_rate": agreement_rate,
            "resolution": resolution,
            "notes": notes,
            "smells_detected": json.dumps(sl.get("code_smells_detected", [])),
            "total_smells_count": sl.get("total_smells_count", 0),
            "unique_smell_categories": json.dumps(smells_cats),
            "smell_counts": smell_counts,
            "smell_agreement": smell_agreement,
            "disputed_smells": disputed_smells,
            "tools_that_detected": json.dumps(sl.get("tools_that_detected", [])),
            "tool_agreement_count": sl.get("tool_agreement_count", 0),
            "category_weights": json.dumps(sl.get("category_weights", {})),
            "max_category_weight": sl.get("max_category_weight", 0),
            "avg_category_weight": (
                round(
                    sum(cw["weight"] for cw in sl.get("category_weights", {}).values())
                    / len(sl["category_weights"]),
                    4,
                ) if sl.get("category_weights") else 0
            ),
            "repo_stars": metadata_repo.get("stars", ""),
            "repo_forks": metadata_repo.get("forks", ""),
            "repo_license": metadata_repo.get("license", ""),
            "repo_category": metadata_repo.get("category", ""),
            "code": sm.get("code", ""),
        }
        writer.writerow(row)
        rows_written += 1

csv_size = os.path.getsize(OUT_CSV)
print(f"  Dataset: {OUT_CSV}")
print(f"  Registros: {rows_written}")
print(f"  Tamanho: {csv_size / 1024:.1f} KB")

# ─────────────────────────────────────────────────────────────
# Relatório de Validação
# ─────────────────────────────────────────────────────────────
report = {
    "timestamp": datetime.now().isoformat(),
    "phase": "Fase 5 — Validação e Controle de Qualidade",
    "input": {"total_snippets": total_initial},
    "duplicate_detection": {
        "method": "Jaccard similarity on code tokens",
        "threshold": JACCARD_THRESHOLD,
        "pairs_found": len(duplicate_pairs),
        "snippets_removed": len(duplicates_to_remove),
    },
    "exclusion_filters": {
        "total_excluded": len(excluded_ids),
        "reasons": dict(reason_counts),
    },
    "statistical_validation": {
        "dataset_size_after_filters": n_kept,
        "label_distribution": dict(label_counter),
        "smell_category_distribution": dict(smell_counter),
        "category_weight_stats": category_weight_stats,
        "category_weight_distribution_global": dict(sorted(weight_global_dist.items())),
        "point_biserial_correlations": correlations,
    },
    "output": {
        "csv_path": OUT_CSV,
        "rows": rows_written,
        "columns": len(csv_fields),
        "file_size_kb": round(csv_size / 1024, 1),
    },
}

with open(OUT_REPORT, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)
print(f"\n  Relatório: {OUT_REPORT}")

# ─────────────────────────────────────────────────────────────
# Resumo
# ─────────────────────────────────────────────────────────────
print(f"\n{'='*70}")
print(f"RESUMO DA FASE 5")
print(f"{'='*70}")
print(f"  Snippets de entrada:        {total_initial}")
print(f"  Duplicatas removidas:       {len(duplicates_to_remove)}")
print(f"  Excluídos (total):          {len(excluded_ids)}")
print(f"  Dataset final:              {rows_written} snippets")
print(f"  Colunas no CSV:             {len(csv_fields)}")
print(f"  Categorias de smell:        {len(smell_counter)}")
if manual_annotations:
    print(f"  Anotações manuais usadas:   {sum(1 for sid in kept_ids if sid in manual_annotations)}")
print(f"{'='*70}")
print(f"✓ Fase 5 concluída com sucesso!")
