"""Segunda leitura da resposta: uma chamada compara o texto gerado com o gabarito.

A nota numérica continua sendo o exact match GSM8K do repositório oficial.
Esta chamada acrescenta um parecer sobre o número e o raciocínio.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from cliente import ClienteCompativel, extrair_json

PROMPT = Path(__file__).resolve().parent / "prompts" / "juiz_math.txt"
RACIOCINIOS = {"correto", "parcial", "incorreto"}
SISTEMA = (
    "Você escreve o parecer em português do Brasil. "
    "divergencia e comentario saem em português. "
    "Responda somente com o objeto JSON pedido."
)


def texto_gerado(registro: dict[str, Any]) -> str:
    turnos = registro.get("turns") or []
    if not turnos:
        return ""
    if registro.get("condition") == "sharded" and len(turnos) > 1:
        partes = []
        for turno in turnos:
            partes.append(
                f"Turno {turno['turn_index']}\n"
                f"Usuário: {turno.get('user_message', '')}\n"
                f"Assistente: {turno.get('assistant_response', '')}"
            )
        return "\n\n".join(partes)
    return str(turnos[-1].get("assistant_response") or "")


def _booleano(valor: Any) -> bool | None:
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, str):
        texto = valor.strip().lower()
        if texto in {"true", "sim", "yes", "iguais"}:
            return True
        if texto in {"false", "nao", "não", "no", "diferentes"}:
            return False
    return None


def _raciocinio(valor: Any) -> str:
    texto = str(valor or "").strip().lower()
    return texto if texto in RACIOCINIOS else ""


def anexar_juiz(
    cliente: ClienteCompativel,
    modelo: str,
    registro: dict[str, Any],
    amostra: dict[str, Any],
) -> dict[str, Any]:
    """Chama o juiz, grava o parecer em registro['avaliacao_juiz'] e o rastro em chamadas."""
    prompt = (
        PROMPT.read_text(encoding="utf-8")
        .replace("[[PROBLEMA]]", str(amostra.get("question") or registro.get("question") or ""))
        .replace("[[GABARITO]]", str(amostra.get("answer") or registro.get("resposta_oficial") or ""))
        .replace("[[RESPOSTA]]", texto_gerado(registro))
    )
    mensagens = [
        {"role": "system", "content": SISTEMA},
        {"role": "user", "content": prompt},
    ]
    try:
        pacote = cliente.gerar(mensagens, modelo=modelo, temperatura=0.0, max_tokens=700, json_mode=True)
        bruto: Any = pacote["message"]
        tokens = pacote.get("total_tokens")
    except Exception:
        pacote = cliente.gerar(mensagens, modelo=modelo, temperatura=0.0, max_tokens=700, json_mode=False)
        bruto = pacote["message"]
        tokens = pacote.get("total_tokens")

    registro.setdefault("chamadas", []).append(
        {
            "quando": datetime.now().isoformat(timespec="seconds"),
            "papel": "juiz",
            "modelo": modelo,
            "temperatura": 0.0,
            "max_tokens": 700,
            "json_mode": True,
            "mensagens": [dict(item) for item in mensagens],
            "resposta": dict(bruto) if isinstance(bruto, dict) else bruto,
            "total_tokens": tokens,
        }
    )

    dados = bruto if isinstance(bruto, dict) else None
    if dados is None:
        try:
            dados = extrair_json(str(bruto))
        except Exception as exc:
            parecer = {
                "modelo": modelo,
                "prompt": prompt,
                "erro": f"O juiz não devolveu JSON: {exc}",
                "resposta_bruta": str(bruto),
            }
            registro["avaliacao_juiz"] = parecer
            registro["juiz_model"] = modelo
            return parecer

    raciocinio = _raciocinio(dados.get("raciocinio"))
    parecer = {
        "modelo": modelo,
        "prompt": prompt,
        "numero_na_resposta": str(dados.get("numero_na_resposta") or ""),
        "numero_oficial": str(dados.get("numero_oficial") or ""),
        "numeros_coincidem": _booleano(dados.get("numeros_coincidem")),
        "raciocinio": raciocinio,
        "divergencia": str(dados.get("divergencia") or ""),
        "comentario": str(dados.get("comentario") or ""),
    }
    if not raciocinio and dados.get("raciocinio") not in (None, ""):
        parecer["raciocinio_original"] = dados.get("raciocinio")
    registro["avaliacao_juiz"] = parecer
    registro["juiz_model"] = modelo
    return parecer
