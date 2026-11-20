"""Detecção de respostas e bounces lendo a caixa de entrada (IMAP do Gmail).

POR QUE EXISTE: sem medir, a gente fica no achismo ("será que caiu em spam?").
Este módulo olha a INBOX da conta de envio e:
  - marca "respondeu" quem respondeu (isso ENCERRA a cadência de follow-up);
  - marca "bounce" o que voltou (mailer-daemon), para nunca mais tentar.

Usa as MESMAS credenciais do envio (SMTP_USUARIO / SMTP_SENHA no .env). No Gmail
a "senha de app" também vale para IMAP. É só leitura — nada é apagado ou movido.
"""
from __future__ import annotations

import csv
import email
import imaplib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parseaddr
from pathlib import Path

from .config import Config
from .supressao import registrar_emails

IMAP_HOST = "imap.gmail.com"
_DAEMON = ("mailer-daemon@", "postmaster@")


@dataclass
class ResultadoRespostas:
    respostas: list[str]
    bounces: list[str]
    lidos: int
    erro: str = ""


def _arquivo(cfg: Config) -> Path:
    return cfg.root / "data" / "enviados.csv"


def _enviados_e_data(cfg: Config) -> tuple[set[str], datetime | None]:
    """(e-mails para quem enviamos, data do 1º envio) — só quem já recebeu algo."""
    p = _arquivo(cfg)
    enviados: set[str] = set()
    primeiro: datetime | None = None
    if not p.is_file():
        return enviados, primeiro
    with p.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            status = (row.get("status") or "enviado").strip().lower()
            if status != "enviado" and not status.startswith("followup"):
                continue
            e = (row.get("email") or "").strip().lower()
            if e:
                enviados.add(e)
            try:
                d = datetime.fromisoformat((row.get("data") or "").strip())
                d = d if d.tzinfo else d.replace(tzinfo=timezone.utc)
                primeiro = d if primeiro is None else min(primeiro, d)
            except ValueError:
                pass
    return enviados, primeiro


def _texto(msg: email.message.Message) -> str:
    """Concatena o texto do corpo (para achar o endereço que deu bounce)."""
    partes = []
    if msg.is_multipart():
        for p in msg.walk():
            if p.get_content_maintype() == "text" or "delivery-status" in (p.get_content_type() or ""):
                try:
                    partes.append(p.get_payload(decode=True).decode(errors="ignore"))
                except (AttributeError, TypeError):
                    pass
    else:
        try:
            partes.append(msg.get_payload(decode=True).decode(errors="ignore"))
        except (AttributeError, TypeError):
            pass
    return "\n".join(partes).lower()


def detectar(cfg: Config, dry_run: bool = False) -> ResultadoRespostas:
    user = cfg.env("SMTP_USUARIO")
    senha = cfg.env("SMTP_SENHA")
    if not user or not senha:
        return ResultadoRespostas([], [], 0, "Faltam SMTP_USUARIO/SMTP_SENHA no .env.")

    enviados, primeiro = _enviados_e_data(cfg)
    if not enviados:
        return ResultadoRespostas([], [], 0, "Ninguém contatado ainda (nada a checar).")

    try:
        M = imaplib.IMAP4_SSL(IMAP_HOST)
        M.login(user, senha)
    except imaplib.IMAP4.error as e:
        return ResultadoRespostas([], [], 0,
            f"Login IMAP falhou ({e}). No Gmail, ative o IMAP em Configurações > "
            f"Encaminhamento e POP/IMAP, e use a mesma senha de app do envio.")

    respostas: set[str] = set()
    bounces: set[str] = set()
    lidos = 0
    try:
        M.select("INBOX", readonly=True)
        criterio = "ALL"
        if primeiro:
            criterio = f'(SINCE "{primeiro.strftime("%d-%b-%Y")}")'
        typ, dados = M.search(None, criterio)
        ids = dados[0].split() if dados and dados[0] else []
        for num in ids:
            typ, raw = M.fetch(num, "(RFC822)")
            if typ != "OK" or not raw or not raw[0]:
                continue
            lidos += 1
            msg = email.message_from_bytes(raw[0][1])
            de = parseaddr(msg.get("From", ""))[1].strip().lower()
            if any(sig in de for sig in _DAEMON):
                # bounce: o endereço que falhou aparece no corpo/delivery-status
                corpo = _texto(msg)
                for alvo in enviados:
                    if alvo in corpo:
                        bounces.add(alvo)
            elif de in enviados:
                respostas.add(de)
    finally:
        try:
            M.logout()
        except Exception:
            pass

    respostas -= bounces          # se deu bounce, não conta como resposta
    if not dry_run:
        if respostas:
            registrar_emails(cfg, sorted(respostas), "respondeu")
        if bounces:
            registrar_emails(cfg, sorted(bounces), "bounce")
    return ResultadoRespostas(sorted(respostas), sorted(bounces), lidos)
