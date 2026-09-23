"""Pipeline de recomendação: critérios do cliente -> tabela ranqueada da Receita.

NÃO é ML (não temos histórico de 'deu match' para treinar). É um motor de
PONTUAÇÃO por regras, transparente: cada empresa ganha um score 0-100 explicável,
somando sinais de encaixe (porte, capital, contato, tempo de mercado). Reusa o
provedor da Receita e os filtros de qualidade do FinIntegra.
"""
from __future__ import annotations

import sqlite3
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from urllib.parse import quote

from finintegra.config import load_config
from finintegra.sourcing.base import ICPFilter
from finintegra.sourcing.receita import ReceitaFederalProvider
from finintegra.export_html import (
    _dominio_proprio, _em_dificuldade, _nome_no_dominio,
)
from finintegra.messaging.render import _empresa_exibicao
from . import lookups, setores, verificar


def _site(nome: str, dominio: str) -> str:
    """URL do site: usa o domínio da empresa quando é próprio; se não temos, cai
    numa BUSCA no Google pelo site oficial. A coluna sempre tem um link útil."""
    dom = (dominio or "").lower().strip()
    if dom and _dominio_proprio(dom):
        return f"https://{dom}"
    limpo = _empresa_exibicao(nome) or nome
    return "https://www.google.com/search?q=" + quote(f"{limpo} site oficial")


