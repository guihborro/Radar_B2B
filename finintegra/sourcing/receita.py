"""Provedor: RECEITA FEDERAL — Dados Abertos do CNPJ (gratuito).

NÃO é uma API de busca. São arquivos CSV públicos que você baixa e este provedor
filtra localmente por CNAE, UF e porte. É a mesma base que os provedores pagos
revendem; o que eles cobram é o enriquecimento (e-mail do decisor, nº de
funcionários) — que aqui é coberto pela camada de enriquecimento + validação.

-------------------------------------------------------------------------------
COMO BAIXAR (uma vez):
  A URL oficial mudou em jan/2026. Use o ESPELHO (cópia oficial, CDN, mais rápido):
    https://dados-abertos-rf-cnpj.casadosdados.com.br/arquivos/
  Entre na pasta do mês mais recente (ex.: 2026-06-14/). Lá ficam, divididos em
  10 partes cada: Estabelecimentos0..9.zip, Empresas0..9.zip, Socios0..9.zip.
  (Oficial alternativo: https://dados.gov.br/dados/conjuntos-dados/cadastro-nacional-da-pessoa-juridica---cnpj)

  Baixe e DESCOMPACTE para a pasta configurada (padrão: data/receita/):
       - Estabelecimentos0.zip  -> arquivo terminando em .ESTABELE  (OBRIGATÓRIO)
       - Empresas0..9.zip       -> arquivos .EMPRECSV  (recomendado: razão social + porte)
       - Socios0..9.zip         -> arquivos .SOCIOCSV  (opcional: nome do sócio/decisor)

  PRIMEIRO TESTE rápido: baixe só Estabelecimentos0.zip (já dá milhares de empresas).
  Para nomes (razão social) melhores, baixe também Empresas0..9.zip — esses são
  bem menores que os de estabelecimentos.

Sem chave de API. Config em config.yaml -> seção `receita`.
-------------------------------------------------------------------------------

LAYOUT DAS COLUNAS (CSV, separador ';', sem cabeçalho, encoding latin-1).
Estes índices são o "contrato" do arquivo da Receita — não invente, é posicional.
"""
from __future__ import annotations

import csv
from pathlib import Path

from .base import ICPFilter, SourcingProvider
from ..config import _norm_cnae
from ..storage.models import Contato, Empresa, Lead

# --- ESTABELECIMENTOS (.ESTABELE) -------------------------------------------
EST_CNPJ_BASICO = 0      # 8 dígitos
EST_CNPJ_ORDEM = 1       # 4 dígitos
EST_CNPJ_DV = 2          # 2 dígitos
EST_MATRIZ_FILIAL = 3    # 1=matriz, 2=filial
EST_NOME_FANTASIA = 4
EST_SITUACAO = 5         # 02 = ativa
EST_DATA_INICIO = 10     # data de início de atividade (AAAAMMDD) — idade da empresa
EST_CNAE_PRINCIPAL = 11  # 7 dígitos
EST_UF = 19
EST_MUNICIPIO = 20       # código da Receita (não IBGE)
EST_DDD1 = 21
EST_TEL1 = 22
EST_EMAIL = 27           # correio_eletronico (da empresa, não do decisor)

# --- EMPRESAS (.EMPRECSV) ----------------------------------------------------
EMP_CNPJ_BASICO = 0
EMP_RAZAO_SOCIAL = 1
EMP_NATUREZA = 2        # natureza jurídica (2135=Empresário Individual/MEI; 2062=LTDA)
EMP_CAPITAL = 4         # capital social (decimal com vírgula)
EMP_PORTE = 5           # 01=ME, 03=EPP, 05=Demais, 00=não informado

# naturezas a excluir quando excluir_empresario_individual=true (MEI/EI)
NATUREZAS_MICRO = {"2135"}  # Empresário (Individual)

