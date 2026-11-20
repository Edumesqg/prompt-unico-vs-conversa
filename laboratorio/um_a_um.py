"""Teste automático: uma tarefa da v2 por vez, nas três condições do artigo.

FULL, CONCAT e SHARDED usam os textos em português deste laboratório. A nota
oficial é o exact match GSM8K. A análise adicional, se estiver ligada, lê a
resposta gerada e o gabarito oficial. Cada execução fica em resultados/um_a_um.jsonl.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from cliente import ClienteCompativel
from juiz import anexar_juiz
from metricas import resumir
from simulacao import (
    LaboratorioMath,
    TAREFAS_V2,
    carregar_problemas,
    ids_v2,
    instrucao_sistema,
    mensagem_concat,
    mensagem_full,
    rodar_uma,
)

RESULTADOS = Path(__file__).resolve().parent / "resultados"
ARQUIVO = RESULTADOS / "um_a_um.jsonl"
PASTA = RESULTADOS / "um_a_um"
TITULOS = dict(TAREFAS_V2)
ORDEM = ("full", "concat", "sharded")
ROTULOS = {"full": "FULL", "concat": "CONCAT", "sharded": "SHARDED"}
ESTRATEGIAS = {
    "answer_attempt": "Tentativa de resposta",
    "clarification": "Pedido de esclarecimento",
    "interrogation": "Múltiplas perguntas",
    "discussion": "Discussão do problema",
    "hedge": "Resposta baseada em hipóteses",
    "refuse": "Recusa de resposta",
    "missing": "Não classificado",
}
PAPEIS = {
    "modelo_avaliado": "Modelo avaliado",
    "simulador_de_usuario": "Simulador de usuário",
    "classificador": "Classificador de turno",
    "extrator": "Extrator de resultado",
    "juiz": "Analisador adicional",
}
RACIOCINIO = {
    "correto": "Correto",
    "parcial": "Parcialmente correto",
    "incorreto": "Incorreto",
}


def _ler() -> list[dict]:
    if not ARQUIVO.exists():
        return []
    registros = []
    for linha in ARQUIVO.read_text(encoding="utf-8").splitlines():
        if linha.strip():
            registros.append(json.loads(linha))
    return registros


def _salvar(registro: dict) -> None:
    RESULTADOS.mkdir(exist_ok=True)
    PASTA.mkdir(exist_ok=True)
    with ARQUIVO.open("a", encoding="utf-8") as arquivo:
        arquivo.write(json.dumps(registro, ensure_ascii=False) + "\n")
    destino = PASTA / f"{registro['run_id']}.json"
    destino.write_text(json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")
    st.session_state.registros_um.append(registro)


def _proxima_repeticao(registros: list[dict], task_id: str, condicao: str, modelo: str) -> int:
    feitas = [
        registro["repetition_index"]
        for registro in registros
        if registro.get("task_id") == task_id
        and registro.get("condition") == condicao
        and registro.get("assistant_model") == modelo
    ]
    return (max(feitas) if feitas else 0) + 1


def _rotulo_coincide(valor: bool | None) -> str:
    if valor is True:
        return "Números coincidem"
    if valor is False:
        return "Números diferentes"
    return "Não foi possível determinar"


def _rotulo_raciocinio(valor: str | None) -> str:
    if not valor:
        return "—"
    return RACIOCINIO.get(str(valor).strip().lower(), str(valor))


def _nota_do_registro(registro: dict) -> float | None:
    if registro.get("erro"):
        return None
    oficial = registro.get("avaliacao_oficial") or {}
    nota = oficial.get("score", registro.get("score"))
    if nota is None:
        return None
    return float(nota)


def _rotulo_resultado(nota: float | None) -> str:
    if nota is None:
        return "Resultado indisponível"
    if nota == 100.0:
        return "Resposta correta"
    return "Resposta incorreta"


def _nota_oficial(nota: float | None) -> str:
    if nota is None:
        return "—"
    if nota == 100.0:
        return "1"
    if nota == 0.0:
        return "0"
    return f"{nota:.0f}"


def mensagem_de_carga(exc: BaseException) -> str:
    detalhe = str(exc)
    if isinstance(exc, FileNotFoundError):
        return f"Os arquivos da pesquisa original não foram encontrados.\n\nCaminho configurado: {detalhe}"
    if isinstance(exc, ImportError):
        return f"Não foi possível carregar o avaliador numérico oficial.\n\nArquivo: {detalhe}"
    if isinstance(exc, KeyError):
        return f"Algumas tarefas não foram encontradas no conjunto de dados.\n\nIdentificadores: {detalhe}"
    return (
        "Não foi possível carregar os problemas do experimento. "
        "Verifique se o repositório original está disponível e se os arquivos necessários foram configurados corretamente.\n\n"
        f"Detalhes técnicos: {detalhe}"
    )


def juiz_esta_ligado() -> bool:
    return bool(st.session_state.get("juiz_ligado", True))


def interruptor_juiz(manual: bool = False) -> bool:
    """Interruptor no topo da página. O mesmo estado vale nas duas modalidades de teste."""
    ligado = st.toggle(
        "Habilitar análise adicional por IA",
        value=True,
        key="juiz_ligado",
        help=(
            "Ligada, uma IA compara a resposta produzida com a solução oficial e escreve um parecer. "
            "Desligada, o teste fica só com a comparação numérica. O parecer não altera a nota oficial."
        ),
    )
    if ligado and manual:
        st.caption(
            "A análise adicional está habilitada. Você poderá solicitá-la depois de concluir a conversa. "
            "O resultado numérico não exige chave de API."
        )
    elif ligado:
        st.caption("A análise adicional está habilitada. No teste automático, ela será solicitada após a avaliação numérica.")
    else:
        st.caption("A análise adicional está desabilitada. O teste utilizará somente a comparação numérica oficial.")
    return ligado


def titulo_com_ajuda(titulo: str, passos: str, observacao: str = "") -> None:
    """Título da página com um ícone que abre o passo a passo de uso."""
    coluna_titulo, coluna_ajuda = st.columns([0.86, 0.14], vertical_alignment="center")
    with coluna_titulo:
        st.title(titulo)
    with coluna_ajuda:
        with st.popover(
            "Ajuda",
            icon=":material/help:",
            type="tertiary",
            help="Mostra o passo a passo para usar esta página",
            width=480,
        ):
            st.markdown("**Passo a passo**")
            st.markdown(passos)
            if observacao:
                st.caption(observacao)


def mostrar_vereditos(registro: dict) -> None:
    if registro.get("erro"):
        st.error(
            "Não foi possível concluir esta execução. Consulte os detalhes do erro e verifique a configuração da API."
        )
        st.caption(str(registro["erro"]))

    nota = _nota_do_registro(registro)
    oficial = registro.get("avaliacao_oficial") or {}
    numero = oficial.get("extraido") or registro.get("final_extracted_answer") or "—"
    esperado = oficial.get("gabarito") or registro.get("expected_ground_truth") or "—"
    condicao = ROTULOS.get(registro.get("condition"), registro.get("condition") or "—")
    modelo = registro.get("assistant_model") or "—"

    coluna_resultado, coluna_numero, coluna_esperado, coluna_condicao = st.columns(4)
    coluna_resultado.metric("Resultado numérico", _rotulo_resultado(nota))
    coluna_numero.metric("Resposta apresentada pela IA", numero)
    coluna_esperado.metric("Resposta esperada", esperado)
    coluna_condicao.metric("Condição testada", condicao)
    st.caption(f"Modelo ou plataforma: {modelo}")

    if nota is None:
        st.info(
            "**Não foi possível verificar o resultado numérico.** "
            "O laboratório não possui um número final válido para comparar com o gabarito. "
            "Revise o resultado registrado ou os detalhes da execução."
        )
    elif nota == 100.0:
        st.success(
            "**A IA chegou ao resultado esperado.** "
            "O número final corresponde ao gabarito oficial do problema. "
            "Isso confirma o acerto numérico nesta execução, mas não significa necessariamente "
            "que todas as etapas do raciocínio foram corretas."
        )
    else:
        st.warning(
            "**A IA não chegou ao resultado esperado.** "
            "O número final apresentado é diferente do gabarito oficial. "
            "Consulte o histórico da conversa para observar como a resposta foi construída e, "
            "se desejar, solicite a análise adicional por IA."
        )
    if registro.get("origem") == "na_mao" and nota is not None:
        st.caption("No teste manual, a comparação considera o número informado por você.")

    st.markdown("**Avaliação numérica oficial**")
    st.caption(
        "A avaliação utiliza o critério de correspondência numérica exata do GSM8K, "
        "conforme a implementação original utilizada pelo laboratório. "
        "Nota 1: o resultado numérico corresponde ao gabarito. "
        "Nota 0: o resultado numérico não corresponde ao gabarito. "
        "Essa nota avalia o número final, não a qualidade integral do raciocínio."
    )
    st.metric("Nota oficial", _nota_oficial(nota))

    with st.expander("Solução oficial"):
        st.caption(
            "Esta é a resolução de referência disponível no conjunto de dados deste laboratório. "
            "O número final indicado após `####` é o que verifica a resposta."
        )
        st.code(registro.get("resposta_oficial") or "", language="text")

    juiz = registro.get("avaliacao_juiz") or {}
    with st.expander("Análise do raciocínio"):
        if not juiz:
            if juiz_esta_ligado():
                st.caption(
                    "Esta conversa ainda não possui uma análise adicional. "
                    "Você pode solicitar uma avaliação por IA ou consultar somente o resultado numérico oficial."
                )
            else:
                st.caption("A análise adicional está desabilitada. O teste utilizou somente a comparação numérica oficial.")
        elif juiz.get("erro"):
            st.error("Não foi possível concluir a análise adicional.")
            st.caption("O resultado numérico do teste permanece registrado.")
            st.caption(f"Detalhes: {juiz['erro']}")
            if juiz.get("resposta_bruta"):
                st.markdown("**Ver texto original da análise**")
                st.code(juiz["resposta_bruta"], language="text")
        else:
            st.caption(
                "A análise adicional compara a resposta produzida com a solução de referência. "
                "Ela é complementar e não altera a nota numérica oficial. "
                "Como o parecer também é produzido por inteligência artificial, pode conter interpretações incorretas."
            )
            coluna_numeros, coluna_raciocinio = st.columns(2)
            coluna_numeros.metric("Comparação dos números", _rotulo_coincide(juiz.get("numeros_coincidem")))
            coluna_raciocinio.metric("Avaliação do raciocínio", _rotulo_raciocinio(juiz.get("raciocinio")))
            st.markdown("**Onde a resposta divergiu**")
            st.write(juiz.get("divergencia") or "A análise não identificou uma divergência a relatar.")
            if juiz.get("comentario"):
                st.markdown("**Interpretação do resultado**")
                st.write(juiz["comentario"])
            st.caption(f"Modelo responsável pela análise: {juiz.get('modelo') or registro.get('juiz_model') or '—'}")
            if juiz.get("prompt"):
                with st.expander("Ver instruções enviadas para a análise"):
                    st.code(juiz.get("prompt") or "", language="text")
            if juiz.get("resposta_bruta"):
                with st.expander("Ver texto original da análise"):
                    st.code(juiz["resposta_bruta"], language="text")


def mostrar_conversa(registro: dict) -> None:
    st.markdown("**Conversa registrada**")
    st.caption("Veja as mensagens enviadas e as respostas produzidas pela IA ao longo do teste. Cada etapa está na ordem em que ocorreu.")
    for turno in registro.get("turns") or []:
        with st.container(border=True):
            estrategia = ESTRATEGIAS.get(turno.get("classified_strategy"), turno.get("classified_strategy") or "Não classificado")
            st.markdown(f"**Turno {turno['turn_index']}**")
            st.markdown("**Mensagem enviada**")
            st.chat_message("user").write(turno.get("user_message") or "")
            st.markdown("**Resposta da IA**")
            st.chat_message("assistant").write(turno.get("assistant_response") or "")
            st.caption(f"Classificação do turno: {estrategia}")
            if turno.get("extracted_answer"):
                nota = turno.get("score")
                texto_nota = "—" if nota is None else _nota_oficial(float(nota))
                st.caption(
                    f"Resultado numérico identificado: {turno['extracted_answer']}. "
                    f"Nota numérica do turno: {texto_nota}."
                )


def mostrar_detalhes(registro: dict) -> None:
    with st.expander("Detalhes técnicos"):
        st.caption(
            "Esta seção reúne os registros utilizados para executar e avaliar o experimento. "
            "Ela permite consultar os prompts, as respostas das APIs e as etapas auxiliares da simulação."
        )
        visto = registro.get("prompt_visto") or {}
        if visto:
            st.markdown("**Prompts utilizados**")
            if visto.get("sistema"):
                st.markdown("**Instrução de sistema**")
                st.code(visto["sistema"], language="text")
            if visto.get("usuario"):
                st.markdown("**Mensagem enviada ao modelo**")
                st.code(visto["usuario"], language="text")
            if visto.get("fragmentos"):
                st.markdown("**Fragmentos do problema**")
                for indice, fragmento in enumerate(visto["fragmentos"], start=1):
                    st.markdown(f"{indice}. {fragmento}")
        chamadas = registro.get("chamadas") or []
        st.markdown("**Registro das chamadas à API**")
        if not chamadas:
            st.caption("Nenhuma chamada registrada nesta execução.")
            return
        rotulos = []
        for indice, chamada in enumerate(chamadas, start=1):
            papel = PAPEIS.get(chamada.get("papel"), chamada.get("papel"))
            falha = " · não concluída" if chamada.get("erro") else ""
            rotulos.append(f"Chamada {indice} · {papel} · {chamada.get('quando')}{falha}")
        escolha = st.selectbox(
            "Chamada",
            range(len(rotulos)),
            format_func=lambda indice: rotulos[indice],
            key=f"rastro_{registro.get('run_id')}",
        )
        chamada = chamadas[escolha]
        papel = PAPEIS.get(chamada.get("papel"), chamada.get("papel"))
        st.caption(
            f"Função: {papel}. Modelo utilizado: {chamada.get('modelo')}. "
            f"Temperatura: {chamada.get('temperatura')}. Tokens registrados: {chamada.get('total_tokens')}. "
            f"Data e hora: {chamada.get('quando')}."
        )
        if chamada.get("erro"):
            st.error("Esta chamada não foi concluída.")
            st.caption(f"Detalhes: {chamada['erro']}")
        for mensagem in chamada.get("mensagens") or []:
            st.markdown(f"**{mensagem.get('role')}**")
            st.code(mensagem.get("content") or "", language="text")
        st.markdown("**Resposta recebida**")
        corpo = chamada.get("resposta")
        if isinstance(corpo, dict):
            st.json(corpo)
        else:
            st.code(corpo or "", language="text")


def tabela_historico(registros: list[dict]) -> pd.DataFrame:
    linhas = []
    for registro in registros:
        juiz = registro.get("avaliacao_juiz") or {}
        if not juiz:
            comparacao = "—"
            raciocinio = "—"
        elif juiz.get("erro"):
            comparacao = "Falhou"
            raciocinio = "—"
        else:
            comparacao = _rotulo_coincide(juiz.get("numeros_coincidem"))
            raciocinio = _rotulo_raciocinio(juiz.get("raciocinio"))
        linhas.append(
            {
                "Data": registro.get("iniciado_em"),
                "Condição": ROTULOS.get(registro.get("condition"), registro.get("condition")),
                "Repetição": registro.get("repetition_index"),
                "Modelo ou plataforma": registro.get("assistant_model"),
                "Resultado numérico": _rotulo_resultado(_nota_do_registro(registro)),
                "Número registrado": registro.get("final_extracted_answer") or "—",
                "Comparação da análise": comparacao,
                "Avaliação do raciocínio": raciocinio,
                "Arquivo": registro.get("run_id"),
            }
        )
    return pd.DataFrame(linhas)


def bloco_metricas(registros: list[dict], arquivo: Path, nome_arquivo: str) -> None:
    if not registros:
        return
    st.divider()
    st.subheader("Desempenho e consistência das respostas")
    st.markdown(
        "Além do resultado de cada conversa, o laboratório apresenta três métricas utilizadas na pesquisa original. "
        "Elas permitem explorar o desempenho médio, os melhores resultados e a variação entre diferentes tentativas."
    )
    st.markdown(
        "**P — Desempenho médio.** Em média, com que frequência o modelo acerta? "
        "Representa a média das notas obtidas nas execuções.\n\n"
        "**A90 — Desempenho superior.** Que nível de desempenho o modelo alcança nas melhores tentativas? "
        "Representa o percentil 90 das notas de cada tarefa.\n\n"
        "**U — Instabilidade entre tentativas.** Quanto o resultado varia quando repetimos o mesmo teste? "
        "Representa a diferença entre os percentis 90 e 10 das notas de uma tarefa."
    )
    st.caption(
        "As medidas são calculadas para cada tarefa e depois agregadas entre as tarefas avaliadas, "
        "seguindo a metodologia do artigo. Os valores estão na escala de 0 a 100."
    )
    grupos: dict[tuple, int] = {}
    for registro in registros:
        if registro.get("erro") or registro.get("score") is None:
            continue
        chave = (registro.get("condition"), registro.get("task_id"))
        grupos[chave] = grupos.get(chave, 0) + 1
    if grupos and max(grupos.values()) < 3:
        st.info(
            "Ainda existem poucas execuções para avaliar a consistência. "
            "Com apenas uma execução por tarefa, não há variação observável entre tentativas, e a medida U será zero. "
            "Três repetições permitem uma exploração inicial, mas ainda não oferecem uma estimativa robusta da instabilidade."
        )
    resumo = resumir(registros)
    if not resumo.empty:
        visao = resumo.rename(
            columns={
                "Conversas": "Conversas avaliadas",
                "P": "Desempenho médio (P)",
                "A90": "Desempenho superior (A90)",
                "U": "Instabilidade (U)",
                "Tamanho médio": "Tamanho médio das respostas",
                "Turno médio da 1ª tentativa": "Turno médio da primeira tentativa de resposta",
            }
        )
        visao["Condição"] = visao["Condição"].map(lambda valor: ROTULOS.get(valor, valor))
        st.dataframe(visao, hide_index=True, width="stretch")
    if arquivo.exists():
        st.download_button(
            "Exportar histórico de testes",
            data=arquivo.read_bytes(),
            file_name=nome_arquivo,
            mime="application/jsonl",
        )
        st.caption(
            "O histórico será disponibilizado em formato JSONL, permitindo consultar as execuções e realizar análises posteriores. "
            f"Arquivo: `{nome_arquivo}`."
        )


def _mostrar_registro(registro: dict) -> None:
    condicao = ROTULOS.get(registro.get("condition"), registro.get("condition"))
    st.caption(
        f"{registro.get('assistant_model')} · {condicao} · "
        f"repetição {registro.get('repetition_index')} · {registro.get('iniciado_em')}"
    )
    mostrar_vereditos(registro)
    if registro.get("turns"):
        st.subheader("O que aconteceu durante o teste?")
        st.caption(
            "Uma resposta incorreta pode surgir por diferentes motivos. "
            "A IA pode interpretar uma informação de maneira equivocada, introduzir suposições, "
            "cometer erros de cálculo ou deixar de considerar dados apresentados anteriormente."
        )
        if registro.get("origem") == "na_mao":
            st.caption(
                "No teste manual, os turnos intermediários recebem uma classificação simplificada, baseada em regras de texto. "
                "Essa classificação não equivale à classificação do experimento automatizado."
            )
        mostrar_conversa(registro)
    mostrar_detalhes(registro)


def _texto_do_turno(texto: str) -> str:
    partes = [parte.strip() for parte in texto.split("·")]
    if len(partes) != 3 or not partes[0].startswith("Turno"):
        return texto
    numero = partes[0].removeprefix("Turno").strip()
    estrategia = ESTRATEGIAS.get(partes[1], partes[1])
    fragmentos = partes[2].removeprefix("fragmentos").strip()
    revelados, separador, total = fragmentos.partition("/")
    if not separador:
        return texto
    return (
        f"Acompanhando a conversa — turno {numero}. "
        f"Fragmentos apresentados: {revelados.strip()} de {total.strip()}. "
        f"Classificação do turno: {estrategia}."
    )


def _executar(problemas_por_id: dict, task_id: str, condicoes: list[str], repeticoes: int) -> None:
    base_url = st.session_state.get("ua_base", "").strip()
    api_key = st.session_state.get("ua_key", "").strip()
    modelo = st.session_state.get("ua_modelo", "").strip()
    apoio = st.session_state.get("ua_apoio", "").strip()
    juiz = st.session_state.get("ua_juiz", "").strip() or apoio or modelo
    temperatura = float(st.session_state.get("ua_temperatura", 1.0))
    if not api_key or not modelo:
        st.error("Informe a chave de API e o modelo que deseja testar.")
        return

    cliente = ClienteCompativel(api_key=api_key, base_url=base_url)
    lab = LaboratorioMath(
        cliente=cliente,
        modelo_avaliado=modelo,
        modelo_apoio=apoio,
        temperatura=temperatura,
    )
    amostra = problemas_por_id[task_id]
    status = st.status("Preparando o teste…", expanded=True)
    caixa = status.empty()
    for condicao in condicoes:
        for passo in range(repeticoes):
            repeticao = _proxima_repeticao(st.session_state.registros_um, task_id, condicao, modelo)
            caixa.write(f"Executando {ROTULOS[condicao]} — repetição {passo + 1} de {repeticoes}.")

            def aviso(texto: str, condicao: str = condicao, passo: int = passo) -> None:
                caixa.write(
                    f"Executando {ROTULOS[condicao]} — repetição {passo + 1} de {repeticoes}. "
                    f"{_texto_do_turno(texto)}"
                )

            registro = rodar_uma(
                lab,
                amostra,
                condicao,
                repeticao,
                ao_turno=aviso if condicao == "sharded" else None,
            )
            if not registro.get("erro"):
                caixa.write("Verificando o resultado numérico…")
            if not registro.get("erro") and juiz_esta_ligado():
                caixa.write("Realizando análise adicional por IA…")
                try:
                    anexar_juiz(cliente, juiz, registro, amostra)
                except Exception as exc:
                    registro["avaliacao_juiz"] = {"erro": str(exc), "modelo": juiz}
                    registro["juiz_model"] = juiz
            _salvar(registro)
    status.update(label="Execução concluída e registrada no histórico.", state="complete")


PASSOS_AUTOMATICO = """
1. **Decida a análise adicional.** No topo, o interruptor liga um parecer em português depois da comparação numérica. Desligado, o teste fica só com o resultado numérico.
2. **Configure a IA.** Em **Configuração da IA**, informe a URL da API, a chave e o modelo que será testado. O modelo auxiliar e o modelo da análise adicional são opcionais. As chamadas podem gerar custo.
3. **Escolha o problema.** Selecione uma das dez tarefas matemáticas.
4. **Veja como a IA receberá o problema.** **FULL** envia o enunciado completo. **CONCAT** reúne os fragmentos em uma lista. **SHARDED** revela um fragmento por turno.
5. **Escolha as repetições.** Uma execução serve para explorar. Três execuções mostram se o resultado muda entre tentativas da mesma tarefa.
6. **Execute.** Use **Testar FULL**, **Testar CONCAT**, **Testar SHARDED** ou **Testar as três condições**.
7. **Compare os resultados.** Veja o que mudou entre as condições, abra a conversa de cada uma e consulte o histórico.
"""


def pagina_um_a_um() -> None:
    interruptor_juiz()
    titulo_com_ajuda(
        "Teste automático",
        PASSOS_AUTOMATICO,
        "O laboratório envia as mensagens pela API configurada e registra cada execução.",
    )
    st.subheader("Compare como uma IA responde ao mesmo problema em diferentes formatos de interação.")
    st.markdown(
        "Nesta modalidade, o laboratório executa o experimento utilizando uma API de inteligência artificial. "
        "Você escolhe o problema e o modelo que deseja avaliar. O sistema prepara as mensagens, executa a conversa "
        "e registra o resultado de cada condição.\n\n"
        "As três condições e o avaliador numérico seguem a pesquisa original. "
        "Neste laboratório, os dez problemas e a instrução de sistema estão em português."
    )
    if "registros_um" not in st.session_state:
        st.session_state.registros_um = _ler()

    try:
        problemas = carregar_problemas(ids_v2())
    except Exception as exc:
        st.error(mensagem_de_carga(exc))
        return
    por_id = {problema["task_id"]: problema for problema in problemas}

    with st.expander("Configuração da IA", expanded=True):
        st.markdown(
            "Informe os dados de conexão para executar o experimento. "
            "As chamadas serão enviadas ao serviço configurado e poderão gerar custos de utilização da API."
        )
        st.text_input(
            "URL da API",
            key="ua_base",
            help="Endereço base de um serviço compatível com a API de chat da OpenAI.",
        )
        st.text_input(
            "Chave de API",
            type="password",
            key="ua_key",
            help="Credencial utilizada para acessar o serviço configurado.",
        )
        coluna_modelo, coluna_apoio, coluna_juiz = st.columns(3)
        with coluna_modelo:
            st.text_input(
                "Modelo que será testado",
                key="ua_modelo",
                help="Nome ou identificador do modelo cujas respostas serão avaliadas.",
            )
        with coluna_apoio:
            st.text_input(
                "Modelo auxiliar",
                key="ua_apoio",
                help=(
                    "Utilizado para simular o usuário, classificar as respostas intermediárias e extrair os resultados numéricos. "
                    "Se ficar vazio, será utilizado o modelo avaliado."
                ),
            )
        with coluna_juiz:
            st.text_input(
                "Modelo responsável pela análise adicional",
                key="ua_juiz",
                help=(
                    "Utilizado para interpretar as respostas e produzir um parecer em português. "
                    "Se ficar vazio, será utilizado o modelo auxiliar ou, na ausência dele, o modelo avaliado."
                ),
            )
        st.slider(
            "Temperatura do modelo",
            0.0,
            1.0,
            1.0,
            0.1,
            key="ua_temperatura",
            help="Configuração de geração que pode influenciar a variabilidade das respostas, quando suportada pela API escolhida.",
        )

    st.subheader("Escolha um problema")
    st.markdown(
        "Selecione uma das dez tarefas matemáticas utilizadas neste recorte do experimento. "
        "Cada problema possui um enunciado, uma sequência de fragmentos e uma resposta numérica de referência. "
        "Para preservar a experiência, o gabarito será apresentado depois da execução."
    )
    escolha = st.radio(
        "Problema matemático",
        ids_v2(),
        format_func=lambda item: f"{ids_v2().index(item) + 1}. {TITULOS.get(item, item)}",
    )
    amostra = por_id[escolha]
    st.caption(f"Identificador original: {amostra['task_id']}. Quantidade de fragmentos: {len(amostra['shards'])}.")

    with st.expander("Como a IA receberá o problema", expanded=True):
        st.markdown(
            "Veja como a mesma tarefa será enviada em cada condição experimental. "
            "Os textos estão em português, nesta versão do laboratório."
        )
        st.markdown("**Instrução utilizada neste laboratório**")
        st.caption("As três condições utilizam a mesma instrução de sistema.")
        st.code(instrucao_sistema(), language="text")
        aba_full, aba_concat, aba_sharded = st.tabs(["FULL", "CONCAT", "SHARDED"])
        with aba_full:
            st.markdown("**Enunciado completo**")
            st.caption("O modelo recebe todas as informações necessárias em uma única mensagem.")
            st.code(mensagem_full(amostra), language="text")
        with aba_concat:
            st.markdown("**Fragmentos reunidos**")
            st.caption("O modelo recebe todos os fragmentos organizados em uma lista, dentro de uma única mensagem.")
            st.code(mensagem_concat(amostra), language="text")
        with aba_sharded:
            st.markdown("**Informações distribuídas na conversa**")
            st.caption(
                "O primeiro fragmento inicia a interação. Nos turnos seguintes, um simulador de usuário continua a conversa "
                "e apresenta, no máximo, um novo fragmento por turno."
            )
            for indice, fragmento in enumerate(amostra["shards"], start=1):
                st.markdown(f"{indice}. {fragmento['shard']}")

    st.subheader("Executar comparação")
    opcoes_repeticao = {
        "1 execução — exploração inicial": 1,
        "3 execuções — comparação com repetições": 3,
    }
    rotulo_repeticao = st.radio(
        "Quantas vezes deseja repetir cada condição?",
        list(opcoes_repeticao),
        horizontal=True,
        help=(
            "Repetir o mesmo teste permite observar se o modelo produz resultados diferentes para a mesma tarefa. "
            "Com apenas uma execução por condição, ainda não é possível avaliar a instabilidade entre tentativas."
        ),
    )
    repeticoes = opcoes_repeticao[rotulo_repeticao]
    botao_full, botao_concat, botao_sharded, botao_tres = st.columns(4)
    with botao_full:
        rodar_full = st.button("Testar FULL", type="primary")
    with botao_concat:
        rodar_concat = st.button("Testar CONCAT", type="primary")
    with botao_sharded:
        rodar_sharded = st.button("Testar SHARDED", type="primary")
    with botao_tres:
        rodar_tres = st.button("Testar as três condições")

    if rodar_full:
        _executar(por_id, escolha, ["full"], int(repeticoes))
    elif rodar_concat:
        _executar(por_id, escolha, ["concat"], int(repeticoes))
    elif rodar_sharded:
        _executar(por_id, escolha, ["sharded"], int(repeticoes))
    elif rodar_tres:
        _executar(por_id, escolha, ["full", "concat", "sharded"], int(repeticoes))

    deste = [registro for registro in st.session_state.registros_um if registro.get("task_id") == escolha]
    if not deste:
        st.info(
            "Este problema ainda não foi testado. "
            "Escolha uma condição e execute o experimento para visualizar os resultados."
        )
    else:
        st.subheader("O que mudou entre os testes?")
        st.markdown(
            "Compare os resultados obtidos quando o mesmo problema foi apresentado de formas diferentes. "
            "Uma única execução mostra apenas o que aconteceu naquela tentativa. "
            "Acertar em uma condição e errar em outra não demonstra, isoladamente, que a diferença foi causada pelo formato da interação."
        )
        ultimos: dict[str, dict] = {}
        for registro in deste:
            ultimos[registro.get("condition")] = registro
        colunas = st.columns(3)
        for coluna, condicao in zip(colunas, ORDEM):
            with coluna:
                ultimo = ultimos.get(condicao)
                st.markdown(f"**{ROTULOS[condicao]}**")
                if ultimo is None:
                    st.caption("Esta condição ainda não foi testada.")
                else:
                    st.caption(f"Último resultado: {_rotulo_resultado(_nota_do_registro(ultimo))}")
        abas = st.tabs([ROTULOS[condicao] for condicao in ORDEM])
        for aba, condicao in zip(abas, ORDEM):
            with aba:
                if condicao not in ultimos:
                    st.caption("Esta condição ainda não foi testada.")
                else:
                    _mostrar_registro(ultimos[condicao])

        st.subheader("Histórico de execuções")
        st.caption(
            "Consulte os testes realizados para este problema, incluindo a condição utilizada, o modelo avaliado, "
            "o resultado numérico e, quando disponível, a análise adicional."
        )
        st.dataframe(tabela_historico(deste), hide_index=True, width="stretch")

    bloco_metricas(st.session_state.registros_um, ARQUIVO, "um_a_um.jsonl")

