"""Prompt Único vs. Conversa: laboratório local do experimento de Laban et al. (2025).

Os problemas e a instrução de sistema desta versão estão em português.
O avaliador numérico vem de microsoft/lost_in_conversation (MIT).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from cliente import ClienteCompativel
from conexao_demo import aplicar_campos
from metricas import curva_prematura, curva_tamanho, resumir
from observatorio import EXEMPLO, ILUSTRACAO
from na_mao import pagina_na_mao
from simulacao import LaboratorioMath, carregar_problemas, gabarito, rodar_recorte
from um_a_um import pagina_um_a_um

RESULTADOS = Path(__file__).resolve().parent / "resultados"
NOMES_CONDICAO = {
    "full": "FULL",
    "concat": "CONCAT",
    "sharded": "SHARDED",
}
NOMES_ESTRATEGIA = {
    "answer_attempt": "tentativa de resposta",
    "clarification": "pedido de esclarecimento",
    "interrogation": "várias perguntas",
    "discussion": "discussão",
    "hedge": "resposta com hipóteses",
    "refuse": "recusa",
    "missing": "sem classificação",
}


def _rotulo_condicao(valor: str) -> str:
    return NOMES_CONDICAO.get(valor, valor)


def pagina_observatorio() -> None:
    st.title("O modelo se perde quando a instrução chega aos poucos")
    st.markdown(
        "Quando a pergunta inteira vai de uma vez, o modelo parece capaz. "
        "Quando os mesmos dados chegam um por turno, ele completa o que ainda não foi dito, "
        "prende-se a essa suposição e a nota cai. No artigo, a queda média entre 15 modelos foi de **39%**. "
        "O teto (aptidão) recuou pouco. O que explodiu foi a variação entre tentativas da mesma tarefa."
    )

    colunas = st.columns(3)
    cartoes = [
        ("FULL", "A pergunta original, num turno só. É o teste usual."),
        ("CONCAT", "Os mesmos fragmentos, em lista, ainda num turno só. No artigo, recupera cerca de 95% do FULL."),
        ("SHARDED", "Um fragmento por turno. É aqui que a conversa desvia."),
    ]
    for coluna, (titulo, texto) in zip(colunas, cartoes):
        with coluna:
            with st.container(border=True):
                st.subheader(titulo)
                st.write(texto)

    st.divider()
    st.header("O exemplo do artigo")
    st.caption(f"{EXEMPLO['fonte']} Modelo avaliado: {EXEMPLO['modelo']}. Tarefa: {EXEMPLO['tarefa']}.")

    esquerda, direita = st.columns([1, 1.4])
    with esquerda:
        st.subheader("Fragmentos, na ordem em que aparecem")
        for indice, fragmento in enumerate(EXEMPLO["fragmentos"], start=1):
            st.markdown(f"**{indice}.** {fragmento}")
        st.info(EXEMPLO["conta"])
    with direita:
        for indice, turno in enumerate(EXEMPLO["turnos"], start=1):
            with st.container(border=True):
                st.markdown(f"**Turno {indice}**")
                st.markdown(f"Usuário: {turno['usuario']}")
                st.caption(turno["leitura"])
                st.write(turno["desvio"])

    acerto, erro = st.columns(2)
    acerto.metric("Gabarito", "85.000 calorias")
    erro.metric("Valor extraído no último turno", "45.000", delta="-40.000", delta_color="inverse")
    st.caption("O modelo fechou a conta dos muffins e esqueceu de somar os rolos de canela. Nota 0.")

    st.divider()
    st.header("Como ler o resultado de uma rodada")
    st.markdown(
        "**P** é a nota média. **A90** é o percentil 90, o teto da tarefa. "
        "**U** é a distância entre o percentil 90 e o percentil 10: quanto a mesma tarefa oscila entre uma execução e outra."
    )
    st.dataframe(pd.DataFrame(ILUSTRACAO), hide_index=True, width="stretch")
    st.caption(
        "Números ilustrativos do Apêndice E, para uma queda de P = 90 no FULL para P = 60 no SHARDED. "
        "No experimento real, a aptidão caiu cerca de 16% e a não confiabilidade subiu cerca de 112%."
    )


def _grafico_metricas(resumo: pd.DataFrame) -> None:
    longo = resumo.melt(id_vars=["Condição"], value_vars=["P", "A90", "U"], var_name="Métrica", value_name="Valor")
    longo["Condição"] = longo["Condição"].map(_rotulo_condicao)
    grafico = (
        alt.Chart(longo)
        .mark_bar()
        .encode(
            x=alt.X("Condição:N", sort=["FULL", "CONCAT", "SHARDED"], title=None),
            y=alt.Y("Valor:Q", scale=alt.Scale(domain=[0, 100])),
            color=alt.Color("Métrica:N", sort=["P", "A90", "U"]),
            xOffset="Métrica:N",
            tooltip=["Condição", "Métrica", alt.Tooltip("Valor:Q", format=".1f")],
        )
        .properties(height=320)
    )
    st.altair_chart(grafico, width="stretch")


def _grafico_prematura(registros: list[dict]) -> None:
    curva = curva_prematura(registros)
    if curva.empty:
        return
    st.subheader("Nota conforme o turno da primeira tentativa")
    grafico = (
        alt.Chart(curva)
        .mark_bar()
        .encode(
            x=alt.X("Turno da 1ª tentativa:O", title="Turno da primeira tentativa"),
            y=alt.Y("Nota média:Q", scale=alt.Scale(domain=[0, 100])),
            tooltip=[alt.Tooltip("Nota média:Q", format=".1f")],
        )
        .properties(height=260)
    )
    st.altair_chart(grafico, width="stretch")
    st.caption("No SHARDED, tentativa cedo costuma carregar uma suposição que os turnos seguintes não desfazem.")


def _grafico_tamanho(registros: list[dict], resumo: pd.DataFrame) -> None:
    curva = curva_tamanho(registros)
    if curva.empty:
        return
    st.subheader("Tamanho da resposta ao longo dos turnos")
    grafico = alt.Chart(curva).mark_line(point=True).encode(
        x=alt.X("Turno:O", title="Turno no SHARDED"),
        y=alt.Y("Caracteres:Q", title="Caracteres da resposta"),
        tooltip=[alt.Tooltip("Caracteres:Q", format=".0f")],
    )
    referencia = resumo.loc[resumo["Condição"] == "full", "Tamanho médio"]
    if not referencia.empty and pd.notna(referencia.iloc[0]):
        regra = alt.Chart(pd.DataFrame({"Caracteres": [float(referencia.iloc[0])]})).mark_rule(
            strokeDash=[6, 4], color="#b45309"
        ).encode(y="Caracteres:Q")
        grafico = grafico + regra
    st.altair_chart(grafico.properties(height=260), width="stretch")
    st.caption("A linha tracejada é o tamanho médio da resposta no FULL, quando existe essa condição na rodada.")


def _mostrar_transcricao(registros: list[dict]) -> None:
    st.subheader("Transcrição")
    opcoes = []
    for indice, registro in enumerate(registros):
        nota = "erro" if registro.get("erro") else f"nota {registro.get('score')}"
        opcoes.append(
            f"{_rotulo_condicao(registro['condition'])} · {registro['task_id']} · repetição {registro['repetition_index']} · {nota}"
        )
    escolha = st.selectbox("Conversa", range(len(opcoes)), format_func=lambda i: opcoes[i])
    registro = registros[escolha]
    if registro.get("erro"):
        st.error(registro["erro"])
        return
    st.markdown(f"**Gabarito:** {registro['expected_ground_truth']}")
    if registro.get("final_extracted_answer"):
        st.markdown(f"**Última extração:** {registro['final_extracted_answer']}")
    juiz = registro.get("avaliacao_juiz") or {}
    if juiz.get("erro"):
        st.warning(f"Juiz: {juiz['erro']}")
    elif juiz:
        coincide = juiz.get("numeros_coincidem")
        if coincide is True:
            texto_coincide = "iguais"
        elif coincide is False:
            texto_coincide = "diferentes"
        else:
            texto_coincide = "—"
        st.markdown(
            f"**Juiz:** números {texto_coincide} · raciocínio {juiz.get('raciocinio') or '—'}"
        )
        if juiz.get("comentario"):
            st.write(juiz["comentario"])
    with st.expander("Fragmentos desta tarefa"):
        for indice, fragmento in enumerate(registro.get("shards", []), start=1):
            st.markdown(f"{indice}. {fragmento}")
    for turno in registro.get("turns", []):
        with st.container(border=True):
            st.markdown(f"**Turno {turno['turn_index']}** · {NOMES_ESTRATEGIA.get(turno['classified_strategy'], turno['classified_strategy'])}")
            st.chat_message("user").write(turno["user_message"])
            st.chat_message("assistant").write(turno["assistant_response"])
            if turno.get("extracted_answer"):
                st.caption(f"Extraído: {turno['extracted_answer']} · nota deste turno: {turno.get('score')}")


def mostrar_rodada(registros: list[dict]) -> None:
    resumo = resumir(registros)
    if resumo.empty:
        st.warning("Nenhuma conversa desta rodada entrou no cálculo. Veja o erro na transcrição.")
        _mostrar_transcricao(registros)
        return
    visao = resumo.copy()
    visao["Condição"] = visao["Condição"].map(_rotulo_condicao)
    for coluna, casas in (("P", 1), ("A90", 1), ("U", 1), ("Tamanho médio", 0), ("Turno médio da 1ª tentativa", 1)):
        visao[coluna] = visao[coluna].map(lambda valor, casas=casas: None if pd.isna(valor) else round(float(valor), casas))
    st.dataframe(visao, hide_index=True, width="stretch")
    _grafico_metricas(resumo)
    coluna_a, coluna_b = st.columns(2)
    with coluna_a:
        _grafico_prematura(registros)
    with coluna_b:
        _grafico_tamanho(registros, resumo)
    repeticoes = {r["repetition_index"] for r in registros}
    if max(repeticoes or {1}) < 3:
        st.caption("Com uma repetição por problema, U fica perto de zero: ainda não há variação para medir. Use 3 repetições para ler a instabilidade.")
    _mostrar_transcricao(registros)


def pagina_laboratorio() -> None:
    st.title("Laboratório Math")
    st.markdown(
        "Roda o recorte de demonstração da tarefa Math nas três condições, com o modelo que você indicar. "
        "Os prompts, os fragmentos e os gabaritos estão em português. A nota continua o exact match numérico do GSM8K. "
        "As 10 tarefas da v2, uma por vez e com a análise adicional, estão em Teste automático. "
        "Cada conversa gasta chamadas de API no endpoint que você configurar."
    )

    try:
        problemas = carregar_problemas()
    except Exception as exc:
        st.error(str(exc))
        return

    conexao, recorte = st.columns(2)
    with conexao:
        st.subheader("O seu modelo")
        base_url = st.text_input(
            "URL base",
            key="ua_base",
            help="Endpoint compatível com a API de chat da OpenAI. A demo usa o endpoint compatível da Anthropic.",
        )
        api_key = st.text_input("Chave de API", type="password", key="ua_key")
        modelo = st.text_input("Modelo avaliado", key="ua_modelo")
        apoio = st.text_input(
            "Modelo de apoio",
            key="ua_apoio",
            help="Simula o usuário, classifica o turno e extrai o número. No artigo esse papel é do gpt-4o-mini, separado do modelo avaliado. Vazio usa o modelo avaliado.",
        )
        temperatura = st.slider("Temperatura do modelo avaliado", 0.0, 1.0, 1.0, 0.1, key="ua_temperatura")
    with recorte:
        st.subheader("Recorte")
        escolhidos = []
        for problema in problemas:
            marcado = st.checkbox(problema["task_id"], value=True, key=f"problema_{problema['task_id']}")
            if marcado:
                escolhidos.append(problema)
            st.caption(problema["question"][:180] + ("…" if len(problema["question"]) > 180 else ""))
        repeticoes = st.radio("Repetições de cada problema", [1, 3], horizontal=True, index=0)
        st.caption(f"Gabaritos: {', '.join(gabarito(p) for p in problemas)}")

    conversas = len(escolhidos) * int(repeticoes) * 3
    st.markdown(f"Esta rodada tem **{conversas} conversas** (problemas × repetições × FULL, CONCAT e SHARDED).")

    if st.button(f"Rodar {conversas} conversas", type="primary", disabled=conversas == 0):
        if not api_key.strip() or not modelo.strip():
            st.error("Informe a chave e o nome do modelo avaliado.")
            return
        cliente = ClienteCompativel(api_key=api_key.strip(), base_url=base_url.strip())
        lab = LaboratorioMath(
            cliente=cliente,
            modelo_avaliado=modelo.strip(),
            modelo_apoio=apoio.strip(),
            temperatura=float(temperatura),
        )
        status = st.status("Rodando o recorte…", expanded=True)
        caixa = status.empty()

        def aviso(texto: str) -> None:
            caixa.write(texto)

        registros = rodar_recorte(lab, escolhidos, int(repeticoes), ao_comecar=aviso)
        RESULTADOS.mkdir(exist_ok=True)
        destino = RESULTADOS / datetime.now().strftime("rodada_%Y%m%d_%H%M%S.jsonl")
        with destino.open("w", encoding="utf-8") as arquivo:
            for registro in registros:
                arquivo.write(json.dumps(registro, ensure_ascii=False) + "\n")
        st.session_state["registros"] = registros
        st.session_state["arquivo"] = str(destino)
        status.update(label=f"Rodada salva em {destino.name}", state="complete")

    if st.session_state.get("registros"):
        st.caption(f"Arquivo: {st.session_state.get('arquivo', '')}")
        mostrar_rodada(st.session_state["registros"])


def pagina_experimento() -> None:
    st.title("Prompt Único vs. Conversa")
    st.subheader("A forma como você conversa com uma IA pode mudar a qualidade das respostas?")
    st.markdown(
        "Imagine apresentar um problema completo para uma inteligência artificial e receber a resposta correta. "
        "Agora imagine apresentar exatamente o mesmo problema, mas revelando as informações aos poucos, ao longo de uma conversa. "
        "Será que a IA chega ao mesmo resultado?\n\n"
        "Pesquisas mostram que a maneira como as informações são distribuídas durante uma interação pode afetar "
        "o desempenho dos modelos de linguagem. Este laboratório compara respostas produzidas quando a IA recebe "
        "todas as informações de uma vez ou precisa acompanhá-las ao longo de vários turnos.\n\n"
        "**O objetivo não é descobrir qual IA é melhor, mas investigar como o formato da interação influencia o resultado.**"
    )
    st.caption(
        "Este projeto reproduz um recorte do experimento LLMs Get Lost in Multi-Turn Conversation, "
        "de Laban, Hayashi, Zhou e Neville (2025). A pesquisa observou uma queda média de 39% no desempenho "
        "dos 15 modelos avaliados quando as informações foram apresentadas ao longo de conversas. "
        "Esses resultados pertencem ao estudo original. Os testes realizados neste laboratório produzem resultados próprios. "
        "Nesta versão, os dez problemas matemáticos e a instrução de sistema estão em português."
    )

    st.subheader("Três formas de apresentar o mesmo problema")
    st.markdown("Em todas, o objetivo matemático permanece o mesmo. O que muda é a maneira como as informações são apresentadas à IA.")
    colunas = st.columns(3)
    cartoes = [
        ("FULL — Enunciado completo", "Tudo de uma vez. A IA recebe o problema com todas as informações necessárias, em uma única mensagem."),
        ("CONCAT — Informações organizadas", "Todas as partes em uma única mensagem. A IA recebe os fragmentos do problema organizados em uma lista."),
        ("SHARDED — Conversa em etapas", "Uma informação por vez. A IA recebe as informações progressivamente e precisa acompanhar o contexto até a resposta final."),
    ]
    for coluna, (titulo, texto) in zip(colunas, cartoes):
        with coluna:
            with st.container(border=True):
                st.markdown(f"**{titulo}**")
                st.write(texto)
    st.markdown("**O problema é o mesmo. A forma de apresentar as informações é diferente.**")

    st.subheader("Como uma IA pode se perder durante uma conversa?")
    st.markdown(
        "No exemplo apresentado pelos pesquisadores, o modelo precisava calcular o total de calorias de dois tipos de doces. "
        "Ele começou a responder antes de possuir todas as informações. Na resposta final, considerou apenas um dos dois tipos.\n\n"
        "**Resposta correta:** 85.000 calorias. **Resposta final do modelo:** 45.000 calorias. "
        "A IA calculou o subtotal dos muffins, mas deixou de incluir os rolos de canela.\n\n"
        "**O problema não foi apenas calcular. Foi manter o objetivo da tarefa ao longo da conversa.** "
        "Esse exemplo mostra um desvio observado em uma execução específica, não um comportamento inevitável de todas as IAs."
    )
    st.caption(
        "Exemplo adaptado do Apêndice J, Figura 11, de LLMs Get Lost in Multi-Turn Conversation (2025). "
        "Modelo analisado: Llama-3.1-8B-Instruct."
    )

    st.subheader("O que este laboratório permite concluir?")
    st.markdown(
        "As tarefas utilizadas são matemáticas e possuem respostas numéricas verificáveis. "
        "O comportamento observado nesses problemas não representa automaticamente o desempenho da IA em todas as atividades profissionais. "
        "Uma execução isolada também não basta para estabelecer a confiabilidade geral de um modelo.\n\n"
        "O teste automático segue a simulação configurada no laboratório. O teste manual depende da plataforma escolhida "
        "e da forma como as mensagens são enviadas. Os dois modos ajudam a explorar o fenômeno, mas não são metodologicamente idênticos.\n\n"
        "Nas empresas, uma análise pode começar com um pedido simples e evoluir conforme novos dados aparecem. "
        "**Receber uma resposta convincente não significa, necessariamente, que a IA considerou corretamente todas as informações da tarefa.**"
    )

    st.subheader("Agora experimente com a sua IA")
    st.markdown("Escolha uma tarefa, realize os testes e observe os resultados.")
    coluna_auto, coluna_manual = st.columns(2)
    with coluna_auto:
        if st.button("Executar teste automático", type="primary", key="ir_automatico"):
            st.session_state.ir_para = "Teste automático"
            st.rerun()
    with coluna_manual:
        if st.button("Experimentar na minha IA", key="ir_manual"):
            st.session_state.ir_para = "Teste na sua IA"
            st.rerun()
    st.markdown("[Consultar o artigo original](https://arxiv.org/abs/2505.06120)")


def main() -> None:
    st.set_page_config(page_title="Prompt Único vs. Conversa", layout="wide")
    if st.session_state.get("ir_para"):
        st.session_state.pagina_visivel = st.session_state.pop("ir_para")
    st.sidebar.title("Prompt Único vs. Conversa")
    st.sidebar.caption("Um laboratório para explorar como a apresentação das informações influencia as respostas de IA.")
    aplicar_campos()
    pagina = st.sidebar.radio(
        "Menu",
        ["Teste automático", "Teste na sua IA", "O experimento"],
        key="pagina_visivel",
    )
    st.sidebar.markdown("**Sobre o experimento**")
    st.sidebar.caption(
        "Baseado no estudo LLMs Get Lost in Multi-Turn Conversation (2025). "
        "O laboratório utiliza dez problemas matemáticos do conjunto experimental original, apresentados em português. "
        "A simulação automatizada observa o comportamento dos modelos de IA. Ela não representa uma pesquisa com usuários humanos."
    )
    st.sidebar.markdown("[Artigo científico](https://arxiv.org/abs/2505.06120)")
    st.sidebar.caption(
        "Pesquisa original: Laban, Hayashi, Zhou e Neville (2025). "
        "Implementação experimental baseada no repositório microsoft/lost_in_conversation, licença MIT."
    )
    if pagina == "Teste na sua IA":
        pagina_na_mao()
    elif pagina == "O experimento":
        pagina_experimento()
    else:
        pagina_um_a_um()


if __name__ == "__main__":
    main()
