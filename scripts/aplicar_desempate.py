#!/usr/bin/env python3
"""
Aplica decisões do desempate (exportadas pelo revisor 4) sobre o JSON consolidado.
Gera um novo arquivo final pronto para a Fase 5.

Uso:
  python3 aplicar_desempate.py \
      --consolidado output/fase4/anotacoes_consolidadas.json \
      --desempate desempate_2026-05-13.json \
      --output output/fase4/anotacoes_final.json
"""
import json
import argparse
import sys
from datetime import datetime


def main():
    ap = argparse.ArgumentParser(description="Aplica desempate humano no JSON consolidado")
    ap.add_argument("--consolidado", required=True, help="JSON consolidado original")
    ap.add_argument("--desempate", required=True, help="JSON exportado pelo HTML de revisão")
    ap.add_argument("--output", required=True, help="JSON final com decisões aplicadas")
    args = ap.parse_args()

    with open(args.consolidado, "r", encoding="utf-8") as f:
        cons = json.load(f)
    with open(args.desempate, "r", encoding="utf-8") as f:
        tie = json.load(f)

    decisions = tie.get("decisions", {})
    if not decisions:
        print("Aviso: arquivo de desempate não tem decisões. Saída idêntica ao consolidado.", file=sys.stderr)

    applied = 0
    skipped = 0
    for sid, dec in decisions.items():
        if sid not in cons["annotations"]:
            skipped += 1
            continue
        if not dec.get("label"):
            continue
        record = cons["annotations"][sid]
        record["label_before_tiebreak"] = record["label"]
        record["label"] = dec["label"]
        if dec.get("smells") is not None:  # revisor escolheu smells explicitamente
            record["smells_before_tiebreak"] = record.get("smells", [])
            record["smells"] = dec["smells"]
        record["resolution"] = "human_tiebreak"
        record["requires_review"] = False
        record["tiebreak_decided_at"] = dec.get("decided_at")

        # Determinar o motivo do desempate (usa flags originais do consolidado)
        had_label_conflict = record.get("label_conflict", False)
        had_smell_conflict = record.get("smells_conflict", False)
        if had_label_conflict and had_smell_conflict:
            record["tiebreak_reason"] = "both"
        elif had_smell_conflict:
            record["tiebreak_reason"] = "smells"
        elif had_label_conflict:
            record["tiebreak_reason"] = "label"
        else:
            record["tiebreak_reason"] = "unknown"
        if dec.get("notes"):
            existing_notes = record.get("notes", "")
            record["notes"] = (existing_notes + " | " if existing_notes else "") + "[desempate] " + dec["notes"]
        applied += 1

    cons["metadata"]["tiebreak_applied"] = True
    cons["metadata"]["tiebreak_applied_at"] = datetime.now().isoformat()
    cons["metadata"]["tiebreak_decisions_applied"] = applied
    cons["metadata"]["requires_review_count"] = sum(
        1 for v in cons["annotations"].values() if v.get("requires_review")
    )

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(cons, f, indent=2, ensure_ascii=False)

    print(f"✓ Desempate aplicado:")
    print(f"  Decisões aplicadas:    {applied}")
    print(f"  Decisões ignoradas:    {skipped} (snippet_id inexistente no consolidado)")
    print(f"  Ainda exigem revisão:  {cons['metadata']['requires_review_count']}")
    print(f"  Arquivo gerado: {args.output}")
    print(f"\nPróximo passo — Fase 5:")
    print(f"  python3 scripts/fase5_validar_dataset.py --annotations {args.output} --output output/fase5")


if __name__ == "__main__":
    main()
