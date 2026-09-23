"""Camada de armazenamento (SQLite no início, Postgres depois)."""

from .models import Channel, Contato, Empresa, Lead, LeadStatus, Mensagem
from .db import Repository

__all__ = [
    "Channel",
    "Contato",
    "Empresa",
    "Lead",
    "LeadStatus",
    "Mensagem",
    "Repository",
]
