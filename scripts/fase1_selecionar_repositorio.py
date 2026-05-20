#!/usr/bin/env python3
"""
Fase 1 — Seleção e Validação de Repositório PHP
=================================================
Consulta a GitHub API, valida critérios da metodologia e salva metadados.

Critérios de seleção:
  - Linguagem principal: PHP
  - Estrelas >= 1000 (indicador de adoção)
  - Forks >= 100
  - Último push após 2024-01-01 (manutenção ativa)
  - Criado antes de 2023-01-01 (projeto maduro)
  - Licença permissiva (MIT, Apache-2.0, BSD)

Uso:
  python3 fase1_selecionar_repositorio.py [--repo OWNER/REPO] [--output DIR]
  python3 fase1_selecionar_repositorio.py --search "keyword" [--output DIR]

Variáveis de ambiente:
  GITHUB_TOKEN  — Token pessoal do GitHub (recomendado para evitar rate-limit)
"""
import json
import os
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERRO: 'requests' não instalado. Execute: pip install requests")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────
# Configuração
# ─────────────────────────────────────────────────────────────
GITHUB_API = "https://api.github.com"
CRITERIA = {
    "min_stars": 1000,
    "min_forks": 100,
    "last_push_after": "2024-01-01",
    "created_before": "2023-01-01",
    "allowed_licenses": ["MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause"],
    "language": "PHP",
}


def get_headers():
    headers = {"Accept": "application/vnd.github.v3+json"}
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = f"token {token}"
    else:
        print("[AVISO] GITHUB_TOKEN não definido. Rate-limit será de 60 req/hora.")
        print("        Defina com: export GITHUB_TOKEN=ghp_seuTokenAqui\n")
    return headers


def fetch_repo_data(owner_repo: str) -> dict:
    """Busca dados de um repositório específico."""
    url = f"{GITHUB_API}/repos/{owner_repo}"
    resp = requests.get(url, headers=get_headers(), timeout=30)
    if resp.status_code == 404:
        print(f"ERRO: Repositório '{owner_repo}' não encontrado.")
        sys.exit(1)
    resp.raise_for_status()
    return resp.json()


def search_php_repos(query: str = "", max_results: int = 10) -> list:
    """Busca repositórios PHP no GitHub que atendam critérios mínimos."""
    search_q = f"language:php stars:>={CRITERIA['min_stars']} forks:>={CRITERIA['min_forks']}"
    if query:
        search_q = f"{query} {search_q}"

    url = f"{GITHUB_API}/search/repositories"
    params = {
        "q": search_q,
        "sort": "stars",
        "order": "desc",
        "per_page": min(max_results, 30),
    }
    resp = requests.get(url, headers=get_headers(), params=params, timeout=30)
    resp.raise_for_status()
    return resp.json().get("items", [])


def detect_license(data: dict, owner_repo: str) -> str:
    """Tenta detectar a licença do repositório por múltiplos métodos."""
    license_info = data.get("license") or {}
    spdx = license_info.get("spdx_id", "NOASSERTION")
    if spdx and spdx != "NOASSERTION":
        return spdx

    # Fallback: verificar arquivo LICENSE via API
    try:
        url = f"{GITHUB_API}/repos/{owner_repo}/license"
        resp = requests.get(url, headers=get_headers(), timeout=15)
        if resp.status_code == 200:
            lic = resp.json().get("license", {}).get("spdx_id", "")
            if lic and lic != "NOASSERTION":
                return lic
    except Exception:
        pass

    # Fallback: verificar composer.json
    try:
        url = f"{GITHUB_API}/repos/{owner_repo}/contents/composer.json"
        resp = requests.get(url, headers=get_headers(), timeout=15)
        if resp.status_code == 200:
            import base64
            content = base64.b64decode(resp.json()["content"]).decode("utf-8")
            composer = json.loads(content)
            lic = composer.get("license", "")
            if isinstance(lic, list):
                lic = lic[0] if lic else ""
            if lic:
                return lic
    except Exception:
        pass

    return spdx or "unknown"


def detect_php_version(owner_repo: str) -> str:
    """Detecta versão PHP requerida via composer.json."""
    try:
        url = f"{GITHUB_API}/repos/{owner_repo}/contents/composer.json"
        resp = requests.get(url, headers=get_headers(), timeout=15)
        if resp.status_code == 200:
            import base64
            content = base64.b64decode(resp.json()["content"]).decode("utf-8")
            composer = json.loads(content)
            return composer.get("require", {}).get("php", "unknown")
    except Exception:
        pass
    return "unknown"


