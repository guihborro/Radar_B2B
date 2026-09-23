"""Cadência de follow-up: o 2º, 3º e 4º contato com quem já recebeu o 1º e-mail.

POR QUE EXISTE: campanha de 1 e-mail responde ~3,0%; com 3 e-mails vai a ~5,8%.
58% das respostas vêm do 1º e-mail, mas 42% vêm dos follow-ups. Mandar UM
e-mail e nunca mais voltar joga fora quase metade do resultado possível.

CUSTO ZERO: o follow-up vai para um e-mail que já foi validado no 1º envio,
então não consome crédito do verificador.

COMO FUNCIONA: o histórico vem de data/enviados.csv. O 1º envio grava status
"enviado"; cada follow-up grava "followup1"/"followup2"/... A etapa devida sai
de quantos follow-ups já foram somados aos dias desde o 1º envio (cadência em
config/followup.yaml). Quem deu bounce, pediu opt-out, foi marcado inválido ou
RESPONDEU sai da sequência e nunca mais recebe nada.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .config import Config
from .messaging.render import render_followup
from .storage.models import Contato, Empresa, Lead

# Status que ENCERRAM a sequência — o lead nunca mais recebe follow-up.
_ENCERRA = {"bounce", "optout", "invalido", "respondeu"}


def _arquivo(cfg: Config) -> Path:
    return cfg.root / "data" / "enviados.csv"


def _config(cfg: Config) -> dict:
    p = cfg.root / "config" / "followup.yaml"
    if not p.is_file():
        return {}
    with p.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _data(s: str) -> datetime | None:
    try:
        d = datetime.fromisoformat((s or "").strip())
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _historico(cfg: Config) -> dict[str, dict]:
    """e-mail -> {cnpj, empresa, primeiro_envio, n_followups, encerrado}."""
    p = _arquivo(cfg)
    hist: dict[str, dict] = {}
    if not p.is_file():
        return hist
    with p.open(encoding="utf-8-sig", newline="") as fh:   # tolera BOM
        for row in csv.DictReader(fh):
            email = (row.get("email") or "").strip().lower()
            if not email:
                continue
            h = hist.setdefault(email, {
                "email": email, "cnpj": "", "empresa": "",
                "primeiro_envio": None, "n_followups": 0, "encerrado": False,
            })
            status = (row.get("status") or "enviado").strip().lower()
            quando = _data(row.get("data", ""))
            if status in _ENCERRA:
                h["encerrado"] = True
            elif status == "enviado":
                # o 1º envio é a âncora da cadência (o mais antigo vence)
                if h["primeiro_envio"] is None or (quando and quando < h["primeiro_envio"]):
                    h["primeiro_envio"] = quando
                h["cnpj"] = row.get("cnpj") or h["cnpj"]
                h["empresa"] = row.get("empresa") or h["empresa"]
            elif status.startswith("followup"):
                h["n_followups"] += 1
    return hist


def _indice_fila(cfg: Config) -> dict[str, Lead]:
    """e-mail -> Lead completo (com CNAE) vindo da fila já ranqueada."""
    from .fila import ler_fila
    idx: dict[str, Lead] = {}
    for l in ler_fila(cfg):
        e = (l.contato.email or "").strip().lower()
        if e:
            idx[e] = l
    return idx


def _lead_de(h: dict, idx: dict[str, Lead]) -> Lead:
    lead = idx.get(h["email"])
    if lead is None:
        # envio anterior à fila: sem CNAE, o template cai no genérico da indústria
        lead = Lead(empresa=Empresa(nome=h["empresa"] or "", cnpj=h["cnpj"] or ""),
                    contato=Contato(email=h["email"]))
    # o e-mail já foi validado e entregue no 1º envio — libera a guarda de envio
    lead.canal = "email"
    lead.contato.email_status = "valid"
    return lead


def devidos(cfg: Config, limite: int | None = None) -> list[tuple[Lead, int]]:
    """(lead, etapa) de quem está no prazo de receber o próximo follow-up.

    Já vem com `lead.mensagem` renderizada. Ordena os mais adiantados na
    sequência primeiro (contato mais quente, e fecha o ciclo antes de abrir
    novos).
    """
    conf = _config(cfg)
    cadencia = conf.get("cadencia_dias") or []
    etapas = conf.get("etapas") or []
    n_etapas = min(len(cadencia), len(etapas))
    if not n_etapas:
        return []

    # MESMA régua de qualidade da seleção: a base tem centenas de envios antigos,
    # feitos antes dos filtros, para contador/terceiro (fiscal@, contabilidade@,
    # escritório que atende várias empresas). Insistir com esses queima cota e
    # reputação, então eles não entram na cadência.
    from .export_html import _email_da_empresa

    agora = datetime.now(timezone.utc)
    idx = _indice_fila(cfg)
    saida: list[tuple[Lead, int]] = []
    for h in _historico(cfg).values():
        if h["encerrado"] or h["primeiro_envio"] is None:
            continue
        n = h["n_followups"]
        if n >= n_etapas:
            continue                                    # sequência concluída
        if (agora - h["primeiro_envio"]).days < cadencia[n]:
            continue                                    # ainda não chegou o dia
        lead = _lead_de(h, idx)
        if not _email_da_empresa(lead):
            continue                                    # e-mail de terceiro
        lead.mensagem = render_followup(lead, cfg, etapas[n], n + 1)
        saida.append((lead, n + 1))

    saida.sort(key=lambda t: -t[1])
    return saida[:limite] if limite is not None else saida


def agenda(cfg: Config) -> list[dict]:
    """Panorama da cadência (para o comando `followups`): quem está em qual
    etapa e quantos dias faltam para o próximo contato."""
    from .export_html import _email_da_empresa

    conf = _config(cfg)
    cadencia = conf.get("cadencia_dias") or []
    n_etapas = min(len(cadencia), len(conf.get("etapas") or []))
    agora = datetime.now(timezone.utc)
    idx = _indice_fila(cfg)
    linhas: list[dict] = []
    for h in _historico(cfg).values():
        if h["primeiro_envio"] is None:
            continue
        n = h["n_followups"]
        dias = (agora - h["primeiro_envio"]).days
        if not _email_da_empresa(_lead_de(h, idx)):
            # envio antigo para contador/terceiro: fora da cadência
            situacao, faltam = "fora_padrao", None
        elif h["encerrado"]:
            situacao, faltam = "encerrado", None
        elif n >= n_etapas:
            situacao, faltam = "concluido", None
        else:
            faltam = cadencia[n] - dias
            situacao = "devido" if faltam <= 0 else "aguardando"
        linhas.append({"email": h["email"], "empresa": h["empresa"],
                       "etapas_enviadas": n, "dias": dias,
                       "situacao": situacao, "faltam": faltam})
    linhas.sort(key=lambda d: (d["situacao"] != "devido", d["faltam"] if d["faltam"] is not None else 999))
    return linhas
