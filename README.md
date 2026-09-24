# Radar B2B — Outreach & Matchmaker

Dois produtos de **inteligência comercial B2B** construídos sobre dados públicos:
os **dados abertos da Receita Federal** (CNPJ) e a **Dívida Ativa da União** (PGFN).

| Produto | O que faz |
|---|---|
| 🎯 **Matchmaker** | Recebe o perfil de cliente ideal (setor, região, porte, saúde financeira…) e devolve uma **lista ranqueada de empresas** que encaixam, com export em CSV/Excel. Base de **22 milhões de empresas ativas**, busca instantânea. |
| 📧 **Outreach** | Pipeline **de prospecção por e-mail**: acha empresas no ICP, gera/valida o contato, escreve a abordagem por nicho, envia por SMTP com cadência de follow-up e mede as respostas. |

> **Stack:** Python 3.12 · Flask · SQLite · pandas-free (CSV/sqlite puro) · openpyxl.
> Roda 100% local. Nenhum serviço pago é obrigatório.

---

## 🎯 Matchmaker (recomendação de leads)

Um site (Flask) que consulta um índice SQLite de **22,4 milhões de empresas ativas**
do Brasil, montado a partir da Receita Federal + Dívida Ativa da PGFN.

### Filtros disponíveis
- **Setor** — catálogo de ~97 nichos (supermercado, farmácia, metalúrgica, restaurante, academia…) com busca; e **CNAE secundário** ("também atua em").
- **Região** — estados + **cidade por estado** (autocomplete das cidades reais de cada UF).
- **Porte e tamanho** — porte, faixa de capital social, idade da empresa, natureza jurídica.
- **Qualidade** — só com e-mail / telefone / domínio próprio / decisor identificado; matriz ou filial.
- **Saúde financeira** 🌟 — **Dívida Ativa federal** (só empresas saudáveis × endividadas) e regime **Simples/MEI**.
- **Avançados** — rede/franquia (nº de estabelecimentos), nº de sócios, sócio estrangeiro (multinacional), CEP.

Cada empresa recebe um **score de encaixe** (0–100) e a lista sai ordenada. O site
verifica se o **site da empresa está no ar** antes de linká-lo, e exporta em
**CSV** e **Excel formatado**.

### Rodar
```powershell
python -m matchmaker.app
```
Abra **http://localhost:5001** (na mesma rede, `http://<ip-da-maquina>:5001`).

### Construir o índice (uma vez, após baixar os dados)
```powershell
python -m matchmaker.indexar      # lê os CSV da Receita -> data/matchmaker.sqlite (~40 min)
python -m matchmaker.divida        # marca quem tem Dívida Ativa federal (PGFN)
```

---

## 📧 Outreach: pipeline de prospecção por e-mail

Pipeline modular e supervisionado. Cada camada é trocável por config, e os defaults
rodam **sem serviço pago e sem enviar nada** (modo seguro).

```
sourcing → enrichment → validation → routing → messaging → sending
```

Destaques: cadência de **follow-up** (dia 3/10/17), **validação real** de e-mail
antes de enviar (evita bounce), **medição de respostas** via IMAP, copy por nicho
com A/B de assunto, e **limite diário** de aquecimento.

### Comandos principais
```powershell
python -m finintegra.cli rodar               # envia (follow-ups + leads novos, respeita limite)
python -m finintegra.cli rodar --no-enviar   # prévia, sem enviar
python -m finintegra.cli followups           # agenda da cadência
python -m finintegra.cli checar-respostas    # lê a INBOX (IMAP) e marca respostas/bounces
python -m finintegra.cli funil               # métricas: enviados, respostas, bounce, taxa
python -m finintegra.cli ligacoes            # lista de ligação/WhatsApp (tier1 sem resposta)
```

Tudo que é do negócio vive em `config/` (nunca no código): `config.yaml` (ICP,
canais, ferramentas), `config/cnaes.yaml` (CNAEs por tier) e
`config/templates/*.yaml` (uma copy por nicho).

---

## Instalação

Requer **Python 3.11+**.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env        # preencha só o que for usar (SMTP, ZeroBounce…)
```

## Dados (não vão no repositório)

Os datasets são grandes (dezenas de GB) e **não são versionados** — baixe-os localmente:

- **Receita Federal (CNPJ)** — espelho: <https://dados-abertos-rf-cnpj.casadosdados.com.br/arquivos/>
  → descompacte em `data/receita/` (`Estabelecimentos*`, `Empresas*`, `Socios*`, `Municipios`, `Cnaes`, `Simples`).
- **Dívida Ativa da União (PGFN)** — <https://www.gov.br/pgfn/pt-br/assuntos/divida-ativa-da-uniao/transparencia-fiscal-1/dados-abertos>
  → descompacte as pastas `Dados_abertos_*` na raiz do projeto.

> Os dados de empresa (CNPJ, CNAE, endereço, porte, dívida) são **públicos**. O nome
> do sócio é **dado pessoal** — use com base legal e respeite opt-out (LGPD).

## Estrutura

```
config/            # tudo que você edita (ICP, CNAEs, templates de copy)
finintegra/        # pipeline outbound (sourcing → … → sending, cli.py)
matchmaker/        # site de recomendação (app.py, recomendador.py, indexar.py, divida.py)
tests/             # testes offline
data/              # base, índice, exports (gitignored)
```

## Testes

```powershell
python tests/test_pipeline.py
```
