"""Registro de empresas já tratadas (suppression list), para NUNCA reenviar.

Grava em data/enviados.csv (cnpj, email, empresa, data, status). Status:
  enviado  -> e-mail disparado com sucesso
  invalido -> reprovado na validação real (não existe / risco) — não tentar de novo
  bounce   -> voltou (destinatário inexistente)
  optout   -> pediu para sair
Qualquer um deles é excluído nas próximas seleções.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

from .config import Config
from .storage.models import Lead


def _arquivo(cfg: Config) -> Path:
    return cfg.root / "data" / "enviados.csv"


def _digitos(s: str) -> str:
    return "".join(c for c in (s or "") if c.isdigit())


def carregar_suprimidos(cfg: Config) -> tuple[set[str], set[str]]:
    """(cnpjs, emails) já tratados antes — excluídos de novas seleções."""
    p = _arquivo(cfg)
    cnpjs: set[str] = set()
    emails: set[str] = set()
    if p.is_file():
        with p.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                if row.get("cnpj"):
                    cnpjs.add(_digitos(row["cnpj"]))
                if row.get("email"):
                    emails.add(row["email"].strip().lower())
    return cnpjs, emails


def ja_enviado(lead: Lead, cnpjs: set[str], emails: set[str]) -> bool:
    c = _digitos(lead.empresa.cnpj)
    e = (lead.contato.email or "").strip().lower()
    return bool((c and c in cnpjs) or (e and e in emails))


def enviados_hoje(cfg: Config) -> int:
    """Quantos e-mails saíram hoje (para respeitar o limite diário).

    Conta o 1º envio E os follow-ups: para a reputação do Gmail o que importa é
    quantas mensagens saíram, não se eram contato novo ou repetido.
    """
    p = _arquivo(cfg)
    if not p.is_file():
        return 0
    hoje = datetime.now(timezone.utc).date().isoformat()
    n = 0
    # utf-8-sig: se o arquivo tiver BOM, sem isto a 1ª coluna vira "﻿cnpj"
    # e a supressão por CNPJ para de funcionar silenciosamente.
    with p.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            status = row.get("status", "enviado")
            saiu = status == "enviado" or status.startswith("followup")
            if saiu and row.get("data", "").startswith(hoje):
                n += 1
    return n


def registrar(cfg: Config, leads: list[Lead], status: str = "enviado") -> int:
    """Adiciona leads ao CSV com um status. Retorna quantos gravou."""
    if not leads:
        return 0
    p = _arquivo(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    novo = not p.is_file()
    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with p.open("a", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        if novo:
            w.writerow(["cnpj", "email", "empresa", "data", "status"])
        for l in leads:
            w.writerow([l.empresa.cnpj, l.contato.email, l.empresa.nome, agora, status])
    return len(leads)


def registrar_emails(cfg: Config, emails: list[str], status: str) -> int:
    """Registra e-mails soltos (ex.: bounces informados manualmente)."""
    if not emails:
        return 0
    p = _arquivo(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    novo = not p.is_file()
    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with p.open("a", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        if novo:
            w.writerow(["cnpj", "email", "empresa", "data", "status"])
        for e in emails:
            w.writerow(["", e.strip().lower(), "", agora, status])
    return len(emails)
