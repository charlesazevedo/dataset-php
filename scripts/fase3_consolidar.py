#!/usr/bin/env python3
"""
Fase 3 — Consolidação de Análise Estática
==========================================
Mapeia os findings das 5 ferramentas para os snippets da Fase 2,
classifica code smells e gera pré-rotulação automática.

Uso direto (chamado por fase3_analise_estatica.sh):
  python3 fase3_consolidar.py \
    --snippets ../output/fase2/snippets_com_metricas.json \
    --phpmd    ../output/fase3/phpmd_output.json \
    --phpstan  ../output/fase3/phpstan_output.json \
    --psalm    ../output/fase3/psalm_output.json \
    --phpcs    ../output/fase3/phpcs_output.json \
    --repo-root ../repos/meu-repo \
    --output-json ../output/fase3/pre_rotulacao.json \
    --output-csv  ../output/fase3/pre_rotulacao.csv
"""
import json
import csv
import os
import sys
import argparse
from collections import defaultdict, Counter
from datetime import datetime, timezone
from pathlib import Path

# ── Argumentos ──
parser = argparse.ArgumentParser(description="Fase 3 — Consolidação de Análise Estática")
parser.add_argument("--snippets", required=True, help="JSON de snippets da Fase 2")
parser.add_argument("--phpmd", required=True, help="Output PHPMD (JSON)")
parser.add_argument("--phpstan", required=True, help="Output PHPStan (JSON)")
parser.add_argument("--psalm", required=True, help="Output Psalm (JSON)")
parser.add_argument("--phpcs", required=True, help="Output PHPCS (JSON)")
parser.add_argument("--sonar", default=None, help="Output SonarQube (JSON, opcional)")
parser.add_argument("--repo-root", required=True, help="Raiz do repositório clonado")
parser.add_argument("--output-json", required=True, help="JSON de saída consolidado")
parser.add_argument("--output-csv", required=True, help="CSV de saída consolidado")
args = parser.parse_args()

REPO_ROOT = os.path.realpath(args.repo_root).rstrip("/") + "/"

# ── Carregar snippets da Fase 2 ──
with open(args.snippets) as f:
    phase2 = json.load(f)
snippets = phase2["snippets"]
print(f"Loaded {len(snippets)} snippets from Phase 2")

file_snippets = defaultdict(list)
for s in snippets:
    file_snippets[s["file_path"]].append(s)


def normalize_path(raw_path):
    if ":" in raw_path:
        raw_path = raw_path.split(":", 1)[1]
    if REPO_ROOT in raw_path:
        raw_path = raw_path.replace(REPO_ROOT, "")
    raw_path = raw_path.lstrip("/")
    return raw_path


def find_matching_snippets(file_path, line):
    norm = normalize_path(file_path)
    matches = []
    for s in file_snippets.get(norm, []):
        if s["start_line"] <= line <= s["end_line"]:
            matches.append(s["snippet_id"])
    return matches


# ── Parsers para cada ferramenta ──
def parse_phpmd():
    findings = []
    with open(args.phpmd) as f:
        data = json.load(f)
    for file_entry in data.get("files", []):
        fpath = file_entry["file"]
        for v in file_entry.get("violations", []):
            findings.append({
                "tool": "PHPMD", "file_path": normalize_path(fpath),
                "line": v["beginLine"], "end_line": v.get("endLine", v["beginLine"]),
                "rule": v.get("rule", ""), "ruleset": v.get("ruleSet", ""),
                "severity": str(v.get("priority", 3)), "message": v.get("description", "").strip(),
            })
    return findings


def parse_phpstan():
    findings = []
    with open(args.phpstan) as f:
        data = json.load(f)
    for fpath, errors in data.get("files", {}).items():
        for msg in errors.get("messages", []):
            findings.append({
                "tool": "PHPStan", "file_path": normalize_path(fpath),
                "line": msg.get("line", 0), "end_line": msg.get("line", 0),
                "rule": msg.get("identifier", "phpstan.error"), "ruleset": "PHPStan Level 5",
                "severity": "error" if not msg.get("ignorable", True) else "warning",
                "message": msg.get("message", "").strip(),
            })
    return findings


def parse_psalm():
    findings = []
    with open(args.psalm) as f:
        data = json.load(f)
    for issue in data if isinstance(data, list) else []:
        findings.append({
            "tool": "Psalm", "file_path": normalize_path(issue.get("file_path", "")),
            "line": issue.get("line_from", 0), "end_line": issue.get("line_to", issue.get("line_from", 0)),
            "rule": issue.get("type", ""), "ruleset": "Psalm",
            "severity": issue.get("severity", "error"), "message": issue.get("message", "").strip(),
        })
    return findings


