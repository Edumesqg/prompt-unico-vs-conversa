"""Recorte Math do experimento de Laban et al. (2025).

Os enunciados, os fragmentos, os gabaritos e os prompts saem em português,
a partir de laboratorio/dados/tarefas_pt.json e laboratorio/prompts. O avaliador
GSM8K continua o do repositório oficial (microsoft/lost_in_conversation, licença MIT):
a nota compara o número depois de ####. O cliente de modelo é o deste laboratório.

Condições:
- full: a pergunta original inteira, num turno
- concat: os fragmentos em lista, num turno
- sharded: no máximo um fragmento novo por turno
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from cliente import ClienteCompativel

RAIZ = Path(__file__).resolve().parent
REPO = RAIZ.parent / "lost_in_conversation"
PROMPTS = RAIZ / "prompts"
DADOS_PT = RAIZ / "dados" / "tarefas_pt.json"
DESCRICAO_RESPOSTA = "A resposta deve ser um único número (pode ser decimal, negativo ou uma fração)."
PROBLEMAS_PADRAO = (
    "sharded-GSM8K/2",
    "sharded-GSM8K/799",
    "sharded-GSM8K/929",
)

# As 10 tarefas de v2/10_tarefas_math.md, na ordem do arquivo.
TAREFAS_V2 = (
    ("sharded-GSM8K/1011", "Galões que faltam para encher um tanque"),
    ("sharded-GSM8K/144", "Lucro semanal de um serviço de limpeza"),
    ("sharded-GSM8K/976", "Venda de pão de mel e torta de maçã"),
    ("sharded-GSM8K/369", "Gastos com presentes de formatura"),
    ("sharded-GSM8K/642", "Custo de um guarda-roupa"),
    ("sharded-GSM8K/584", "Preço de um par de lentes"),
    ("sharded-GSM8K/953", "Tempo total de sono"),
    ("sharded-GSM8K/1197", "Gastos com uísque e conhaque"),
    ("sharded-GSM8K/916", "Mesada de duas irmãs"),
    ("sharded-GSM8K/901", "Quantidade de almoços com a sopa restante"),
)


def ids_v2() -> list[str]:
    return [task_id for task_id, _titulo in TAREFAS_V2]

Progresso = Callable[[str], None]


def _ler_prompt(nome: str) -> str:
    return (PROMPTS / nome).read_text(encoding="utf-8")


def _tabela_pt() -> dict[str, Any]:
    return json.loads(DADOS_PT.read_text(encoding="utf-8"))


def aplicar_portugues(amostra: dict[str, Any]) -> dict[str, Any]:
    """Troca enunciado, fragmentos e gabarito pela versão em português. O número depois de #### não muda."""
    tabela = _tabela_pt()
    task_id = amostra["task_id"]
    if task_id not in tabela:
        raise KeyError(f"Sem tradução em português para {task_id}")
    trad = tabela[task_id]
    copia = json.loads(json.dumps(amostra))
    copia["question"] = trad["question"]
    copia["answer"] = trad["answer"]
    por_id = {int(item["shard_id"]): item for item in copia["shards"]}
    trad_shards = trad["shards"]
    if len(trad_shards) != len(por_id):
        raise ValueError(
            f"{task_id}: a tradução tem {len(trad_shards)} fragmentos e o original tem {len(por_id)}"
        )
    vistos: set[int] = set()
    for item in trad_shards:
        shard_id = int(item["shard_id"])
        if shard_id not in por_id:
            raise KeyError(f"{task_id}: fragmento {shard_id} não existe no original")
        por_id[shard_id]["shard"] = item["shard"]
        vistos.add(shard_id)
    if vistos != set(por_id):
        raise ValueError(f"{task_id}: a tradução não cobre todos os fragmentos")
    return copia


def _carregar_tarefa():
    if not REPO.exists():
        raise FileNotFoundError(f"Repositório oficial não encontrado em {REPO}")
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    anterior = os.getcwd()
    os.chdir(REPO)
    try:
        caminho = REPO / "tasks" / "math" / "task_math.py"
        spec = importlib.util.spec_from_file_location("lic_task_math", caminho)
        if spec is None or spec.loader is None:
            raise ImportError(f"Não foi possível carregar {caminho}")
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        return modulo.TaskMath()
    finally:
        os.chdir(anterior)