def get_latest_commit(owner_repo: str, branch: str) -> str:
    """Obtém hash do último commit na branch padrão."""
    try:
        url = f"{GITHUB_API}/repos/{owner_repo}/commits/{branch}"
        resp = requests.get(url, headers=get_headers(), timeout=15)
        if resp.status_code == 200:
            return resp.json()["sha"]
    except Exception:
        pass
    return "unknown"


def validate_criteria(data: dict, license_str: str) -> dict:
    """Valida todos os critérios da metodologia."""
    stars = data.get("stargazers_count", 0)
    forks = data.get("forks_count", 0)
    last_push = data.get("pushed_at", "")
    created = data.get("created_at", "")
    lang = data.get("language", "")

    validations = {
        "language_php": {
            "required": "PHP",
            "actual": lang,
            "passed": lang == "PHP",
        },
        "stars_min": {
            "required": f">= {CRITERIA['min_stars']}",
            "actual": stars,
            "passed": stars >= CRITERIA["min_stars"],
        },
        "forks_min": {
            "required": f">= {CRITERIA['min_forks']}",
            "actual": forks,
            "passed": forks >= CRITERIA["min_forks"],
        },
        "last_push_recent": {
            "required": f"after {CRITERIA['last_push_after']}",
            "actual": last_push,
            "passed": last_push >= CRITERIA["last_push_after"] if last_push else False,
        },
        "created_mature": {
            "required": f"before {CRITERIA['created_before']}",
            "actual": created,
            "passed": created < CRITERIA["created_before"] if created else False,
        },
        "license_permissive": {
            "required": f"one of {CRITERIA['allowed_licenses']}",
            "actual": license_str,
            "passed": license_str in CRITERIA["allowed_licenses"],
        },
    }
    return validations


def categorize_repo(data: dict) -> str:
    """Classifica o tipo de repositório (framework, library, CMS, etc.)."""
    desc = (data.get("description") or "").lower()
    topics = [t.lower() for t in data.get("topics", [])]

    if any(k in desc or k in " ".join(topics) for k in ["framework", "mvc"]):
        return "framework"
    if any(k in desc or k in " ".join(topics) for k in ["cms", "content management"]):
        return "cms"
    if any(k in desc or k in " ".join(topics) for k in ["ecommerce", "e-commerce", "shop"]):
        return "ecommerce"
    if any(k in desc or k in " ".join(topics) for k in ["library", "lib", "sdk", "utility", "helper"]):
        return "library/utility"
    if any(k in desc or k in " ".join(topics) for k in ["api", "rest", "graphql"]):
        return "api"
    return "other"


def build_metadata(data: dict, output_dir: str) -> dict:
    """Constrói o JSON de metadados completo."""
    owner_repo = data["full_name"]
    license_str = detect_license(data, owner_repo)
    php_version = detect_php_version(owner_repo)
    branch = data.get("default_branch", "main")
    commit = get_latest_commit(owner_repo, branch)
    validations = validate_criteria(data, license_str)
    all_passed = all(v["passed"] for v in validations.values())

    metadata = {
        "repo_name": data["full_name"],
        "github_url": data["html_url"],
        "commit_hash": commit,
        "snapshot_date": datetime.now(timezone.utc).isoformat(),
        "stars": data["stargazers_count"],
        "forks": data["forks_count"],
        "license": license_str,
        "php_version_required": php_version,
        "category": categorize_repo(data),
        "created_at": data["created_at"],
        "last_push": data["pushed_at"],
        "description": data.get("description", ""),
        "default_branch": branch,
        "language": data.get("language", ""),
        "topics": data.get("topics", []),
        "criteria_validation": validations,
        "all_criteria_met": all_passed,
        "notes": [],
    }

    # Adicionar notas sobre critérios não atendidos
    for key, v in validations.items():
        if not v["passed"]:
            metadata["notes"].append(
                f"Critério '{key}' NÃO atendido: esperado {v['required']}, obtido {v['actual']}"
            )

    if all_passed:
        metadata["notes"].append("Todos os critérios atendidos ✓")

    return metadata


def print_validation_table(validations: dict):
    """Exibe tabela de validação de critérios."""
    print("\n╔═══════════════════════╦════════════════════════════════╦════════╗")
    print("║ Critério              ║ Valor                          ║ Status ║")
    print("╠═══════════════════════╬════════════════════════════════╬════════╣")
    for key, v in validations.items():
        status = "  ✓  " if v["passed"] else "  ✗  "
        actual = str(v["actual"])[:30]
        print(f"║ {key:<21} ║ {actual:<30} ║  {status} ║")
    print("╚═══════════════════════╩════════════════════════════════╩════════╝")


