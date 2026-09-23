"""Indexa a Receita COMPLETA em um SQLite para busca instantânea.

Lê uma vez os ~23 GB de CSV (Estabelecimentos + Empresas + Sócios + Simples),
junta tudo e grava data/matchmaker.sqlite com índices. Depois, o matchmaker
consulta o banco em milissegundos em vez de varrer os arquivos a cada busca.

Constrói num .tmp e só troca no fim, então o site continua no ar durante o
reindex. Rodar (da raiz do workspace):  python -m matchmaker.indexar
É demorado (roda UMA vez). Reexecute só quando baixar dados novos da Receita.
"""
from __future__ import annotations

import csv
import sqlite3
import time
from pathlib import Path

from finintegra.config import load_config

csv.field_size_limit(10_000_000)
PORTE = {"01": "ME", "03": "EPP", "05": "Demais", "00": ""}
LOTE = 200_000


def _files(pasta: Path, *pats: str) -> list[Path]:
    out: list[Path] = []
    for p in pats:
        out += sorted(pasta.glob(p))
    return out


def _rows(path: Path):
    with path.open(encoding="latin-1", newline="") as fh:
        yield from csv.reader(fh, delimiter=";", quotechar='"')


def _capital(v: str):
    v = (v or "").strip().replace(".", "").replace(",", ".")
    try:
        return float(v) if v else None
    except ValueError:
        return None


def _ano(v: str):
    v = (v or "").strip()
    if len(v) >= 4 and v[:4].isdigit():
        a = int(v[:4])
        return a if 1900 <= a <= 2100 else None
    return None


def _so_digitos(v: str) -> str:
    return "".join(c for c in (v or "") if c.isdigit())


def _cnae_sec(v: str) -> str:
    """Lista de CNAEs secundários -> ',4711302,4930201,' (delimitado p/ filtrar)."""
    codes = [c for c in "".join(
        ch for ch in (v or "") if ch.isdigit() or ch == ",").split(",") if c]
    return ("," + ",".join(codes) + ",") if codes else ""


def _municipios(pasta: Path) -> dict[str, str]:
    d: dict[str, str] = {}
    for f in _files(pasta, "*MUNICCSV"):
        for r in _rows(f):
            if len(r) >= 2 and r[0].strip():
                d[r[0].strip()] = r[1].strip()
    return d