def carregar_problemas(ids: list[str] | None = None) -> list[dict[str, Any]]:
    caminho = REPO / "data" / "sharded_instructions_600.json"
    amostras = json.loads(caminho.read_text(encoding="utf-8"))
    matematica = [item for item in amostras if item.get("task") == "math"]
    escolhidos = ids or list(PROBLEMAS_PADRAO)
    por_id = {item["task_id"]: item for item in matematica}
    faltando = [item for item in escolhidos if item not in por_id]
    if faltando:
        raise KeyError(f"Problemas ausentes no dataset: {faltando}")
    return [aplicar_portugues(por_id[item]) for item in escolhidos]


def gabarito(amostra: dict[str, Any]) -> str:
    return amostra["answer"].split("####")[1].strip()


_TAREFA = None


def obter_tarefa():
    global _TAREFA
    if _TAREFA is None:
        _TAREFA = _carregar_tarefa()
    return _TAREFA


def instrucao_sistema() -> str:
    return _ler_prompt("sistema_math.txt").strip()


def mensagem_full(amostra: dict[str, Any]) -> str:
    return _prompt_pergunta(_ler_prompt("pergunta_math.txt"), amostra["question"])


def mensagem_concat(amostra: dict[str, Any]) -> str:
    return _prompt_concat(_ler_prompt("pergunta_math.txt"), amostra)


def mensagem_do_turno(amostra: dict[str, Any], condicao: str, turnos_feitos: int) -> str:
    if condicao == "full":
        return mensagem_full(amostra)
    if condicao == "concat":
        return mensagem_concat(amostra)
    return amostra["shards"][turnos_feitos]["shard"]


def ultimo_numero(texto: str) -> str | None:
    import re

    achados = re.findall(r"(-?[$0-9.,]{2,})|(-?[0-9]+)", (texto or "").strip())
    if not achados:
        return None
    grupos = [parte for parte in achados[-1] if parte]
    if not grupos:
        return None
    numero = grupos[0].rstrip(".")
    return numero or None


def pontuar_texto(texto: str, amostra: dict[str, Any]) -> dict[str, Any]:
    resultado = obter_tarefa().evaluator_function(texto, amostra)
    return {
        "score": float(resultado.get("score") or 0.0) * 100.0,
        "numero": ultimo_numero(texto),
    }


def _prompt_pergunta(modelo_prompt: str, pergunta: str) -> str:
    return modelo_prompt.replace("[[QUESTION]]", pergunta)


def _prompt_concat(modelo_prompt: str, amostra: dict[str, Any]) -> str:
    lista = "\n".join(f"- {fragmento['shard']}" for fragmento in amostra["shards"])
    return modelo_prompt.replace("[[QUESTION]]", lista)


def _ultimo_turno_assistente(mensagens: list[dict[str, str]]) -> str:
    for mensagem in reversed(mensagens):
        if mensagem["role"] == "assistant":
            return f"[assistant] {mensagem['content']}"
    return ""


def _conversa_visivel(mensagens: list[dict[str, str]]) -> str:
    linhas = []
    for mensagem in mensagens:
        if mensagem["role"] in ("user", "assistant"):
            linhas.append(f"[{mensagem['role']}] {mensagem['content']}")
    return "\n\n".join(linhas)


