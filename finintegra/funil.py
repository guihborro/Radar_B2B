"""Funil de prospecção: os números reais do que foi enviado e do que voltou.

É o passo 4 do framework do Alfredo Soares ("métricas de conversão e insights").
Lê data/enviados.csv e mostra o funil: contatos, follow-ups, respostas, bounces
e a taxa de resposta — comparada ao benchmark de mercado (3,4% em B2B).
"""
from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

from .config import Config

# Benchmarks 2026 (cold e-mail B2B) para dar contexto aos nossos números.
BENCH_RESPOSTA = 0.034     # 3,4% média; >5% é bom; 10%+ é topo
BENCH_BOUNCE_MAX = 0.04    # acima de 4% o Gmail começa a punir a reputação


def _linhas(cfg: Config) -> list[dict]:
    p = cfg.root / "data" / "enviados.csv"
    if not p.is_file():
        return []
    with p.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def calcular(cfg: Config) -> dict:
    linhas = _linhas(cfg)
    por_status: Counter[str] = Counter(
        (r.get("status") or "enviado").strip().lower() for r in linhas)

    enviados_1 = por_status.get("enviado", 0)
    fups = {n: por_status.get(f"followup{n}", 0) for n in (1, 2, 3)}
    total_fup = sum(fups.values())
    respostas = por_status.get("respondeu", 0)
    bounces = por_status.get("bounce", 0)
    invalidos = por_status.get("invalido", 0)
    optouts = por_status.get("optout", 0)
    msgs = enviados_1 + total_fup

    return {
        "contatos": enviados_1,
        "followups": fups,
        "total_followups": total_fup,
        "mensagens": msgs,
        "respostas": respostas,
        "bounces": bounces,
        "invalidos": invalidos,
        "optouts": optouts,
        "taxa_resposta": (respostas / enviados_1) if enviados_1 else 0.0,
        "taxa_bounce": (bounces / msgs) if msgs else 0.0,
    }


def _barra(valor: float, ref: float, larg: int = 24) -> str:
    cheio = min(larg, round((valor / ref) * larg)) if ref else 0
    return "█" * cheio + "·" * (larg - cheio)


def relatorio_texto(cfg: Config) -> str:
    d = calcular(cfg)
    if d["contatos"] == 0 and d["mensagens"] == 0:
        return "Nada enviado ainda. Rode 'rodar' primeiro."

    tr = d["taxa_resposta"]
    tb = d["taxa_bounce"]
    if tr == 0:
        veredito_tr = "sem respostas ainda (normal no começo: 50 envios × 3,4% ≈ 1-2)"
    elif tr >= 0.10:
        veredito_tr = "TOPO de mercado (10%+)"
    elif tr >= 0.05:
        veredito_tr = "BOM (acima de 5%)"
    elif tr >= BENCH_RESPOSTA:
        veredito_tr = "na média de mercado"
    else:
        veredito_tr = "abaixo da média (3,4%)"

    l = []
    l.append("FUNIL DE PROSPECÇÃO — FinIntegra")
    l.append("=" * 46)
    l.append(f"  1º e-mails enviados .......... {d['contatos']:>5}")
    for n in (1, 2, 3):
        l.append(f"    follow-up etapa {n} .......... {d['followups'][n]:>5}")
    l.append(f"  total de mensagens ........... {d['mensagens']:>5}")
    l.append("-" * 46)
    l.append(f"  RESPOSTAS .................... {d['respostas']:>5}")
    l.append(f"  bounces (voltaram) ........... {d['bounces']:>5}")
    l.append(f"  inválidos (barrados) ......... {d['invalidos']:>5}")
    l.append(f"  opt-out (pediram sair) ....... {d['optouts']:>5}")
    l.append("=" * 46)
    l.append(f"  TAXA DE RESPOSTA .... {tr*100:5.1f}%  [{_barra(tr, 0.10)}]")
    l.append(f"                        {veredito_tr}")
    l.append(f"  taxa de bounce ...... {tb*100:5.1f}%  "
             f"({'OK' if tb <= BENCH_BOUNCE_MAX else 'ALTO — pare e revise'} "
             f"| limite {BENCH_BOUNCE_MAX*100:.0f}%)")
    if d["contatos"] < 50:
        l.append("")
        l.append(f"  Nota: só {d['contatos']} contatos. A taxa só fica confiável "
                 f"com ~100+ envios.")
    return "\n".join(l)
