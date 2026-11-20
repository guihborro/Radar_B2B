"""Catálogo de setores (nome amigável -> prefixos de CNAE).

O cliente escolhe setores por nome; aqui traduzimos para os códigos CNAE que o
provedor da Receita entende (comparação por PREFIXO: "4711" casa "4711-3/02").
Catálogo GRANULAR: além das divisões largas, tem os nichos específicos
(supermercado, farmácia, restaurante, academia...). A busca no site filtra.
"""
from __future__ import annotations

SETORES: list[dict] = [
    # ================= INDÚSTRIA =========================================
    {"id": "autopecas", "nome": "Autopeças e fabricação de veículos", "grupo": "Indústria", "cnaes": ["29"]},
    {"id": "metalmecanica", "nome": "Metalmecânica / usinagem / produtos de metal", "grupo": "Indústria", "cnaes": ["25"]},
    {"id": "metalurgia", "nome": "Metalurgia básica", "grupo": "Indústria", "cnaes": ["24"]},
    {"id": "maquinas", "nome": "Máquinas e equipamentos", "grupo": "Indústria", "cnaes": ["28"]},
    {"id": "eletroeletronicos", "nome": "Eletroeletrônicos e componentes", "grupo": "Indústria", "cnaes": ["26"]},
    {"id": "materiais_eletricos", "nome": "Máquinas e materiais elétricos", "grupo": "Indústria", "cnaes": ["27"]},
    {"id": "plasticos", "nome": "Plásticos e borracha", "grupo": "Indústria", "cnaes": ["22"]},
    {"id": "quimica", "nome": "Química", "grupo": "Indústria", "cnaes": ["20"]},
    {"id": "farmaceutica_ind", "nome": "Farmacêutica (indústria)", "grupo": "Indústria", "cnaes": ["21"]},
    {"id": "cosmeticos_ind", "nome": "Cosméticos e higiene (indústria)", "grupo": "Indústria", "cnaes": ["2063"]},
    {"id": "alimentos", "nome": "Alimentos (indústria, geral)", "grupo": "Indústria", "cnaes": ["10"]},
    {"id": "frigorifico", "nome": "Frigoríficos e abate de carnes", "grupo": "Indústria", "cnaes": ["101"]},
    {"id": "laticinios", "nome": "Laticínios", "grupo": "Indústria", "cnaes": ["1052"]},
    {"id": "panificacao_ind", "nome": "Panificação e biscoitos (fabricação)", "grupo": "Indústria", "cnaes": ["1091", "1092"]},
    {"id": "bebidas", "nome": "Bebidas (indústria)", "grupo": "Indústria", "cnaes": ["11"]},
    {"id": "textil", "nome": "Têxtil", "grupo": "Indústria", "cnaes": ["13"]},
    {"id": "confeccao", "nome": "Confecção e vestuário (fabricação)", "grupo": "Indústria", "cnaes": ["14"]},
    {"id": "calcados", "nome": "Couro e calçados (fabricação)", "grupo": "Indústria", "cnaes": ["15"]},
    {"id": "madeira", "nome": "Madeira", "grupo": "Indústria", "cnaes": ["16"]},
    {"id": "moveis", "nome": "Móveis (fabricação)", "grupo": "Indústria", "cnaes": ["31"]},
    {"id": "papel", "nome": "Papel e celulose", "grupo": "Indústria", "cnaes": ["17"]},
    {"id": "grafica", "nome": "Impressão e gráfica", "grupo": "Indústria", "cnaes": ["18"]},
    {"id": "construcao_mat", "nome": "Materiais de construção (não-metálicos)", "grupo": "Indústria", "cnaes": ["23"]},

    # ================= CONSTRUÇÃO =========================================
    {"id": "construcao", "nome": "Construção de edifícios e obras", "grupo": "Construção", "cnaes": ["41", "42"]},
    {"id": "construcao_esp", "nome": "Serviços especializados de construção", "grupo": "Construção", "cnaes": ["43"]},

    # ================= ATACADO ===========================================
    {"id": "atacado_alimentos", "nome": "Atacado de alimentos e bebidas", "grupo": "Atacado", "cnaes": ["463"]},
    {"id": "atacado_medicamentos", "nome": "Atacado de medicamentos e produtos médicos", "grupo": "Atacado", "cnaes": ["4644", "4645"]},
    {"id": "atacado_cosmeticos", "nome": "Atacado de cosméticos e higiene", "grupo": "Atacado", "cnaes": ["4646"]},
    {"id": "atacado_vestuario", "nome": "Atacado de vestuário e tecidos", "grupo": "Atacado", "cnaes": ["464"]},
    {"id": "atacado_construcao", "nome": "Atacado de material de construção", "grupo": "Atacado", "cnaes": ["467"]},
    {"id": "atacado_maquinas", "nome": "Atacado de máquinas e equipamentos", "grupo": "Atacado", "cnaes": ["466"]},
    {"id": "atacado_eletro", "nome": "Atacado de eletrodomésticos e móveis", "grupo": "Atacado", "cnaes": ["4649"]},
    {"id": "atacado_papelaria", "nome": "Atacado de papelaria e livros", "grupo": "Atacado", "cnaes": ["4647", "4761"]},
    {"id": "atacado_agro", "nome": "Insumos agropecuários (atacado)", "grupo": "Atacado", "cnaes": ["4623"]},
    {"id": "atacado_geral", "nome": "Distribuidoras / mercadorias em geral", "grupo": "Atacado", "cnaes": ["469"]},

    # ================= VAREJO ============================================
    {"id": "supermercados", "nome": "Supermercados e mercados", "grupo": "Varejo", "cnaes": ["4711", "4712"]},
    {"id": "lojas_departamento", "nome": "Lojas de departamento / variedades", "grupo": "Varejo", "cnaes": ["4713"]},
    {"id": "padaria_varejo", "nome": "Padarias e confeitarias (loja)", "grupo": "Varejo", "cnaes": ["4721"]},
    {"id": "acougue", "nome": "Açougues e casas de carne", "grupo": "Varejo", "cnaes": ["4722"]},
    {"id": "bebidas_varejo", "nome": "Bebidas (varejo)", "grupo": "Varejo", "cnaes": ["4723"]},
    {"id": "hortifruti", "nome": "Hortifrúti e mercearias de frutas", "grupo": "Varejo", "cnaes": ["4724"]},
    {"id": "postos", "nome": "Postos de combustível", "grupo": "Varejo", "cnaes": ["4731"]},
    {"id": "material_construcao_varejo", "nome": "Material de construção (varejo/lojas)", "grupo": "Varejo", "cnaes": ["4741", "4742", "4743", "4744"]},
    {"id": "informatica_varejo", "nome": "Informática e eletrônicos (varejo)", "grupo": "Varejo", "cnaes": ["4751", "4752"]},
    {"id": "eletro_moveis_varejo", "nome": "Eletrodomésticos e móveis (varejo)", "grupo": "Varejo", "cnaes": ["4753", "4754"]},
    {"id": "tecidos_armarinho", "nome": "Tecidos e armarinho", "grupo": "Varejo", "cnaes": ["4755"]},
    {"id": "livraria_papelaria", "nome": "Livrarias e papelarias", "grupo": "Varejo", "cnaes": ["4761"]},
    {"id": "esportes_brinquedos", "nome": "Artigos esportivos e brinquedos", "grupo": "Varejo", "cnaes": ["4763"]},
    {"id": "farmacias", "nome": "Farmácias e drogarias", "grupo": "Varejo", "cnaes": ["4771"]},
    {"id": "cosmeticos_varejo", "nome": "Cosméticos e perfumaria (varejo)", "grupo": "Varejo", "cnaes": ["4772"]},
    {"id": "oticas", "nome": "Óticas", "grupo": "Varejo", "cnaes": ["4774"]},
    {"id": "vestuario_varejo", "nome": "Lojas de roupa e acessórios", "grupo": "Varejo", "cnaes": ["4781"]},
    {"id": "calcados_varejo", "nome": "Calçados e artigos de couro (varejo)", "grupo": "Varejo", "cnaes": ["4782"]},
    {"id": "joias", "nome": "Joalherias e relógios", "grupo": "Varejo", "cnaes": ["4783"]},
    {"id": "autopecas_varejo", "nome": "Autopeças e acessórios (varejo)", "grupo": "Varejo", "cnaes": ["4530"]},
    {"id": "veiculos", "nome": "Concessionárias e comércio de veículos", "grupo": "Varejo", "cnaes": ["451", "454"]},
    {"id": "varejo_geral", "nome": "Varejo (todos os tipos)", "grupo": "Varejo", "cnaes": ["47"]},

    # ================= ALIMENTAÇÃO E HOSPEDAGEM ==========================
    {"id": "restaurantes", "nome": "Restaurantes, lanchonetes e bares", "grupo": "Alimentação e hospedagem", "cnaes": ["561"]},
    {"id": "catering", "nome": "Catering e refeições coletivas", "grupo": "Alimentação e hospedagem", "cnaes": ["562"]},
    {"id": "hoteis", "nome": "Hotéis e pousadas", "grupo": "Alimentação e hospedagem", "cnaes": ["551"]},
    {"id": "outros_alojamentos", "nome": "Outros alojamentos", "grupo": "Alimentação e hospedagem", "cnaes": ["559"]},

    # ================= TECNOLOGIA E TELECOM ==============================
    {"id": "software", "nome": "Desenvolvimento de software", "grupo": "Tecnologia e telecom", "cnaes": ["6201", "6202", "6203", "6204"]},
    {"id": "ti_servicos", "nome": "Serviços de TI, suporte e hospedagem", "grupo": "Tecnologia e telecom", "cnaes": ["6209", "6311"]},
    {"id": "portais_internet", "nome": "Portais e provedores de conteúdo", "grupo": "Tecnologia e telecom", "cnaes": ["6319"]},
    {"id": "telecom", "nome": "Telecomunicações e provedores de internet", "grupo": "Tecnologia e telecom", "cnaes": ["61"]},

    # ================= SERVIÇOS PROFISSIONAIS ============================
    {"id": "contabilidade", "nome": "Contabilidade e auditoria", "grupo": "Serviços profissionais", "cnaes": ["6920"]},
    {"id": "advocacia", "nome": "Advocacia e jurídico", "grupo": "Serviços profissionais", "cnaes": ["6911"]},
    {"id": "consultoria_gestao", "nome": "Consultoria empresarial", "grupo": "Serviços profissionais", "cnaes": ["7020"]},
    {"id": "engenharia", "nome": "Engenharia", "grupo": "Serviços profissionais", "cnaes": ["7112"]},
    {"id": "arquitetura", "nome": "Arquitetura", "grupo": "Serviços profissionais", "cnaes": ["7111"]},
    {"id": "publicidade", "nome": "Publicidade e marketing", "grupo": "Serviços profissionais", "cnaes": ["731"]},
    {"id": "design", "nome": "Design e criação", "grupo": "Serviços profissionais", "cnaes": ["741"]},
    {"id": "rh", "nome": "Recursos humanos e recrutamento", "grupo": "Serviços profissionais", "cnaes": ["78"]},

    # ================= SAÚDE =============================================
    {"id": "hospitais", "nome": "Hospitais", "grupo": "Saúde", "cnaes": ["8610"]},
    {"id": "clinicas", "nome": "Clínicas médicas e odontológicas", "grupo": "Saúde", "cnaes": ["8630"]},
    {"id": "laboratorios", "nome": "Laboratórios e diagnóstico", "grupo": "Saúde", "cnaes": ["8640"]},
    {"id": "veterinaria", "nome": "Veterinária", "grupo": "Saúde", "cnaes": ["750"]},

    # ================= EDUCAÇÃO ==========================================
    {"id": "escolas", "nome": "Escolas (infantil, fundamental, médio)", "grupo": "Educação", "cnaes": ["851", "852"]},
    {"id": "ensino_superior", "nome": "Ensino superior / faculdades", "grupo": "Educação", "cnaes": ["853"]},
    {"id": "cursos", "nome": "Cursos e ensino profissional", "grupo": "Educação", "cnaes": ["854", "8599"]},
    {"id": "idiomas", "nome": "Escolas de idiomas", "grupo": "Educação", "cnaes": ["8593"]},

    # ================= SERVIÇOS PESSOAIS =================================
    {"id": "academias", "nome": "Academias e condicionamento físico", "grupo": "Serviços pessoais", "cnaes": ["9313"]},
    {"id": "beleza", "nome": "Salões de beleza e estética", "grupo": "Serviços pessoais", "cnaes": ["9602"]},
    {"id": "lavanderia", "nome": "Lavanderias", "grupo": "Serviços pessoais", "cnaes": ["9601"]},
    {"id": "limpeza", "nome": "Limpeza e conservação (empresas)", "grupo": "Serviços pessoais", "cnaes": ["8121"]},
    {"id": "seguranca", "nome": "Segurança e vigilância", "grupo": "Serviços pessoais", "cnaes": ["801"]},
    {"id": "eventos", "nome": "Eventos e festas", "grupo": "Serviços pessoais", "cnaes": ["823", "9001"]},

    # ================= TRANSPORTE E LOGÍSTICA ============================
    {"id": "transporte_carga", "nome": "Transporte rodoviário de carga", "grupo": "Transporte e logística", "cnaes": ["4930"]},
    {"id": "transporte_passageiros", "nome": "Transporte de passageiros", "grupo": "Transporte e logística", "cnaes": ["4921", "4922", "4923", "4924"]},
    {"id": "logistica_armazenagem", "nome": "Armazenagem e logística", "grupo": "Transporte e logística", "cnaes": ["521", "522"]},
    {"id": "entregas", "nome": "Correios e entregas", "grupo": "Transporte e logística", "cnaes": ["532"]},

    # ================= FINANCEIRO E IMOBILIÁRIO ==========================
    {"id": "financeiro", "nome": "Bancos e serviços financeiros", "grupo": "Financeiro e imobiliário", "cnaes": ["64"]},
    {"id": "seguros", "nome": "Seguros e previdência", "grupo": "Financeiro e imobiliário", "cnaes": ["65"]},
    {"id": "imobiliarias", "nome": "Imobiliárias e incorporação", "grupo": "Financeiro e imobiliário", "cnaes": ["68"]},

    # ================= AGRONEGÓCIO =======================================
    {"id": "agricultura", "nome": "Agricultura (lavouras)", "grupo": "Agronegócio", "cnaes": ["011", "012", "013"]},
    {"id": "pecuaria", "nome": "Pecuária (bovinos, aves, suínos)", "grupo": "Agronegócio", "cnaes": ["015"]},
    {"id": "agro_servicos", "nome": "Serviços agropecuários", "grupo": "Agronegócio", "cnaes": ["016"]},
]