def _save_metadata(metadata: dict, output_dir: Path, create_symlink: bool = True, index: int = None) -> Path:
    """Salva metadados no diretório de saída e opcionalmente cria symlink."""
    safe_name = metadata["repo_name"].replace("/", "_")
    prefix = f"{index:02d}_" if index is not None else ""
    output_file = output_dir / f"repositorio_metadata_{prefix}{safe_name}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    if create_symlink:
        link_path = output_dir / "repositorio_metadata.json"
        if link_path.exists() or link_path.is_symlink():
            link_path.unlink()
        try:
            link_path.symlink_to(output_file.name)
        except OSError:
            import shutil
            shutil.copy2(output_file, link_path)

    return output_file


def _update_symlink(output_dir: Path, metadata: dict):
    """Atualiza o symlink repositorio_metadata.json para apontar ao repo dado.
    Procura o arquivo com ou sem prefixo de índice (batch vs single)."""
    safe_name = metadata["repo_name"].replace("/", "_")
    # Buscar o arquivo real que contém os metadados (com ou sem prefixo)
    candidates = sorted(output_dir.glob(f"repositorio_metadata_*_{safe_name}.json"))
    candidates += sorted(output_dir.glob(f"repositorio_metadata_{safe_name}.json"))
    if not candidates:
        # Fallback: cria com nome sem prefixo
        target_name = f"repositorio_metadata_{safe_name}.json"
    else:
        target_name = candidates[0].name
    link_path = output_dir / "repositorio_metadata.json"
    if link_path.exists() or link_path.is_symlink():
        link_path.unlink()
    try:
        link_path.symlink_to(target_name)
    except OSError:
        target = output_dir / target_name
        if target.exists():
            import shutil
            shutil.copy2(target, link_path)
    print(f"  Symlink atualizado → {metadata['repo_name']} ({target_name})")


def _batch_summary_table(repos_metadata: list):
    """Exibe tabela resumo de múltiplos repositórios selecionados."""
    header = f"{'#':<3} {'Repositório':<38} {'★':>7} {'Licença':<12} {'Critérios':<10}"
    sep = "─" * 82
    print(f"\n{sep}")
    print(header)
    print(sep)
    for i, m in enumerate(repos_metadata, 1):
        stars = m.get("stars", 0)
        lic = m.get("license", "?")[:10]
        all_ok = m.get("all_criteria_met", False)
        # Conta quantos critérios passaram
        validations = m.get("criteria_validation", {})
        passed = sum(1 for v in validations.values() if v.get("passed")) if validations else 0
        total = len(validations) if validations else 6
        status = f"✓ {passed}/{total}" if all_ok else f"✗ {passed}/{total}"
        print(f"{i:<3} {m['repo_name']:<38} {stars:>7} {lic:<12} {status:<10}")
    print(sep)