class LaboratorioMath:
    def __init__(self, cliente: ClienteCompativel, modelo_avaliado: str, modelo_apoio: str, temperatura: float = 1.0):
        self.cliente = cliente
        self.modelo_avaliado = modelo_avaliado
        self.modelo_apoio = modelo_apoio or modelo_avaliado
        self.temperatura = temperatura
        self.tarefa = _carregar_tarefa()
        self.sistema = _ler_prompt("sistema_math.txt").strip()
        self.prompt_full = _ler_prompt("pergunta_math.txt")
        self.prompt_usuario = _ler_prompt("simulador_usuario.txt")
        self.prompt_classe = _ler_prompt("classificador.txt")
        self.prompt_extracao = _ler_prompt("extrator.txt")
        self.descricao = DESCRICAO_RESPOSTA
        self.eventos: list[dict[str, Any]] = []

    def _gerar(
        self,
        papel: str,
        mensagens: list[dict[str, str]],
        modelo: str,
        temperatura: float,
        max_tokens: int,
        json_mode: bool = False,
    ) -> dict[str, Any]:
        evento: dict[str, Any] = {
            "quando": datetime.now().isoformat(timespec="seconds"),
            "papel": papel,
            "modelo": modelo,
            "temperatura": temperatura,
            "max_tokens": max_tokens,
            "json_mode": json_mode,
            "mensagens": [dict(item) for item in mensagens],
            "resposta": None,
            "total_tokens": None,
            "erro": None,
        }
        try:
            resposta = self.cliente.gerar(
                mensagens,
                modelo=modelo,
                temperatura=temperatura,
                max_tokens=max_tokens,
                json_mode=json_mode,
            )
        except Exception as exc:
            evento["erro"] = str(exc)
            self.eventos.append(evento)
            raise
        corpo = resposta["message"]
        evento["resposta"] = dict(corpo) if isinstance(corpo, dict) else corpo
        evento["total_tokens"] = resposta.get("total_tokens")
        self.eventos.append(evento)
        return resposta

    def _classificar(self, mensagens: list[dict[str, str]], amostra: dict[str, Any]) -> str:
        inicial = amostra["shards"][0]["shard"]
        resto = json.dumps(amostra["shards"][1:], ensure_ascii=False)
        prompt = (
            self.prompt_classe.replace("[[CONVERSATION_SO_FAR]]", _ultimo_turno_assistente(mensagens))
            .replace("[[INITIAL_SHARD]]", inicial)
            .replace("[[SHARDS]]", resto)
            .replace("[[ANSWER_DESCRIPTION]]", self.descricao)
        )
        resposta = self._gerar(
            "classificador",
            [{"role": "user", "content": prompt}],
            modelo=self.modelo_apoio,
            temperatura=0.0,
            max_tokens=200,
            json_mode=True,
        )
        tipo = str(resposta["message"].get("response_type", "missing"))
        permitidos = {
            "answer_attempt",
            "clarification",
            "interrogation",
            "discussion",
            "hedge",
            "refuse",
            "missing",
        }
        return tipo if tipo in permitidos else "missing"

    def _extrair(self, mensagens: list[dict[str, str]]) -> str:
        assistente = [m["content"] for m in mensagens if m["role"] == "assistant"][-1]
        prompt_base = self.prompt_extracao.replace("[[ANSWER_DESCRIPTION]]", self.descricao)
        extraido = ""
        for _ in range(3):
            prompt = prompt_base.replace("[[ASSISTANT_RESPONSE]]", _ultimo_turno_assistente(mensagens))
            resposta = self._gerar(
                "extrator",
                [{"role": "user", "content": prompt}],
                modelo=self.modelo_apoio,
                temperatura=0.0,
                max_tokens=200,
                json_mode=True,
            )
            candidato = str(resposta["message"].get("answer", "")).strip()
            if candidato and candidato in assistente:
                extraido = candidato
                break
        return extraido

    def _avaliar(self, extraido: str, amostra: dict[str, Any]) -> float:
        if not extraido:
            return 0.0
        anterior = os.getcwd()
        os.chdir(REPO)
        try:
            resultado = self.tarefa.evaluator_function(extraido, amostra)
        finally:
            os.chdir(anterior)
        return float(resultado.get("score") or 0.0) * 100.0

    def _registro_base(self, amostra: dict[str, Any], condicao: str, repeticao: int) -> dict[str, Any]:
        return {
            "task_id": amostra["task_id"],
            "question": amostra["question"],
            "shards": [fragmento["shard"] for fragmento in amostra["shards"]],
            "condition": condicao,
            "repetition_index": repeticao,
            "assistant_model": self.modelo_avaliado,
            "support_model": self.modelo_apoio,
            "temperature": self.temperatura,
            "idioma": "pt",
            "expected_ground_truth": gabarito(amostra),
            "resposta_oficial": amostra.get("answer"),
            "turns": [],
            "first_answer_attempt_turn": None,
            "final_extracted_answer": None,
            "score": None,
            "is_correct": False,
            "final_length": None,
            "erro": None,
        }

    def _turno_unico(self, amostra: dict[str, Any], condicao: str, repeticao: int, pergunta: str) -> dict[str, Any]:
        registro = self._registro_base(amostra, condicao, repeticao)
        registro["prompt_visto"] = {"sistema": self.sistema, "usuario": pergunta}
        mensagens = [
            {"role": "system", "content": self.sistema},
            {"role": "user", "content": pergunta},
        ]
        resposta = self._gerar(
            "modelo_avaliado",
            mensagens,
            modelo=self.modelo_avaliado,
            temperatura=self.temperatura,
            max_tokens=1000,
        )
        texto = resposta["message"]
        mensagens.append({"role": "assistant", "content": texto})
        estrategia = self._classificar(mensagens, amostra)
        extraido = self._extrair(mensagens)
        nota = self._avaliar(extraido, amostra)
        registro["turns"].append(
            {
                "turn_index": 1,
                "user_message": pergunta,
                "assistant_response": texto,
                "classified_strategy": estrategia,
                "extracted_answer": extraido or None,
                "score": nota,
                "response_char_length": len(texto),
            }
        )
        registro["first_answer_attempt_turn"] = 1
        registro["final_extracted_answer"] = extraido or None
        registro["score"] = nota
        registro["is_correct"] = nota == 100.0
        registro["final_length"] = len(texto)
        self._fechar_avaliacao_oficial(registro)
        return registro

    def rodar_full(self, amostra: dict[str, Any], repeticao: int) -> dict[str, Any]:
        pergunta = _prompt_pergunta(self.prompt_full, amostra["question"])
        return self._turno_unico(amostra, "full", repeticao, pergunta)

    def rodar_concat(self, amostra: dict[str, Any], repeticao: int) -> dict[str, Any]:
        pergunta = _prompt_concat(self.prompt_full, amostra)
        return self._turno_unico(amostra, "concat", repeticao, pergunta)

    def _fala_do_usuario(self, mensagens: list[dict[str, str]], amostra: dict[str, Any], revelados: set[int]) -> tuple[str, int]:
        if not any(m["role"] == "user" for m in mensagens):
            primeiro = amostra["shards"][0]
            return primeiro["shard"], int(primeiro["shard_id"])

        conhecidos = [s for s in amostra["shards"][1:] if s["shard_id"] in revelados]
        pendentes = [s for s in amostra["shards"][1:] if s["shard_id"] not in revelados]
        prompt = (
            self.prompt_usuario.replace("[[CONVERSATION_SO_FAR]]", _conversa_visivel(mensagens))
            .replace("[[SHARDS_REVEALED]]", json.dumps(conhecidos, ensure_ascii=False))
            .replace("[[SHARDS_NOT_REVEALED]]", json.dumps(pendentes, ensure_ascii=False))
        )
        resposta = self._gerar(
            "simulador_de_usuario",
            [{"role": "user", "content": prompt}],
            modelo=self.modelo_apoio,
            temperatura=self.temperatura,
            max_tokens=300,
            json_mode=True,
        )
        corpo = resposta["message"]
        try:
            shard_id = int(corpo.get("shard_id", -1))
        except (TypeError, ValueError):
            shard_id = -1
        ids_validos = {int(s["shard_id"]) for s in pendentes}
        if shard_id not in ids_validos:
            shard_id = -1
        return str(corpo.get("response", "")).strip(), shard_id

    def rodar_sharded(
        self,
        amostra: dict[str, Any],
        repeticao: int,
        ao_turno: Progresso | None = None,
    ) -> dict[str, Any]:
        registro = self._registro_base(amostra, "sharded", repeticao)
        registro["prompt_visto"] = {
            "sistema": self.sistema,
            "fragmentos": [fragmento["shard"] for fragmento in amostra["shards"]],
        }
        mensagens: list[dict[str, str]] = [{"role": "system", "content": self.sistema}]
        revelados: set[int] = set()
        total = len(amostra["shards"])
        nota_atual = None
        extraido_atual = None
        limite = total + 2

        for indice in range(1, limite + 1):
            if len(revelados) >= total:
                break
            fala, shard_id = self._fala_do_usuario(mensagens, amostra, revelados)
            if shard_id != -1:
                revelados.add(shard_id)
            if not fala:
                fala = "Não sei."
            mensagens.append({"role": "user", "content": fala})
            resposta = self._gerar(
                "modelo_avaliado",
                mensagens,
                modelo=self.modelo_avaliado,
                temperatura=self.temperatura,
                max_tokens=1000,
            )
            texto = resposta["message"]
            mensagens.append({"role": "assistant", "content": texto})
            estrategia = self._classificar(mensagens, amostra)
            extraido = None
            nota = None
            if estrategia == "answer_attempt":
                extraido = self._extrair(mensagens)
                nota = self._avaliar(extraido, amostra)
                nota_atual = nota
                extraido_atual = extraido or None
                if registro["first_answer_attempt_turn"] is None:
                    registro["first_answer_attempt_turn"] = indice
            registro["turns"].append(
                {
                    "turn_index": indice,
                    "user_message": fala,
                    "shard_id": shard_id if shard_id != -1 else None,
                    "assistant_response": texto,
                    "classified_strategy": estrategia,
                    "extracted_answer": extraido or None,
                    "score": nota,
                    "response_char_length": len(texto),
                }
            )
            if ao_turno:
                ao_turno(f"Turno {indice} · {estrategia} · fragmentos {len(revelados)}/{total}")
            if nota == 100.0:
                break
            if len(revelados) >= total:
                break

        registro["final_extracted_answer"] = extraido_atual
        registro["score"] = 0.0 if nota_atual is None else nota_atual
        registro["is_correct"] = registro["score"] == 100.0
        if registro["turns"]:
            registro["final_length"] = registro["turns"][-1]["response_char_length"]
        self._fechar_avaliacao_oficial(registro)
        return registro

    def _fechar_avaliacao_oficial(self, registro: dict[str, Any]) -> None:
        registro["avaliacao_oficial"] = {
            "metodo": "gsm8k_exact_match",
            "fonte": "lost_in_conversation/tasks/math/task_math.py",
            "extraido": registro.get("final_extracted_answer"),
            "gabarito": registro.get("expected_ground_truth"),
            "score": registro.get("score"),
            "is_correct": registro.get("is_correct"),
        }


