#!/usr/bin/env python3
"""
Utilitário para Consolidação de Múltiplos Anotadores (Fase 4)
=============================================================
Lê múltiplos arquivos JSON de anotação e resolve conflitos
por votação de maioria com desempate conservador.

Uso:
  python3 consolidar_anotacoes.py dev1.json dev2.json dev3.json \
      --output anotacoes_consolidadas.json \
      [--snippets-data output/fase4/dados_integrados.json] \
      [--review-html revisao_desempate.html]

Quando houver casos `requires_review` E `--snippets-data` for fornecido,
gera automaticamente um HTML interativo para um 4º revisor desempatar
os casos conflitantes, com código + voto de cada dev lado a lado.
"""
import json
import os
import sys
import argparse
import html
from collections import Counter
from pathlib import Path
from datetime import datetime


def annotator_name(filepath):
    """Extrai nome do anotador do nome do arquivo (sem extensão)."""
    name = Path(filepath).stem
    # Heurística: pega o último segmento após 'dev_' ou 'dev', senão usa o nome inteiro
    for marker in ("_dev_", "_dev"):
        if marker in name:
            suffix = name.split(marker)[-1]
            return f"dev_{suffix}" if not suffix.startswith("dev") else suffix
    return name


def main():
    parser = argparse.ArgumentParser(
        description="Consolidar anotações de múltiplos especialistas",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("files", nargs="+", help="Arquivos JSON dos anotadores (1 por dev)")
    parser.add_argument("--output", default="anotacoes_consolidadas.json",
                        help="JSON consolidado de saída (padrão: anotacoes_consolidadas.json)")
    parser.add_argument("--snippets-data",
                        help="JSON com código + métricas dos snippets (ex.: output/fase4/dados_integrados.json). "
                             "Necessário para gerar o HTML de revisão.")
    parser.add_argument("--review-html", default=None,
                        help="HTML de desempate (gerado só se houver requires_review). "
                             "Padrão: revisao_desempate.html ao lado do --output")
    args = parser.parse_args()

    if len(args.files) < 2:
        print("Erro: forneça ao menos 2 arquivos para consolidar.", file=sys.stderr)
        sys.exit(1)

    # Carregar arquivos e identificar anotadores por nome de arquivo
    annotators = []   # lista de (nome, dict de annotations)
    for fpath in args.files:
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)
        name = annotator_name(fpath)
        annotators.append((name, data.get("annotations", {})))
        print(f"  Carregado: {name:<20}  ({len(data.get('annotations', {}))} anotações)")

    # Pegar todos os snippet_ids únicos
    all_ids = set()
    for _, anns in annotators:
        all_ids.update(anns.keys())

    consolidated = {}
    conflicts = 0
    review_cases = []  # lista enriquecida para o HTML de desempate

    print(f"\nConsolidando {len(all_ids)} snippets de {len(annotators)} anotadores...")

    for sid in all_ids:
        # Coletar voto de cada anotador para este snippet
        votes_per_dev = {}    # dev_name -> {label, smells, notes}
        labels = []
        smells_list = []
        notes = []

        for name, anns in annotators:
            ann = anns.get(sid)
            if ann:
                votes_per_dev[name] = {
                    "label": ann["label"],
                    "smells": ann.get("smells", []),
                    "notes": ann.get("notes", ""),
                }
                labels.append(ann["label"])
                smells_list.append(set(ann.get("smells", [])))
                if ann.get("notes"):
                    notes.append(ann["notes"])

        if not labels:
            continue

        # Votação de Maioria
        counts = Counter(labels)
        most_common = counts.most_common()
        n_annotators = len(labels)
        top_count = most_common[0][1]

        requires_review = False
        label_conflict = False
        resolution = "consensus"

        if top_count == n_annotators:
            final_label = most_common[0][0]
            resolution = "consensus"
        elif len(most_common) > 1 and top_count == most_common[1][1]:
            priority = {"smelly": 3, "potentially_smelly": 2, "clean": 1}
            tied_labels = [l for l, c in most_common if c == top_count]
            final_label = max(tied_labels, key=lambda x: priority.get(x, 0))
            resolution = "tie_broken"
            requires_review = True
            label_conflict = True
            conflicts += 1
        else:
            final_label = most_common[0][0]
            resolution = "majority"
            if top_count < (n_annotators / 2) + 0.5:
                requires_review = True
                label_conflict = True
                conflicts += 1

        # Consolidação de Smells (threshold ≥2 com 3+ anotadores)
        all_smells = []
        for s_set in smells_list:
            all_smells.extend(list(s_set))
        smell_counts = Counter(all_smells)
        threshold = 2 if n_annotators >= 3 else 1
        final_smells = [s for s, c in smell_counts.items() if c >= threshold]

        # Detecção de divergência de smells (mesmo com label concordante)
        smell_agreement = {}
        for s, c in smell_counts.items():
            smell_agreement[s] = round(c / n_annotators, 2)
        disputed_smells = [s for s, c in smell_counts.items() if c < threshold]
        smells_conflict = bool(disputed_smells) and any(smells_list)

        # Se label teve consenso/maioria mas smells divergem, exige revisao
        if not requires_review and final_label in ("smelly", "potentially_smelly") and smells_conflict:
            requires_review = True
            conflicts += 1

        record = {
            "label": final_label,
            "smells": final_smells,
            "notes": " | ".join(sorted(set(notes))),
            "agreement_rate": round(top_count / n_annotators, 2),
            "annotators_count": n_annotators,
            "resolution": resolution,
            "requires_review": requires_review,
            "label_conflict": label_conflict,
            "all_votes": dict(counts),
            "votes_per_annotator": votes_per_dev,
            "smell_counts": dict(smell_counts),
            "smell_agreement": smell_agreement,
            "disputed_smells": disputed_smells,
            "smells_conflict": smells_conflict,
        }
        consolidated[sid] = record

        if requires_review:
            review_cases.append({"snippet_id": sid, **record})

    # Estatísticas
    resolutions = Counter(c["resolution"] for c in consolidated.values())
    review_count = len(review_cases)
    label_dist = Counter(c["label"] for c in consolidated.values())
    smell_conflict_count = sum(1 for c in consolidated.values() if c.get("smells_conflict"))
    label_conflict_count = sum(1 for c in consolidated.values() if c.get("label_conflict"))
    label_only_review = sum(1 for c in consolidated.values()
                            if c.get("label_conflict") and not c.get("smells_conflict"))
    smell_only_review = sum(1 for c in consolidated.values()
                            if c.get("smells_conflict") and not c.get("label_conflict"))
    both_conflict = sum(1 for c in consolidated.values()
                         if c.get("smells_conflict") and c.get("label_conflict"))

    output_payload = {
        "metadata": {
            "description": "Consolidado por votação de maioria com desempate conservador",
            "generated_at": datetime.now().isoformat(),
            "files_processed": args.files,
            "annotator_names": [n for n, _ in annotators],
            "total_annotators": len(annotators),
            "total_snippets": len(consolidated),
            "conflicts_resolved": conflicts,
            "requires_review_count": review_count,
            "label_conflict_count": label_conflict_count,
            "smell_conflict_count": smell_conflict_count,
            "label_only_review": label_only_review,
            "smell_only_review": smell_only_review,
            "both_conflict": both_conflict,
            "resolution_summary": dict(resolutions),
            "label_distribution": dict(label_dist),
            "tie_break_rule": "smelly > potentially_smelly > clean",
            "smell_threshold": "smell mantido se ≥2 anotadores apontaram (ou ≥1 se houver só 1 anotador)",
        },
        "annotations": consolidated,
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output_payload, f, indent=2, ensure_ascii=False)

    print(f"\n✓ Consolidação concluída!")
    print(f"  Snippets processados:     {len(consolidated)}")
    print(f"  Anotadores:               {len(annotators)} ({', '.join(n for n, _ in annotators)})")
    print(f"  Resolução:")
    for r, c in resolutions.most_common():
        print(f"    - {r:<15}        {c}")
    print(f"  Snippets que exigem revisão humana: {review_count}")
    print(f"    - Divergência de label:           {label_conflict_count}")
    print(f"      · só label:                     {label_only_review}")
    print(f"      · label + smells:               {both_conflict}")
    print(f"    - Divergência de smells:          {smell_conflict_count}")
    print(f"      · só smells (label OK):         {smell_only_review}")
    print(f"  Distribuição final:")
    for lbl, c in label_dist.most_common():
        print(f"    - {lbl:<20}   {c}")
    print(f"\n  Arquivo gerado: {args.output}")

    # Geração do HTML de desempate
    if review_count > 0:
        if not args.snippets_data:
            print(f"\n⚠ {review_count} snippets requerem revisão humana.")
            print("  Para gerar o HTML interativo de desempate, rode novamente com:")
            print("    --snippets-data output/fase4/dados_integrados.json")
        else:
            if not os.path.exists(args.snippets_data):
                print(f"\n✗ Arquivo --snippets-data não encontrado: {args.snippets_data}", file=sys.stderr)
                sys.exit(1)

            with open(args.snippets_data, "r", encoding="utf-8") as f:
                snippets_data = json.load(f)

            # Lookup por snippet_id
            snippets_by_id = {s["snippet_id"]: s for s in snippets_data.get("snippets", [])}

            # Tentar localizar o repo clonado para re-extrair o código exato
            # (mesmo fix da interface principal — alinha linhas com smells)
            project_dir = Path(__file__).resolve().parent.parent
            repos_root = project_dir / "repos"
            repo_dir = None
            if repos_root.exists():
                subs = [p for p in repos_root.iterdir() if p.is_dir()]
                repo_dir = subs[0] if subs else None
            file_cache = {}

            def reextract_code(file_path, start_line, end_line):
                if not repo_dir or not file_path:
                    return None
                fp = repo_dir / file_path
                if str(fp) not in file_cache:
                    try:
                        with open(fp, "r", encoding="utf-8", errors="replace") as f:
                            file_cache[str(fp)] = f.read().splitlines()
                    except Exception:
                        file_cache[str(fp)] = None
                lines = file_cache[str(fp)]
                if not lines:
                    return None
                start_line = max(1, int(start_line or 1))
                end_line = min(len(lines), int(end_line or len(lines)))
                if end_line < start_line:
                    return None
                return "\n".join(lines[start_line - 1:end_line])

            # Enriquecer review_cases com código/métricas/smells
            enriched_cases = []
            for case in review_cases:
                sid = case["snippet_id"]
                snip = snippets_by_id.get(sid, {})
                precise_code = reextract_code(
                    snip.get("file_path", ""),
                    snip.get("start_line"),
                    snip.get("end_line"),
                )
                # Determinar tipo de conflito
                has_label_conflict = case.get("label_conflict", False)
                has_smell_conflict = case.get("smells_conflict", False)
                if has_label_conflict and has_smell_conflict:
                    conflict_type = "both"
                elif has_smell_conflict:
                    conflict_type = "smells"
                else:
                    conflict_type = "label"
                enriched_cases.append({
                    **case,
                    "conflict_type": conflict_type,
                    "file_path": snip.get("file_path", ""),
                    "snippet_name": snip.get("snippet_name", ""),
                    "snippet_type": snip.get("snippet_type", ""),
                    "start_line": snip.get("start_line", 0),
                    "end_line": snip.get("end_line", 0),
                    "code": precise_code if precise_code is not None else snip.get("code", ""),
                    "metrics": snip.get("metrics", {}),
                    "smells_detected": snip.get("smells_detected", []),
                    "category_weights": snip.get("category_weights", {}),
                    "max_category_weight": snip.get("max_category_weight", 0),
                    "tools_that_detected": snip.get("tools_that_detected", []),
                    "tool_agreement_count": snip.get("tool_agreement_count", 0),
                })

            review_html_path = args.review_html or str(Path(args.output).parent / "revisao_desempate.html")
            generate_review_html(
                enriched_cases,
                [n for n, _ in annotators],
                args.output,
                review_html_path,
            )
            print(f"\n✓ HTML de desempate gerado: {review_html_path}")
            print(f"  Abra no navegador, escolha o rótulo final de cada caso e exporte o JSON final.")

    print(f"\nPróximo passo — Fase 5 com este consolidado (ou com o desempatado final):")
    print(f"  python3 scripts/fase5_validar_dataset.py \\")
    print(f"    --annotations {args.output} \\")
    print(f"    --output output/fase5")