def parse_phpcs():
    findings = []
    with open(args.phpcs) as f:
        data = json.load(f)
    for fpath, file_data in data.get("files", {}).items():
        for msg in file_data.get("messages", []):
            findings.append({
                "tool": "PHPCS", "file_path": normalize_path(fpath),
                "line": msg.get("line", 0), "end_line": msg.get("line", 0),
                "rule": msg.get("source", ""), "ruleset": "PHPCS CodeSmell",
                "severity": msg.get("type", "WARNING").lower(), "message": msg.get("message", "").strip(),
            })
    return findings


def parse_sonar():
    """Extrai findings do SonarQube (API issues/search JSON)."""
    if not args.sonar or not os.path.exists(args.sonar):
        return []
    findings = []
    with open(args.sonar) as f:
        data = json.load(f)
    for issue in data.get("issues", []):
        comp = issue.get("component", "")
        file_path = comp.split(":", 1)[1] if ":" in comp else comp
        severity_map = {"BLOCKER": "high", "CRITICAL": "high", "MAJOR": "warning", "MINOR": "info", "INFO": "info"}
        findings.append({
            "tool": "SonarQube",
            "file_path": normalize_path(file_path) if file_path else "",
            "line": issue.get("line", 0) or 0,
            "end_line": issue.get("textRange", {}).get("endLine", issue.get("line", 0)) or 0,
            "rule": issue.get("rule", ""),
            "ruleset": issue.get("type", "CODE_SMELL"),
            "severity": severity_map.get(issue.get("severity", ""), "warning"),
            "message": issue.get("message", "").strip(),
        })
    return findings


# ── Coletar findings ──
print("Parsing tool outputs...")
all_findings = []
tool_counts = {}

for name, parser_fn in [("PHPMD", parse_phpmd), ("PHPStan", parse_phpstan),
                         ("Psalm", parse_psalm), ("PHPCS", parse_phpcs),
                         ("SonarQube", parse_sonar)]:
    try:
        findings = parser_fn()
        tool_counts[name] = len(findings)
        all_findings.extend(findings)
        print(f"  {name}: {len(findings)} findings")
    except Exception as e:
        print(f"  {name}: ERRO ao parsear - {e}")
        tool_counts[name] = 0

print(f"Total findings: {len(all_findings)}")

# Total de ferramentas no universo de análise (denominador do peso normalizado).
# Usa só as ferramentas que efetivamente rodaram (parsearam algo OU foram declaradas);
# fallback para 1 evita divisão por zero em ambientes degenerados.
TOTAL_TOOLS = max(len(tool_counts), 1)

# ── Mapear findings para snippets ──
print("Mapping findings to snippets...")
snippet_smells = defaultdict(list)
unmapped_count = 0

for f in all_findings:
    if not f["line"]:
        unmapped_count += 1
        continue
    matched_ids = find_matching_snippets(f["file_path"], f["line"])
    if matched_ids:
        for sid in matched_ids:
            snippet_smells[sid].append({
                "tool_name": f["tool"], "smell_type": f["rule"], "ruleset": f["ruleset"],
                "severity": f["severity"], "message": f["message"], "line": f["line"], "end_line": f["end_line"],
            })
    else:
        unmapped_count += 1

print(f"Mapped to {len(snippet_smells)} snippets, {unmapped_count} findings unmapped")

# ── Mapa de categorias de code smell ──
SMELL_CATEGORY_MAP = {
    "CyclomaticComplexity": "Complex Method", "NPathComplexity": "Complex Method",
    "ExcessiveMethodLength": "Long Method", "ExcessiveClassLength": "Large Class",
    "ExcessiveParameterList": "Long Parameter List", "TooManyFields": "Large Class",
    "TooManyMethods": "Large Class", "TooManyPublicMethods": "Large Class",
    "ExcessiveClassComplexity": "Large Class", "BooleanArgumentFlag": "Boolean Parameter",
    "ElseExpression": "Unnecessary Else", "StaticAccess": "Static Coupling",
    "CouplingBetweenObjects": "Feature Envy", "ShortVariable": "Poor Naming",
    "LongVariable": "Poor Naming", "ShortMethodName": "Poor Naming",
    "LongClassName": "Poor Naming", "ShortClassName": "Poor Naming",
    "UnusedPrivateField": "Dead Code", "UnusedLocalVariable": "Dead Code",
    "UnusedPrivateMethod": "Dead Code", "UnusedFormalParameter": "Dead Code",
    "DepthOfInheritance": "Deep Hierarchy", "GodClass": "God Class",
    "Generic.Metrics.CyclomaticComplexity": "Complex Method",
    "Generic.Metrics.NestingLevel": "Deep Nesting",
    "Generic.CodeAnalysis.EmptyStatement": "Empty Block",
    "Generic.CodeAnalysis.UselessOverridingMethod": "Useless Override",
    "Generic.CodeAnalysis.UnconditionalIfStatement": "Useless Condition",
    "Generic.Files.LineLength": "Long Line",
    "Squiz.PHP.CommentedOutCode": "Commented Out Code",
}


