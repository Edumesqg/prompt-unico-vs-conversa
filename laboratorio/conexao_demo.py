"""Preenche a conexão da demo a partir do .env local.

O arquivo .env fica de fora do git. A chave só entra na sessão do navegador.
"""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

ENV = Path(__file__).resolve().parent / ".env"
URL_ABERTA = "https://api.openai.com/v1"


def carregar_env() -> None:
    if not ENV.exists():
        return
    for linha in ENV.read_text(encoding="utf-8").splitlines():
        texto = linha.strip()
        if not texto or texto.startswith("#") or "=" not in texto:
            continue
        chave, valor = texto.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))


def padroes() -> dict[str, str]:
    carregar_env()
    return {
        "base": os.environ.get("DEMO_BASE_URL", URL_ABERTA).strip(),
        "chave": (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY") or "").strip(),
        "modelo": os.environ.get("DEMO_MODEL", "").strip(),
    }


def _se_vazio(chave: str, valor: str, tambem: set[str] | None = None) -> None:
    if not valor:
        return
    atual = st.session_state.get(chave)
    vazios = {None, ""}
    if tambem:
        vazios |= tambem
    if atual in vazios:
        st.session_state[chave] = valor


def aplicar_campos() -> None:
    dados = padroes()
    _se_vazio("ua_base", dados["base"], tambem={URL_ABERTA})
    _se_vazio("ua_key", dados["chave"])
    _se_vazio("ua_modelo", dados["modelo"])
    _se_vazio("ua_apoio", dados["modelo"])
    _se_vazio("ua_juiz", dados["modelo"])
