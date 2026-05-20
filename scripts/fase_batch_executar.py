#!/usr/bin/env python3
"""
Fase Batch — Orquestrador de múltiplos repositórios
=====================================================
Executa as fases 2-4 para todos os repositórios listados em batch_selection.json.

Uso:
  python3 fase_batch_executar.py [--batch-file PATH] [--start-from N]
                                 [--only-repo OWNER/REPO] [--offline]
                                 [--skip-fase2] [--skip-fase3]
                                 [--output-base DIR]

Flags:
  --batch-file <path>  — Caminho para batch_selection.json (padrão: output/fase1/batch_selection.json)
  --start-from <N>     — Índice (1-based) para retomar batch interrompido
  --only-repo <O/R>    — Processa apenas um repositório do batch
  --offline            — Repassa --offline para a interface HTML da Fase 4
  --skip-fase2         — Pula a Fase 2 (útil para retomar)
  --skip-fase3         — Pula a Fase 3 (útil para retomar)
  --output-base <dir>  — Base para outputs per-repo (padrão: output/)
"""

import json
import os
import sys
import argparse
import subprocess
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

# ─────────────────────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────────────────────
SONARQUBE_URL = "http://localhost:9000/api/system/status"
SONARQUBE_TIMEOUT = 10  # segundos por tentativa
SONARQUBE_MAX_RETRIES = 12  # ~2 minutos com intervalos de 10s


def sanitize_dirname(repo_name: str) -> str:
    return repo_name.replace("/", "_")


