"""Persistência em SQLite (stdlib, zero dependência).

Repository é uma fachada fina. Trocar para Postgres depois é só reimplementar
esta classe mantendo a assinatura.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

from .models import Contato, Empresa, Lead, Mensagem


_SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    status          TEXT NOT NULL,
    tier            TEXT,
    canal           TEXT,
    motivo_rejeicao TEXT,
    opt_out         INTEGER DEFAULT 0,
    criado_em       TEXT,
    empresa         TEXT NOT NULL,   -- JSON
    contato         TEXT,            -- JSON
    mensagem        TEXT             -- JSON
);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
"""


class Repository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Repository":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # --- escrita --------------------------------------------------------------
    def upsert(self, lead: Lead) -> Lead:
        row = lead.to_row()
        if lead.id is None:
            cur = self._conn.execute(
                """INSERT INTO leads
                   (status,tier,canal,motivo_rejeicao,opt_out,criado_em,
                    empresa,contato,mensagem)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (row["status"], row["tier"], row["canal"], row["motivo_rejeicao"],
                 row["opt_out"], row["criado_em"], row["empresa"], row["contato"],
                 row["mensagem"]),
            )
            lead.id = int(cur.lastrowid)
        else:
            self._conn.execute(
                """UPDATE leads SET status=?,tier=?,canal=?,motivo_rejeicao=?,
                   opt_out=?,empresa=?,contato=?,mensagem=? WHERE id=?""",
                (row["status"], row["tier"], row["canal"], row["motivo_rejeicao"],
                 row["opt_out"], row["empresa"], row["contato"], row["mensagem"],
                 lead.id),
            )
        self._conn.commit()
        return lead

    def upsert_many(self, leads: Iterable[Lead]) -> list[Lead]:
        return [self.upsert(l) for l in leads]

    # --- leitura --------------------------------------------------------------
    def all(self) -> list[Lead]:
        rows = self._conn.execute("SELECT * FROM leads ORDER BY id").fetchall()
        return [_row_to_lead(r) for r in rows]

    def by_status(self, status: str) -> list[Lead]:
        rows = self._conn.execute(
            "SELECT * FROM leads WHERE status=? ORDER BY id", (status,)
        ).fetchall()
        return [_row_to_lead(r) for r in rows]

    def counts_by_status(self) -> dict[str, int]:
        rows = self._conn.execute(
            "SELECT status, COUNT(*) c FROM leads GROUP BY status"
        ).fetchall()
        return {r["status"]: r["c"] for r in rows}


def _row_to_lead(r: sqlite3.Row) -> Lead:
    empresa = Empresa(**json.loads(r["empresa"]))
    contato = Contato(**json.loads(r["contato"])) if r["contato"] else Contato()
    mensagem = Mensagem(**json.loads(r["mensagem"])) if r["mensagem"] else None
    return Lead(
        id=r["id"],
        status=r["status"],
        tier=r["tier"] or "",
        canal=r["canal"] or "",
        motivo_rejeicao=r["motivo_rejeicao"] or "",
        opt_out=bool(r["opt_out"]),
        criado_em=r["criado_em"] or "",
        empresa=empresa,
        contato=contato,
        mensagem=mensagem,
    )
