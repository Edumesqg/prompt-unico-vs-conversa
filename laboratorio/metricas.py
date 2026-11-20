"""Métricas de Laban et al. (2025): P, A90 e U10^90.

P é a média das notas. A90 é o percentil 90 (o teto da tarefa).
U é a distância entre o percentil 90 e o percentil 10.
Cada métrica é calculada dentro da tarefa e depois tirada a média entre tarefas,
como na seção 4.2 do artigo. O percentil usa o método linear do NumPy.
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd


def resumir(registros: list[dict]) -> pd.DataFrame:
    validos = [r for r in registros if r.get("score") is not None and not r.get("erro")]
    if not validos:
        return pd.DataFrame()

    por_condicao: dict[str, list[dict]] = defaultdict(list)
    for registro in validos:
        por_condicao[registro["condition"]].append(registro)

    linhas = []
    for condicao, grupo in por_condicao.items():
        por_tarefa: dict[str, list[dict]] = defaultdict(list)
        for registro in grupo:
            por_tarefa[registro["task_id"]].append(registro)

        tarefas = []
        for itens in por_tarefa.values():
            notas = np.array([item["score"] for item in itens], dtype=float)
            a90 = float(np.percentile(notas, 90))
            p10 = float(np.percentile(notas, 10))
            tarefas.append({"p": float(np.mean(notas)), "a90": a90, "u": a90 - p10})

        quadro = pd.DataFrame(tarefas)
        comprimentos = [item["final_length"] for item in grupo if item.get("final_length") is not None]
        primeiras = [
            item["first_answer_attempt_turn"]
            for item in grupo
            if item.get("first_answer_attempt_turn") is not None
        ]
        linhas.append(
            {
                "Condição": condicao,
                "Conversas": len(grupo),
                "P": quadro["p"].mean(),
                "A90": quadro["a90"].mean(),
                "U": quadro["u"].mean(),
                "Tamanho médio": float(np.mean(comprimentos)) if comprimentos else None,
                "Turno médio da 1ª tentativa": float(np.mean(primeiras)) if primeiras else None,
            }
        )

    ordem = {"full": 0, "concat": 1, "sharded": 2}
    linhas.sort(key=lambda linha: ordem.get(linha["Condição"], 9))
    return pd.DataFrame(linhas)


def curva_prematura(registros: list[dict]) -> pd.DataFrame:
    sharded = [
        r
        for r in registros
        if r.get("condition") == "sharded" and r.get("score") is not None and not r.get("erro") and r.get("first_answer_attempt_turn")
    ]
    if not sharded:
        return pd.DataFrame()
    quadro = pd.DataFrame(sharded)
    agrupado = (
        quadro.groupby("first_answer_attempt_turn", as_index=False)["score"]
        .mean()
        .rename(columns={"first_answer_attempt_turn": "Turno da 1ª tentativa", "score": "Nota média"})
    )
    return agrupado


def curva_tamanho(registros: list[dict]) -> pd.DataFrame:
    linhas = []
    for registro in registros:
        if registro.get("erro") or registro.get("condition") != "sharded":
            continue
        for turno in registro.get("turns", []):
            if turno.get("response_char_length") is None:
                continue
            linhas.append(
                {
                    "Turno": turno["turn_index"],
                    "Caracteres": turno["response_char_length"],
                }
            )
    if not linhas:
        return pd.DataFrame()
    quadro = pd.DataFrame(linhas)
    return quadro.groupby("Turno", as_index=False)["Caracteres"].mean()