def classify_smell(rule):
    if rule in SMELL_CATEGORY_MAP:
        return SMELL_CATEGORY_MAP[rule]
    for key, category in SMELL_CATEGORY_MAP.items():
        if key.lower() in rule.lower():
            return category
    rule_lower = rule.lower()
    if "complex" in rule_lower: return "Complex Method"
    if "unused" in rule_lower or "dead" in rule_lower: return "Dead Code"
    if "naming" in rule_lower or "name" in rule_lower: return "Poor Naming"
    if "deprecated" in rule_lower: return "Deprecated Usage"
    if "null" in rule_lower: return "Null Safety"
    if "type" in rule_lower: return "Type Inconsistency"
    if "long" in rule_lower or "length" in rule_lower: return "Long Method"
    return "Other"


# ── Construir output ──
print("Building pre-labeling output...")
output_snippets = []

for s in snippets:
    sid = s["snippet_id"]
    smells = snippet_smells.get(sid, [])

    enriched_smells = []
    for smell in smells:
        enriched_smells.append({
            "tool_name": smell["tool_name"], "smell_type": smell["smell_type"],
            "smell_category": classify_smell(smell["smell_type"]),
            "severity": smell["severity"], "message": smell["message"], "line": smell["line"],
        })

    unique_categories = list(set(sm["smell_category"] for sm in enriched_smells))
    tools_detected = list(set(sm["tool_name"] for sm in enriched_smells))
    tool_agreement = len(tools_detected)
    total_findings = len(enriched_smells)

    # ── Peso por smell_category ──
    # Conta quantas ferramentas *distintas* detectaram cada categoria.
    # weight            = nº de ferramentas distintas (1..TOTAL_TOOLS)
    # weight_normalized = weight / TOTAL_TOOLS  (0..1)
    # tools             = lista das ferramentas que apontaram aquela categoria
    # findings_count    = total bruto de findings naquela categoria (pode > weight
    #                     quando a mesma ferramenta dispara múltiplas regras na cat.)
    cat_tools = defaultdict(set)
    cat_findings = Counter()
    for sm in enriched_smells:
        cat = sm["smell_category"]
        cat_tools[cat].add(sm["tool_name"])
        cat_findings[cat] += 1

    category_weights = {}
    for cat in unique_categories:
        w = len(cat_tools[cat])
        category_weights[cat] = {
            "weight": w,
            "weight_normalized": round(w / TOTAL_TOOLS, 4) if TOTAL_TOOLS else 0.0,
            "tools": sorted(cat_tools[cat]),
            "findings_count": cat_findings[cat],
        }

    # Enriquece cada smell individual com o peso da sua categoria
    # (útil pra ordenar/colorizar tags na interface da Fase 4 sem recalcular).
    for sm in enriched_smells:
        cw = category_weights.get(sm["smell_category"], {})
        sm["category_weight"] = cw.get("weight", 1)
        sm["category_weight_normalized"] = cw.get("weight_normalized", 0.0)

    if total_findings == 0:
        pre_label, confidence = "clean", "high"
    elif tool_agreement >= 3:
        pre_label, confidence = "smelly", "high"
    elif tool_agreement >= 2:
        pre_label, confidence = "smelly", "medium"
    elif total_findings >= 3:
        pre_label, confidence = "smelly", "medium"
    elif total_findings >= 1:
        pre_label, confidence = "potentially_smelly", "low"
    else:
        pre_label, confidence = "clean", "high"

    output_snippets.append({
        "snippet_id": sid, "file_path": s["file_path"],
        "snippet_type": s["snippet_type"], "snippet_name": s["snippet_name"],
        "start_line": s["start_line"], "end_line": s["end_line"],
        "loc_executable": s["loc_executable"], "cyclomatic_complexity": s["cyclomatic_complexity"],
        "code_smells_detected": enriched_smells, "total_smells_count": total_findings,
        "unique_smell_categories": unique_categories, "tools_that_detected": tools_detected,
        "tool_agreement_count": tool_agreement,
        "category_weights": category_weights,
        "max_category_weight": max((w["weight"] for w in category_weights.values()), default=0),
        "pre_label": pre_label, "pre_label_confidence": confidence,
    })