def _batch_select(n: int, output_dir: Path) -> list:
    """Modo batch: seleciona top N repos PHP que passam em TODOS os critérios.
    Repos que falham são pulados; a busca continua até completar N válidos.
    Retorna lista de metadados dos aprovados."""
    print(f"\n🔍 Buscando top {n} repositórios PHP (apenas os que passam em todos os critérios)...")

    repos_metadata = []
    skipped = []
    page = 1

    while len(repos_metadata) < n:
        repos = search_php_repos("", max_results=30)
        if not repos:
            print(f"\n⚠ Apenas {len(repos_metadata)}/{n} repositórios foram encontrados antes do esgotamento.")
            break

        for r in repos:
            if len(repos_metadata) >= n:
                break
            owner_repo = r["full_name"]

            # Pular se já processado (evitar duplicatas entre páginas)
            seen = any(m["repo_name"] == owner_repo for m in repos_metadata)
            seen_skipped = any(s == owner_repo for s in skipped)
            if seen or seen_skipped:
                continue

            print(f"  [{len(repos_metadata) + 1}/{n}] Obtendo dados de {owner_repo}...")
            try:
                data = fetch_repo_data(owner_repo)
            except Exception as e:
                print(f"    ⚠ Erro ao buscar {owner_repo}: {e} — pulando")
                skipped.append(owner_repo)
                continue

            metadata = build_metadata(data, str(output_dir))
            validations = metadata.get("criteria_validation", {})

            if metadata["all_criteria_met"]:
                idx = len(repos_metadata) + 1
                _save_metadata(metadata, output_dir, create_symlink=(len(repos_metadata) == 0), index=idx)
                repos_metadata.append(metadata)
                failed_str = ""
            else:
                failed = [k for k, v in validations.items() if not v.get("passed")]
                failed_str = f"  ✗ falhou em: {', '.join(failed)}"
                skipped.append(owner_repo)

            ok = "✓" if metadata["all_criteria_met"] else "✗"
            print(f"    {ok} {metadata['repo_name']:<40} ★{metadata['stars']:<7} {metadata['license']}{failed_str}")

        page += 1

    # Salvar batch_selection.json (apenas os aprovados)
    batch_file = output_dir / "batch_selection.json"
    batch_data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "selection_mode": "auto",
        "criteria": {
            "min_stars": CRITERIA["min_stars"],
            "min_forks": CRITERIA["min_forks"],
            "last_push_after": CRITERIA["last_push_after"],
            "created_before": CRITERIA["created_before"],
            "allowed_licenses": CRITERIA["allowed_licenses"],
            "language": CRITERIA["language"],
        },
        "total_selected": len(repos_metadata),
        "total_skipped": len(skipped),
        "repositories": [
            {
                "index": i,
                "repo_name": m["repo_name"],
                "stars": m["stars"],
                "license": m["license"],
                "all_criteria_met": m["all_criteria_met"],
                "file": f"repositorio_metadata_{i:02d}_{m['repo_name'].replace('/', '_')}.json",
            }
            for i, m in enumerate(repos_metadata, 1)
        ],
    }
    with open(batch_file, "w", encoding="utf-8") as f:
        json.dump(batch_data, f, indent=2, ensure_ascii=False)

    _batch_summary_table(repos_metadata)

    print(f"\n✓ {len(repos_metadata)}/{n} repositórios aprovados ({len(skipped)} pulados por não atenderem critérios).")
    if repos_metadata:
        print(f"  Batch salvo em: {batch_file}")
        print(f"  Symlink ativo → {repos_metadata[0]['repo_name']}")
    else:
        print("  Nenhum repositório aprovado. Ajuste os critérios ou tente novamente com mais tokens de API.")

    return repos_metadata