def _norm(s: str) -> str:
    """minúsculas + sem acento — para comparar nome de cidade digitado x base."""
    nfkd = unicodedata.normalize("NFKD", (s or "").strip().lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


# natureza jurídica (Receita): grupo amigável -> códigos aceitos
_NATUREZA = {
    "ltda": {"2062"},                 # Sociedade Empresária Limitada
    "sa": {"2046", "2054"},           # S.A. (Fechada + Aberta)
    "sa_aberta": {"2054"},
    "sa_fechada": {"2046"},
    "eireli": {"2305"},               # EIRELI
    "cooperativa": {"2143"},
    "associacao": {"3999"},           # Associação privada
    "empresario": {"2135"},           # Empresário individual
}


@dataclass
class Criterios:
    setores_ids: list[str]
    ufs: list[str] = field(default_factory=list)         # vazio = Brasil todo
    # cidade POR ESTADO: {UF: [cidades]}. UF com lista = restringe; UF sem = todas.
    cidades_uf: dict = field(default_factory=dict)
    portes: list[str] = field(default_factory=list)      # 01/03/05; vazio = todos
    capital_min: float = 0.0
    capital_max: float = 0.0                             # 0 = sem teto
    idade_min: int = 0
    idade_max: int = 0                                   # 0 = sem teto
    natureza: str = ""                                   # "" = todas | ver _NATUREZA
    so_matriz: bool = False                              # só matriz
    so_filial: bool = False                              # só filiais
    so_simples: bool = False                             # só optantes do Simples/MEI
    excluir_simples: bool = False                        # sem Simples (só lucro real/maiores)
    so_decisor: bool = False                             # só com nome do sócio/decisor
    exigir_email: bool = False
    exigir_telefone: bool = False
    exigir_dominio: bool = False
    excluir_mei: bool = True
    excluir_recjud: bool = True
    verificar_site: bool = True                          # só linka site que está no ar
    # --- Nível 2 + Dívida (do reindex 2026-08) ---
    setores_sec_ids: list[str] = field(default_factory=list)  # CNAE secundário (faz TAMBÉM)
    n_estab_min: int = 0                                 # rede/franquia: mín. de estabelecimentos
    socios_min: int = 0
    socios_max: int = 0
    so_estrangeiro: bool = False                         # tem sócio estrangeiro (multinacional)
    cep_prefixo: str = ""                                # começo do CEP (região dentro da cidade)
    divida: str = ""                                     # "" | "sem" | "com" dívida ativa
    n: int = 50

    @property
    def cnaes(self) -> list[str]:
        return setores.cnaes_de(self.setores_ids)

    @property
    def cnaes_sec(self) -> list[str]:
        return setores.cnaes_de(self.setores_sec_ids)


def _fmt_capital(v) -> str:
    if not v:
        return "—"
    if v >= 1_000_000_000:
        return f"R$ {v/1_000_000_000:.1f} bi".replace(".", ",")
    if v >= 1_000_000:
        return f"R$ {v/1_000_000:.1f}M".replace(".", ",")
    if v >= 1_000:
        return f"R$ {v/1_000:.0f} mil"
    return f"R$ {v:.0f}"


def _score(lead, crit: Criterios) -> tuple[int, list[str]]:
    """Score 0-100 + motivos legíveis. Cada sinal soma pontos de encaixe."""
    e, c = lead.empresa, lead.contato
    s, motivos = 0, []

    cap = e.capital_social or 0
    if cap >= 1_000_000:
        s += 28; motivos.append(f"capital {_fmt_capital(cap)}")
    elif cap >= 300_000:
        s += 20; motivos.append(f"capital {_fmt_capital(cap)}")
    elif cap >= 100_000:
        s += 12; motivos.append(f"capital {_fmt_capital(cap)}")
    elif cap > 0:
        s += 5

    if e.porte == "Demais":
        s += 16; motivos.append("porte grande")
    elif e.porte == "EPP":
        s += 10; motivos.append("porte médio")
    elif e.porte == "ME":
        s += 4

    if c.email_candidatos:
        s += 12; motivos.append("tem e-mail")
    if c.telefone:
        s += 8; motivos.append("tem telefone")

    dom = (e.dominio or "").lower()
    if dom and _dominio_proprio(dom) and _nome_no_dominio(e.nome, dom):
        s += 16; motivos.append("domínio próprio")

    if e.fundacao_ano:
        idade = date.today().year - e.fundacao_ano
        if idade >= 15:
            s += 12; motivos.append(f"{idade} anos de mercado")
        elif idade >= 8:
            s += 7; motivos.append(f"{idade} anos")
        elif idade >= 3:
            s += 3

    return min(100, s), motivos


_PORTE_LBL = {"01": "ME", "03": "EPP", "05": "Demais"}


def _db_path():
    return load_config().root / "data" / "matchmaker.sqlite"


def _db_pronto(db) -> bool:
    """True só quando a indexação TERMINOU (o índice ix_cnae é o último passo).
    Durante a construção o arquivo existe mas está incompleto — aí usamos o CSV."""
    if not db.is_file():
        return False
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=1)
        r = con.execute("SELECT 1 FROM sqlite_master "
                        "WHERE type='index' AND name='ix_cnae'").fetchone()
        con.close()
        return bool(r)
    except sqlite3.Error:
        return False


def recomendar(crit: Criterios) -> list[dict]:
    """Ponto de entrada. Usa o índice SQLite (instantâneo) quando pronto; senão,
    cai no caminho antigo que varre os CSV da Receita."""
    if not crit.cnaes:
        return []
    db = _db_path()
    if _db_pronto(db):
        return _recomendar_sqlite(crit, db)
    return _recomendar_csv(crit)


