"""Análise completa dos arquivos da Receita em data/receita/ com os filtros
ativos: total de empresas no alvo, quebra por setor, cobertura de e-mail/telefone
e EXEMPLOS reais de empresas de cada setor.

Varre os arquivos inteiros (sem amostragem para os totais). Chamado por
`cli analisar`. ATENÇÃO: opera sobre os arquivos baixados (parte 0 de 10).
"""
from __future__ import annotations

import re
import time
from collections import Counter, defaultdict

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# nomes dos grupos de CNAE (4 dígitos) que aparecem nos nossos nichos
_CNAE_NOMES = {
    # agro
    "0111": "Cereais", "0113": "Cana-de-açúcar", "0115": "Soja",
    "0119": "Lavoura temporária", "0121": "Horticultura", "0133": "Frutas",
    "0134": "Café", "0139": "Lavoura permanente", "0151": "Criação de bovinos",
    "0152": "Animais de grande porte", "0155": "Aves", "0159": "Outros animais",
    "0161": "Apoio à agricultura", "0162": "Apoio à pecuária", "4623": "Atacado de insumos agro",
    # tier1
    "4530": "Comércio de autopeças", "2949": "Fabricação de autopeças",
    "2229": "Artefatos de plástico", "2222": "Embalagens plásticas",
    "2539": "Usinagem e solda", "2599": "Produtos de metal",
    "2512": "Esquadrias de metal", "2542": "Serralheria/ferramentas",
    "2511": "Estruturas metálicas", "2592": "Tratamento de metais",
    # tier2
    "1091": "Panificação", "1099": "Alimentos diversos", "1013": "Produtos de carne",
    "1011": "Abate", "1066": "Ração animal", "2829": "Máquinas de uso geral",
    "2869": "Máquinas industriais", "2833": "Máquinas agrícolas",
    "2651": "Instrumentos de medição", "2790": "Equipamentos elétricos",
    # tier3
    "1412": "Confecção de vestuário", "1413": "Roupas profissionais",
    "1351": "Tecidos", "1359": "Produtos têxteis", "3101": "Móveis de madeira",
    "3102": "Móveis de metal", "2330": "Artefatos de concreto",
    "2342": "Produtos cerâmicos", "2391": "Britamento de pedras",
    "2399": "Minerais não-metálicos",
}


def _email_ok(email: str) -> bool:
    return bool(_EMAIL_RE.match(email.strip().lower()))

from .config import Config, _norm_cnae
from .export_html import _dominio_proprio
from .sourcing.receita import (
    EST_CNAE_PRINCIPAL, EST_CNPJ_BASICO, EST_EMAIL, EST_SITUACAO, EST_TEL1, EST_UF,
    EST_DDD1, EMP_CNPJ_BASICO, EMP_NATUREZA, EMP_PORTE, EMP_RAZAO_SOCIAL,
    NATUREZAS_MICRO, _arquivos, _ler, _uf,
)

_POR_TIER = 150        # candidatos guardados por setor para os exemplos
_EXEMPLOS = 4          # exemplos exibidos por setor


def _canal(email: str, tel: str) -> str:
    if _email_ok(email):
        dom = email.split("@", 1)[1].lower()
        return "e-mail próprio" if _dominio_proprio(dom) else "e-mail webmail/contador"
    return "só telefone" if tel else "sem canal"


def _rank_exemplo(rec: dict) -> int:
    # ordena exemplos: e-mail próprio > webmail > só telefone
    c = _canal(rec["email"], rec["tel"])
    return {"e-mail próprio": 0, "e-mail webmail/contador": 1,
            "só telefone": 2, "sem canal": 3}[c]