def load_batch_selection(batch_file: Path) -> dict:
    if not batch_file.exists():
        print(f"ERRO: Arquivo de batch não encontrado: {batch_file}")
        print("Execute primeiro: python3 scripts/fase1_selecionar_repositorio.py --auto-select N")
        sys.exit(1)
    with open(batch_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    repos = data.get("repositories", [])
    if not repos:
        print("ERRO: batch_selection.json não contém repositórios.")
        sys.exit(1)
    return data


def update_symlink(fase1_dir: Path, repo_name: str, index: int):
    safe_name = sanitize_dirname(repo_name)
    candidates = sorted(fase1_dir.glob(f"repositorio_metadata_*_{safe_name}.json"))
    candidates += sorted(fase1_dir.glob(f"repositorio_metadata_{safe_name}.json"))
    if not candidates:
        target_name = f"repositorio_metadata_{index:02d}_{safe_name}.json"
    else:
        target_name = candidates[0].name
    link_path = fase1_dir / "repositorio_metadata.json"
    if link_path.exists() or link_path.is_symlink():
        link_path.unlink()
    try:
        link_path.symlink_to(target_name)
    except OSError:
        target = fase1_dir / target_name
        if target.exists():
            shutil.copy2(target, link_path)
    return target_name


def load_github_url(fase1_dir: Path) -> str:
    link_path = fase1_dir / "repositorio_metadata.json"
    if not link_path.exists():
        return ""
    try:
        with open(link_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        return meta.get("github_url", "")
    except Exception:
        return ""


def load_repo_branch(fase1_dir: Path) -> str:
    link_path = fase1_dir / "repositorio_metadata.json"
    if not link_path.exists():
        return "main"
    try:
        with open(link_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        return meta.get("default_branch", "main")
    except Exception:
        return "main"


def check_sonarqube() -> bool:
    import urllib.request
    import urllib.error
    for i in range(1, SONARQUBE_MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(SONARQUBE_URL)
            with urllib.request.urlopen(req, timeout=SONARQUBE_TIMEOUT) as resp:
                body = json.loads(resp.read().decode())
                if body.get("status") == "UP":
                    print(f"  SonarQube UP (tentativa {i})")
                    return True
        except Exception:
            pass
        print(f"  Aguardando SonarQube... ({i}/{SONARQUBE_MAX_RETRIES})")
        time.sleep(10)
    return False


def clone_or_cache(repo_name: str, github_url: str, branch: str,
                   repos_dir: Path) -> Path:
    safe_name = sanitize_dirname(repo_name)
    repo_path = repos_dir / safe_name
    if repo_path.exists():
        print(f"  ♻ Repositório já clonado em: {repo_path}")
        return repo_path
    print(f"  ⬇ Clonando {repo_name} (branch {branch})...")
    cmd = ["git", "clone", "--depth", "1", "--branch", branch,
           f"{github_url}.git", str(repo_path)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300,
                            cwd=str(repos_dir))
    if result.returncode != 0:
        stderr = result.stderr.strip()[-300:]
        raise RuntimeError(f"Falha ao clonar {repo_name}: {stderr}")
    return repo_path


def run_fase2(repo_dir: Path, project_dir: Path) -> subprocess.CompletedProcess:
    script = project_dir / "scripts" / "fase2_extrair_snippets.php"
    print(f"  ▶ Fase 2 — php {script.relative_to(project_dir)} {repo_dir.relative_to(project_dir)}")
    return subprocess.run(
        ["php", str(script), str(repo_dir)],
        capture_output=True, text=True, timeout=600, cwd=str(project_dir)
    )


def run_fase3(repo_dir: Path, snippets_json: Path,
              project_dir: Path) -> subprocess.CompletedProcess:
    script = project_dir / "scripts" / "fase3_analise_estatica.sh"
    print(f"  ▶ Fase 3 — bash {script.relative_to(project_dir)} {repo_dir.relative_to(project_dir)}")
    return subprocess.run(
        ["bash", str(script), str(repo_dir), str(snippets_json)],
        capture_output=True, text=True, timeout=900, cwd=str(project_dir)
    )


def run_fase4(snippets_json: Path, labels_json: Path, output_dir: Path,
              project_dir: Path, offline: bool = False) -> subprocess.CompletedProcess:
    script = project_dir / "scripts" / "fase4_preparar_interface.py"
    cmd = [
        "python3", str(script),
        "--snippets", str(snippets_json),
        "--labels", str(labels_json),
        "--output", str(output_dir),
    ]
    if offline:
        cmd.append("--offline")
    print(f"  ▶ Fase 4 — python3 {script.relative_to(project_dir)}")
    return subprocess.run(cmd, capture_output=True, text=True, timeout=300,
                          cwd=str(project_dir))


def extract_fase2_stats(fase2_dir: Path) -> dict:
    json_file = fase2_dir / "snippets_com_metricas.json"
    if not json_file.exists():
        return {"total": 0, "error": "snippets_com_metricas.json não encontrado"}
    try:
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            "total": data.get("metadata", {}).get("total_snippets", len(data.get("snippets", []))),
            "files": data.get("metadata", {}).get("total_files", 0),
            "errors": data.get("metadata", {}).get("parse_errors", 0),
        }
    except Exception as e:
        return {"total": 0, "error": str(e)}


def extract_fase3_stats(fase3_dir: Path) -> dict:
    json_file = fase3_dir / "pre_rotulacao.json"
    if not json_file.exists():
        return {"total": 0, "error": "pre_rotulacao.json não encontrado"}
    try:
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        distribution = data.get("metadata", {}).get("distribution", {})
        return {
            "total": len(data.get("snippets", [])),
            "findings_total": data.get("metadata", {}).get("total_findings", 0),
            "findings_mapped": data.get("metadata", {}).get("mapped_findings", 0),
            "smelly": distribution.get("smelly", 0),
            "potentially": distribution.get("potentially_smelly", 0),
            "clean": distribution.get("clean", 0),
        }
    except Exception as e:
        return {"total": 0, "error": str(e)}


def copy_outputs(src_dir: Path, dst_dir: Path):
    if dst_dir.exists():
        shutil.rmtree(dst_dir)
    shutil.copytree(src_dir, dst_dir)
    print(f"    output: {dst_dir}")


def compute_distribution(fase3_stats: dict) -> dict:
    return {
        "smelly": fase3_stats.get("smelly", 0),
        "potentially_smelly": fase3_stats.get("potentially", 0),
        "clean": fase3_stats.get("clean", 0),
    }


def generate_batch_summary(results: list, output_dir: Path):
    total = len(results)
    succeeded = [r for r in results if r["status"] == "success"]
    failed = [r for r in results if r["status"] in ("fase2_failed", "fase3_failed")]
    skipped = [r for r in results if r["status"] == "skipped"]

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_repositories": total,
        "succeeded": len(succeeded),
        "failed": len(failed),
        "skipped": len(skipped),
        "repositories": results,
    }

    batch_file = output_dir / "batch_summary.json"
    with open(batch_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"\n✓ batch_summary.json salvo em: {batch_file}")

    return summary


def generate_landing_page(results: list, project_dir: Path, output_dir: Path):
    repos = [r for r in results if r["status"] in ("success", "skipped")]
    if not repos:
        return

    safe_name_from = lambda n: sanitize_dirname(n)

    cards_html = ""
    for r in repos:
        name = r["repo_name"]
        safe = safe_name_from(name)
        stars = r.get("stars", 0)
        total_f2 = r.get("fase2_total", 0)
        dist = r.get("distribution", {})
        smelly = dist.get("smelly", 0)
        potentially = dist.get("potentially_smelly", 0)
        clean = dist.get("clean", 0)
        status_icon = "✓" if r["status"] == "success" else "⚠"
        status_class = "badge-ok" if r["status"] == "success" else "badge-warn"
        href = f"../{safe}/fase4/interface_anotacao.html"
        cards_html += f'''
  <a class="card" href="{href}">
    <div class="card-title">{status_icon} {name} <span class="badge {status_class}">{r['status']}</span></div>
    <div class="card-meta">★ {stars}</div>
    <div class="card-stats">{total_f2} snippets · {smelly} smelly · {potentially} potentially · {clean} clean</div>
  </a>'''

    html = f'''<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Pipeline — Dataset de Code Smells PHP</title>
<style>
:root{{--bg:#0f1117;--card:#1a1d27;--border:#2d3248;--accent:#e74c3c;--green:#00b894;--yellow:#fdcb6e;--text:#e0e0e0;--text2:#a0a4b8}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif;min-height:100vh;padding:40px}}
h1{{font-size:1.4rem;margin-bottom:8px;text-align:center}}
h1 span{{color:var(--accent)}}
.sub{{color:var(--text2);font-size:.85rem;margin-bottom:32px;text-align:center}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(380px,1fr));gap:16px;max-width:1200px;margin:0 auto}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:20px;transition:border-color .2s;display:block;text-decoration:none;color:inherit}}
.card:hover{{border-color:var(--accent)}}
.card-title{{font-size:1rem;font-weight:600;margin-bottom:4px}}
.card-meta{{font-size:.72rem;color:var(--text2);margin-bottom:6px}}
.card-stats{{font-size:.75rem;color:var(--text2)}}
.badge{{display:inline-block;padding:2px 8px;border-radius:4px;font-size:.65rem;margin-left:8px}}
.badge-ok{{background:#1b4a3a;color:var(--green)}}
.badge-warn{{background:#3a2a1b;color:var(--yellow)}}
.footer{{color:var(--text2);font-size:.72rem;margin-top:40px;text-align:center;border-top:1px solid var(--border);padding-top:16px}}
</style>
</head>
<body>
  <h1>Dataset de <span>Code Smells</span> PHP</h1>
  <div class="sub">Pipeline de anotação — {len(repos)} repositório(s) processado(s)</div>
  <div class="grid">
    {cards_html}
  </div>
  <div class="footer">
    Pipeline de doutorado — datasets/php-codesmell-dataset
  </div>
</body>
</html>
'''
    index_path = output_dir / "index.html"
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✓ Landing page multi-repo gerada: {index_path}")


def process_repo(repo_entry: dict, args, project_dir: Path) -> dict:
    repo_name = repo_entry["repo_name"]
    index = repo_entry.get("index", 0)
    safe_name = sanitize_dirname(repo_name)
    fase1_dir = project_dir / "output" / "fase1"
    output_base = Path(args.output_base) if args.output_base else project_dir / "output"
    repos_dir = project_dir / "repos"

    result = {
        "index": index,
        "repo_name": repo_name,
        "stars": repo_entry.get("stars", 0),
        "license": repo_entry.get("license", ""),
        "status": "pending",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }

    print(f"\n{'═' * 60}")
    print(f"  [{index}] {repo_name}")
    print(f"{'═' * 60}")

    # ── Step 1: atualizar symlink ──
    try:
        target = update_symlink(fase1_dir, repo_name, index)
        print(f"  Symlink → {target}")
    except Exception as e:
        result["status"] = "symlink_failed"
        result["error"] = str(e)
        print(f"  ✗ Erro no symlink: {e}")
        return result

    # ── Step 2: clonar se necessário ──
    github_url = load_github_url(fase1_dir)
    branch = load_repo_branch(fase1_dir)
    if not github_url:
        github_url = f"https://github.com/{repo_name}"

    try:
        repo_path = clone_or_cache(repo_name, github_url, branch, repos_dir)
        result["repo_path"] = str(repo_path)
    except Exception as e:
        result["status"] = "clone_failed"
        result["error"] = str(e)
        print(f"  ✗ Falha no clone: {e}")
        return result

    # ── Step 3: Fase 2 ──
    if args.skip_fase2:
        print("  ⏭ Fase 2 pulada (--skip-fase2)")
    else:
        try:
            proc = run_fase2(repo_path, project_dir)
            if proc.returncode != 0:
                stderr_tail = proc.stderr.strip()[-400:]
                raise RuntimeError(f"exit code {proc.returncode}: {stderr_tail}")

            # Log stdout condensado
            lines = [l for l in proc.stdout.strip().split("\n") if l.strip()]
            for line in lines[-6:]:
                print(f"    {line.strip()}")
        except Exception as e:
            result["status"] = "fase2_failed"
            result["error"] = str(e)
            print(f"  ✗ Fase 2 falhou: {e}")
            return result

        # Copiar outputs da Fase 2
        repo_fase2_dir = output_base / safe_name / "fase2"
        src_fase2 = project_dir / "output" / "fase2"
        try:
            copy_outputs(src_fase2, repo_fase2_dir)
        except Exception as e:
            print(f"  ⚠ Erro ao copiar outputs fase2: {e}")

    fase2_stats = extract_fase2_stats(project_dir / "output" / "fase2")
    result["fase2_total"] = fase2_stats.get("total", 0)
    result["fase2_files"] = fase2_stats.get("files", 0)
    print(f"  Fase 2: {fase2_stats.get('total', 0)} snippets ({fase2_stats.get('files', 0)} arquivos)")

    if fase2_stats.get("total", 0) == 0:
        print(f"  ⚠ Zero snippets extraídos — continuando (não é erro fatal)")

    # ── Step 4: Fase 3 ──
    if args.skip_fase3:
        print("  ⏭ Fase 3 pulada (--skip-fase3)")
    else:
        snippets_json = project_dir / "output" / "fase2" / "snippets_com_metricas.json"
        try:
            proc = run_fase3(repo_path, snippets_json, project_dir)
            if proc.returncode != 0:
                stderr_tail = proc.stderr.strip()[-400:]
                raise RuntimeError(f"exit code {proc.returncode}: {stderr_tail}")

            lines = [l for l in proc.stdout.strip().split("\n") if l.strip()]
            for line in lines[-8:]:
                print(f"    {line.strip()}")
        except Exception as e:
            result["status"] = "fase3_failed"
            result["error"] = str(e)
            print(f"  ✗ Fase 3 falhou: {e}")
            return result

        # Copiar outputs da Fase 3
        repo_fase3_dir = output_base / safe_name / "fase3"
        src_fase3 = project_dir / "output" / "fase3"
        try:
            copy_outputs(src_fase3, repo_fase3_dir)
        except Exception as e:
            print(f"  ⚠ Erro ao copiar outputs fase3: {e}")

    fase3_stats = extract_fase3_stats(project_dir / "output" / "fase3")
    result["fase3_total"] = fase3_stats.get("total", 0)
    result["fase3_findings"] = fase3_stats.get("findings_total", 0)
    result["distribution"] = compute_distribution(fase3_stats)
    print(f"  Fase 3: {fase3_stats.get('total', 0)} snippets, "
          f"{fase3_stats.get('findings_mapped', 0)}/{fase3_stats.get('findings_total', 0)} findings mapeados")

    # ── Step 5: Fase 4 ──
    repo_fase4_dir = output_base / safe_name / "fase4"
    snippets_json = project_dir / "output" / "fase2" / "snippets_com_metricas.json"
    labels_json = project_dir / "output" / "fase3" / "pre_rotulacao.json"
    try:
        proc = run_fase4(snippets_json, labels_json, repo_fase4_dir, project_dir,
                         offline=args.offline)
        if proc.returncode != 0:
            stderr_tail = proc.stderr.strip()[-400:]
            raise RuntimeError(f"exit code {proc.returncode}: {stderr_tail}")

        lines = [l for l in proc.stdout.strip().split("\n") if l.strip()]
        for line in lines[-4:]:
            print(f"    {line.strip()}")
    except Exception as e:
        result["status"] = "fase4_failed"
        result["error"] = str(e)
        print(f"  ✗ Fase 4 falhou: {e}")
        return result

    # ── Sucesso ──
    result["status"] = "success"
    dist = result.get("distribution", {})
    print(f"\n  ✓ [{index}] {repo_name} concluído — "
          f"{result.get('fase2_total', 0)} snippets, "
          f"s:{dist.get('smelly', 0)} "
          f"p:{dist.get('potentially_smelly', 0)} "
          f"c:{dist.get('clean', 0)}")

    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Fase Batch — Orquestrador de múltiplos repositórios (Fases 2-4)"
    )
    parser.add_argument(
        "--batch-file", type=str,
        default=None,
        help="Caminho para batch_selection.json (padrão: output/fase1/batch_selection.json)",
    )
    parser.add_argument(
        "--start-from", type=int, default=1, metavar="N",
        help="Índice (1-based) para retomar batch interrompido",
    )
    parser.add_argument(
        "--only-repo", type=str, default=None, metavar="OWNER/REPO",
        help="Processa apenas um repositório específico do batch",
    )
    parser.add_argument(
        "--offline", action="store_true",
        help="Repassa --offline para a interface HTML da Fase 4",
    )
    parser.add_argument(
        "--skip-fase2", action="store_true",
        help="Pula a Fase 2 (útil para retomar após falha)",
    )
    parser.add_argument(
        "--skip-fase3", action="store_true",
        help="Pula a Fase 3 (útil para retomar após falha)",
    )
    parser.add_argument(
        "--output-base", type=str, default=None,
        help="Base para outputs per-repo (padrão: output/)",
    )
    args = parser.parse_args()

    project_dir = Path(__file__).resolve().parent.parent
    output_base = Path(args.output_base) if args.output_base else project_dir / "output"

    # Carregar batch
    batch_file = Path(args.batch_file) if args.batch_file else project_dir / "output" / "fase1" / "batch_selection.json"
    batch = load_batch_selection(batch_file)
    repos = batch["repositories"]

    # Filtrar por --only-repo
    if args.only_repo:
        repos = [r for r in repos if r["repo_name"] == args.only_repo]
        if not repos:
            print(f"ERRO: Repositório '{args.only_repo}' não encontrado no batch.")
            print(f"  Repositórios disponíveis: {[r['repo_name'] for r in batch['repositories']]}")
            sys.exit(1)

    # Aplicar --start-from
    start_idx = max(1, args.start_from)
    if start_idx > 1:
        repos = [r for r in repos if r["index"] >= start_idx]
        if not repos:
            print(f"ERRO: --start-from {start_idx} está além do último repositório (índice máximo: {batch['repositories'][-1]['index']})")
            sys.exit(1)

    print("=" * 60)
    print("  FASE BATCH — Processamento de múltiplos repositórios")
    print("=" * 60)
    print(f"  Repositórios: {len(repos)}")
    print(f"  Modo offline: {'sim' if args.offline else 'não'}")
    print(f"  Pular Fase 2: {'sim' if args.skip_fase2 else 'não'}")
    print(f"  Pular Fase 3: {'sim' if args.skip_fase3 else 'não'}")
    print(f"  Output base:  {output_base}")
    print(f"  Batch file:   {batch_file}")

    # Verificar GITHUB_TOKEN
    if not os.environ.get("GITHUB_TOKEN"):
        print("\n⚠ GITHUB_TOKEN não definido — clone pode falhar por rate-limit.")

    # Verificar espaço em disco
    try:
        stat = os.statvfs(str(output_base))
        free_gb = (stat.f_frsize * stat.f_bavail) / (1024 ** 3)
        print(f"  Espaço livre: {free_gb:.1f} GB")
        if free_gb < 1.0:
            print("  ⚠ Menos de 1 GB livre — risco de disco cheio.")
    except Exception:
        pass

    # ── Verificar SonarQube antes de iniciar ──
    if not args.skip_fase3:
        print("\n  Verificando SonarQube...")
        if not check_sonarqube():
            print("  ✗ SonarQube não respondeu a tempo. Verifique se o container está rodando:")
            print("    docker compose --profile fase3 up sonarqube -d")
            print("  Continuando sem garantia — Fase 3 pode falhar.")

    # ── Processar cada repositório ──
    results = []
    for repo_entry in repos:
        result = process_repo(repo_entry, args, project_dir)
        results.append(result)

    # ── Resumo final ──
    succeeded = [r for r in results if r["status"] == "success"]
    failed = [r for r in results if r["status"] not in ("success", "skipped")]

    print(f"\n{'═' * 60}")
    print(f"  RESUMO FINAL DO BATCH")
    print(f"{'═' * 60}")
    print(f"  Total:       {len(results)}")
    print(f"  Sucesso:     {len(succeeded)}")
    print(f"  Falhas:      {len(failed)}")
    for r in failed:
        print(f"    ✗ [{r['index']}] {r['repo_name']}: {r['status']} — {r.get('error', '')[:80]}")
    for r in succeeded:
        dist = r.get("distribution", {})
        print(f"    ✓ [{r['index']}] {r['repo_name']}: {r.get('fase2_total', 0)} snippets, "
              f"s:{dist.get('smelly', 0)} p:{dist.get('potentially_smelly', 0)} c:{dist.get('clean', 0)}")

    # ── Gerar batch_summary.json ──
    generate_batch_summary(results, project_dir / "output" / "fase4")

    # ── Gerar/atualizar landing page multi-repo ──
    generate_landing_page(results, project_dir, project_dir / "output" / "fase4")

    print("\n✓ Batch concluído!")
    if failed:
        print(f"  {len(failed)} repositório(s) com falha. Verifique batch_summary.json para detalhes.")
        sys.exit(1)


if __name__ == "__main__":
    main()