def _recomendar_csv(crit: Criterios) -> list[dict]:
    """Fallback: varre os CSV da Receita (lento). Usado só sem o índice SQLite."""
    if not crit.cnaes:
        return []

    cfg = load_config()
    r = cfg.raw.setdefault("receita", {})
    r["portes"] = list(crit.portes)
    r["capital_social_min"] = crit.capital_min
    r["excluir_empresario_individual"] = crit.excluir_mei
    r["situacao_ativa"] = True
    cfg.raw.setdefault("ferramentas", {})["provedor_dados"] = "receita"

    # puxa bastante (oversample) porque os filtros pós-busca cortam parte
    f = ICPFilter(cnaes=crit.cnaes, regioes=list(crit.ufs),
                  limite=max(crit.n * 6, 120))
    leads = ReceitaFederalProvider(cfg).search(f)

    munis = lookups.municipios()
    cidades_alvo = [_norm(c) for cids in crit.cidades_uf.values() for c in cids]
    hoje = date.today().year
    linhas: list[dict] = []
    for lead in leads:
        e, c = lead.empresa, lead.contato
        nome = (e.nome or "").strip()
        if not nome or nome == "(sem nome)":     # sem razão social/fantasia: inútil
            continue
        cidade = munis.get(e.municipio_cod, "")
        if cidades_alvo and not any(ca in _norm(cidade) for ca in cidades_alvo):
            continue
        if crit.excluir_recjud and _em_dificuldade(e.nome):
            continue
        if crit.so_matriz and not e.matriz:
            continue
        if crit.so_filial and e.matriz:
            continue
        cap = e.capital_social or 0
        if crit.capital_max and cap > crit.capital_max:
            continue
        if crit.natureza and e.natureza not in _NATUREZA.get(crit.natureza, set()):
            continue
        tem_email = bool(c.email_candidatos)
        if crit.exigir_email and not tem_email:
            continue
        if crit.exigir_telefone and not c.telefone:
            continue
        dom = (e.dominio or "").lower()
        dom_proprio = bool(dom and _dominio_proprio(dom) and _nome_no_dominio(e.nome, dom))
        if crit.exigir_dominio and not dom_proprio:
            continue
        idade = (hoje - e.fundacao_ano) if e.fundacao_ano else None
        if crit.idade_min and (idade is None or idade < crit.idade_min):
            continue
        if crit.idade_max and idade is not None and idade > crit.idade_max:
            continue

        score, _ = _score(lead, crit)
        linhas.append({
            "empresa": e.nome,
            "setor": setores.nome_do_cnae(e.cnae),
            "cnpj": e.cnpj,
            "cidade": cidade.title() if cidade else "—",
            "uf": e.uf,
            "porte": e.porte or "—",
            "capital": _fmt_capital(e.capital_social),
            "idade": f"{idade} anos" if idade is not None else "—",
            "decisor": c.nome or "—",
            "email": (c.email_candidatos or [""])[0],
            "telefone": c.telefone or "—",
            "site": _site(e.nome, e.dominio),
            "score": score,
        })

    linhas.sort(key=lambda d: d["score"], reverse=True)
    return linhas[: crit.n]


# faixas de capital (limite, pontos) — escala FINA para não saturar no topo
_CAP_FAIXAS = ((100_000_000, 40), (50_000_000, 36), (10_000_000, 32),
               (5_000_000, 28), (1_000_000, 24), (500_000, 18),
               (300_000, 14), (100_000, 9), (1, 3))


def _score_row(r, hoje: int, dom_prop: bool) -> tuple[int, list[str]]:
    """Pontua uma linha do SQLite. Capital em escala fina + desempate por capital
    (feito no ORDER BY / sort) para o ranking não ficar todo igual no topo."""
    s, motivos = 0, []
    cap = r["capital"] or 0
    for lim, pts in _CAP_FAIXAS:
        if cap >= lim:
            s += pts
            break
    if cap > 0:
        motivos.append(f"capital {_fmt_capital(cap)}")
    porte = r["porte"] or ""
    if porte == "Demais":
        s += 12; motivos.append("porte grande")
    elif porte == "EPP":
        s += 8; motivos.append("porte médio")
    elif porte == "ME":
        s += 3
    if r["email"]:
        s += 10; motivos.append("tem e-mail")
    if r["telefone"]:
        s += 6; motivos.append("tem telefone")
    if dom_prop:
        s += 14; motivos.append("domínio próprio")
    if r["ano"]:
        idade = hoje - r["ano"]
        if idade >= 25:
            s += 14; motivos.append(f"{idade} anos de mercado")
        elif idade >= 15:
            s += 10; motivos.append(f"{idade} anos de mercado")
        elif idade >= 8:
            s += 6; motivos.append(f"{idade} anos")
        elif idade >= 3:
            s += 2
    return min(100, s), motivos


