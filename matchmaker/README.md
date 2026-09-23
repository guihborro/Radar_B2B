# Matchmaker de leads

Produto paralelo ao FinIntegra. Em vez de **enviar** e-mails, aqui o cliente
descreve o ICP dele num questionário e recebe uma **tabela ranqueada** de
empresas da Receita Federal que mais se encaixam.

## Como rodar

Da raiz do workspace (para o pacote `finintegra` ser importável):

```bash
python -m matchmaker.app
```

Abra **http://localhost:5001**. Responda o questionário (setores, região, porte,
capital, idade, exigências de contato) e clique em *Gerar lista*. A busca varre a
Receita (~1 min) e devolve a tabela ranqueada, com botão de **download CSV**.

## Como funciona (arquitetura)

```
questionário (Flask/HTML)
   -> Criterios (matchmaker/recomendador.py)
   -> filtro na Receita  (reusa finintegra.sourcing.receita)
   -> pontuação por regras 0-100 (transparente, não é ML)
   -> tabela ranqueada + CSV
```

- **matchmaker/setores.py** — catálogo de 37 setores (nome amigável -> CNAE).
- **matchmaker/recomendador.py** — `Criterios` + `recomendar()` + o motor de score.
- **matchmaker/app.py** — rotas Flask (`/`, `/recomendar`, `/baixar/<token>.csv`).
- **matchmaker/templates/** — `index.html` (questionário) e `resultados.html` (tabela).

Reaproveita do FinIntegra: o provedor da Receita, o `ICPFilter`, os filtros de
qualidade (`_dominio_proprio`, `_em_dificuldade`) e os mesmos dados em `data/receita/`.

## Score (como ranqueia)

Cada empresa soma pontos de encaixe (máx. 100): capital social, porte, ter
e-mail/telefone, domínio próprio e tempo de mercado. O motivo de cada score
aparece na coluna "Por que encaixa" — nada é caixa-preta.

## Limitações conhecidas (fase 2)

- **Dados = só a parte 0 da Receita (~1/10 do Brasil).** Para cobrir o país,
  baixar as 10 partes de Estabelecimentos/Empresas.
- **Cada busca re-varre o arquivo (~1 min).** Indexar a Receita em SQLite deixaria
  as consultas instantâneas.
- **Porte/capital vêm só de quem está no `Empresas0`** — por isso algumas linhas
  mostram "—". Baixar todas as partes de Empresas resolve.
- **É ferramenta local, sem login/multiusuário.** Virar produto hospedado exige
  deploy + autenticação.