def build() -> None:
    cfg = load_config()
    pasta = cfg.root / "data" / "receita"
    db = cfg.root / "data" / "matchmaker.sqlite"
    tmp = db.with_name("matchmaker.sqlite.tmp")
    if tmp.exists():
        tmp.unlink()
    con = sqlite3.connect(tmp)
    con.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF; "
                      "PRAGMA temp_store=FILE; PRAGMA cache_size=-500000;")
    cur = con.cursor()
    t0 = time.time()

    def dt() -> str:
        return f"{time.time()-t0:.0f}s"

    munis = _municipios(pasta)
    print(f"municipios: {len(munis)} ({dt()})", flush=True)

    # --- EMPRESAS: base -> razão/natureza/capital/porte ---------------------
    cur.execute("CREATE TABLE emp(base TEXT PRIMARY KEY, razao TEXT, natureza TEXT, "
                "capital REAL, porte TEXT)")
    n, buf = 0, []
    for f in _files(pasta, "*.EMPRECSV"):
        for r in _rows(f):
            if len(r) < 6:
                continue
            buf.append((r[0], r[1].strip(), r[2].strip(), _capital(r[4]),
                        PORTE.get(r[5].strip(), "")))
            if len(buf) >= LOTE:
                cur.executemany("INSERT OR REPLACE INTO emp VALUES(?,?,?,?,?)", buf)
                n += len(buf); buf = []
    if buf:
        cur.executemany("INSERT OR REPLACE INTO emp VALUES(?,?,?,?,?)", buf); n += len(buf)
    con.commit()
    print(f"EMPRESAS: {n:,} ({dt()})", flush=True)

    # --- SÓCIOS: 1º sócio PF (decisor) + todos (p/ contar e achar estrangeiro) --
    cur.execute("CREATE TABLE soc(base TEXT PRIMARY KEY, nome TEXT)")
    cur.execute("CREATE TABLE soc_all(base TEXT, ident TEXT)")
    n, buf_pf, buf_all = 0, [], []
    for f in _files(pasta, "*.SOCIOCSV"):
        for r in _rows(f):
            if len(r) <= 2:
                continue
            ident = r[1].strip()
            buf_all.append((r[0], ident))
            if ident == "2":
                buf_pf.append((r[0], r[2].strip().title()))
            n += 1
            if len(buf_all) >= LOTE:
                cur.executemany("INSERT INTO soc_all VALUES(?,?)", buf_all); buf_all = []
            if len(buf_pf) >= LOTE:
                cur.executemany("INSERT OR IGNORE INTO soc VALUES(?,?)", buf_pf); buf_pf = []
    if buf_all:
        cur.executemany("INSERT INTO soc_all VALUES(?,?)", buf_all)
    if buf_pf:
        cur.executemany("INSERT OR IGNORE INTO soc VALUES(?,?)", buf_pf)
    con.commit()
    print(f"SOCIOS: {n:,} linhas ({dt()})", flush=True)
    # stats por base: nº de sócios + tem sócio estrangeiro (ident=3)
    cur.execute("CREATE TABLE soc_stats AS SELECT base, COUNT(*) AS n_socios, "
                "MAX(CASE WHEN ident='3' THEN 1 ELSE 0 END) AS estrangeiro "
                "FROM soc_all GROUP BY base")
    cur.execute("CREATE UNIQUE INDEX ix_socstats ON soc_stats(base)")
    cur.execute("DROP TABLE soc_all")
    con.commit()
    print(f"soc_stats pronto ({dt()})", flush=True)

    # --- SIMPLES: base -> optante (Simples ou MEI) --------------------------
    cur.execute("CREATE TABLE sim(base TEXT PRIMARY KEY, opt INTEGER)")
    n, buf = 0, []
    for f in _files(pasta, "*SIMPLES*"):
        for r in _rows(f):
            if len(r) >= 5:
                opt = 1 if (r[1].strip() == "S" or r[4].strip() == "S") else 0
                buf.append((r[0], opt))
                if len(buf) >= LOTE:
                    cur.executemany("INSERT OR IGNORE INTO sim VALUES(?,?)", buf)
                    n += len(buf); buf = []
    if buf:
        cur.executemany("INSERT OR IGNORE INTO sim VALUES(?,?)", buf); n += len(buf)
    con.commit()
    print(f"SIMPLES: {n:,} ({dt()})", flush=True)

    # --- ESTABELECIMENTOS ativos -> staging ---------------------------------
    cur.execute("CREATE TABLE estab(base TEXT, cnpj TEXT, fantasia TEXT, cnae TEXT, "
                "cnae_sec TEXT, cep TEXT, uf TEXT, cidade TEXT, matriz INTEGER, "
                "ano INTEGER, email TEXT, dominio TEXT, telefone TEXT)")
    n, buf = 0, []
    for f in _files(pasta, "*.ESTABELE"):
        for r in _rows(f):
            if len(r) <= 27 or r[5] != "02":     # só situação ativa
                continue
            base = r[0]
            cnpj = f"{base[:2]}.{base[2:5]}.{base[5:8]}/{r[1]}-{r[2]}"
            cnae = "".join(c for c in r[11] if c.isdigit())
            email = r[27].strip().lower()
            dom = email.split("@", 1)[1] if "@" in email else ""
            tel = f"+55 {r[21].strip()} {r[22].strip()}".strip() if r[22].strip() else ""
            buf.append((base, cnpj, r[4].strip(), cnae, _cnae_sec(r[12]),
                        _so_digitos(r[18]), r[19].strip().upper(),
                        munis.get(r[20].strip(), ""),
                        1 if r[3].strip() == "1" else 0, _ano(r[10]), email, dom, tel))
            if len(buf) >= LOTE:
                cur.executemany("INSERT INTO estab VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", buf)
                n += len(buf); buf = []
        print(f"  estab {f.name}: {n:,} ({dt()})", flush=True)
    if buf:
        cur.executemany("INSERT INTO estab VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", buf); n += len(buf)
    con.commit()
    print(f"ESTABELECIMENTOS ativos: {n:,} ({dt()})", flush=True)
    # nº de estabelecimentos ativos por base (rede/franquia)
    cur.execute("CREATE TABLE estab_stats AS SELECT base, COUNT(*) AS n_estab "
                "FROM estab GROUP BY base")
    cur.execute("CREATE UNIQUE INDEX ix_estabstats ON estab_stats(base)")
    con.commit()
    print(f"estab_stats pronto ({dt()})", flush=True)

    # --- JOIN final ---------------------------------------------------------
    print("montando tabela final (join)...", flush=True)
    cur.execute("""CREATE TABLE empresas AS
        SELECT e.base, e.cnpj,
               COALESCE(NULLIF(emp.razao,''), e.fantasia) AS nome,
               e.cnae, e.cnae_sec, e.cep, e.uf, e.cidade, e.matriz, e.ano,
               e.email, e.dominio, e.telefone,
               emp.capital, emp.porte, emp.natureza,
               soc.nome AS decisor, COALESCE(sim.opt,0) AS simples,
               COALESCE(ss.n_socios,0) AS n_socios,
               COALESCE(ss.estrangeiro,0) AS estrangeiro,
               COALESCE(est.n_estab,1) AS n_estab,
               0 AS divida_ativa
        FROM estab e
        LEFT JOIN emp ON emp.base=e.base
        LEFT JOIN soc ON soc.base=e.base
        LEFT JOIN sim ON sim.base=e.base
        LEFT JOIN soc_stats ss ON ss.base=e.base
        LEFT JOIN estab_stats est ON est.base=e.base""")
    con.commit()
    print(f"tabela empresas criada ({dt()})", flush=True)

    cur.executescript("DROP TABLE estab; DROP TABLE emp; DROP TABLE soc; "
                      "DROP TABLE sim; DROP TABLE soc_stats; DROP TABLE estab_stats;")
    print("criando índices...", flush=True)
    cur.execute("CREATE INDEX ix_cnae ON empresas(cnae)")
    cur.execute("CREATE INDEX ix_uf ON empresas(uf)")
    cur.execute("CREATE INDEX ix_cidade ON empresas(cidade)")
    cur.execute("CREATE INDEX ix_uf_cnae ON empresas(uf, cnae)")
    con.commit()
    print(f"índices ok, compactando (VACUUM)... ({dt()})", flush=True)
    cur.execute("VACUUM")
    total = cur.execute("SELECT COUNT(*) FROM empresas").fetchone()[0]
    con.close()

    # troca o banco antigo pelo novo só agora (site ficou no ar o tempo todo)
    db.unlink(missing_ok=True)
    tmp.rename(db)
    mb = db.stat().st_size / 1024 / 1024
    print(f"PRONTO: {total:,} empresas em {db.name} ({mb:,.0f} MB) — {dt()}", flush=True)


if __name__ == "__main__":
    build()