def _recomendar_sqlite(crit: Criterios, db) -> list[dict]:
    """Consulta o índice SQLite: filtra em SQL (rápido), ranqueia e devolve N."""
    import sqlite3

    hoje = date.today().year
    where = ["nome IS NOT NULL", "nome <> ''", "nome <> '(sem nome)'"]
    params: list = []

    ors = []
    for c in crit.cnaes:
        ors.append("cnae GLOB ?"); params.append(c + "*")
    where.append("(" + " OR ".join(ors) + ")")

    if crit.ufs and crit.cidades_uf:
        # cidade POR ESTADO: UF com cidades escolhidas restringe; UF sem = todas
        parts = []
        for uf in crit.ufs:
            u = uf.upper()
            cids = crit.cidades_uf.get(u, [])
            if cids:
                city_ors = " OR ".join("cidade = ?" for _ in cids)
                parts.append(f"(uf=? AND ({city_ors}))")
                params.append(u); params += [_norm(c).upper() for c in cids]
            else:
                parts.append("uf=?"); params.append(u)
        where.append("(" + " OR ".join(parts) + ")")
    elif crit.ufs:
        where.append("uf IN (%s)" % ",".join("?" * len(crit.ufs)))
        params += [u.upper() for u in crit.ufs]
    if crit.portes:
        labels = [_PORTE_LBL[p] for p in crit.portes if p in _PORTE_LBL]
        if labels:
            where.append("porte IN (%s)" % ",".join("?" * len(labels))); params += labels
    if crit.so_matriz:
        where.append("matriz=1")
    if crit.so_filial:
        where.append("matriz=0")
    if crit.so_simples:
        where.append("simples=1")
    if crit.excluir_simples:
        where.append("simples=0")
    if crit.so_decisor:
        where.append("decisor IS NOT NULL AND decisor <> ''")
    if crit.capital_min:
        where.append("capital >= ?"); params.append(crit.capital_min)
    if crit.capital_max:
        where.append("capital <= ?"); params.append(crit.capital_max)
    if crit.natureza in _NATUREZA:
        codes = list(_NATUREZA[crit.natureza])
        where.append("natureza IN (%s)" % ",".join("?" * len(codes))); params += codes
    if crit.idade_min:
        where.append("ano IS NOT NULL AND ano <= ?"); params.append(hoje - crit.idade_min)
    if crit.idade_max:
        where.append("ano IS NOT NULL AND ano >= ?"); params.append(hoje - crit.idade_max)
    if crit.exigir_email:
        where.append("email <> ''")
    if crit.exigir_telefone:
        where.append("telefone <> ''")
    # --- Nível 2 + Dívida ---
    if crit.cnaes_sec:
        ors = []
        for c in crit.cnaes_sec:
            ors.append("cnae_sec LIKE ?"); params.append("%," + c + "%")
        where.append("(" + " OR ".join(ors) + ")")
    if crit.n_estab_min:
        where.append("n_estab >= ?"); params.append(crit.n_estab_min)
    if crit.socios_min:
        where.append("n_socios >= ?"); params.append(crit.socios_min)
    if crit.socios_max:
        where.append("n_socios <= ?"); params.append(crit.socios_max)
    if crit.so_estrangeiro:
        where.append("estrangeiro=1")
    if crit.cep_prefixo:
        d = "".join(c for c in crit.cep_prefixo if c.isdigit())
        if d:
            where.append("cep LIKE ?"); params.append(d + "%")
    if crit.divida == "sem":
        where.append("divida_ativa=0")
    elif crit.divida == "com":
        where.append("divida_ativa=1")

    # score aproximado em SQL (sem domínio próprio) só para ORDENAR o pool;
    # o score final e os motivos saem do _score_row em Python. Capital com escala
    # FINA para não saturar (uma de R$174M tem que rankear acima de uma de R$2M).
    y25, y15, y8, y3 = hoje - 25, hoje - 15, hoje - 8, hoje - 3
    sc = (
        "(CASE WHEN COALESCE(capital,0)>=100000000 THEN 40 WHEN capital>=50000000 THEN 36 "
        "WHEN capital>=10000000 THEN 32 WHEN capital>=5000000 THEN 28 WHEN capital>=1000000 THEN 24 "
        "WHEN capital>=500000 THEN 18 WHEN capital>=300000 THEN 14 WHEN capital>=100000 THEN 9 "
        "WHEN capital>0 THEN 3 ELSE 0 END"
        "+CASE porte WHEN 'Demais' THEN 12 WHEN 'EPP' THEN 8 WHEN 'ME' THEN 3 ELSE 0 END"
        "+(email<>'')*10+(telefone<>'')*6"
        f"+CASE WHEN ano IS NULL THEN 0 WHEN ano<={y25} THEN 14 WHEN ano<={y15} THEN 10 "
        f"WHEN ano<={y8} THEN 6 WHEN ano<={y3} THEN 2 ELSE 0 END)")
    # pool maior porque vamos deduplicar empresas (matriz+filiais viram 1 só)
    pool = max(crit.n * 10, 800)
    # desempate por CAPITAL: entre scores iguais, a empresa maior vem primeiro
    sql = (f"SELECT * FROM empresas WHERE {' AND '.join(where)} "
           f"ORDER BY {sc} DESC, COALESCE(capital,0) DESC, matriz DESC LIMIT ?")
    params.append(pool)

    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    rows = con.execute(sql, params).fetchall()
    con.close()

    ranked: list[tuple] = []        # (score, capital, linha) — capital desempata
    vistos: set[str] = set()
    for r in rows:
        base = r["base"]
        if base in vistos:          # mesma empresa (outro estabelecimento): pula
            continue
        vistos.add(base)
        nome = r["nome"]
        if crit.excluir_recjud and _em_dificuldade(nome):
            continue
        dom = (r["dominio"] or "").lower()
        dom_prop = bool(dom and _dominio_proprio(dom) and _nome_no_dominio(nome, dom))
        if crit.exigir_dominio and not dom_prop:
            continue
        score, _ = _score_row(r, hoje, dom_prop)
        idade = (hoje - r["ano"]) if r["ano"] else None
        linha = {
            "empresa": nome,
            "setor": setores.nome_do_cnae(r["cnae"]),
            "cnpj": r["cnpj"],
            "cidade": r["cidade"].title() if r["cidade"] else "—",
            "uf": r["uf"],
            "porte": r["porte"] or "—",
            "capital": _fmt_capital(r["capital"]),
            "idade": f"{idade} anos" if idade is not None else "—",
            "decisor": r["decisor"] or "—",
            "email": r["email"] or "",
            "telefone": r["telefone"] or "—",
            "score": score,
            "_dom": dom if dom_prop else "",     # domínio próprio (verificado depois)
        }
        ranked.append((score, r["capital"] or 0, linha))

    ranked.sort(key=lambda t: (t[0], t[1]), reverse=True)
    top = [t[2] for t in ranked[: crit.n]]

    # monta a coluna "site" SÓ dos exibidos: linka direto se o domínio está no ar
    # (quando verificar_site); senão manda pra uma busca no Google (sempre segura).
    doms = [l["_dom"] for l in top if l["_dom"]]
    ativos = verificar.sites_ativos(doms) if (doms and crit.verificar_site) else None
    for l in top:
        dom = l.pop("_dom")
        if dom and (ativos is None or ativos.get(dom, False)):
            l["site"] = f"https://{dom}"
        else:
            limpo = _empresa_exibicao(l["empresa"]) or l["empresa"]
            l["site"] = "https://www.google.com/search?q=" + quote(f"{limpo} site oficial")
    return top