# ── Estatísticas ──
label_dist = Counter(s["pre_label"] for s in output_snippets)
category_dist = Counter()
tool_snippet_coverage = Counter()
for s in output_snippets:
    for cat in s["unique_smell_categories"]:
        category_dist[cat] += 1
    for t in s["tools_that_detected"]:
        tool_snippet_coverage[t] += 1

# Distribuição de pesos: agrupa (category, weight) por nº de snippets
weight_dist_per_category = defaultdict(Counter)
weight_dist_global = Counter()
for s in output_snippets:
    for cat, cw in s["category_weights"].items():
        weight_dist_per_category[cat][cw["weight"]] += 1
        weight_dist_global[cw["weight"]] += 1

stats = {
    "total_snippets": len(output_snippets),
    "total_findings_all_tools": len(all_findings),
    "findings_mapped_to_snippets": sum(s["total_smells_count"] for s in output_snippets),
    "findings_unmapped": unmapped_count,
    "tool_finding_counts": tool_counts,
    "total_tools_considered": TOTAL_TOOLS,
    "tool_snippet_coverage": dict(tool_snippet_coverage),
    "pre_label_distribution": dict(label_dist),
    "smell_category_distribution": dict(category_dist.most_common(30)),
    "category_weight_distribution_global": dict(sorted(weight_dist_global.items())),
    "category_weight_distribution_per_category": {
        cat: dict(sorted(wd.items())) for cat, wd in weight_dist_per_category.items()
    },
    "snippets_with_smells": sum(1 for s in output_snippets if s["total_smells_count"] > 0),
    "snippets_clean": sum(1 for s in output_snippets if s["total_smells_count"] == 0),
}

# ── Salvar ──
output = {
    "metadata": {
        "phase": "Fase 3", "description": "Pre-labeling based on static analysis tools",
        "repo": phase2.get("metadata", {}).get("repo", "unknown"),
        "analysis_date": datetime.now(timezone.utc).isoformat(),
        "tools_used": ["PHPMD", "PHPStan", "Psalm", "PHPCS"],
        "statistics": stats,
    },
    "snippets": output_snippets,
}

with open(args.output_json, "w") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)
print(f"\nJSON salvo: {args.output_json}")

csv_rows = []
for s in output_snippets:
    # Formato compacto "Categoria:peso(t1,t2); ..." pra inspeção rápida no CSV.
    cw_compact = "; ".join(
        f"{cat}:{cw['weight']}({','.join(cw['tools'])})"
        for cat, cw in sorted(s["category_weights"].items(), key=lambda kv: -kv[1]["weight"])
    )
    csv_rows.append({
        "snippet_id": s["snippet_id"], "file_path": s["file_path"],
        "snippet_type": s["snippet_type"], "snippet_name": s["snippet_name"],
        "total_smells_count": s["total_smells_count"],
        "unique_smell_categories": "; ".join(s["unique_smell_categories"]),
        "tools_that_detected": "; ".join(s["tools_that_detected"]),
        "tool_agreement_count": s["tool_agreement_count"],
        "max_category_weight": s["max_category_weight"],
        "category_weights": cw_compact,
        "pre_label": s["pre_label"], "pre_label_confidence": s["pre_label_confidence"],
    })

if csv_rows:
    with open(args.output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=csv_rows[0].keys())
        writer.writeheader()
        writer.writerows(csv_rows)
    print(f"CSV salvo: {args.output_csv}")

# ── Resumo ──
print(f"\n{'='*60}")
print(f"FASE 3 — RESUMO")
print(f"{'='*60}")
print(f"  Snippets analisados:     {stats['total_snippets']}")
print(f"  Total findings:          {stats['total_findings_all_tools']}")
print(f"  Findings mapeados:       {stats['findings_mapped_to_snippets']}")
print(f"  Snippets com smells:     {stats['snippets_with_smells']}")
print(f"  Snippets limpos:         {stats['snippets_clean']}")
print(f"\n  Distribuição de pré-labels:")
for label, c in label_dist.most_common():
    print(f"    {label}: {c}")
print(f"\n✓ Consolidação concluída!")