# --- SOCIOS (.SOCIOCSV) ------------------------------------------------------
SOC_CNPJ_BASICO = 0
SOC_IDENTIFICADOR = 1   # 1=PJ, 2=PF, 3=estrangeiro
SOC_NOME = 2

_PORTE_LABEL = {"01": "ME", "03": "EPP", "05": "Demais", "00": ""}


class ReceitaFederalProvider(SourcingProvider):
    def search(self, f: ICPFilter) -> list[Lead]:
        pasta = self.cfg.root / self.cfg.get("receita", "pasta", default="data/receita")
        est_files = _arquivos(pasta, "*.ESTABELE", "*ESTABELE*.csv")
        if not est_files:
            raise RuntimeError(
                f"Nenhum arquivo de Estabelecimentos (.ESTABELE) em {pasta}.\n"
                f"Baixe o open data da Receita e descompacte ali. Instruções no topo "
                f"de finintegra/sourcing/receita.py."
            )

        portes_ok = set(self.cfg.get("receita", "portes", default=[]) or [])
        so_ativa = bool(self.cfg.get("receita", "situacao_ativa", default=True))
        excluir_ei = bool(self.cfg.get("receita", "excluir_empresario_individual", default=True))
        capital_min = float(self.cfg.get("receita", "capital_social_min", default=0) or 0)
        cnaes = [_norm_cnae(c) for c in f.cnaes]
        ufs = {_uf(r) for r in f.regioes} if f.regioes else set()
        # filtros de Empresas (natureza/capital/porte) cortam MUITO (mar de MEIs),
        # então coletamos bastante no passo 1 quando há filtro estrito.
        estrito = excluir_ei or capital_min > 0 or bool(portes_ok)
        teto = f.limite * (12 if estrito else 2)

        # Passo 1: varre Estabelecimentos, filtra por CNAE/UF/situação.
        parciais: dict[str, Lead] = {}  # cnpj_basico -> Lead
        for arq in est_files:
            for row in _ler(arq):
                if len(row) <= EST_EMAIL:
                    continue
                if so_ativa and row[EST_SITUACAO] != "02":
                    continue
                cnae = _norm_cnae(row[EST_CNAE_PRINCIPAL])
                if cnaes and not any(cnae.startswith(c) for c in cnaes):
                    continue
                uf = row[EST_UF].strip().upper()
                if ufs and uf not in ufs:
                    continue
                base = row[EST_CNPJ_BASICO]
                if base in parciais:
                    continue  # 1 estabelecimento por empresa basta
                parciais[base] = _lead_de_estabelecimento(row, cnae, uf)
                if len(parciais) >= teto:
                    break
            if len(parciais) >= teto:
                break

        # Passo 2: enriquece com Empresas (razão social + porte) e filtra porte.
        emp_files = _arquivos(pasta, "*.EMPRECSV", "*EMPRE*.csv")
        if emp_files:
            alvo_bases = set(parciais)
            achados: set[str] = set()
            for arq in emp_files:
                if len(achados) >= len(alvo_bases):
                    break
                for row in _ler(arq):
                    base = row[EMP_CNPJ_BASICO] if row else ""
                    if base not in alvo_bases or base in achados:
                        continue
                    lead = parciais.get(base)
                    if lead is not None:
                        lead.empresa.nome = (row[EMP_RAZAO_SOCIAL].strip()
                                             or lead.empresa.nome)
                        natureza = row[EMP_NATUREZA] if len(row) > EMP_NATUREZA else ""
                        porte_cod = row[EMP_PORTE] if len(row) > EMP_PORTE else "00"
                        capital = _parse_capital(row[EMP_CAPITAL] if len(row) > EMP_CAPITAL else "")
                        lead.empresa.natureza = natureza
                        lead.empresa.porte = _PORTE_LABEL.get(porte_cod, "")
                        lead.empresa.capital_social = capital
                        # filtros que removem o "mar de MEIs" / micro
                        remover = (
                            (portes_ok and porte_cod not in portes_ok)
                            or (excluir_ei and natureza in NATUREZAS_MICRO)
                            or (capital_min > 0 and (capital or 0) < capital_min)
                        )
                        if remover:
                            del parciais[base]
                    achados.add(base)
                    if len(achados) >= len(alvo_bases):
                        break
            # (empresas não achadas no arquivo permanecem com nome fantasia)

        # Passo 3: nome do sócio/decisor (opcional).
        soc_files = _arquivos(pasta, "*.SOCIOCSV", "*SOCIO*.csv")
        if soc_files:
            faltam = set(parciais)
            for arq in soc_files:
                if not faltam:
                    break
                for row in _ler(arq):
                    base = row[SOC_CNPJ_BASICO] if row else ""
                    if base not in faltam:
                        continue
                    if len(row) > SOC_NOME and row[SOC_IDENTIFICADOR] == "2":
                        parciais[base].contato.nome = row[SOC_NOME].strip().title()
                        faltam.discard(base)

        return list(parciais.values())[: f.limite]