_POR_ID = {s["id"]: s for s in SETORES}

# lista (prefixo, nome) ordenada do mais específico (4 díg) ao mais genérico (2)
_PREFIXO_NOME = sorted(
    ((c, s["nome"]) for s in SETORES for c in s["cnaes"]),
    key=lambda t: -len(t[0]),
)

UFS = ["AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
       "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
       "SP", "SE", "TO"]


def grupos() -> dict[str, list[dict]]:
    """Setores agrupados por grande área, preservando a ordem do catálogo."""
    out: dict[str, list[dict]] = {}
    for s in SETORES:
        out.setdefault(s["grupo"], []).append(s)
    return out


def cnaes_de(ids: list[str]) -> list[str]:
    """Junta os prefixos CNAE de vários setores escolhidos (sem duplicar)."""
    vistos: list[str] = []
    for i in ids:
        for c in _POR_ID.get(i, {}).get("cnaes", []):
            if c not in vistos:
                vistos.append(c)
    return vistos


def _so_digitos(c: str) -> str:
    return "".join(ch for ch in str(c) if ch.isdigit())


def nome_do_cnae(cnae: str) -> str:
    """CNAE cru -> nome do setor amigável (casa pelo prefixo mais longo)."""
    d = _so_digitos(cnae)
    for prefixo, nome in _PREFIXO_NOME:
        if d.startswith(_so_digitos(prefixo)):
            return nome
    return "Outro"


def nome_do_id(sid: str) -> str:
    return _POR_ID.get(sid, {}).get("nome", sid)
