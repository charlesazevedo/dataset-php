#!/usr/bin/env python3
"""
Fase 4 — Preparação da Interface de Anotação
=============================================
Integra dados das Fases 2 e 3 e gera uma interface HTML autocontida
para anotação manual de code smells por especialistas.

Uso:
  python3 fase4_preparar_interface.py [--snippets FASE2_JSON] [--labels FASE3_JSON] [--output DIR]

A interface gerada é um arquivo HTML único que:
  - Exibe cada snippet com syntax highlighting
  - Mostra métricas calculadas (LOC, CC, Halstead, etc.)
  - Mostra pré-rótulos da análise estática
  - Permite ao anotador confirmar/rejeitar/modificar labels
  - Exporta anotações em JSON ao final
"""
import json
import html
import os
import sys
import argparse
from pathlib import Path
from datetime import datetime


def main():
    parser = argparse.ArgumentParser(description="Fase 4 — Interface de Anotação")
    parser.add_argument("--snippets", help="JSON da Fase 2 (snippets + métricas)")
    parser.add_argument("--labels", help="JSON da Fase 3 (pré-rotulação)")
    parser.add_argument("--output", help="Diretório de saída")
    args = parser.parse_args()

    project_dir = Path(__file__).resolve().parent.parent
    output_dir = Path(args.output) if args.output else project_dir / "output" / "fase4"
    output_dir.mkdir(parents=True, exist_ok=True)

    snippets_file = args.snippets or str(project_dir / "output" / "fase2" / "snippets_com_metricas.json")
    labels_file = args.labels or str(project_dir / "output" / "fase3" / "pre_rotulacao.json")

    # Carregar dados
    print("=" * 60)
    print("  FASE 4 — Preparação da Interface de Anotação")
    print("=" * 60)

    if not os.path.exists(snippets_file):
        print(f"ERRO: Arquivo de snippets não encontrado: {snippets_file}")
        print("Execute as Fases 1-2 primeiro.")
        sys.exit(1)

    if not os.path.exists(labels_file):
        print(f"ERRO: Arquivo de pré-rotulação não encontrado: {labels_file}")
        print("Execute a Fase 3 primeiro.")
        sys.exit(1)

    with open(snippets_file) as f:
        fase2 = json.load(f)
    with open(labels_file) as f:
        fase3 = json.load(f)

    snippets_metrics = {s["snippet_id"]: s for s in fase2["snippets"]}
    snippets_labels = {s["snippet_id"]: s for s in fase3["snippets"]}

    print(f"  Snippets carregados: {len(snippets_metrics)}")
    print(f"  Labels carregados:   {len(snippets_labels)}")

    # Tentar localizar o repo clonado para re-extrair o code exatamente
    # do start_line ao end_line (garantindo alinhamento com smells)
    repo_name = fase2.get("metadata", {}).get("repo", "").replace("/", "_")
    repo_dir = project_dir / "repos" / repo_name
    if not repo_dir.exists():
        # fallback: procurar qualquer subdir de repos/
        repos_root = project_dir / "repos"
        if repos_root.exists():
            subs = [p for p in repos_root.iterdir() if p.is_dir()]
            repo_dir = subs[0] if subs else None
    file_cache = {}
    realigned = 0

    def reextract_code(file_path, start_line, end_line):
        """Lê o arquivo do repo e retorna as linhas start_line..end_line (1-indexed, inclusive)."""
        nonlocal realigned
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
        realigned += 1
        return "\n".join(lines[start_line - 1:end_line])

    # Construir dados integrados para o JavaScript da interface
    integrated_data = []
    for sid, metrics in snippets_metrics.items():
        label_info = snippets_labels.get(sid, {})
        # Re-extrair code do arquivo real para garantir alinhamento de linhas
        precise_code = reextract_code(metrics.get("file_path", ""), metrics.get("start_line"), metrics.get("end_line"))
        integrated_data.append({
            "snippet_id": sid,
            "file_path": metrics.get("file_path", ""),
            "snippet_type": metrics.get("snippet_type", ""),
            "snippet_name": metrics.get("snippet_name", ""),
            "start_line": metrics.get("start_line", 0),
            "end_line": metrics.get("end_line", 0),
            "code": precise_code if precise_code is not None else metrics.get("code", ""),
            "metrics": {
                "loc_total": metrics.get("loc_total", 0),
                "loc_executable": metrics.get("loc_executable", 0),
                "cyclomatic_complexity": metrics.get("cyclomatic_complexity", 0),
                "nesting_depth": metrics.get("nesting_depth", 0),
                "halstead_volume": metrics.get("halstead_volume", 0),
                "halstead_difficulty": metrics.get("halstead_difficulty", 0),
                "halstead_effort": metrics.get("halstead_effort", 0),
                "halstead_bugs": metrics.get("halstead_bugs", 0),
                "num_methods": metrics.get("num_methods"),
                "num_parameters": metrics.get("num_parameters"),
            },
            "pre_label": label_info.get("pre_label", "unknown"),
            "pre_label_confidence": label_info.get("pre_label_confidence", ""),
            "smells_detected": label_info.get("code_smells_detected", []),
            "total_smells_count": label_info.get("total_smells_count", 0),
            "unique_smell_categories": label_info.get("unique_smell_categories", []),
            "tools_that_detected": label_info.get("tools_that_detected", []),
            "tool_agreement_count": label_info.get("tool_agreement_count", 0),
            "category_weights": label_info.get("category_weights", {}),
            "max_category_weight": label_info.get("max_category_weight", 0),
        })

    # Estatísticas para o cabeçalho
    total = len(integrated_data)
    smelly = sum(1 for d in integrated_data if d["pre_label"] == "smelly")
    potentially = sum(1 for d in integrated_data if d["pre_label"] == "potentially_smelly")
    clean = sum(1 for d in integrated_data if d["pre_label"] == "clean")

    repo_name = fase2.get("metadata", {}).get("repo", "unknown")

    if realigned > 0:
        print(f"  Code re-extraído do arquivo: {realigned}/{len(snippets_metrics)} snippets (garante alinhamento com smells)")

    # Gerar HTML
    print("\n  Gerando interface HTML...")

    html_content = generate_annotation_html(integrated_data, repo_name, total, smelly, potentially, clean)

    output_file = output_dir / "interface_anotacao.html"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_content)

    # Salvar dados integrados como JSON (backup para uso programático)
    data_file = output_dir / "dados_integrados.json"
    with open(data_file, "w", encoding="utf-8") as f:
        json.dump({
            "metadata": {
                "phase": "Fase 4",
                "repo": repo_name,
                "generation_date": datetime.now().isoformat(),
                "total_snippets": total,
                "distribution": {"smelly": smelly, "potentially_smelly": potentially, "clean": clean},
            },
            "snippets": integrated_data,
        }, f, indent=2, ensure_ascii=False)

    # Gerar index.html (landing page) se não existir
    index_file = output_dir / "index.html"
    if not index_file.exists():
        with open(index_file, "w", encoding="utf-8") as f:
            f.write(generate_index_html())
        print(f"  ✓ index.html gerado:  {index_file}")
    else:
        print(f"  ✓ index.html já existe (preservado): {index_file}")

    print(f"\n  ✓ Interface salva em: {output_file}")
    print(f"  ✓ Dados integrados:  {data_file}")
    print(f"\n  Para usar a interface, abra o arquivo HTML no navegador:")
    print(f"    open {output_file}    # macOS")
    print(f"    xdg-open {output_file}    # Linux")
    print(f"    start {output_file}    # Windows")
    print(f"\n  ✓ Fase 4 concluída!")