# -----------------------------------------------------------------------------
def _lead_de_estabelecimento(row: list[str], cnae: str, uf: str) -> Lead:
    email = row[EST_EMAIL].strip().lower()
    dominio = email.split("@", 1)[1] if "@" in email else ""
    ddd = row[EST_DDD1].strip()
    tel = row[EST_TEL1].strip()
    telefone = f"+55 {ddd} {tel}".strip() if tel else ""
    empresa = Empresa(
        nome=row[EST_NOME_FANTASIA].strip() or "(sem nome)",
        cnae=cnae,
        dominio=dominio,
        uf=uf,
        regiao=uf,
        municipio_cod=row[EST_MUNICIPIO].strip() if len(row) > EST_MUNICIPIO else "",
        cnpj=_fmt_cnpj(row),
        fundacao_ano=_ano_fundacao(row[EST_DATA_INICIO] if len(row) > EST_DATA_INICIO else ""),
        matriz=(row[EST_MATRIZ_FILIAL].strip() == "1"),
    )
    # e-mail da empresa entra como candidato fraco; o decisor é gerado no enrichment
    contato = Contato(telefone=telefone)
    if email and "@" in email:
        contato.email_candidatos = [email]
    return Lead(empresa=empresa, contato=contato)


def _fmt_cnpj(row: list[str]) -> str:
    b, o, d = row[EST_CNPJ_BASICO], row[EST_CNPJ_ORDEM], row[EST_CNPJ_DV]
    return f"{b[:2]}.{b[2:5]}.{b[5:8]}/{o}-{d}"


def _ano_fundacao(v: str) -> int | None:
    """Extrai o ano de 'AAAAMMDD'. Ignora datas vazias/zeradas/absurdas."""
    v = (v or "").strip()
    if len(v) < 4 or not v[:4].isdigit():
        return None
    ano = int(v[:4])
    return ano if 1900 <= ano <= 2100 else None


def _parse_capital(v: str) -> float | None:
    v = (v or "").strip().replace(".", "").replace(",", ".")
    try:
        return float(v) if v else None
    except ValueError:
        return None


def _uf(regiao: str) -> str:
    """'SP-interior' -> 'SP'; 'RS' -> 'RS'. (interior x capital não é separável só por UF)."""
    return regiao.split("-")[0].strip().upper()[:2]


def _arquivos(pasta: Path, *padroes: str) -> list[Path]:
    if not pasta.is_dir():
        return []
    achados: list[Path] = []
    for p in padroes:
        achados += [x for x in pasta.glob(p) if x.is_file()]
    # dedup mantendo ordem
    vistos, unicos = set(), []
    for a in sorted(achados):
        if a not in vistos:
            vistos.add(a)
            unicos.append(a)
    return unicos


def _ler(arq: Path):
    """Itera linhas de um CSV da Receita (latin-1, ';' , aspas)."""
    with arq.open(encoding="latin-1", newline="") as fh:
        yield from csv.reader(fh, delimiter=";", quotechar='"')