def _registro_falha(
    lab: LaboratorioMath,
    problema: dict[str, Any],
    condicao: str,
    repeticao: int,
    exc: Exception,
) -> dict[str, Any]:
    return {
        "task_id": problema["task_id"],
        "question": problema["question"],
        "shards": [fragmento["shard"] for fragmento in problema["shards"]],
        "condition": condicao,
        "repetition_index": repeticao,
        "assistant_model": lab.modelo_avaliado,
        "support_model": lab.modelo_apoio,
        "temperature": lab.temperatura,
        "idioma": "pt",
        "expected_ground_truth": gabarito(problema),
        "resposta_oficial": problema.get("answer"),
        "turns": [],
        "first_answer_attempt_turn": None,
        "final_extracted_answer": None,
        "score": None,
        "is_correct": False,
        "final_length": None,
        "erro": str(exc),
    }


def rodar_uma(
    lab: LaboratorioMath,
    problema: dict[str, Any],
    condicao: str,
    repeticao: int,
    ao_turno: Progresso | None = None,
    origem: str = "um_a_um",
) -> dict[str, Any]:
    """Roda uma condição de um problema e devolve o registro com o rastro das chamadas."""
    inicio = datetime.now().isoformat(timespec="seconds")
    lab.eventos = []
    try:
        if condicao == "full":
            registro = lab.rodar_full(problema, repeticao)
        elif condicao == "concat":
            registro = lab.rodar_concat(problema, repeticao)
        elif condicao == "sharded":
            registro = lab.rodar_sharded(problema, repeticao, ao_turno=ao_turno)
        else:
            raise ValueError(f"Condição desconhecida: {condicao}")
    except Exception as exc:
        registro = _registro_falha(lab, problema, condicao, repeticao, exc)
    registro["chamadas"] = list(lab.eventos)
    registro["iniciado_em"] = inicio
    registro["terminado_em"] = datetime.now().isoformat(timespec="seconds")
    registro["run_id"] = (
        datetime.now().strftime("%Y%m%d_%H%M%S")
        + f"_{condicao}_{problema['task_id'].split('/')[-1]}_r{repeticao}"
    )
    registro["origem"] = origem
    return registro


def rodar_recorte(
    lab: LaboratorioMath,
    problemas: list[dict[str, Any]],
    repeticoes: int,
    ao_comecar: Progresso | None = None,
) -> list[dict[str, Any]]:
    saida: list[dict[str, Any]] = []
    plano = [
        (problema, condicao, repeticao)
        for problema in problemas
        for condicao in ("full", "concat", "sharded")
        for repeticao in range(1, repeticoes + 1)
    ]
    for ordem, (problema, condicao, repeticao) in enumerate(plano, start=1):
        if ao_comecar:
            ao_comecar(f"{ordem}/{len(plano)} · {condicao} · {problema['task_id']} · repetição {repeticao}")

        def aviso(
            texto: str,
            ordem: int = ordem,
            condicao: str = condicao,
            problema: dict[str, Any] = problema,
            repeticao: int = repeticao,
        ) -> None:
            if ao_comecar:
                ao_comecar(
                    f"{ordem}/{len(plano)} · {condicao} · {problema['task_id']} · repetição {repeticao} · {texto}"
                )

        registro = rodar_uma(
            lab,
            problema,
            condicao,
            repeticao,
            ao_turno=aviso if condicao == "sharded" else None,
            origem="laboratorio",
        )
        saida.append(registro)
    return saida