def generate_index_html():
    """Gera a landing page (index.html) da Fase 4.

    A página mostra dois cartões:
      - Interface de Anotação (sempre disponível após Fase 4)
      - Revisão de Desempate (disponível só se revisao_desempate.html existir)
    """
    return '''<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Pipeline — Dataset de Code Smells PHP</title>
<style>
:root{--bg:#0f1117;--card:#1a1d27;--border:#2d3248;--accent:#e74c3c;--green:#00b894;--text:#e0e0e0;--text2:#a0a4b8}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh}
.container{text-align:center;max-width:500px;padding:40px}
h1{font-size:1.4rem;margin-bottom:8px}
h1 span{color:var(--accent)}
.sub{color:var(--text2);font-size:.85rem;margin-bottom:40px}
.card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:24px;margin-bottom:16px;text-align:left;transition:border-color .2s;display:block;text-decoration:none;color:inherit}
.card:hover{border-color:var(--accent)}
.card-title{font-size:1rem;font-weight:600;margin-bottom:4px}
.card-desc{font-size:.78rem;color:var(--text2)}
.card-icon{font-size:1.3rem;margin-right:8px}
.badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:.65rem;margin-left:8px}
.badge-ok{background:#1b4a3a;color:var(--green)}
.badge-off{background:#2a2a2a;color:var(--text2)}
.card.disabled{pointer-events:none;opacity:.5;cursor:not-allowed}
.footer{color:var(--text2);font-size:.72rem;margin-top:32px}
</style>
</head>
<body>
<div class="container">
  <h1>Dataset de <span>Code Smells</span> PHP</h1>
  <div class="sub">Pipeline de anotação &mdash; Fase 4</div>

  <a class="card" href="interface_anotacao.html">
    <div class="card-title"><span class="card-icon">🏷️</span>Interface de Anotação<span class="badge badge-ok">disponível</span></div>
    <div class="card-desc">Análise manual dos snippets: revisar código, métricas e pré-rótulos. Exportar JSON/CSV ao final.</div>
  </a>

  <a class="card disabled" id="cardRevisao">
    <div class="card-title"><span class="card-icon">⚖️</span>Revisão de Desempate<span class="badge badge-off" id="badgeRevisao">verificando...</span></div>
    <div class="card-desc">Resolver divergências entre anotadores. Só aparece após a consolidação detectar empates.</div>
  </a>

  <div class="footer">
    Pipeline de doutorado &mdash; datasets/php-codesmell-dataset
  </div>
</div>
<script>
fetch('revisao_desempate.html', {method:'HEAD'}).then(r => {
  const badge = document.getElementById('badgeRevisao');
  const card  = document.getElementById('cardRevisao');
  if (r.ok) {
    badge.textContent = 'disponível';
    badge.className = 'badge badge-ok';
    card.href = 'revisao_desempate.html';
    card.classList.remove('disabled');
  } else {
    badge.textContent = 'indisponível';
    badge.className = 'badge badge-off';
    card.classList.add('disabled');
  }
}).catch(() => {
  document.getElementById('badgeRevisao').textContent = 'indisponível';
});
</script>
</body>
</html>
'''