def main():
    parser = argparse.ArgumentParser(
        description="Fase 1 — Seleção e Validação de Repositório PHP"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--repo",
        type=str,
        help="Repositório específico (ex: laravel/framework, FakerPHP/Faker)",
    )
    group.add_argument(
        "--search", type=str, help="Buscar repositórios PHP por keyword"
    )
    group.add_argument(
        "--auto-select",
        type=int,
        metavar="N",
        help="Selecionar automaticamente os top N repositórios PHP (não-interativo)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Diretório de saída (padrão: output/fase1/)",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=10,
        help="Máximo de resultados na busca (padrão: 10)",
    )
    args = parser.parse_args()

    # Determinar diretório de saída
    project_dir = Path(__file__).resolve().parent.parent
    output_dir = Path(args.output) if args.output else project_dir / "output" / "fase1"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("  FASE 1 — Seleção e Validação de Repositório PHP")
    print("=" * 60)

    if args.search:
        # Modo busca
        print(f"\nBuscando repositórios PHP: '{args.search}'...")
        repos = search_php_repos(args.search, args.max_results)
        if not repos:
            print("Nenhum repositório encontrado.")
            sys.exit(1)

        print(f"\n{'#':<4} {'Repositório':<35} {'★':>7} {'Forks':>7} {'Licença':<12}")
        print("-" * 70)
        for i, r in enumerate(repos, 1):
            lic = (r.get("license") or {}).get("spdx_id", "?")
            print(f"{i:<4} {r['full_name']:<35} {r['stargazers_count']:>7} {r['forks_count']:>7} {lic:<12}")

        print(f"\nDigite o número do repositório desejado (1-{len(repos)}):")
        try:
            choice = int(input("> ")) - 1
            if 0 <= choice < len(repos):
                data = fetch_repo_data(repos[choice]["full_name"])
            else:
                print("Escolha inválida.")
                sys.exit(1)
        except (ValueError, EOFError):
            print("Usando primeiro resultado.")
            data = fetch_repo_data(repos[0]["full_name"])

    elif args.repo:
        # Modo repositório específico
        owner_repo = args.repo
        # Verificar se metadados já existem no cache (ex.: batch anterior)
        safe_name = owner_repo.replace("/", "_")
        cached = output_dir / f"repositorio_metadata_{safe_name}.json"
        # Também procurar com prefixo de índice (batch mode): 01_, 02_, ...
        if not cached.exists():
            candidates = sorted(output_dir.glob(f"repositorio_metadata_??_{safe_name}.json"))
            cached = candidates[0] if candidates else cached
        if cached.exists():
            print(f"\n♻  Metadados de {owner_repo} já existem no cache ({cached.name}).")
            print("   Reutilizando sem consultar a API...")
            with open(cached, "r", encoding="utf-8") as f:
                metadata = json.load(f)
        else:
            print(f"\nAnalisando repositório: {owner_repo}")
            data = fetch_repo_data(owner_repo)
            metadata = build_metadata(data, str(output_dir))
            _save_metadata(metadata, output_dir, create_symlink=False)

        print_validation_table(metadata["criteria_validation"])

        if not metadata["all_criteria_met"]:
            print(f"\n⚠ Repositório {metadata['repo_name']} NÃO atende todos os critérios.")
            for note in metadata.get("notes", []):
                print(f"  → {note}")
            print("\nDeseja continuar mesmo assim? [s/N]")
            try:
                resp = input("> ").strip().lower()
                if resp not in ("s", "sim", "y", "yes"):
                    print("Abortado pelo usuário.")
                    sys.exit(0)
            except EOFError:
                print("Continuando em modo não-interativo...")

        # Atualizar symlink
        _update_symlink(output_dir, metadata)

        print(f"\n✓ Fase 1 concluída com sucesso!")
        print(f"  Repositório:   {metadata['repo_name']}")
        print(f"  Estrelas:      {metadata['stars']}")
        print(f"  Forks:         {metadata['forks']}")
        print(f"  Licença:       {metadata['license']}")
        print(f"  PHP:           {metadata.get('php_version_required', '?')}")
        return metadata

    elif args.auto_select:
        # Modo batch: seleciona N repositórios automaticamente
        _batch_select(args.auto_select, output_dir)
        print(f"\n  Para listar o batch: cat {output_dir / 'batch_selection.json'}")
        print( "  Para trocar o repo ativo: python3 scripts/fase1_selecionar_repositorio.py --repo OWNER/REPO")
        print( "\n✓ Fase 1 concluída com sucesso!")
        sys.exit(0)

    else:
        # Modo padrão: listar top repositórios PHP
        print("\nBuscando top repositórios PHP...")
        repos = search_php_repos("", args.max_results)
        if not repos:
            print("Nenhum repositório encontrado.")
            sys.exit(1)

        print(f"\n{'#':<4} {'Repositório':<35} {'★':>7} {'Forks':>7} {'Licença':<12}")
        print("-" * 70)
        for i, r in enumerate(repos, 1):
            lic = (r.get("license") or {}).get("spdx_id", "?")
            print(f"{i:<4} {r['full_name']:<35} {r['stargazers_count']:>7} {r['forks_count']:>7} {lic:<12}")

        print(f"\nDigite o número do repositório desejado (1-{len(repos)}):")
        try:
            choice = int(input("> ")) - 1
            if 0 <= choice < len(repos):
                data = fetch_repo_data(repos[choice]["full_name"])
            else:
                print("Escolha inválida.")
                sys.exit(1)
        except (ValueError, EOFError):
            print("Usando primeiro resultado.")
            data = fetch_repo_data(repos[0]["full_name"])

    # Construir e validar metadados (comum a --search e modo padrão)
    metadata = build_metadata(data, str(output_dir))
    print_validation_table(metadata["criteria_validation"])

    all_ok = metadata["all_criteria_met"]
    if all_ok:
        print(f"\n✓ Repositório {metadata['repo_name']} atende TODOS os critérios!")
    else:
        print(f"\n⚠ Repositório {metadata['repo_name']} NÃO atende todos os critérios.")
        for note in metadata["notes"]:
            print(f"  → {note}")
        print("\nDeseja continuar mesmo assim? [s/N]")
        try:
            resp = input("> ").strip().lower()
            if resp not in ("s", "sim", "y", "yes"):
                print("Abortado pelo usuário.")
                sys.exit(0)
        except EOFError:
            print("Continuando em modo não-interativo...")

    # Salvar metadados e atualizar symlink
    output_file = _save_metadata(metadata, output_dir, create_symlink=True)

    print(f"\n✓ Metadados salvos em: {output_file}")
    print(f"\n  Repositório:    {metadata['repo_name']}")
    print(f"  Estrelas:       {metadata['stars']}")
    print(f"  Forks:          {metadata['forks']}")
    print(f"  Licença:        {metadata['license']}")
    print(f"  PHP:            {metadata.get('php_version_required', '?')}")
    print(f"  Commit:         {metadata['commit_hash'][:12]}...")
    print(f"  Categoria:      {metadata.get('category', '?')}")

    print("\n✓ Fase 1 concluída com sucesso!")
    return metadata


if __name__ == "__main__":
    main()
