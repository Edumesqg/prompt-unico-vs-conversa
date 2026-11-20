"""Teste manual: a pessoa envia a pergunta na plataforma de IA e cola a resposta aqui.

O laboratório compara o número informado no último turno com o gabarito.
A análise adicional, se for pedida, lê o texto inteiro e a solução oficial.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import streamlit as st

from cliente import ClienteCompativel
from juiz import anexar_juiz
from simulacao import (
    carregar_problemas,
    gabarito,
    ids_v2,
    mensagem_concat,
    mensagem_do_turno,
    mensagem_full,
    pontuar_texto,
    TAREFAS_V2,
)
from um_a_um import (
    _nota_do_registro,
    _rotulo_resultado,
    bloco_metricas,
    interruptor_juiz,
    juiz_esta_ligado,
    mensagem_de_carga,
    titulo_com_ajuda,
    mostrar_conversa,
    mostrar_detalhes,
    mostrar_vereditos,
    tabela_historico,
)

RESULTADOS = Path(__file__).resolve().parent / "resultados"
ARQUIVO = RESULTADOS / "na_mao.jsonl"
PASTA = RESULTADOS / "na_mao"
TITULOS = dict(TAREFAS_V2)
ORDEM = ("full", "concat", "sharded")
ROTULOS = {"full": "FULL", "concat": "CONCAT", "sharded": "SHARDED"}


def _ler_salvos() -> list[dict]:
    if not ARQUIVO.exists():
        return []
    registros = []
    for linha in ARQUIVO.read_text(encoding="utf-8").splitlines():
        if linha.strip():
            registros.append(json.loads(linha))
    return registros


def _gravar_json(registro: dict) -> None:
    if not registro.get("run_id"):
        return
    PASTA.mkdir(exist_ok=True)
    destino = PASTA / f"{registro['run_id']}.json"
    destino.write_text(json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")


def _acrescentar(registro: dict) -> None:
    RESULTADOS.mkdir(exist_ok=True)
    with ARQUIVO.open("a", encoding="utf-8") as arquivo:
        arquivo.write(json.dumps(registro, ensure_ascii=False) + "\n")
    _gravar_json(registro)
    st.session_state.registros_manuais.append(registro)


def _reescrever(registros: list[dict]) -> None:
    RESULTADOS.mkdir(exist_ok=True)
    with ARQUIVO.open("w", encoding="utf-8") as arquivo:
        for registro in registros:
            arquivo.write(json.dumps(registro, ensure_ascii=False) + "\n")
            _gravar_json(registro)


def _estrategia(texto: str) -> str:
    perguntas = texto.count("?")
    if perguntas >= 2:
        return "interrogation"
    if perguntas == 1:
        return "clarification"
    if not texto.strip():
        return "missing"
    return "discussion"


def _total_turnos(condicao: str, amostra: dict) -> int:
    if condicao == "sharded":
        return len(amostra["shards"])
    return 1


def _fechar(rodada: dict, amostra: dict) -> dict:
    turnos = rodada["turns"]
    ultimo = turnos[-1]
    nota = float(ultimo.get("score") or 0.0)
    return {
        "task_id": amostra["task_id"],
        "question": amostra["question"],
        "shards": [fragmento["shard"] for fragmento in amostra["shards"]],
        "condition": rodada["condition"],
        "repetition_index": rodada["repetition_index"],
        "assistant_model": rodada["nome_sistema"],
        "support_model": "leitura local",
        "temperature": None,
        "idioma": "pt",
        "expected_ground_truth": gabarito(amostra),
        "turns": turnos,
        "first_answer_attempt_turn": ultimo["turn_index"],
        "final_extracted_answer": ultimo.get("extracted_answer"),
        "score": nota,
        "is_correct": nota == 100.0,
        "final_length": ultimo.get("response_char_length"),
        "erro": None,
        "origem": "na_mao",
        "run_id": rodada.get("run_id"),
        "iniciado_em": rodada.get("iniciado_em"),
        "terminado_em": datetime.now().isoformat(timespec="seconds"),
        "resposta_oficial": amostra.get("answer"),
        "chamadas": [],
        "prompt_visto": {
            "usuario": turnos[0]["user_message"] if rodada["condition"] != "sharded" else "",
            "fragmentos": [fragmento["shard"] for fragmento in amostra["shards"]] if rodada["condition"] == "sharded" else [],
        },
        "avaliacao_oficial": {
            "metodo": "gsm8k_exact_match",
            "fonte": "lost_in_conversation/tasks/math/task_math.py",
            "extraido": ultimo.get("extracted_answer"),
            "gabarito": gabarito(amostra),
            "score": nota,
            "is_correct": nota == 100.0,
        },
    }


def _instrucao_do_turno(condicao: str, feitos: int, total: int) -> str:
    ultimo = feitos + 1 == total
    if condicao == "sharded" and feitos == 0:
        return (
            "Abra uma conversa nova na IA escolhida. Envie apenas a mensagem apresentada abaixo. "
            "Depois, copie a resposta recebida e volte ao laboratório para continuar. "
            "Não envie os próximos fragmentos antecipadamente."
        )
    if condicao == "sharded" and not ultimo:
        return (
            "Continue no mesmo chat. Envie somente a próxima mensagem apresentada pelo laboratório, "
            "sem reunir os fragmentos anteriores. Depois, registre a resposta recebida e avance para a próxima etapa. "
            "Ainda não é necessário informar o resultado numérico final."
        )
    if condicao == "sharded":
        return (
            "Este é o último fragmento do problema. Continue no mesmo chat, envie a mensagem apresentada "
            "e registre a resposta completa da IA. Depois, informe o número final que a IA apresentou como resultado."
        )
    if condicao == "concat":
        return (
            "Abra uma conversa nova na IA escolhida. Copie a lista completa de informações apresentada abaixo "
            "e envie em uma única mensagem. Em seguida, registre a resposta completa e o resultado numérico final."
        )
    return (
        "Abra uma conversa nova na IA escolhida e envie o texto abaixo. "
        "Depois, copie a resposta completa produzida pela plataforma e cole no laboratório. "
        "Registre também o resultado numérico final informado pela IA."
    )


def _pedir_juiz(registro: dict, amostra: dict) -> None:
    if registro.get("avaliacao_juiz") or not juiz_esta_ligado():
        return
    st.caption(
        "A análise adicional compara a resposta produzida com a solução de referência. "
        "Ela não altera a nota numérica oficial."
    )
    if st.button("Analisar resposta com IA", key=f"mao_btn_{registro.get('run_id')}"):
        modelo = st.session_state.get("ua_juiz", "").strip()
        chave = st.session_state.get("ua_key", "").strip()
        if not chave or not modelo:
            st.warning(
                "Para solicitar a análise adicional, informe uma chave de API válida e o nome do modelo responsável "
                "em Configurar análise adicional."
            )
            return
        cliente = ClienteCompativel(api_key=chave, base_url=st.session_state.get("ua_base", "").strip())
        try:
            anexar_juiz(cliente, modelo, registro, amostra)
        except Exception as exc:
            registro["avaliacao_juiz"] = {"erro": str(exc), "modelo": modelo}
            registro["juiz_model"] = modelo
        _reescrever(st.session_state.registros_manuais)
        st.rerun()


def _desenhar_turno(rodada: dict, amostra: dict) -> None:
    feitos = len(rodada["turns"])
    total = _total_turnos(rodada["condition"], amostra)
    ultimo = feitos + 1 == total
    fala = mensagem_do_turno(amostra, rodada["condition"], feitos)
    st.subheader("Teste em andamento")
    st.caption(
        f"{rodada['nome_sistema']} · {ROTULOS[rodada['condition']]} · {TITULOS.get(rodada['task_id'], rodada['task_id'])}"
    )
    st.markdown(f"**Etapa {feitos + 1} de {total}**")
    if rodada.pop("etapa_registrada", False):
        st.success("Esta etapa foi registrada. Continue no mesmo chat para preservar a sequência da conversa.")
    st.info(_instrucao_do_turno(rodada["condition"], feitos, total))

    st.markdown("**Mensagem para a IA**")
    st.caption("Copie exatamente este texto e envie para a plataforma escolhida.")
    st.code(fala, language="text")

    if rodada["turns"]:
        with st.expander("O que já foi neste chat"):
            for turno in rodada["turns"]:
                st.markdown(f"**Turno {turno['turn_index']}**")
                st.chat_message("user").write(turno["user_message"])
                st.chat_message("assistant").write(turno["assistant_response"])

    chave = f"cola_{rodada['id']}_{feitos}"
    texto = st.text_area(
        "Resposta da IA",
        height=220,
        key=chave,
        placeholder="Cole aqui a resposta completa, sem resumir ou modificar o texto.",
        help="Registrar a resposta completa permite consultar o que aconteceu durante a conversa.",
    )
    numero = ""
    if ultimo:
        numero = st.text_input(
            "Qual foi a resposta numérica final da IA?",
            key=f"numero_{rodada['id']}_{feitos}",
            placeholder="Exemplo: 6000",
            help=(
                "Informe o número apresentado pela IA, e não o valor que você acredita ser correto. "
                "Esse número será comparado com o gabarito oficial."
            ),
        )
    if st.button("Finalizar teste" if ultimo else "Registrar e continuar", type="primary"):
        if not texto.strip():
            st.warning("Cole a resposta recebida antes de continuar.")
        elif ultimo and not numero.strip():
            st.warning("Informe o resultado numérico final antes de concluir o teste.")
        else:
            turno = {
                "turn_index": feitos + 1,
                "user_message": fala,
                "assistant_response": texto.strip(),
                "classified_strategy": "answer_attempt" if ultimo else _estrategia(texto),
                "extracted_answer": None,
                "score": None,
                "response_char_length": len(texto.strip()),
            }
            if ultimo:
                pontuacao = pontuar_texto(numero.strip(), amostra)
                turno["numero_informado"] = numero.strip()
                turno["extracted_answer"] = pontuacao["numero"] or numero.strip()
                turno["score"] = pontuacao["score"]
            rodada["turns"].append(turno)
            if ultimo:
                registro = _fechar(rodada, amostra)
                _acrescentar(registro)
                rodada["encerrada"] = True
                rodada["registro"] = registro
            else:
                rodada["etapa_registrada"] = True
            st.rerun()
    if st.button("Abandonar conversa"):
        st.session_state.manual_rodada = None
        st.session_state.manual_aviso = "A conversa foi abandonada. Você pode iniciar outro teste quando desejar."
        st.rerun()


def _desenhar_encerrada(rodada: dict, amostra: dict) -> None:
    registro = rodada["registro"]
    st.subheader("Teste concluído")
    st.success(
        "Sua conversa foi registrada. O laboratório comparou o número informado com o gabarito oficial do problema. "
        "Agora você pode verificar o resultado, consultar as respostas anteriores e observar se a IA manteve o objetivo da tarefa até o final."
    )
    mostrar_vereditos(registro)
    if registro.get("turns"):
        mostrar_conversa(registro)
    _pedir_juiz(registro, amostra)
    mostrar_detalhes(registro)
    if st.button("Iniciar outro teste", type="primary"):
        st.session_state.manual_rodada = None
        st.rerun()


def _mostrar_registro(registro: dict, amostra: dict | None, oferecer_juiz: bool) -> None:
    condicao = ROTULOS.get(registro.get("condition"), registro.get("condition"))
    st.caption(
        f"{registro.get('assistant_model')} · {condicao} · "
        f"repetição {registro.get('repetition_index')} · {registro.get('iniciado_em') or '—'}"
    )
    mostrar_vereditos(registro)
    if oferecer_juiz and amostra is not None:
        _pedir_juiz(registro, amostra)
    if registro.get("turns"):
        st.subheader("O que aconteceu durante o teste?")
        st.caption(
            "No teste manual, os turnos intermediários recebem uma classificação simplificada, baseada em regras de texto. "
            "Essa classificação não equivale à classificação do experimento automatizado."
        )
        mostrar_conversa(registro)
    mostrar_detalhes(registro)


PASSOS_MANUAL = """
1. **Escolha a IA.** Informe o nome da plataforma que deseja utilizar, como ChatGPT, Copilot ou Gemini.
2. **Escolha o problema.** Selecione uma das tarefas e confira, em **Como a IA receberá o problema**, o texto de cada condição.
3. **Inicie o teste.** Use **Iniciar FULL**, **Iniciar CONCAT** ou **Iniciar SHARDED**. Cada condição pede uma conversa nova.
4. **Abra uma conversa nova.** Acesse a plataforma escolhida e inicie um chat sem mensagens anteriores.
5. **Envie a pergunta.** Copie o texto apresentado no laboratório e envie como uma mensagem comum. Não é necessário configurar uma instrução de sistema.
6. **Registre a resposta.** Copie a resposta completa produzida pela IA e cole no campo indicado.
7. **Continue, quando necessário.** Na condição SHARDED, permaneça no mesmo chat e envie o próximo fragmento apresentado pelo laboratório.
8. **Finalize e compare.** Na última etapa, registre a resposta numérica final. O laboratório compara esse número com o gabarito oficial.
"""


def pagina_na_mao() -> None:
    interruptor_juiz(manual=True)
    titulo_com_ajuda(
        "Teste na sua IA",
        PASSOS_MANUAL,
        "As mensagens são enviadas por você, e a plataforma usa as próprias instruções internas. "
        "O resultado numérico não exige chave de API. A análise adicional, se for pedida, sim.",
    )
    st.subheader("Descubra como a plataforma de IA que você já utiliza responde quando recebe informações de maneiras diferentes.")
    st.markdown(
        "Você não precisa de uma API para experimentar. Escolha um problema e utilize o ChatGPT, Copilot, Gemini "
        "ou outra plataforma de inteligência artificial. O laboratório mostra exatamente quais mensagens devem ser enviadas. "
        "Você copia o texto, envia para a IA escolhida e registra a resposta recebida.\n\n"
        "Ao final, compara o resultado numérico com o gabarito. Nesta modalidade, as respostas são produzidas na plataforma "
        "escolhida por você. O laboratório orienta as mensagens e registra os resultados, mas não controla as configurações internas dessa plataforma. "
        "Os dez problemas estão em português, nesta versão do laboratório."
    )
    st.caption("Não é necessário conhecimento de programação para realizar o teste manual.")
    if "registros_manuais" not in st.session_state:
        st.session_state.registros_manuais = _ler_salvos()
    if "manual_rodada" not in st.session_state:
        st.session_state.manual_rodada = None

    try:
        problemas = carregar_problemas(ids_v2())
    except Exception as exc:
        st.error(mensagem_de_carga(exc))
        return
    por_id = {problema["task_id"]: problema for problema in problemas}

    st.subheader("Qual IA você vai testar?")
    nome = st.text_input(
        "Nome da plataforma",
        key="mao_nome",
        placeholder="ChatGPT, Copilot, Gemini, Claude…",
        help="O nome informado será utilizado para identificar a origem das respostas no histórico.",
    )
    st.caption("Informe o nome da IA antes de iniciar uma conversa.")

    with st.expander("Configurar análise adicional", expanded=False):
        st.markdown(
            "Esta configuração é opcional. Você pode realizar o teste manual e obter o resultado numérico "
            "sem informar uma chave de API. Caso deseje também uma interpretação textual da resposta, "
            "configure um modelo para realizar a análise."
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
        st.text_input(
            "Modelo responsável pela análise",
            key="ua_juiz",
            help="Utilizado para interpretar a resposta colada e produzir um parecer em português.",
        )

    if st.session_state.get("manual_aviso"):
        st.info(st.session_state.pop("manual_aviso"))

    st.subheader("Escolha um problema")
    st.markdown(
        "Selecione uma das dez tarefas disponíveis. Você poderá apresentar o enunciado completo, "
        "reunir os fragmentos em uma única mensagem ou revelá-los progressivamente ao longo da conversa."
    )
    escolha = st.radio(
        "Problema matemático",
        ids_v2(),
        key="mao_problema",
        format_func=lambda item: f"{ids_v2().index(item) + 1}. {TITULOS.get(item, item)}",
    )
    amostra = por_id[escolha]
    st.caption(f"Identificador da tarefa: {amostra['task_id']}. Número de fragmentos: {len(amostra['shards'])}.")
    rodada = st.session_state.manual_rodada

    if rodada is None:
        with st.expander("Como a IA receberá o problema", expanded=True):
            st.markdown(
                "Os textos estão em português, nesta versão do laboratório. "
                "Na conversa, vale a instrução da plataforma. Não é necessário configurar uma instrução de sistema."
            )
            aba_full, aba_concat, aba_sharded = st.tabs(["FULL", "CONCAT", "SHARDED"])
            with aba_full:
                st.markdown("**FULL — Tudo de uma vez**")
                st.caption("Envie o enunciado completo em uma única mensagem.")
                st.code(mensagem_full(amostra), language="text")
            with aba_concat:
                st.markdown("**CONCAT — Fragmentos reunidos**")
                st.caption("Envie todos os fragmentos organizados em uma lista, dentro de uma única mensagem.")
                st.code(mensagem_concat(amostra), language="text")
            with aba_sharded:
                st.markdown("**SHARDED — Conversa por etapas**")
                st.caption(
                    "Envie um fragmento por vez, sempre no mesmo chat. "
                    "O laboratório apresenta a próxima mensagem depois que você registra a resposta anterior."
                )
                for indice, fragmento in enumerate(amostra["shards"], start=1):
                    st.markdown(f"{indice}. {fragmento['shard']}")
            st.caption("Para comparar as três condições, realize uma conversa nova para cada uma delas.")

    if rodada and escolha != rodada["task_id"]:
        st.warning("Você já tem um teste em andamento.")
        st.markdown(
            f"Plataforma: {rodada['nome_sistema']}. "
            f"Condição: {ROTULOS[rodada['condition']]}. "
            f"Problema: {TITULOS.get(rodada['task_id'], rodada['task_id'])}."
        )
        st.caption("Para preservar o registro da tentativa, conclua a conversa atual ou abandone-a antes de iniciar outra.")
        if st.button("Continuar teste"):
            st.session_state["mao_problema"] = rodada["task_id"]
            st.rerun()
        if st.button("Abandonar teste"):
            st.session_state.manual_rodada = None
            st.session_state.manual_aviso = "A conversa foi abandonada. Você pode iniciar outro teste quando desejar."
            st.rerun()
    elif rodada and rodada.get("encerrada"):
        _desenhar_encerrada(rodada, por_id[rodada["task_id"]])
    elif rodada:
        _desenhar_turno(rodada, por_id[rodada["task_id"]])
    else:
        st.subheader("Sua próxima experiência")
        st.caption("Escolha uma condição para começar. Cada nova tentativa deve ser realizada em um chat separado na plataforma escolhida.")
        botao_full, botao_concat, botao_sharded = st.columns(3)
        with botao_full:
            rodar_full = st.button("Iniciar FULL", type="primary", key="mao_full")
        with botao_concat:
            rodar_concat = st.button("Iniciar CONCAT", type="primary", key="mao_concat")
        with botao_sharded:
            rodar_sharded = st.button("Iniciar SHARDED", type="primary", key="mao_sharded")
        escolhida = "full" if rodar_full else "concat" if rodar_concat else "sharded" if rodar_sharded else ""
        if escolhida:
            if not nome.strip():
                st.warning("Informe o nome da IA antes de iniciar uma conversa.")
            else:
                repeticao = 1 + sum(
                    1
                    for registro in st.session_state.registros_manuais
                    if registro.get("task_id") == escolha
                    and registro.get("condition") == escolhida
                    and registro.get("assistant_model") == nome.strip()
                )
                identificador = datetime.now().strftime("%Y%m%d_%H%M%S")
                st.session_state.manual_rodada = {
                    "id": identificador,
                    "run_id": f"{identificador}_{escolhida}_{escolha.split('/')[-1]}_r{repeticao}",
                    "task_id": escolha,
                    "condition": escolhida,
                    "nome_sistema": nome.strip(),
                    "repetition_index": repeticao,
                    "turns": [],
                    "encerrada": False,
                    "iniciado_em": datetime.now().isoformat(timespec="seconds"),
                }
                st.rerun()

    deste = [registro for registro in st.session_state.registros_manuais if registro.get("task_id") == escolha]
    if not deste:
        st.info("Nenhum teste registrado para este problema. Realize uma execução para começar a construir o histórico.")
    else:
        st.subheader("O que mudou entre os testes?")
        st.markdown(
            "Compare os resultados obtidos quando o mesmo problema foi apresentado de formas diferentes. "
            "Uma única execução mostra apenas o que aconteceu naquela tentativa."
        )
        ultimos: dict[str, dict] = {}
        for registro in deste:
            ultimos[registro.get("condition")] = registro
        destaque = ""
        if rodada and rodada.get("encerrada") and rodada.get("task_id") == escolha:
            destaque = rodada["registro"].get("run_id") or ""
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
                elif ultimos[condicao].get("run_id") == destaque:
                    st.caption("O resultado desta tentativa está acima.")
                else:
                    registro = ultimos[condicao]
                    _mostrar_registro(
                        registro,
                        por_id.get(registro.get("task_id")),
                        oferecer_juiz=True,
                    )

        st.subheader("Histórico de execuções")
        st.caption(
            "Consulte os testes realizados para este problema, incluindo a condição utilizada, a plataforma, "
            "o resultado numérico e, quando disponível, a análise adicional."
        )
        st.dataframe(tabela_historico(deste), hide_index=True, width="stretch")

    bloco_metricas(st.session_state.registros_manuais, ARQUIVO, "na_mao.jsonl")