def generate_review_html(cases, annotator_names, consolidated_path, output_path):
    """Gera HTML interativo de desempate. Recebe casos já enriquecidos com código."""
    cases_json = json.dumps(cases, ensure_ascii=False)
    annotators_json = json.dumps(annotator_names, ensure_ascii=False)
    consolidated_basename = os.path.basename(consolidated_path)

    template = '''<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<title>Desempate de Anotações — Revisor Final</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/languages/php.min.js"></script>
<style>
:root{--bg:#0f1117;--card:#1a1d27;--border:#2d3248;--accent:#e74c3c;--green:#00b894;--yellow:#fdcb6e;--red:#e17055;--text:#e0e0e0;--text2:#a0a4b8}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif;line-height:1.5;padding:24px;max-width:1400px;margin:0 auto}
header{margin-bottom:24px;padding-bottom:16px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px}
h1{font-size:1.4rem;font-weight:600}
h1 span{color:var(--accent)}
.summary{color:var(--text2);font-size:.9rem}
.actions{display:flex;gap:8px;flex-wrap:wrap}
.btn{padding:8px 16px;border:1px solid var(--border);background:var(--card);color:var(--text);border-radius:6px;cursor:pointer;font-size:.85rem}
.btn:hover{border-color:var(--accent)}
.btn-primary{background:var(--accent);border-color:var(--accent);color:#fff}
.btn-success{background:var(--green);border-color:var(--green);color:#fff}
.progress{background:var(--card);height:6px;border-radius:3px;overflow:hidden;margin:8px 0 16px}
.progress-fill{height:100%;background:var(--green);transition:width .3s}
.snippet-card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:20px;margin-bottom:20px}
.snippet-card.resolved{border-color:var(--green)}
.snippet-card h2{font-size:1rem;margin-bottom:8px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.badge{padding:2px 10px;border-radius:4px;font-size:.72rem;font-weight:600}
.badge-clean{background:#1b4a3a;color:#00b894}
.badge-potentially{background:#4a3a1b;color:#fdcb6e}
.badge-smelly{background:#4a1b1b;color:#e17055}
.badge-type{background:#3a1b1b;color:#e8a9a8}
.file-path{color:var(--text2);font-size:.8rem;margin-bottom:12px;font-family:'JetBrains Mono',monospace}
.layout{display:grid;grid-template-columns:1fr 360px;gap:20px;margin-top:12px}
@media (max-width: 900px){.layout{grid-template-columns:1fr}}
.code-block{background:#0d1117;border:1px solid var(--border);border-radius:8px;overflow:hidden}
.code-block pre{margin:0;padding:14px;overflow-x:auto;font-size:.78rem;line-height:1.55;max-height:440px}
.code-block code{font-family:'JetBrains Mono','Fira Code',monospace!important}
.code-line{display:flex;line-height:1.55}
.code-line:nth-child(odd){background:rgba(255,255,255,.01)}
.line-number{min-width:2.8em;text-align:right;padding-right:10px;color:#4a5568;user-select:none;border-right:1px solid #1e2430;margin-right:10px;font-size:.75rem}
.line-content{white-space:pre}
.code-line.hl-red{background:rgba(225,112,85,.18)!important}
.code-line.hl-yellow{background:rgba(253,203,110,.14)!important}
.code-line.hl-blue{background:rgba(108,92,231,.14)!important}
.smells-section{margin:14px 0 8px}
.smells-section h4{font-size:.78rem;color:var(--text2);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px}
.smell-tag{display:inline-block;padding:2px 8px;border-radius:4px;font-size:.7rem;margin:2px;background:rgba(225,112,85,.15);color:var(--red);cursor:pointer;text-decoration:none}
.smell-tag:hover{filter:brightness(1.3)}
.smell-tag .line-link{color:var(--accent);font-weight:600;margin-left:4px}
.votes{display:flex;flex-direction:column;gap:8px}
.vote-row{background:#0d1117;border:1px solid var(--border);border-radius:8px;padding:10px 12px}
.vote-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:4px}
.vote-name{font-weight:600;font-size:.85rem}
.vote-smells{font-size:.72rem;color:var(--text2);margin-top:4px}
.vote-notes{font-size:.72rem;color:var(--text2);font-style:italic;margin-top:4px}
.suggested{background:rgba(231,76,60,.12);border-color:var(--accent)}
.suggested::before{content:"sugestão (desempate conservador)";display:block;font-size:.65rem;color:var(--accent);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px}
.label-picker{display:flex;gap:6px;margin-top:12px;flex-wrap:wrap}
.label-btn{flex:1;min-width:90px;padding:8px;border:2px solid var(--border);background:transparent;color:var(--text);border-radius:6px;cursor:pointer;font-size:.78rem;font-weight:600;transition:all .15s}
.label-btn:hover{border-color:var(--accent)}
.label-btn.picked{color:#fff}
.label-btn.picked[data-l="smelly"]{background:var(--red);border-color:var(--red)}
.label-btn.picked[data-l="potentially_smelly"]{background:var(--yellow);border-color:var(--yellow);color:#000}
.label-btn.picked[data-l="clean"]{background:var(--green);border-color:var(--green)}
.notes-input{width:100%;background:var(--card);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:8px;margin-top:8px;font-size:.78rem;resize:vertical;min-height:40px}
.metrics{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0;font-size:.72rem}
.metric{background:#0d1117;border:1px solid var(--border);padding:3px 8px;border-radius:4px;color:var(--text2)}
.empty-state{text-align:center;padding:60px;color:var(--text2)}
.toast{position:fixed;bottom:20px;right:20px;background:var(--green);color:#fff;padding:12px 20px;border-radius:8px;box-shadow:0 4px 12px rgba(0,0,0,.3);transform:translateY(120%);transition:transform .25s;z-index:1000}
.toast.show{transform:translateY(0)}
.loading-overlay{position:fixed;top:0;left:0;width:100%;height:100%;background:var(--bg);display:flex;flex-direction:column;align-items:center;justify-content:center;z-index:9999;transition:opacity .4s}
.loading-overlay.hidden{opacity:0;pointer-events:none}
.spinner{width:48px;height:48px;border:4px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:spin .8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.loading-text{color:var(--text2);font-size:.9rem;margin-top:16px}
.conflict-banner{display:flex;align-items:center;gap:10px;padding:8px 14px;border-radius:8px;margin-bottom:12px;font-size:.78rem;font-weight:600}
.conflict-banner.label{background:rgba(231,76,60,.12);border:1px solid var(--accent);color:var(--accent)}
.conflict-banner.smells{background:rgba(253,203,110,.12);border:1px solid var(--yellow);color:var(--yellow)}
.conflict-banner.both{background:rgba(225,112,85,.12);border:1px solid var(--red);color:var(--red)}
.smell-consolidated h5{color:var(--green);font-size:.7rem;text-transform:uppercase;letter-spacing:.4px;margin:8px 0 4px}
.smell-disputed h5{color:var(--yellow);font-size:.7rem;text-transform:uppercase;letter-spacing:.4px;margin:8px 0 4px}
.smell-vote-count{display:inline-block;min-width:1.2em;text-align:center;font-size:.6rem;padding:0 4px;border-radius:3px;margin-left:4px}
.smell-vote-count.consensus{background:rgba(0,184,148,.2);color:var(--green)}
.smell-vote-count.disputed{background:rgba(253,203,110,.15);color:var(--yellow)}
.smell-checkbox{display:flex;align-items:center;gap:6px;padding:3px 0;font-size:.75rem;cursor:default}
.smell-checkbox input{accent-color:var(--accent);cursor:pointer;flex:0 0 auto}
.smell-checkbox .smell-name{flex:1 1 auto;line-height:1.25;cursor:default}
.smell-checkbox .smell-help{flex:0 0 auto;font-size:.72rem;color:var(--text2);width:16px;height:16px;display:inline-flex;align-items:center;justify-content:center;border-radius:50%;border:1px solid var(--border);cursor:help;transition:all .15s}
.smell-checkbox:hover{background:rgba(255,255,255,.03);border-radius:4px}
.smell-checkbox:hover .smell-help{color:var(--accent);border-color:var(--accent)}
.smell-filter{width:100%;background:var(--card);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:5px 8px;font-size:.75rem;margin-bottom:6px;position:sticky;top:0;z-index:2}
.weight-badge{display:inline-block;margin-left:4px;padding:0 6px;border-radius:8px;font-size:.62rem;font-weight:700;background:rgba(255,255,255,.12);color:#fff;vertical-align:middle}
.weight-badge.w1{background:#3a4858;color:#cfd6e0}
.weight-badge.w2{background:#7a5a20;color:#fde7a7}
.weight-badge.w3{background:#a04020;color:#ffe0d0}
.weight-badge.w4{background:#8b1e1e;color:#fff}
.weight-badge.w5{background:#601020;color:#fff;box-shadow:0 0 0 1px #ff5050 inset}
.cat-weights-box{background:#0d1117;border:1px solid var(--border);border-radius:6px;padding:8px 10px;margin-top:8px;font-size:.72rem}
.cat-weights-box .cw-row{display:flex;justify-content:space-between;align-items:center;padding:2px 0;color:var(--text2)}
.cat-weights-box .cw-row b{color:var(--text)}
.cat-weights-box .cw-tools{font-size:.66rem;color:var(--text2);font-style:italic}
.dec-stat{background:rgba(255,255,255,.06);padding:3px 10px;border-radius:6px;font-size:.78rem;margin-left:8px}
.dec-stat b{margin:0 3px}
</style>
</head>
<body>

<div class="loading-overlay" id="loadingOverlay">
  <div class="spinner"></div>
  <div class="loading-text">Carregando casos conflitantes...</div>
</div>

<header>
  <div>
    <h1>Desempate de Anotações — <span>Revisor Final</span></h1>
    <div class="summary" id="summaryLine">Carregando...</div>
    <div style="margin-top:6px;display:flex;align-items:center;flex-wrap:wrap" title="Distribuição das decisões finais (atualiza ao escolher cada caso)">
      <span style="font-size:.72rem;color:var(--text2);text-transform:uppercase;letter-spacing:.5px">Decisões:</span>
      <span class="dec-stat" style="color:var(--red)" title="Casos decididos como Smelly">🔴 <b id="decSmelly">0</b></span>
      <span class="dec-stat" style="color:var(--green)" title="Casos decididos como Clean">🟢 <b id="decClean">0</b></span>
      <span class="dec-stat" style="color:var(--text2)" title="Casos ainda não revisados">⚪ pendente <b id="decPending">0</b></span>
    </div>
  </div>
  <div class="actions">
    <a href="index.html" class="btn" style="text-decoration:none;margin-right:8px">🏚️ Início</a>
    <button class="btn btn-success" onclick="exportFinal()">📥 Exportar JSON Final</button>
    <button class="btn" onclick="clearDecisions()">🗑️ Limpar decisões</button>
  </div>
</header>

<div class="progress"><div class="progress-fill" id="progressFill"></div></div>

<div id="cases"></div>

<div class="toast" id="toast">Salvo localmente.</div>

<script>
const CASES = __CASES__;
const ANNOTATORS = __ANNOTATORS__;
const CONSOLIDATED_BASENAME = "__CONSOLIDATED_BASENAME__";
const STORAGE_KEY = `tiebreak_decisions_${CONSOLIDATED_BASENAME}`;

let decisions = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");

// Lista oficial (mesma da interface de anotação) — deduplicada, 49 itens.
// "Other" sempre por último. Categorias legadas (de anotações antigas) aparecem
// no topo com marca (legado).
const SMELL_CATEGORIES = [
  "Boolean Parameter",
  "Class Complexity",
  "Class Length",
  "Clone Implementations",
  "Code Complexity",
  "Code Fragmentation",
  "Commented Out Code",
  "Confusing Incrementers",
  "Confusing Use Of Comments",
  "Dead Code",
  "Deep Nesting",
  "Duplicate Code",
  "Empty Blocks",
  "Empty Catch Block",
  "Excessive Inline Code",
  "Excessive Method Length (EML)",
  "Excessive Number of Children (ENOC)",
  "Excessive Parameter List (EPL)",
  "Excessive Subclassing",
  "Feature Envy",
  "Functions Parentheses on Multiple Lines",
  "God Class",
  "High Coupling (HC)",
  "High Method Complexity (HMC)",
  "Incorrect Spacing After Commas",
  "Incorrect String Manipulation",
  "Incorrect Variable Naming",
  "Inefficient Logic",
  "Misaligned Logic Blocks",
  "Missing @Return Tag in Comments",
  "Missing Function Comments",
  "Names Poorly Defined",
  "Null Safety",
  "Overloaded Classes",
  "Poorly Organized Classes",
  "Static Coupling",
  "Too Many Fields",
  "Too Many Methods",
  "Too Many Public Methods (TMPM)",
  "Type Inconsistency",
  "Unclear Loop Logic",
  "Unnecessary Code",
  "Unnecessary Else",
  "Unused Formal Parameter",
  "Unused Local Variable",
  "Unused Private Field",
  "Unused Private Method",
  "Useless Override",
  "Other"
];

// Descrições por categoria — mesmas da interface de anotação. Usadas como
// tooltip nativo (title) em cada checkbox e no ícone ⓘ. Inclui descrições
// das categorias legadas (que aparecem em anotações antigas com sugestão de
// migração).
const SMELL_DESCRIPTIONS = {
  "Code Complexity": "Código com lógica excessivamente complexa, dificultando entendimento e manutenção.",
  "Confusing Incrementers": "Uso confuso de operadores de incremento/decremento, reduzindo legibilidade.",
  "Confusing Loops": "[LEGADO — migrar para 'Unclear Loop Logic'] Estruturas de repetição difíceis de entender ou seguir.",
  "Duplicate Code": "Trechos de código repetidos em diferentes partes do sistema.",
  "Empty Blocks": "Blocos de código vazios sem funcionalidade implementada.",
  "Empty Catch Block": "Exceções capturadas sem qualquer tratamento.",
  "Excessive Method Length (EML)": "Métodos muito longos e difíceis de manter.",
  "Functions Parentheses on Multiple Lines": "Declarações de funções com parênteses distribuídos de forma inadequada em múltiplas linhas.",
  "Too Many Methods": "Classes com quantidade excessiva de métodos.",
  "Too Many Public Methods (TMPM)": "Classes expondo métodos públicos em excesso.",
  "Unnecessary Code": "Código redundante ou sem utilidade prática.",
  "Unused Formal Parameter": "Parâmetros declarados mas nunca utilizados.",
  "Unused Local Variable": "Variáveis locais declaradas sem uso.",
  "Incorrect Spacing After Commas": "Espaçamento inadequado após vírgulas.",
  "Missing @Return Tag in Comments": "Ausência da anotação @return na documentação.",
  "Too Many Fields": "Classes contendo atributos em excesso.",
  "Unused Private Field": "Atributos privados nunca utilizados.",
  "Unused Private Method": "Métodos privados nunca chamados.",
  "Incorrect String Manipulation": "Manipulação inadequada ou ineficiente de strings.",
  "Inefficient Logic": "Lógica implementada de forma desnecessariamente ineficiente.",
  "Incorrect Variable Naming": "Variáveis com nomes pouco claros ou inconsistentes.",
  "Class Complexity": "Classes excessivamente complexas e difíceis de compreender.",
  "Class Length": "Classes muito extensas, concentrando muitas responsabilidades.",
  "Clone Implementations": "Implementações muito semelhantes replicadas em diferentes locais.",
  "Excessive Parameter List (EPL)": "Métodos com parâmetros em excesso.",
  "Names Poorly Defined": "Nomes pouco descritivos ou ambíguos.",
  "Overloaded Classes": "Classes sobrecarregadas com múltiplas responsabilidades.",
  "High Method Complexity (HMC)": "Métodos com alta complexidade lógica.",
  "Confusing Use Of Comments": "Comentários contraditórios, excessivos ou pouco claros.",
  "Code Fragmentation": "Código excessivamente fragmentado, dificultando navegação e entendimento.",
  "Excessive Inline Code": "Uso exagerado de código inline, prejudicando organização.",
  "Misaligned Logic Blocks": "Blocos lógicos mal estruturados ou desalinhados semanticamente.",
  "Missing Function Comments": "Funções sem documentação ou comentários explicativos.",
  "Excessive Number of Children (ENOC)": "Classes com número excessivo de subclasses.",
  "High Coupling (HC)": "Forte dependência entre classes ou módulos.",
  "Parameter List": "[LEGADO — migrar para 'Excessive Parameter List (EPL)'] Lista de parâmetros extensa e difícil de gerenciar.",
  "Excessive Subclassing": "Uso excessivo de herança e subclasses.",
  "Unclear Loop Logic": "Lógica de repetição pouco intuitiva ou difícil de interpretar.",
  "Poorly Organized Classes": "Classes mal estruturadas ou com baixa coesão interna.",
  "Boolean Parameter": "Parâmetro booleano que sinaliza responsabilidades múltiplas — geralmente indica necessidade de extrair método ou usar polimorfismo.",
  "Commented Out Code": "Código comentado deixado no arquivo, gerando ruído e dúvida sobre a intenção real.",
  "Complex Method": "[LEGADO — migrar para 'High Method Complexity (HMC)'] Método com lógica complexa que dificulta leitura, teste e manutenção.",
  "Dead Code": "Código alcançável que nunca é executado, por inviabilidade lógica ou regra de negócio obsoleta.",
  "Deep Hierarchy": "[LEGADO — migrar para 'Excessive Subclassing'] Cadeia de herança profunda demais, dificultando rastreabilidade e manutenção.",
  "Deep Nesting": "Aninhamento excessivo de blocos (if/for/while dentro de if/for/while) que prejudica legibilidade.",
  "Duplicated Code": "[LEGADO — migrar para 'Duplicate Code'] Trechos quase idênticos espalhados pelo código.",
  "Empty Block": "[LEGADO — migrar para 'Empty Blocks'] Bloco de código vazio, possivelmente esquecido ou marcador de TODO não implementado.",
  "Feature Envy": "Método que acessa dados de outra classe com frequência maior do que da própria — sugere má distribuição de responsabilidades.",
  "God Class": "Classe que concentra grande parte da lógica do sistema, violando coesão e princípio da responsabilidade única.",
  "Large Class": "[LEGADO — migrar para 'Class Length'] Classe muito grande, concentrando responsabilidades demais.",
  "Long Method": "[LEGADO — migrar para 'Excessive Method Length (EML)'] Método demasiadamente longo.",
  "Long Parameter List": "[LEGADO — migrar para 'Excessive Parameter List (EPL)'] Lista de parâmetros longa.",
  "Null Safety": "Uso de null inseguro: acessos potencialmente nulos sem checagem prévia.",
  "Poor Naming": "[LEGADO — migrar para 'Names Poorly Defined' (qualquer identificador) ou 'Incorrect Variable Naming' (variáveis)] Nomes pouco descritivos ou inconsistentes.",
  "Static Coupling": "Acoplamento via chamadas estáticas que dificulta testes e substituição de dependências.",
  "Type Inconsistency": "Inconsistências de tipo: union types incorretos, casts equivocados ou mismatches detectados por análise estática.",
  "Unnecessary Else": "Cláusula else redundante após early return ou throw — pode ser simplificada.",
  "Useless Override": "Sobrescrita de método que apenas chama super sem agregar comportamento.",
  "Other": "Categoria genérica para code smells fora das categorias listadas. Use observações para detalhar."
};

const KNOWN_SMELL_SET = new Set(SMELL_CATEGORIES);
function escAttr(s) {
  return String(s).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
function smellTooltip(cat) {
  const desc = SMELL_DESCRIPTIONS[cat] || 'Sem descrição disponível para esta categoria.';
  return escAttr(`${cat} — ${desc}`);
}
function legacyBadge(cat) {
  return KNOWN_SMELL_SET.has(cat) ? '' : ' <span style="font-size:.6rem;color:var(--yellow);margin-left:4px" title="Categoria legada / fora da lista oficial">(legado)</span>';
}
function helpIcon(cat) {
  return `<span class="smell-help" title="${smellTooltip(cat)}">ⓘ</span>`;
}

function renderSmellChecks(sid, selected, smellCounts, disputedSmells) {
  const smells = Array.isArray(selected) ? selected : [];
  const counts = smellCounts || {};
  const disputed = new Set(disputedSmells || []);
  const consolidated = Object.keys(counts).filter(s => !disputed.has(s)); // atingiram threshold

  // Categorias selecionadas (de anotações antigas) ou nas contagens que estão
  // fora da lista oficial — preservar marcando como (legado).
  const allSeen = new Set([...smells, ...Object.keys(counts)]);
  const extras = [...allSeen].filter(c => !KNOWN_SMELL_SET.has(c)).sort();
  const fullList = [...extras, ...SMELL_CATEGORIES];

  function mkRow(cat, opts) {
    const checked = smells.includes(cat) ? 'checked' : '';
    const cnt = counts[cat] || 0;
    const tip = smellTooltip(cat);
    const tag = legacyBadge(cat);
    const help = helpIcon(cat);
    const cntHtml = opts && opts.showCount && cnt > 0
      ? `<span class="smell-vote-count ${opts.cntCls || 'consensus'}">${cnt}</span>`
      : '';
    return `<div class="smell-checkbox" data-cat="${cat.toLowerCase()}" data-sid="${sid}" title="${tip}" style="opacity:${opts.opacity ?? 1}">
      <input type="checkbox" value="${cat}" ${checked} onchange="toggleSmell('${sid}','${cat}',this.checked)" style="accent-color:${opts.accent || 'var(--accent)'}">
      <span class="smell-name">${cat}${tag}</span>${cntHtml}${help}
    </div>`;
  }

  const consolidatedHtml = fullList.filter(cat => consolidated.includes(cat))
    .map(cat => mkRow(cat, {showCount: true, cntCls: (counts[cat] >= 2 ? 'consensus' : 'disputed'), accent: 'var(--green)'})).join('');
  const disputedHtml = fullList.filter(cat => disputed.has(cat))
    .map(cat => mkRow(cat, {showCount: true, cntCls: 'disputed', accent: 'var(--yellow)', opacity: .9})).join('');
  const otherHtml = fullList.filter(cat => !counts[cat])
    .map(cat => mkRow(cat, {showCount: false, accent: 'var(--border)', opacity: .6})).join('');

  let html = `<input type="text" class="smell-filter" placeholder="🔎 filtrar (ex.: complex, long, unused…)" oninput="filterSmellList('${sid}', this.value)">`;
  if (consolidatedHtml) html += '<div class="smell-consolidated"><h5>✓ Consolidados (≥2 votos)</h5>' + consolidatedHtml + '</div>';
  if (disputedHtml) html += '<div class="smell-disputed"><h5>⚠ Disputados (&lt;2 votos)</h5>' + disputedHtml + '</div>';
  if (otherHtml && (consolidatedHtml || disputedHtml)) html += '<div style="font-size:.65rem;color:var(--text2);margin-top:6px">Outras categorias:</div>';
  html += otherHtml;
  return html;
}

function filterSmellList(sid, q) {
  q = (q || '').trim().toLowerCase();
  const rows = document.querySelectorAll(`.smell-checkbox[data-sid="${sid}"]`);
  rows.forEach(r => {
    const cat = r.dataset.cat || '';
    r.style.display = (!q || cat.includes(q)) ? '' : 'none';
  });
}

function toggleSmell(sid, cat, checked) {
  if (!decisions[sid]) decisions[sid] = { label: '', smells: [], notes: '' };
  if (!decisions[sid].smells) decisions[sid].smells = [];
  if (checked) {
    if (!decisions[sid].smells.includes(cat)) decisions[sid].smells.push(cat);
  } else {
    decisions[sid].smells = decisions[sid].smells.filter(s => s !== cat);
  }
  decisions[sid].decided_at = new Date().toISOString();
  localStorage.setItem(STORAGE_KEY, JSON.stringify(decisions));
}

function escapeHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function renderCodeWithLineNumbers(code, startLine, snippetId, highlightLines) {
  const hlIdx = {};
  if (highlightLines) highlightLines.forEach(h => {
    const cls = {'high':'hl-red','critical':'hl-red','warning':'hl-yellow','info':'hl-blue'}[h.severity] || 'hl-yellow';
    hlIdx[h.idx] = cls;
  });
  // Usa raw code para garantir 1:1 com índices
  const rawLines = code.split('\\n');
  const dig = String(startLine + rawLines.length).length;
  return rawLines.map((raw, i) => {
    const n = String(startLine + i).padStart(dig, ' ');
    let content;
    try {
      content = hljs.highlight(raw, {language:'php',ignoreIllegals:true}).value;
    } catch(e) {
      content = escapeHtml(raw);
    }
    return `<div class="code-line ${hlIdx[i] || ''}" data-line="${n.trim()}" data-snippet="${snippetId}"><span class="line-number">${n}</span><span class="line-content">${content || ' '}</span></div>`;
  }).join('');
}

function scrollToLineInCase(snippetId, lineNum) {
  const target = document.querySelector(`.code-line[data-snippet="${snippetId}"][data-line="${lineNum}"]`);
  if (target) target.scrollIntoView({behavior:'smooth',block:'center'});
}

function updateProgress() {
  const done = Object.keys(decisions).length;
  const total = CASES.length;
  const labelConflicts = CASES.filter(c => c.conflict_type === 'label' || c.conflict_type === 'both').length;
  const smellConflicts = CASES.filter(c => c.conflict_type === 'smells' || c.conflict_type === 'both').length;
  document.getElementById('progressFill').style.width = `${(done/total)*100}%`;
  document.getElementById('summaryLine').innerHTML =
    `${total} snippets em conflito (${labelConflicts} label, ${smellConflicts} smells) de ${ANNOTATORS.length} anotadores (${ANNOTATORS.map(escapeHtml).join(', ')}). ${done} já revisados.`;

  // Distribuição das decisões finais — atualizada em tempo real
  let smelly = 0, clean = 0;
  for (const sid in decisions) {
    const d = decisions[sid];
    if (!d || !d.label) continue;
    if (d.label === 'smelly') smelly++;
    else if (d.label === 'clean') clean++;
  }
  const pending = total - smelly - clean;
  document.getElementById('decSmelly').textContent = smelly;
  document.getElementById('decClean').textContent = clean;
  document.getElementById('decPending').textContent = pending;
}

function escapeHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function labelClass(l) {
  return l === 'smelly' ? 'badge-smelly' : l === 'potentially_smelly' ? 'badge-potentially' : 'badge-clean';
}

function render() {
  const container = document.getElementById('cases');
  if (CASES.length === 0) {
    container.innerHTML = '<div class="empty-state">Nenhum caso em conflito. 🎉</div>';
    return;
  }
  container.innerHTML = CASES.map(c => {
    const decided = decisions[c.snippet_id];
    const finalLabel = decided ? decided.label : c.label;
    const finalNotes = decided ? (decided.notes || '') : '';

    const votesHtml = ANNOTATORS.map(name => {
      const v = c.votes_per_annotator[name];
      if (!v) return `<div class="vote-row"><div class="vote-header"><span class="vote-name">${escapeHtml(name)}</span><span class="badge" style="background:#2a2a2a;color:#888">não votou</span></div></div>`;
      return `<div class="vote-row">
        <div class="vote-header">
          <span class="vote-name">${escapeHtml(name)}</span>
          <span class="badge ${labelClass(v.label)}">${escapeHtml(v.label)}</span>
        </div>
        ${v.smells && v.smells.length ? `<div class="vote-smells">🏷 ${v.smells.map(escapeHtml).join(', ')}</div>` : ''}
        ${v.notes ? `<div class="vote-notes">"${escapeHtml(v.notes)}"</div>` : ''}
      </div>`;
    }).join('');

    const metricLabels = {
      loc_executable: 'LINHAS EXECUTÁVEIS — código com lógica (exclui comentários/branco)',
      cyclomatic_complexity: 'COMPLEXIDADE CICLOMÁTICA — caminhos independentes (>10 = alta)',
      nesting_depth: 'PROFUNDIDADE DE ANINHAMENTO — nível máximo de estruturas aninhadas',
      halstead_volume: 'VOLUME HALSTEAD — tamanho cognitivo (operadores+operandos únicos)',
      halstead_difficulty: 'DIFICULDADE HALSTEAD — esforço para escrever/compreender',
      halstead_effort: 'ESFORÇO HALSTEAD — volume × dificuldade',
      halstead_bugs: 'BUGS ESTIMADOS — previsão de defeitos (Halstead)',
      num_methods: 'NÚMERO DE MÉTODOS — total de métodos na classe',
      num_parameters: 'NÚMERO DE PARÂMETROS — parâmetros na assinatura',
      num_properties: 'NÚMERO DE PROPRIEDADES — atributos da classe',
      loc_total: 'LOC TOTAL — linhas totais incluindo comentários e branco'
    };
    const metricsHtml = c.metrics ? Object.entries(c.metrics).filter(([k,v]) => v != null && v !== 0).slice(0, 6).map(([k,v]) =>
      `<span class="metric" title="${metricLabels[k] || k}">${escapeHtml(k)}: ${typeof v === 'number' ? Math.round(v*100)/100 : v}</span>`
    ).join('') : '';

    // Smells detectados (das ferramentas) + highlightLines para o código
    const highlightLines = [];
    let smellsToolsHtml = '';
    if (c.smells_detected && c.smells_detected.length > 0) {
      const codeLines = (c.code || '').split('\\n');
      smellsToolsHtml = '<div class="smells-section"><h4>🔍 Smells detectados pelas ferramentas</h4><div>';
      for (const s of c.smells_detected) {
        const idx = s.line ? Math.max(0, s.line - c.start_line) : -1;
        if (idx >= 0 && idx < codeLines.length) highlightLines.push({idx, severity: s.severity || 'warning'});
        const lineLink = s.line ? `<span class="line-link" onclick="event.stopPropagation();scrollToLineInCase('${c.snippet_id}',${s.line})">📍 Linha ${s.line}</span>` : '';
        // Peso da categoria deste smell (quantas ferramentas distintas detectaram a categoria)
        const w = s.category_weight || 1;
        const wClass = `w${Math.min(5, Math.max(1, w))}`;
        const wTitle = `Peso ${w}: ${w} ferramenta${w>1?'s':''} detectaram a categoria "${s.smell_category}"`;
        smellsToolsHtml += `<span class="smell-tag" onclick="${s.line ? `scrollToLineInCase('${c.snippet_id}',${s.line})` : ''}" title="${escapeHtml(s.tool_name + ': ' + (s.message || ''))}">${escapeHtml(s.tool_name)}: ${escapeHtml(s.smell_category)}<span class="weight-badge ${wClass}" title="${escapeHtml(wTitle)}">×${w}</span> ${lineLink}</span> `;
      }
      smellsToolsHtml += '</div>';

      // Box agregado: peso por categoria (ordenado por peso desc)
      const cw = c.category_weights || {};
      const cwEntries = Object.entries(cw).sort((a,b) => b[1].weight - a[1].weight);
      if (cwEntries.length > 0) {
        smellsToolsHtml += '<div class="cat-weights-box"><div style="color:var(--text);margin-bottom:4px"><b>⚖ Peso por categoria</b> <span style="color:var(--text2);font-weight:400">(quantas ferramentas distintas detectaram cada categoria)</span></div>';
        for (const [cat, info] of cwEntries) {
          const wClass = `w${Math.min(5, Math.max(1, info.weight))}`;
          const norm = (info.weight_normalized != null) ? ` <span style="color:var(--text2)">(${(info.weight_normalized*100).toFixed(0)}%)</span>` : '';
          smellsToolsHtml += `<div class="cw-row"><span><b>${escapeHtml(cat)}</b> <span class="cw-tools">[${(info.tools||[]).map(escapeHtml).join(', ')}]</span></span><span><span class="weight-badge ${wClass}">×${info.weight}</span>${norm}</span></div>`;
        }
        smellsToolsHtml += '</div>';
      }
      smellsToolsHtml += '</div>';
    }

    // Banner de tipo de conflito
    const conflictBanners = {
      'label': '⚠ Conflito de label — anotadores divergiram no rótulo',
      'smells': '⚠ Conflito de smells — anotadores concordam no rótulo mas divergem nos smells',
      'both': '⚠ Conflito de label + smells — revisão completa necessária'
    };
    const conflictBannerHtml = c.conflict_type ? `<div class="conflict-banner ${c.conflict_type}">${conflictBanners[c.conflict_type]}</div>` : '';

    return `<div class="snippet-card ${decided ? 'resolved' : ''}" id="card-${c.snippet_id}">
      <h2>
        <span>${escapeHtml(c.snippet_id)}</span>
        <span class="badge badge-type">${escapeHtml(c.snippet_type || '?')}</span>
        <span style="color:var(--text)">${escapeHtml(c.snippet_name || '')}</span>
        ${decided ? '<span class="badge badge-clean">✓ revisado</span>' : ''}
      </h2>
      <div class="file-path">${escapeHtml(c.file_path)} : ${c.start_line}–${c.end_line}</div>
      ${conflictBannerHtml}
      <div class="metrics">${metricsHtml}</div>
      ${smellsToolsHtml}

      <div class="layout">
        <div class="code-block"><div class="code-lines" style="padding:14px;font-family:'JetBrains Mono','Fira Code',monospace;font-size:.78rem">${renderCodeWithLineNumbers(c.code, c.start_line, c.snippet_id, highlightLines)}</div></div>

        <div>
          <div style="font-size:.8rem;color:var(--text2);text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px">Votos dos anotadores</div>
          <div class="votes">${votesHtml}</div>

          <div style="font-size:.8rem;color:var(--text2);text-transform:uppercase;letter-spacing:.5px;margin:16px 0 6px">Decisão final</div>
          <div class="label-picker">
            <button class="label-btn ${finalLabel==='smelly'?'picked':''}" data-l="smelly" onclick="pick('${c.snippet_id}','smelly')">🔴 Smelly</button>
            <button class="label-btn ${finalLabel==='clean'?'picked':''}" data-l="clean" onclick="pick('${c.snippet_id}','clean')">🟢 Clean</button>
          </div>
          <div style="font-size:.8rem;color:var(--text2);text-transform:uppercase;letter-spacing:.5px;margin:14px 0 4px">Categorias de smell</div>
          <div id="smells-${c.snippet_id}" style="max-height:420px;overflow-y:auto;margin-bottom:8px;position:relative;border:1px solid var(--border);border-radius:6px;padding:6px 8px;background:rgba(0,0,0,.18)">${renderSmellChecks(c.snippet_id, decided ? (decided.smells || []) : c.smells, c.smell_counts, c.disputed_smells)}</div>
          <textarea class="notes-input" placeholder="Justificativa do desempate (opcional)..." onchange="setNotes('${c.snippet_id}', this.value)">${escapeHtml(finalNotes)}</textarea>
        </div>
      </div>
    </div>`;
  }).join('');

  updateProgress();
}

function pick(sid, label) {
  const existing = decisions[sid] || {};
  decisions[sid] = {
    label,
    smells: existing.smells || [],
    notes: existing.notes || '',
    decided_at: new Date().toISOString(),
  };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(decisions));
  showToast(`Decisão salva: ${label}`);
  render();
}

function setNotes(sid, value) {
  if (!decisions[sid]) decisions[sid] = { label: null, notes: value };
  else decisions[sid].notes = value;
  decisions[sid].decided_at = new Date().toISOString();
  localStorage.setItem(STORAGE_KEY, JSON.stringify(decisions));
}

function clearDecisions() {
  if (!confirm("Apagar todas as decisões deste desempate?")) return;
  decisions = {};
  localStorage.removeItem(STORAGE_KEY);
  render();
}

function exportFinal() {
  const undecided = CASES.filter(c => !decisions[c.snippet_id]);
  if (undecided.length > 0) {
    if (!confirm(`${undecided.length} casos ainda não foram revisados. Exportar mesmo assim?`)) return;
  }
  const payload = {
    metadata: {
      type: "tiebreak_decisions",
      exported_at: new Date().toISOString(),
      consolidated_source: CONSOLIDATED_BASENAME,
      total_cases: CASES.length,
      decided: Object.keys(decisions).length,
      undecided: undecided.length,
    },
    decisions: decisions,
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], {type:'application/json'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `desempate_${new Date().toISOString().slice(0,10)}.json`;
  a.click();
  showToast("Exportado!");
}

function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 1800);
}

render();
document.getElementById('loadingOverlay').classList.add('hidden');
</script>
</body>
</html>'''

    html_content = template.replace("__CASES__", cases_json)
    html_content = html_content.replace("__ANNOTATORS__", annotators_json)
    html_content = html_content.replace("__CONSOLIDATED_BASENAME__", consolidated_basename)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)


if __name__ == "__main__":
    main()
