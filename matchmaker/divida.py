"""Marca no índice quais empresas têm DÍVIDA ATIVA federal (dados abertos PGFN).

Lê os CSVs da PGFN (SIDA / Previdenciário / FGTS), pega os CNPJ de pessoa
jurídica (que NÃO vêm mascarados), extrai a base (8 primeiros dígitos) e marca
`divida_ativa=1` na tabela `empresas`. É um UPDATE rápido — NÃO reindexa.

Rodar (depois do reindex do Nível 2 estar pronto):
    python -m matchmaker.divida
Coloque as pastas Dados_abertos_* na raiz do projeto (ou em data/pgfn/).
"""
from __future__ import annotations

import csv
import sqlite3
import time
from pathlib import Path

from finintegra.config import load_config

csv.field_size_limit(10_000_000)
_PASTAS = ("Dados_abertos_Nao_Previdenciario", "Dados_abertos_Previdenciario",
           "Dados_abertos_FGTS", "pgfn")


def _csvs(root: Path) -> list[Path]:
    achados: list[Path] = []
    for base in (root, root / "data"):
        for p in _PASTAS:
            achados += sorted((base / p).glob("*.csv")) if (base / p).is_dir() else []
    # dedup mantendo ordem
    vistos, out = set(), []
    for a in achados:
        if a not in vistos:
            vistos.add(a); out.append(a)
    return out


def _bases_devedoras(root: Path) -> set[str]:
    bases: set[str] = set()
    arquivos = _csvs(root)
    if not arquivos:
        raise FileNotFoundError("Nenhum CSV da PGFN encontrado (Dados_abertos_* ou data/pgfn/).")
    for arq in arquivos:
        with arq.open(encoding="latin-1", newline="") as fh:
            rd = csv.reader(fh, delimiter=";")
            next(rd, None)                    # cabeçalho
            for r in rd:
                if len(r) < 2 or "jur" not in r[1].lower():   # só Pessoa jurídica
                    continue
                dig = "".join(c for c in r[0] if c.isdigit())
                if len(dig) >= 8:
                    bases.add(dig[:8])
        print(f"  lido: {arq.name} (acumulado {len(bases):,} bases)", flush=True)
    return bases


def marcar() -> None:
    cfg = load_config()
    db = cfg.root / "data" / "matchmaker.sqlite"
    t0 = time.time()

    bases = _bases_devedoras(cfg.root)
    print(f"CNPJs (bases) devedores únicos: {len(bases):,} ({time.time()-t0:.0f}s)", flush=True)

    con = sqlite3.connect(db)
    con.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF; PRAGMA temp_store=FILE;")
    cur = con.cursor()
    cur.execute("DROP TABLE IF EXISTS div")
    cur.execute("CREATE TABLE div(base TEXT PRIMARY KEY)")
    buf = []
    for b in bases:
        buf.append((b,))
        if len(buf) >= 200_000:
            cur.executemany("INSERT OR IGNORE INTO div VALUES(?)", buf); buf = []
    if buf:
        cur.executemany("INSERT OR IGNORE INTO div VALUES(?)", buf)
    con.commit()

    cur.execute("CREATE INDEX IF NOT EXISTS ix_base ON empresas(base)")
    cur.execute("UPDATE empresas SET divida_ativa=0")
    cur.execute("UPDATE empresas SET divida_ativa=1 WHERE base IN (SELECT base FROM div)")
    con.commit()
    cur.execute("DROP TABLE div")

    com = cur.execute("SELECT COUNT(*) FROM empresas WHERE divida_ativa=1").fetchone()[0]
    tot = cur.execute("SELECT COUNT(*) FROM empresas").fetchone()[0]
    con.execute("VACUUM")
    con.close()
    print(f"PRONTO: {com:,} de {tot:,} empresas com dívida ativa federal "
          f"({100*com/tot:.1f}%) — {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    marcar()