def generate_annotation_html(data, repo_name, total, smelly, potentially, clean):
    """Gera o HTML completo da interface de anotação."""
    data_json = json.dumps(data, ensure_ascii=False)

    template = '''<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Fase 4 — Anotação de Code Smells</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/languages/php.min.js"></script>
<style>
:root{--bg:#0f1117;--card:#1a1d27;--border:#2d3248;--accent:#e74c3c;--green:#00b894;--yellow:#fdcb6e;--red:#e17055;--text:#e0e0e0;--text2:#a0a4b8}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif;line-height:1.5}
.header{background:linear-gradient(135deg,#1a1d27,#4a1010);border-bottom:1px solid var(--border);padding:16px 24px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100}
.header h1{font-size:1.2rem;font-weight:600;color:#fff}
.header h1 span{color:var(--accent)}
.stats{display:flex;gap:12px;font-size:.8rem}
.stat{background:rgba(255,255,255,.06);padding:4px 12px;border-radius:6px}
.main{display:grid;grid-template-columns:1fr 380px;height:calc(100vh - 56px)}
.left{overflow-y:auto;padding:20px 24px;border-right:1px solid var(--border)}
.right{overflow:hidden;padding:20px;background:#14161e;display:flex;flex-direction:column;min-height:0}
.right > h3{flex:0 0 auto;margin-top:0}
.annotation-form{flex:1 1 auto;display:flex;flex-direction:column;min-height:0;overflow:hidden}
.form-top{flex:0 0 auto}
.form-smells{flex:1 1 auto;display:flex;flex-direction:column;min-height:0;margin-bottom:0}
.form-smells > label{flex:0 0 auto;display:flex;align-items:center;gap:6px}
.smell-filter{flex:0 0 auto;margin:6px 0 8px;width:100%;background:var(--card);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:6px 10px;font-size:.82rem}
#smellChecks{flex:1 1 auto;overflow-y:auto;min-height:140px;border:1px solid var(--border);border-radius:6px;padding:6px 10px;background:rgba(0,0,0,.18);max-height:none!important}
#smellChecks .smell-checkbox.hidden{display:none}
.form-bottom{flex:0 0 auto;padding-top:12px;margin-top:12px;border-top:1px solid var(--border);background:#14161e}
.form-bottom label{display:block;font-size:.82rem;margin-bottom:4px;color:var(--text2)}
.annotation-form .form-bottom textarea{width:100%;background:var(--card);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:8px;margin-bottom:10px;font-size:.85rem;min-height:60px;max-height:140px;resize:vertical}
.nav-bar{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:16px;flex-wrap:wrap}
.btn{padding:7px 16px;border:1px solid var(--border);background:var(--card);color:var(--text);border-radius:6px;cursor:pointer;font-size:.82rem}
.btn:hover{border-color:var(--accent);color:#fff}
.btn-primary{background:var(--accent);border-color:var(--accent);color:#fff}
.btn-success{background:var(--green);border-color:var(--green);color:#fff}
.snippet-info{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}
.badge{padding:3px 10px;border-radius:4px;font-size:.75rem;font-weight:600}
.badge-clean{background:#1b4a3a;color:#00b894}
.badge-potentially{background:#4a3a1b;color:#fdcb6e}
.badge-smelly{background:#4a1b1b;color:#e17055}
.file-path{color:var(--text2);font-size:.82rem;margin-bottom:6px}
.code-container{background:#0d1117;border:1px solid var(--border);border-radius:8px;overflow:hidden;margin-bottom:16px}
.code-container pre{margin:0;padding:12px;overflow-x:auto;font-size:.82rem;line-height:1.6;max-height:50vh}
.code-container code{font-family:'JetBrains Mono','Fira Code',monospace!important}
.code-line{display:flex;line-height:1.6}
.code-line:nth-child(odd){background:rgba(255,255,255,.01)}
.line-number{min-width:3.2em;text-align:right;padding-right:12px;color:#4a5568;user-select:none;border-right:1px solid #1e2430;margin-right:12px}
.line-content{white-space:pre}
.code-line.hl-red{background:rgba(225,112,85,.15)!important}
.code-line.hl-yellow{background:rgba(253,203,110,.12)!important}
.code-line.hl-blue{background:rgba(108,92,231,.12)!important}
.smell-tag{display:inline-block;padding:2px 8px;border-radius:4px;font-size:.72rem;margin:2px;background:rgba(225,112,85,.15);color:var(--red);cursor:pointer;text-decoration:none}
.smell-tag:hover{filter:brightness(1.3)}
.weight-badge{display:inline-block;margin-left:4px;padding:0 6px;border-radius:8px;font-size:.66rem;font-weight:700;background:rgba(255,255,255,.12);color:#fff;vertical-align:middle}
.weight-badge.w1{background:#3a4858;color:#cfd6e0}
.weight-badge.w2{background:#7a5a20;color:#fde7a7}
.weight-badge.w3{background:#a04020;color:#ffe0d0}
.weight-badge.w4{background:#8b1e1e;color:#fff}
.weight-badge.w5{background:#601020;color:#fff;box-shadow:0 0 0 1px #ff5050 inset}
.cat-weights-box{background:var(--card);border:1px solid var(--border);border-radius:6px;padding:8px 10px;margin-top:8px;font-size:.78rem}
.cat-weights-box .cw-row{display:flex;justify-content:space-between;align-items:center;padding:2px 0;color:var(--text2)}
.cat-weights-box .cw-row b{color:var(--text)}
.cat-weights-box .cw-tools{font-size:.7rem;color:var(--text2);font-style:italic}
.delta{display:inline-block;margin-left:4px;font-size:.7rem;font-weight:700;padding:0 5px;border-radius:3px;background:rgba(255,255,255,.08);color:var(--text2);min-width:2em;text-align:center;transition:background .2s,color .2s}
.delta.zero{background:rgba(255,255,255,.05);color:#6b7080}
.delta.up{background:rgba(0,184,148,.22);color:#5be3b6}
.delta.down{background:rgba(225,112,85,.22);color:#ff9b81}
.stat .now{font-size:.7rem;color:var(--text2);margin-left:2px;font-weight:400}
.metrics-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px;margin-bottom:16px}
.metric-card{background:var(--card);border:1px solid var(--border);border-radius:6px;padding:10px 12px}
.metric-card .label{font-size:.7rem;color:var(--text2);text-transform:uppercase;letter-spacing:.5px}
.metric-card .value{font-size:1.1rem;font-weight:700;margin-top:2px}
.smell-tag{display:inline-block;padding:2px 8px;border-radius:4px;font-size:.72rem;margin:2px;background:rgba(225,112,85,.15);color:var(--red)}
h3{font-size:.95rem;margin:16px 0 8px;color:var(--text2)}
.annotation-form{margin-top:16px}
.annotation-form label{display:block;font-size:.82rem;margin-bottom:4px;color:var(--text2)}
.annotation-form select,.annotation-form textarea{width:100%;background:var(--card);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:8px;margin-bottom:12px;font-size:.85rem}
.annotation-form textarea{min-height:80px;resize:vertical}
.smell-checkbox{display:flex;align-items:center;gap:6px;padding:4px 0;font-size:.82rem;cursor:default}
.smell-checkbox input{accent-color:var(--accent);cursor:pointer;flex:0 0 auto}
.smell-checkbox .smell-name{flex:1 1 auto;line-height:1.25;cursor:default}
.smell-checkbox .smell-help{flex:0 0 auto;font-size:.78rem;color:var(--text2);width:18px;height:18px;display:inline-flex;align-items:center;justify-content:center;border-radius:50%;border:1px solid var(--border);cursor:help;transition:all .15s}
.smell-checkbox:hover{background:rgba(255,255,255,.03);border-radius:4px}
.smell-checkbox:hover .smell-help{color:var(--accent);border-color:var(--accent)}
.progress-bar{width:100%;height:4px;background:var(--card);border-radius:2px;overflow:hidden;margin-top:8px}
.progress-fill{height:100%;background:var(--accent);transition:width .3s}
.loading-overlay{position:fixed;top:0;left:0;width:100%;height:100%;background:var(--bg);display:flex;flex-direction:column;align-items:center;justify-content:center;z-index:9999;transition:opacity .4s}
.loading-overlay.hidden{opacity:0;pointer-events:none}
.spinner{width:48px;height:48px;border:4px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:spin .8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.loading-text{color:var(--text2);font-size:.9rem;margin-top:16px}
.menu-wrap{position:relative;display:inline-block}
.menu-panel{display:none;position:absolute;right:0;top:calc(100% + 6px);min-width:340px;background:var(--card);border:1px solid var(--border);border-radius:8px;box-shadow:0 8px 24px rgba(0,0,0,.5);z-index:200;padding:6px;text-align:left}
.menu-panel.open{display:block}
.menu-group-title{font-size:.65rem;text-transform:uppercase;letter-spacing:.6px;color:var(--text2);padding:8px 10px 4px;font-weight:700}
.menu-item{display:block;width:100%;text-align:left;padding:8px 10px;background:transparent;border:0;color:var(--text);border-radius:6px;cursor:pointer;font-family:inherit;font-size:.82rem;line-height:1.35;transition:background .12s}
.menu-item:hover{background:rgba(255,255,255,.06)}
.menu-item .mi-title{font-weight:600;display:block;margin-bottom:2px}
.menu-item .mi-desc{font-size:.72rem;color:var(--text2);display:block}
.menu-item.danger:hover{background:rgba(231,76,60,.12)}
.menu-item.danger .mi-title{color:var(--red)}
.menu-divider{height:1px;background:var(--border);margin:4px 0}
.ann-warning{display:none;background:rgba(225,112,85,.12);border:1px solid var(--red);color:var(--red);font-size:.78rem;padding:8px 10px;border-radius:6px;margin-bottom:10px}
.smell-required{font-size:.7rem;color:var(--red);margin-left:6px}
.smell-required.ok{color:var(--green)}
#smellChecks.invalid{border:1px solid var(--red);border-radius:6px;padding:4px;background:rgba(225,112,85,.05)}
</style>
</head>
<body>

<div class="loading-overlay" id="loadingOverlay">
  <div class="spinner"></div>
  <div class="loading-text">Carregando {{total}} snippets...</div>
</div>

<div class="header">
  <h1>Fase 4 — <span>Anotação de Code Smells</span></h1>
  <div class="stats">
    <a href="index.html" class="btn" style="text-decoration:none;margin-right:8px">🏚️ Início</a>
    <span class="stat">📦 <span id="statRepo">{{repo_name}}</span></span>
    <span class="stat">Total: <b id="statTotal">{{total}}</b></span>
    <span class="stat" style="color:var(--red)" title="Pré-rótulo da Fase 3 — base inicial. O delta (▲/▼) ao lado mostra a variação após suas anotações.">Smelly: <b id="statSmelly">{{smelly}}</b><span class="delta zero" id="deltaSmelly">=0</span></span>
    <span class="stat" style="color:var(--yellow)" title="Snippets ambíguos da Fase 3 ainda não decididos. Conforme você anota, este número cai (▼) pois cada 'potencial' vira smelly ou clean.">Potencial: <b id="statPot">{{potentially}}</b><span class="delta zero" id="deltaPot">=0</span></span>
    <span class="stat" style="color:var(--green)" title="Pré-rótulo da Fase 3 — base inicial. O delta (▲/▼) ao lado mostra a variação após suas anotações.">Clean: <b id="statClean">{{clean}}</b><span class="delta zero" id="deltaClean">=0</span></span>
    <span class="stat">Anotados: <b id="statAnnotated">0</b>/<span id="statTotalRef">{{total}}</span></span>
  </div>
</div>

<div class="main">
  <div class="left" id="codePanel">
    <div class="nav-bar">
      <div>
        <button class="btn" onclick="prevSnippet()">← Anterior</button>
        <input type="number" id="pageInput" min="1" step="1" onchange="goToPage()" onkeydown="if(event.key==='Enter')goToPage()" style="width:60px;background:var(--card);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:6px 8px;font-size:.82rem;text-align:center;appearance:textfield" title="Ir para página">
        <span style="color:var(--text2);font-size:.85rem;margin:0 4px">/ <b id="navTotal">0</b></span>
        <button class="btn" onclick="nextSnippet()">Próximo →</button>
      </div>
      <div>
        <select id="filterSelect" onchange="applyFilter()" style="background:var(--card);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:6px">
          <option value="all">Todos</option>
          <option value="smelly">Smelly</option>
          <option value="potentially_smelly">Potencialmente Smelly</option>
          <option value="clean">Clean</option>
          <option value="unannotated">Não anotados</option>
        </select>
        <div class="menu-wrap">
          <button class="btn btn-success" id="actionsBtn" onclick="toggleMenu(event)">⚙ Ações ▾</button>
          <div class="menu-panel" id="actionsMenu" onclick="event.stopPropagation()">
            <div class="menu-group-title">Anotações</div>
            <button class="menu-item" onclick="closeMenu();exportAnnotations()">
              <span class="mi-title">📥 Exportar anotações (JSON)</span>
              <span class="mi-desc">Salva apenas suas anotações em JSON — use para enviar a outro anotador ou consolidar via script.</span>
            </button>
            <button class="menu-item" onclick="closeMenu();exportAnnotationsCSV()">
              <span class="mi-title">📊 Exportar anotações (CSV)</span>
              <span class="mi-desc">Planilha pronta para análise no Excel/Pandas. Inclui label, smells e observações.</span>
            </button>
            <button class="menu-item" onclick="closeMenu();document.getElementById('importFile').click()">
              <span class="mi-title">📤 Importar anotações</span>
              <span class="mi-desc">Carrega um JSON de anotações e <b>mescla</b> com as atuais (mantém snippets).</span>
            </button>

            <div class="menu-divider"></div>
            <div class="menu-group-title">Pacote completo</div>
            <button class="menu-item" onclick="closeMenu();exportAll()">
              <span class="mi-title">📦 Exportar pacote completo</span>
              <span class="mi-desc">Snippets + métricas + pré-rótulos + anotações em um único JSON. Ideal para compartilhar entre máquinas.</span>
            </button>
            <button class="menu-item" onclick="closeMenu();document.getElementById('importAllFile').click()">
              <span class="mi-title">📦 Importar pacote completo</span>
              <span class="mi-desc"><b>Substitui</b> os snippets e anotações desta sessão pelos do arquivo. Útil para abrir outro repositório sem rodar o pipeline.</span>
            </button>

            <div class="menu-divider"></div>
            <div class="menu-group-title">Manutenção</div>
            <button class="menu-item danger" onclick="closeMenu();clearCache()">
              <span class="mi-title">🗑️ Limpar anotações deste navegador</span>
              <span class="mi-desc">Apaga as anotações do repositório atual armazenadas no <i>localStorage</i>. Não afeta arquivos já exportados.</span>
            </button>
          </div>
        </div>
        <input type="file" id="importFile" style="display:none" onchange="importAnnotations(event)" accept=".json">
        <input type="file" id="importAllFile" style="display:none" onchange="importAll(event)" accept=".json">
      </div>
    </div>
    <div id="snippetDisplay">Carregando...</div>
    <div class="progress-bar"><div class="progress-fill" id="progressFill"></div></div>
  </div>

  <div class="right" id="annotationPanel">
    <h3>🏷 Anotação</h3>
    <div class="annotation-form" id="annotationForm">
    </div>
  </div>
</div>

<script>
let DATA = __DATA_JSON__;
let REPO_NAME = "__REPO_NAME__";
let STORAGE_KEY = `codesmell_annotations_${REPO_NAME.replace('/','_')}`;
const FULL_STORAGE_KEY = "codesmell_full_dataset";

let annotations = {};
let currentIndex = 0;
let filteredIndices = DATA.map((_,i) => i);

// Carregar do localStorage ao iniciar
const cached = localStorage.getItem(STORAGE_KEY);
if (cached) {
  try {
    annotations = JSON.parse(cached);
    console.log(`Carregadas ${Object.keys(annotations).length} anotações do cache local.`);
  } catch(e) { console.error("Erro ao carregar cache:", e); }
}

function renderCodeWithLineNumbers(code, startLine, highlightLines) {
  const hlIdx = {};
  if (highlightLines) highlightLines.forEach(h => {
    const cls = {'high':'hl-red','critical':'hl-red','warning':'hl-yellow','info':'hl-blue'}[h.severity] || 'hl-yellow';
    hlIdx[h.idx] = cls;
  });
  // Split do código raw (não do highlighted) — garante 1:1 entre linhas e índices
  const rawLines = code.split('\\n');
  const dig = String(startLine + rawLines.length).length;
  return rawLines.map((raw, i) => {
    const n = String(startLine + i).padStart(dig, ' ');
    // Aplica highlight.js em cada linha individualmente; fallback para escape simples
    let content;
    try {
      content = hljs.highlight(raw, {language:'php',ignoreIllegals:true}).value;
    } catch(e) {
      content = raw.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    }
    return `<div class="code-line ${hlIdx[i] || ''}" data-line="${n.trim()}"><span class="line-number">${n}</span><span class="line-content">${content || ' '}</span></div>`;
  }).join('');
}

function scrollToLine(snippetId, lineNum) {
  const container = document.querySelector('#snippetDisplay .code-lines');
  if (!container) return;
  const target = container.querySelector(`.code-line[data-line="${lineNum}"]`);
  if (target) target.scrollIntoView({behavior:'smooth',block:'center'});
}
let currentSnippetStartLine = 0;

// Lista oficial de categorias da metodologia da pesquisa, deduplicada.
// "Other" fica sempre no fim como fallback. "God Class" mantido por ser termo
// clássico de Fowler. Categorias migradas (ex.: Long Method → EML) ainda
// aparecem no topo como (legado) se houver anotação salva no localStorage.
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

// Descrições por categoria — usadas como tooltip (title) em cada checkbox.
// Texto da metodologia da pesquisa para as 39 categorias oficiais;
// para as categorias legadas (não-oficiais), descrição equivalente em pt-BR.
const SMELL_DESCRIPTIONS = {
  // ── Lista oficial da metodologia ──────────────────────────────────────
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

  // ── Categorias legadas (vinham dos pré-rótulos automáticos da Fase 3) ──
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

// Baseline da Fase 3 — recalculada a partir do DATA atual (e atualizada quando
// um pacote é importado via "Importar pacote completo").
let INITIAL_DIST = {smelly: 0, potentially_smelly: 0, clean: 0};
function recomputeInitialDist() {
  INITIAL_DIST = {smelly: 0, potentially_smelly: 0, clean: 0};
  for (const d of DATA) {
    if (d.pre_label in INITIAL_DIST) INITIAL_DIST[d.pre_label] += 1;
  }
}
recomputeInitialDist();

function setDelta(elId, diff) {
  const el = document.getElementById(elId);
  if (!el) return;
  el.classList.remove('zero','up','down');
  if (diff === 0) {
    el.classList.add('zero');
    el.textContent = '=0';
    el.title = 'Sem variação em relação ao pré-rótulo da Fase 3';
  } else if (diff > 0) {
    el.classList.add('up');
    el.textContent = `▲${diff}`;
    el.title = `+${diff} em relação ao pré-rótulo da Fase 3 (suas anotações aumentaram esta categoria)`;
  } else {
    el.classList.add('down');
    el.textContent = `▼${Math.abs(diff)}`;
    el.title = `${diff} em relação ao pré-rótulo da Fase 3 (suas anotações reduziram esta categoria)`;
  }
}

function updateGlobalStats() {
  const annotated = Object.keys(annotations).length;
  document.getElementById('statAnnotated').textContent = annotated;

  // Distribuição "atual": para cada snippet, o label efetivo é
  //   - a anotação do usuário se já anotada (smelly | clean),
  //   - senão o pré-rótulo (smelly | potentially_smelly | clean).
  // Assim a contagem começa idêntica ao inicial e move conforme o anotador decide.
  const cur = {smelly: 0, potentially_smelly: 0, clean: 0};
  for (const d of DATA) {
    const ann = annotations[d.snippet_id];
    let lab;
    if (ann && (ann.label === 'smelly' || ann.label === 'clean')) {
      lab = ann.label;
    } else {
      lab = d.pre_label;
    }
    if (lab in cur) cur[lab] += 1;
  }

  setDelta('deltaSmelly', cur.smelly - INITIAL_DIST.smelly);
  setDelta('deltaPot',    cur.potentially_smelly - INITIAL_DIST.potentially_smelly);
  setDelta('deltaClean',  cur.clean - INITIAL_DIST.clean);
}

function renderSnippet(idx) {
  const realIdx = filteredIndices[idx];
  const d = DATA[realIdx];
  if (!d) return;
  currentIndex = idx;
  updateGlobalStats();

  const labelClass = d.pre_label === 'smelly' ? 'badge-smelly' :
                     d.pre_label === 'potentially_smelly' ? 'badge-potentially' : 'badge-clean';

  let metricsHtml = `<div class="metrics-grid">`;
  const m = d.metrics;
  const metricPairs = [
    ["LOC Exec", m.loc_executable, "Linhas de C\u00f3digo Execut\u00e1veis \u2014 quantidade de linhas com l\u00f3gica (exclui coment\u00e1rios e branco)"],
    ["CC", m.cyclomatic_complexity, "Complexidade Ciclom\u00e1tica \u2014 n\u00famero de caminhos independentes (threshold: >10 = alta)"],
    ["Nesting", m.nesting_depth, "Profundidade de Aninhamento \u2014 n\u00edvel m\u00e1ximo de if/for/while dentro de if/for/while"],
    ["Halstead Vol", Math.round(m.halstead_volume), "Volume de Halstead \u2014 tamanho cognitivo baseado em operadores e operandos \u00fanicos"],
    ["Halstead Diff", m.halstead_difficulty, "Dificuldade de Halstead \u2014 esfor\u00e7o para escrever ou compreender o c\u00f3digo"],
    ["H. Bugs", m.halstead_bugs, "Bugs Estimados \u2014 n\u00famero previsto de defeitos segundo M\u00e9trica de Halstead"],
  ];
  if (m.num_methods != null) metricPairs.push(["Methods", m.num_methods, "N\u00famero de M\u00e9todos \u2014 total de m\u00e9todos na classe"]);
  if (m.num_parameters != null) metricPairs.push(["Params", m.num_parameters, "N\u00famero de Par\u00e2metros \u2014 quantidade de par\u00e2metros na assinatura"]);
  for (const [label, val, tip] of metricPairs) {
    metricsHtml += `<div class="metric-card" title="${tip || ''}"><div class="label">${label}</div><div class="value">${val}</div></div>`;
  }
  metricsHtml += `</div>`;

  const highlightLines = [];  // {idx, severity}
  let smellsHtml = '';
  if (d.smells_detected.length > 0) {
    smellsHtml = '<h3>🔍 Smells Detectados</h3>';
    const codeLines = d.code.split('\\n');
    for (const s of d.smells_detected) {
      const idx = s.line ? Math.max(0, s.line - d.start_line) : -1;
      if (idx >= 0 && idx < codeLines.length) highlightLines.push({idx, severity: s.severity || 'warning'});
      const sevClass = {'high':'hl-red','critical':'hl-red','warning':'hl-yellow','info':'hl-blue'}[s.severity] || 'hl-yellow';
      const lineLink = s.line ? `<a href="javascript:void(0)" onclick="scrollToLine('${d.snippet_id}',${s.line})" style="color:var(--accent);text-decoration:none;font-weight:600">📍 Linha ${s.line}</a>` : '';
      // Peso da categoria deste smell — quantas ferramentas distintas detectaram a categoria.
      const w = s.category_weight || 1;
      const wClass = `w${Math.min(5, Math.max(1, w))}`;
      const wTitle = `Peso ${w}: ${w} ferramenta${w>1?'s':''} detectaram a categoria "${s.smell_category}"`;
      smellsHtml += `<span class="smell-tag" onclick="${s.line ? `scrollToLine('${d.snippet_id}',${s.line})` : ''}" title="${s.tool_name}: ${s.message}">${s.tool_name}: ${s.smell_category}<span class="weight-badge ${wClass}" title="${wTitle}">×${w}</span> ${lineLink}</span> `;
    }

    // Resumo agregado: peso por categoria (deduplicado, ordenado por peso desc).
    const cw = d.category_weights || {};
    const cwEntries = Object.entries(cw).sort((a,b) => b[1].weight - a[1].weight);
    if (cwEntries.length > 0) {
      smellsHtml += '<div class="cat-weights-box"><div style="color:var(--text);margin-bottom:4px"><b>⚖ Peso por categoria</b> <span style="color:var(--text2);font-weight:400">(quantas ferramentas distintas detectaram cada categoria)</span></div>';
      for (const [cat, info] of cwEntries) {
        const wClass = `w${Math.min(5, Math.max(1, info.weight))}`;
        const norm = (info.weight_normalized != null) ? ` <span style="color:var(--text2)">(${(info.weight_normalized*100).toFixed(0)}%)</span>` : '';
        smellsHtml += `<div class="cw-row"><span><b>${cat}</b> <span class="cw-tools">[${(info.tools||[]).join(', ')}]</span></span><span><span class="weight-badge ${wClass}">×${info.weight}</span>${norm}</span></div>`;
      }
      smellsHtml += '</div>';
    }
  }

  currentSnippetStartLine = d.start_line;

  document.getElementById('snippetDisplay').innerHTML = `
    <div class="snippet-info">
      <span class="badge" style="background:#3a1b1b;color:#e8a9a9">${d.snippet_type}</span>
      <span class="badge ${labelClass}">${d.pre_label}</span>
      <span style="font-weight:600">${d.snippet_name}</span>
    </div>
    <div class="file-path">${d.file_path} : ${d.start_line}-${d.end_line}</div>
    ${metricsHtml}
    <div class="code-container"><div class="code-lines" style="padding:12px;font-family:'JetBrains Mono','Fira Code',monospace;font-size:.82rem">${renderCodeWithLineNumbers(d.code, d.start_line, highlightLines)}</div></div>
    ${smellsHtml}
  `;
  document.getElementById('pageInput').value = idx + 1;
  document.getElementById('navTotal').textContent = filteredIndices.length;
  document.getElementById('progressFill').style.width = `${(Object.keys(annotations).length / DATA.length) * 100}%`;
  renderAnnotationForm(d);
}

function renderAnnotationForm(d) {
  const existing = annotations[d.snippet_id] || {};
  // Apenas 'smelly' ou 'clean' são válidos como anotação final.
  // Anotações antigas com 'potentially_smelly' são tratadas como não anotadas (força nova decisão).
  // Pré-seleção a partir do pré-rótulo da Fase 3:
  //   - 'smelly' ou 'clean' → vem pré-selecionado (anotador só confirma).
  //   - 'potentially_smelly' → permanece em '— selecione —' (força decisão).
  const rawLabel = existing.label;
  let selectedLabel = (rawLabel === 'smelly' || rawLabel === 'clean') ? rawLabel : '';
  if (!selectedLabel && (d.pre_label === 'smelly' || d.pre_label === 'clean')) {
    selectedLabel = d.pre_label;
  }
  const selectedSmells = existing.smells || d.unique_smell_categories || [];
  const notes = existing.notes || '';

  // União: categorias já marcadas que não estão na lista padrão (ex.: vindas de
  // anotações antigas ou de pré-rótulos com nomes legados) aparecem no topo,
  // marcadas, pra não sumirem.
  const knownSet = new Set(SMELL_CATEGORIES);
  const extras = (selectedSmells || []).filter(s => !knownSet.has(s));
  const allCats = [...extras, ...SMELL_CATEGORIES];

  // Escapa aspas/<> p/ o atributo title=""
  const escAttr = s => String(s).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

  let smellsRows = '';
  for (const cat of allCats) {
    const checked = selectedSmells.includes(cat) ? 'checked' : '';
    const desc = SMELL_DESCRIPTIONS[cat] || 'Sem descrição disponível para esta categoria.';
    const tip = escAttr(`${cat} — ${desc}`);
    const legacy = !knownSet.has(cat) ? ' <span style="font-size:.65rem;color:var(--yellow);margin-left:4px" title="Categoria legada / fora da lista oficial">(legado)</span>' : '';
    const helpIcon = `<span class="smell-help" title="${tip}">ⓘ</span>`;
    smellsRows += `<div class="smell-checkbox" data-cat="${cat.toLowerCase()}" title="${tip}"><input type="checkbox" value="${cat}" ${checked} onchange="saveAnnotation()"><span class="smell-name">${cat}${legacy}</span>${helpIcon}</div>`;
  }

  const html = `
    <div class="form-top">
      <label>Label Final:</label>
      <select id="annLabel" onchange="saveAnnotation()">
        <option value="" ${selectedLabel===''?'selected':''}>— selecione —</option>
        <option value="smelly" ${selectedLabel==='smelly'?'selected':''}>🔴 Smelly</option>
        <option value="clean" ${selectedLabel==='clean'?'selected':''}>🟢 Clean</option>
      </select>
      <div id="annWarning" class="ann-warning"></div>
    </div>
    <div class="form-smells">
      <label>Categorias de Smell <span id="smellRequired" class="smell-required">(obrigatório se Smelly)</span> <span id="smellCount" style="margin-left:auto;font-size:.7rem;color:var(--text2)">${allCats.length} opções</span></label>
      <input type="text" id="smellFilter" class="smell-filter" placeholder="🔎 filtrar categoria (ex.: complex, long, unused…)" oninput="filterSmellList()">
      <div id="smellChecks">${smellsRows}</div>
    </div>
    <div class="form-bottom">
      <label>Observações:</label>
      <textarea id="annNotes" placeholder="Notas do anotador..." onchange="saveAnnotation()">${notes}</textarea>
      <button class="btn btn-primary" onclick="saveAndNext()" style="width:100%">Salvar & Próximo →</button>
    </div>
  `;
  document.getElementById('annotationForm').innerHTML = html;
}

function filterSmellList() {
  const q = (document.getElementById('smellFilter').value || '').trim().toLowerCase();
  const rows = document.querySelectorAll('#smellChecks .smell-checkbox');
  let visible = 0;
  rows.forEach(r => {
    const cat = r.dataset.cat || '';
    const match = !q || cat.includes(q);
    r.classList.toggle('hidden', !match);
    if (match) visible++;
  });
  const counter = document.getElementById('smellCount');
  if (counter) counter.textContent = q ? `${visible} / ${rows.length}` : `${rows.length} opções`;
}

function saveAnnotation() {
  const realIdx = filteredIndices[currentIndex];
  const d = DATA[realIdx];
  const label = document.getElementById('annLabel').value;
  const checks = document.querySelectorAll('#smellChecks input:checked');
  const smells = Array.from(checks).map(c => c.value);
  const notes = document.getElementById('annNotes').value;

  const warn = document.getElementById('annWarning');
  const smellBox = document.getElementById('smellChecks');
  const smellReq = document.getElementById('smellRequired');

  // Validação 1: label precisa estar selecionado
  if (!label) {
    if (warn) {
      warn.textContent = '⚠ Selecione um label final (Smelly ou Clean) para anotar este snippet.';
      warn.style.display = 'block';
    }
    if (smellBox) smellBox.classList.remove('invalid');
    // Remove eventual anotação parcial salva antes
    if (annotations[d.snippet_id]) {
      delete annotations[d.snippet_id];
      localStorage.setItem(STORAGE_KEY, JSON.stringify(annotations));
      updateGlobalStats();
    }
    return false;
  }

  // Validação 2: smelly exige ≥ 1 categoria
  if (label === 'smelly' && smells.length === 0) {
    if (warn) {
      warn.textContent = '⚠ Snippets marcados como Smelly precisam de pelo menos uma categoria de smell selecionada abaixo.';
      warn.style.display = 'block';
    }
    if (smellBox) smellBox.classList.add('invalid');
    if (smellReq) { smellReq.textContent = '(obrigatório — selecione ao menos uma)'; smellReq.classList.remove('ok'); }
    // Não persiste anotação inválida
    if (annotations[d.snippet_id]) {
      delete annotations[d.snippet_id];
      localStorage.setItem(STORAGE_KEY, JSON.stringify(annotations));
      updateGlobalStats();
    }
    return false;
  }

  // Anotação válida
  if (warn) warn.style.display = 'none';
  if (smellBox) smellBox.classList.remove('invalid');
  if (smellReq) {
    if (label === 'smelly') { smellReq.textContent = '✓ ' + smells.length + ' categoria(s)'; smellReq.classList.add('ok'); }
    else { smellReq.textContent = '(não se aplica a Clean)'; smellReq.classList.remove('ok'); }
  }

  // Clean ⇒ não faz sentido manter smells marcados
  const finalSmells = label === 'clean' ? [] : smells;

  annotations[d.snippet_id] = { label, smells: finalSmells, notes, annotated_at: new Date().toISOString() };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(annotations));
  updateGlobalStats();
  return true;
}

function clearCache() {
  if (confirm("Deseja realmente limpar as anotações SALVAS NO NAVEGADOR para este repositório? Isto não apaga arquivos exportados.")) {
    localStorage.removeItem(STORAGE_KEY);
    annotations = {};
    renderSnippet(currentIndex);
    alert("Cache limpo.");
  }
}

function importAnnotations(event) {
  const file = event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = function(e) {
    try {
      const json = JSON.parse(e.target.result);
      const newAnns = json.annotations || json;
      const count = Object.keys(newAnns).length;
      if (confirm(`Importar ${count} anotações? Isto irá mesclar com as atuais.`)) {
        annotations = { ...annotations, ...newAnns };
        localStorage.setItem(STORAGE_KEY, JSON.stringify(annotations));
        renderSnippet(currentIndex);
        updateGlobalStats();
        alert("Importação concluída!");
      }
    } catch(err) {
      alert("Erro ao ler JSON: " + err.message);
    }
  };
  reader.readAsText(file);
}

function saveAndNext() { if (saveAnnotation()) nextSnippet(); }
function goToPage() {
  const input = document.getElementById('pageInput');
  let page = parseInt(input.value);
  if (isNaN(page) || page < 1) page = 1;
  if (page > filteredIndices.length) page = filteredIndices.length;
  input.value = page;
  renderSnippet(page - 1);
}
function nextSnippet() { if (currentIndex < filteredIndices.length - 1) renderSnippet(currentIndex + 1); }
function prevSnippet() { if (currentIndex > 0) renderSnippet(currentIndex - 1); }

function applyFilter() {
  const filter = document.getElementById('filterSelect').value;
  if (filter === 'all') filteredIndices = DATA.map((_,i) => i);
  else if (filter === 'unannotated') filteredIndices = DATA.map((_,i) => i).filter(i => !annotations[DATA[i].snippet_id]);
  else filteredIndices = DATA.map((_,i) => i).filter(i => DATA[i].pre_label === filter);
  currentIndex = 0;
  if (filteredIndices.length > 0) renderSnippet(0);
  else document.getElementById('snippetDisplay').innerHTML = '<p style="text-align:center;padding:40px;color:var(--text2)">Nenhum snippet neste filtro.</p>';
}

function exportAnnotations() {
  const output = {
    metadata: { exported_at: new Date().toISOString(), total_annotated: Object.keys(annotations).length, total_snippets: DATA.length, repo: REPO_NAME },
    annotations: annotations
  };
  const blob = new Blob([JSON.stringify(output, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `fase4_anotacoes_${REPO_NAME.replace('/','_')}_${new Date().toISOString().slice(0,10)}.json`;
  a.click();
}

function exportAnnotationsCSV() {
  if (Object.keys(annotations).length === 0) {
    alert("Nenhuma anotação para exportar.");
    return;
  }

  const rows = [
    ["snippet_id", "snippet_name", "file_path", "type", "label", "smells", "notes", "annotated_at"]
  ];

  const dataMap = {};
  DATA.forEach(d => dataMap[d.snippet_id] = d);

  for (const [sid, ann] of Object.entries(annotations)) {
    const d = dataMap[sid] || {};
    rows.push([
      sid,
      d.snippet_name || "",
      d.file_path || "",
      d.snippet_type || "",
      ann.label,
      (ann.smells || []).join("; "),
      (ann.notes || "").replace(/\\n/g, " "),
      ann.annotated_at
    ]);
  }

  const csvContent = rows.map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(",")).join("\\n");
  const blob = new Blob(["\\ufeff" + csvContent], { type: 'text/csv;charset=utf-8;' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `fase4_anotacoes_${REPO_NAME.replace('/','_')}_${new Date().toISOString().slice(0,10)}.csv`;
  a.click();
}

function toggleMenu(ev) {
  ev.stopPropagation();
  document.getElementById('actionsMenu').classList.toggle('open');
}
function closeMenu() {
  document.getElementById('actionsMenu').classList.remove('open');
}
document.addEventListener('click', () => closeMenu());
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeMenu(); });

function exportAll() {
  const stats = {
    smelly: DATA.filter(d => d.pre_label === 'smelly').length,
    potentially_smelly: DATA.filter(d => d.pre_label === 'potentially_smelly').length,
    clean: DATA.filter(d => d.pre_label === 'clean').length,
  };
  const output = {
    metadata: {
      phase: "Fase 4 — Pacote Completo",
      exported_at: new Date().toISOString(),
      repo: REPO_NAME,
      total_snippets: DATA.length,
      total_annotated: Object.keys(annotations).length,
      distribution: stats,
      schema_version: 1
    },
    snippets: DATA,
    annotations: annotations
  };
  const blob = new Blob([JSON.stringify(output, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `fase4_pacote_completo_${REPO_NAME.replace('/','_')}_${new Date().toISOString().slice(0,10)}.json`;
  a.click();
}

function importAll(event) {
  const file = event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = function(e) {
    try {
      const json = JSON.parse(e.target.result);
      if (!Array.isArray(json.snippets)) {
        alert("Pacote inválido: campo 'snippets' ausente ou em formato incorreto.\\n" +
              "Use este botão somente para arquivos exportados via 'Exportar Tudo'.\\n" +
              "Para importar somente anotações, use o botão 📤 Importar.");
        event.target.value = '';
        return;
      }
      const newRepo = (json.metadata && json.metadata.repo) || REPO_NAME;
      const snipCount = json.snippets.length;
      const annCount = json.annotations ? Object.keys(json.annotations).length : 0;
      const msg = `Importar pacote completo?\\n\\n` +
                  `  Repo:       ${newRepo}\\n` +
                  `  Snippets:   ${snipCount}\\n` +
                  `  Anotações:  ${annCount}\\n\\n` +
                  `Isto SUBSTITUI os snippets e anotações atualmente em memória.`;
      if (!confirm(msg)) {
        event.target.value = '';
        return;
      }
      DATA = json.snippets;
      annotations = json.annotations || {};
      REPO_NAME = newRepo;
      STORAGE_KEY = `codesmell_annotations_${REPO_NAME.replace('/','_')}`;
      localStorage.setItem(STORAGE_KEY, JSON.stringify(annotations));

      // Recalcular estatísticas e re-renderizar
      const stats = {
        total: DATA.length,
        smelly: DATA.filter(d => d.pre_label === 'smelly').length,
        potentially_smelly: DATA.filter(d => d.pre_label === 'potentially_smelly').length,
        clean: DATA.filter(d => d.pre_label === 'clean').length,
      };
      document.getElementById('statRepo').textContent = REPO_NAME;
      document.title = `Fase 4 — Anotação (${REPO_NAME})`;
      document.getElementById('statTotal').textContent = stats.total;
      document.getElementById('statTotalRef').textContent = stats.total;
      document.getElementById('statSmelly').textContent = stats.smelly;
      document.getElementById('statPot').textContent = stats.potentially_smelly;
      document.getElementById('statClean').textContent = stats.clean;
      recomputeInitialDist();
      updateGlobalStats();

      filteredIndices = DATA.map((_,i) => i);
      currentIndex = 0;
      document.getElementById('filterSelect').value = 'all';
      if (filteredIndices.length > 0) {
        renderSnippet(0);
      } else {
        document.getElementById('snippetDisplay').innerHTML =
          '<p style="text-align:center;padding:40px;color:var(--text2)">Pacote sem snippets.</p>';
      }
      alert(`Pacote importado com sucesso: ${snipCount} snippets, ${annCount} anotações.`);
    } catch(err) {
      alert("Erro ao ler pacote: " + err.message);
    } finally {
      event.target.value = '';
    }
  };
  reader.readAsText(file);
}

document.addEventListener('keydown', e => {
  if (e.target.tagName === 'TEXTAREA' || e.target.tagName === 'INPUT') return;
  if (e.key === 'ArrowRight' || e.key === 'n') nextSnippet();
  if (e.key === 'ArrowLeft' || e.key === 'p') prevSnippet();
  if (e.key === '1') { document.getElementById('annLabel').value = 'smelly'; saveAnnotation(); }
  if (e.key === '2') { document.getElementById('annLabel').value = 'clean'; saveAnnotation(); }
  if (e.key === 'Enter' && !e.shiftKey) saveAndNext();
});

try {
  renderSnippet(0);
} catch(e) {
  document.getElementById('snippetDisplay').innerHTML = `<p style="color:var(--red);padding:40px">Erro ao carregar: ${e.message}</p>`;
  document.getElementById('loadingOverlay').classList.add('hidden');
  console.error(e);
}
document.getElementById('loadingOverlay').classList.add('hidden');
</script>
</body>
</html>'''

    # Substituições finais (seguro contra chaves do Python/JS)
    html_content = template.replace('__DATA_JSON__', data_json)
    html_content = html_content.replace('__REPO_NAME__', repo_name)
    html_content = html_content.replace('{{repo_name}}', repo_name)
    html_content = html_content.replace('{{total}}', str(total))
    html_content = html_content.replace('{{smelly}}', str(smelly))
    html_content = html_content.replace('{{potentially}}', str(potentially))
    html_content = html_content.replace('{{clean}}', str(clean))

    return html_content


if __name__ == "__main__":
    main()