def rodar_analise(cfg: Config) -> None:
    pasta = cfg.root / cfg.get("receita", "pasta", default="data/receita")
    est_files = _arquivos(pasta, "*.ESTABELE", "*ESTABELE*.csv")
    if not est_files:
        raise RuntimeError(
            f"Nenhum arquivo de Estabelecimentos (.ESTABELE) em {pasta}. "
            f"Baixe o open data da Receita primeiro."
        )

    cnaes = [_norm_cnae(str(e["codigo"])) for t in cfg.cnaes["tiers"].values() for e in t]
    ufs = {_uf(r) for r in cfg.get("icp", "regioes", default=[])}
    portes_ok = set(cfg.get("receita", "portes", default=[]) or [])
    excluir_ei = bool(cfg.get("receita", "excluir_empresario_individual", default=True))
    so_ativa = bool(cfg.get("receita", "situacao_ativa", default=True))

    print(f"Filtros: CNAE={cnaes}")
    print(f"         UF={ufs or 'todas'} | porte={portes_ok or 'todos'} | "
          f"exclui_EI={excluir_ei} | so_ativa={so_ativa}")
    print("Varrendo os arquivos (alguns minutos)...\n")
    t0 = time.time()

    # Passo 1: estabelecimentos que batem CNAE + UF + situação
    match: dict[str, list] = {}                    # basico -> [email, tel, proprio, tier]
    amostra: dict[str, list] = defaultdict(list)   # tier -> [rec, ...]
    lidos = 0
    for arq in est_files:
        for row in _ler(arq):
            lidos += 1
            if len(row) <= EST_EMAIL:
                continue
            if so_ativa and row[EST_SITUACAO] != "02":
                continue
            cn = _norm_cnae(row[EST_CNAE_PRINCIPAL])
            if cnaes and not any(cn.startswith(c) for c in cnaes):
                continue
            uf = row[EST_UF].strip().upper()
            if ufs and uf not in ufs:
                continue
            base = row[EST_CNPJ_BASICO]
            email = row[EST_EMAIL].strip().lower()
            tel = row[EST_TEL1].strip()
            tem_email = _email_ok(email)
            proprio = tem_email and _dominio_proprio(email.split("@", 1)[1])
            if base in match:
                continue
            tier = cfg.cnae_tier(cn) or "?"
            match[base] = [tem_email, bool(tel), proprio, tier, cn[:4]]
            if len(amostra[tier]) < _POR_TIER:
                ddd = row[EST_DDD1].strip()
                fone = f"({ddd}) {tel}" if tel else ""
                amostra[tier].append(
                    {"base": base, "cnae": cn, "uf": uf, "email": email,
                     "tel": fone, "fantasia": row[4].strip()})
    print(f"[1] estabelecimentos lidos: {lidos:,} | empresas no alvo "
          f"(CNAE+UF+ativa): {len(match):,}")

    # Passo 2: Empresas -> natureza + porte (filtro) e razão social (exemplos)
    amostra_bases = {r["base"] for recs in amostra.values() for r in recs}
    razao: dict[str, str] = {}
    emp: dict[str, tuple] = {}
    for arq in _arquivos(pasta, "*.EMPRECSV", "*EMPRE*.csv"):
        for row in _ler(arq):
            if not row:
                continue
            base = row[EMP_CNPJ_BASICO]
            if base in match:
                nat = row[EMP_NATUREZA] if len(row) > EMP_NATUREZA else ""
                porte = row[EMP_PORTE] if len(row) > EMP_PORTE else "00"
                emp[base] = (nat, porte)
                if base in amostra_bases:
                    razao[base] = row[EMP_RAZAO_SOCIAL].strip()
    cobertura = 100 * len(emp) / max(1, len(match))
    print(f"[2] empresas casadas com o alvo: {len(emp):,} "
          f"(cobertura {cobertura:.0f}% — o resto está em Empresas1..9)\n")

    def passa(base: str) -> bool:
        dados = emp.get(base)
        if dados is None:
            return False
        nat, porte = dados
        if excluir_ei and nat in NATUREZAS_MICRO:
            return False
        if portes_ok and porte not in portes_ok:
            return False
        return True

    # Contagem final + quebra por setor + sub-CNAE
    total = com_email = com_tel = com_ambos = com_nenhum = proprio_cnt = 0
    por_tier: Counter = Counter()
    sub_cnae: dict[str, Counter] = defaultdict(Counter)
    for base, (tem_email, tem_tel, proprio, tier, cnae4) in match.items():
        if not passa(base):
            continue
        total += 1
        por_tier[tier] += 1
        sub_cnae[tier][cnae4] += 1
        com_email += tem_email
        com_tel += tem_tel
        com_ambos += tem_email and tem_tel
        com_nenhum += not tem_email and not tem_tel
        proprio_cnt += proprio

    def pct(x: int) -> str:
        return f"{100 * x / total:.0f}%" if total else "-"

    print("=" * 60)
    print(f"EMPRESAS QUE PASSAM EM TODOS OS FILTROS : {total:,}")
    print(f"  com e-mail                  : {com_email:,}  ({pct(com_email)})")
    print(f"    - com domínio próprio     : {proprio_cnt:,}  ({pct(proprio_cnt)})")
    print(f"  com telefone                : {com_tel:,}  ({pct(com_tel)})")
    print(f"  com e-mail E telefone       : {com_ambos:,}  ({pct(com_ambos)})")
    print(f"  alcançáveis (e-mail OU tel) : {total - com_nenhum:,}  ({pct(total - com_nenhum)})")

    print("\nPor setor:")
    for tier, n in por_tier.most_common():
        print(f"  {tier:10s} {n:>7,}  ({pct(n)})")

    print("\nPrincipais sub-setores (CNAE) por segmento:")
    for tier, _ in por_tier.most_common():
        print(f"  {tier}:")
        for g, q in sub_cnae[tier].most_common(6):
            nome = _CNAE_NOMES.get(g, "(ver CNAE)")
            print(f"    {g}  {nome:26s} {q:>6,}")

    # Exemplos reais por setor
    print("\n" + "=" * 60)
    print("EXEMPLOS DE EMPRESAS (por setor)")
    for tier in por_tier:
        recs = [r for r in amostra.get(tier, []) if passa(r["base"])]
        if not recs:
            continue
        recs.sort(key=_rank_exemplo)
        print(f"\n  --- {tier} ---")
        for r in recs[:_EXEMPLOS]:
            nome = (razao.get(r["base"]) or r["fantasia"] or "(sem nome)")[:40]
            print(f"  • {nome}  |  CNAE {r['cnae']}  |  {r['uf']}")
            linha = f"      canal: {_canal(r['email'], r['tel'])}"
            if r["email"]:
                linha += f"  |  {r['email']}"
            if r["tel"]:
                linha += f"  |  tel: {r['tel']}"
            print(linha)

    print(f"\nTempo: {time.time() - t0:.0f}s  |  Nota: parte 0 de 10 (~1/10 do Brasil).")

    return {
        "total": total,
        "com_email": com_email,
        "com_tel": com_tel,
        "proprio": proprio_cnt,
        "alcancaveis": total - com_nenhum,
        "no_alvo": len(match),
        "por_tier": dict(por_tier),
        "sub_cnae": {t: dict(c) for t, c in sub_cnae.items()},
    }
