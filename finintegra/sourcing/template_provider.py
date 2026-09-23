"""TEMPLATE de provedor — copie este arquivo para criar o PRÓXIMO provedor.

Cada fonte (Econodata, Speedio, Casa dos Dados, Data Stone...) tem sua forma
exata de buscar e seus próprios nomes de campo. Para plugar uma nova:

  1. Copie este arquivo:  cp template_provider.py speedio.py
  2. Renomeie a classe e preencha NOME / ENV_KEY / BASE_URL.
  3. Implemente search(): chame a API (ou leia o export) e MAPEIE os campos
     da fonte para os campos do nosso modelo (ver "DE-PARA" abaixo).
  4. Registre no sourcing/__init__.py:  "speedio": SpeedioProvider
  5. Aponte ferramentas.provedor_dados: "speedio" no config.yaml e a chave no .env.
  6. ANTES de confiar: python -m finintegra.cli auditar  (mede a qualidade real, §4.3).

DE-PARA (o que a fonte devolve  ->  nosso modelo):
    razão social / nome fantasia ........ Empresa.nome
    CNAE principal ...................... Empresa.cnae      (só dígitos; o tier sai daqui)
    domínio / site ...................... Empresa.dominio   (base p/ gerar e-mail do decisor)
    porte / nº funcionários ............. Empresa.porte / Empresa.funcionarios
    UF / cidade ......................... Empresa.uf / Empresa.cidade / Empresa.regiao
    CNPJ ................................ Empresa.cnpj
    nome do decisor ..................... Contato.nome
    cargo .............................. Contato.cargo
    e-mail do decisor (se houver) ....... Contato.email   (será revalidado mesmo assim)
    telefone / whatsapp ................. Contato.telefone
    linkedin ........................... Contato.linkedin_url

Regra: NÃO confie no e-mail que a fonte entrega — deixe a camada de validação
decidir. O enriquecimento gera candidatos a partir de nome + domínio.
"""
from __future__ import annotations

from .base import ICPFilter, SourcingProvider
from ..config import _norm_cnae
from ..storage.models import Contato, Empresa, Lead


class TemplateProvider(SourcingProvider):
    NOME = "Template"
    ENV_KEY = "TROQUE_ME_API_KEY"     # nome da variável no .env
    BASE_URL = "https://api.exemplo.com/v1/empresas"

    def search(self, f: ICPFilter) -> list[Lead]:
        chave = self.cfg.env(self.ENV_KEY)
        if not chave:
            raise RuntimeError(f"Defina {self.ENV_KEY} no .env.")

        # ------------------------------------------------------------------
        # 1) CHAMAR A FONTE — mapeie os filtros de ICP para os parâmetros dela.
        #    (descomente e ajuste; cada API tem seus nomes de parâmetro)
        # ------------------------------------------------------------------
        # import requests
        # resp = requests.get(self.BASE_URL, timeout=30, headers={
        #     "Authorization": f"Bearer {chave}",
        # }, params={
        #     "cnae": ",".join(f.cnaes),          # <- nome do parâmetro varia!
        #     "uf": ",".join(f.regioes),
        #     "func_min": f.funcionarios_min,
        #     "func_max": f.funcionarios_max,
        #     "limite": f.limite,
        # })
        # resp.raise_for_status()
        # registros = resp.json()["data"]          # <- caminho varia por API
        registros: list[dict] = []

        # ------------------------------------------------------------------
        # 2) MAPEAR cada registro -> Lead. Troque as chaves pelos nomes reais
        #    do JSON/CSV da fonte. Este é o "nome das colunas" específico dela.
        # ------------------------------------------------------------------
        leads: list[Lead] = []
        for r in registros:
            empresa = Empresa(
                nome=r.get("razao_social", ""),
                cnae=_norm_cnae(r.get("cnae", "")),
                dominio=_dominio(r.get("site", "")),
                funcionarios=_int(r.get("funcionarios")),
                uf=r.get("uf", ""),
                cidade=r.get("cidade", ""),
                regiao=r.get("uf", ""),
                cnpj=r.get("cnpj", ""),
            )
            contato = Contato(
                nome=r.get("contato_nome", ""),
                cargo=r.get("cargo", ""),
                email=r.get("email", ""),          # será revalidado
                telefone=r.get("telefone", ""),
                linkedin_url=r.get("linkedin", ""),
            )
            leads.append(Lead(empresa=empresa, contato=contato))
            if len(leads) >= f.limite:
                break
        return leads


def _dominio(site: str) -> str:
    s = site.strip().lower()
    for pref in ("https://", "http://", "www."):
        if s.startswith(pref):
            s = s[len(pref):]
    return s.split("/")[0]


def _int(v) -> int | None:
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None
