"""Cliente compatível com a API de chat da OpenAI.

A chave e a URL ficam só na memória da sessão. Este módulo não calcula preço:
modelos fora da tabela do repositório oficial não têm tarifa conhecida aqui.
"""

from __future__ import annotations

import json
import re
from typing import Any

from openai import OpenAI


def extrair_json(texto: str) -> dict[str, Any]:
    limpo = texto.strip()
    if limpo.startswith("```"):
        limpo = re.sub(r"^```(?:json)?\s*", "", limpo)
        limpo = re.sub(r"\s*```$", "", limpo)
    try:
        valor = json.loads(limpo)
    except json.JSONDecodeError:
        trecho = re.search(r"\{.*\}", limpo, flags=re.DOTALL)
        if trecho is None:
            raise
        valor = json.loads(trecho.group(0))
    if not isinstance(valor, dict):
        raise ValueError("A resposta JSON não é um objeto.")
    return valor


class ClienteCompativel:
    def __init__(self, api_key: str, base_url: str, timeout: float = 90):
        kwargs: dict[str, Any] = {"api_key": api_key, "timeout": timeout}
        url = (base_url or "").strip()
        self.base_url = url
        if url:
            kwargs["base_url"] = url
        if "anthropic.com" in url:
            kwargs["default_headers"] = {"anthropic-version": "2023-06-01"}
        self._sem_temperatura = "anthropic.com" in url
        self._sem_json_object = "anthropic.com" in url
        self.client = OpenAI(**kwargs)

    def _variantes(
        self,
        mensagens: list[dict[str, str]],
        modelo: str,
        temperatura: float,
        max_tokens: int,
        json_mode: bool,
    ) -> list[dict[str, Any]]:
        formatos = [False]
        if json_mode and not self._sem_json_object:
            formatos = [True, False]
        temperaturas: list[float | None] = [None] if self._sem_temperatura else [temperatura, None]
        limites = ("max_completion_tokens", "max_tokens") if self._sem_temperatura else ("max_tokens", "max_completion_tokens")
        vistos: set[str] = set()
        saida: list[dict[str, Any]] = []
        for formato in formatos:
            for limite in limites:
                for temp in temperaturas:
                    item: dict[str, Any] = {"model": modelo, "messages": mensagens, limite: max_tokens}
                    if temp is not None:
                        item["temperature"] = temp
                    if formato:
                        item["response_format"] = {"type": "json_object"}
                    chave = json.dumps(item, sort_keys=True, default=str)
                    if chave in vistos:
                        continue
                    vistos.add(chave)
                    saida.append(item)
        return saida

    def _completar(
        self,
        mensagens: list[dict[str, str]],
        modelo: str,
        temperatura: float,
        max_tokens: int,
        json_mode: bool,
    ) -> Any:
        ultimo_erro: Exception | None = None
        for tentativa in self._variantes(mensagens, modelo, temperatura, max_tokens, json_mode):
            try:
                return self.client.chat.completions.create(**tentativa)
            except Exception as erro:
                ultimo_erro = erro
                texto = str(erro).lower()
                if "temperature" in texto and "deprecated" in texto:
                    self._sem_temperatura = True
                if "response_format" in texto:
                    self._sem_json_object = True
        assert ultimo_erro is not None
        raise ultimo_erro

    def gerar(
        self,
        mensagens: list[dict[str, str]],
        modelo: str,
        temperatura: float = 1.0,
        max_tokens: int = 1000,
        json_mode: bool = False,
    ) -> dict[str, Any]:
        orcamento = max_tokens
        teto = 8000
        ultimo_erro: Exception | None = None
        for _ in range(4):
            resposta = self._completar(mensagens, modelo, temperatura, orcamento, json_mode)
            escolha = resposta.choices[0]
            texto = escolha.message.content or ""
            finish = escolha.finish_reason
            uso = resposta.usage
            total_tokens = getattr(uso, "total_tokens", None) if uso else None
            if json_mode:
                try:
                    mensagem: Any = extrair_json(texto)
                except Exception as erro:
                    ultimo_erro = erro
                    if finish == "length" and orcamento < teto:
                        orcamento = min(teto, max(orcamento * 4, 4000))
                        continue
                    raise
            else:
                mensagem = texto
            if not texto and finish == "length" and orcamento < teto:
                orcamento = min(teto, max(orcamento * 4, 4000))
                continue
            if not texto and finish == "length":
                raise RuntimeError("A resposta veio vazia: o modelo gastou o limite de tokens antes de escrever o texto.")
            return {"message": mensagem, "total_tokens": total_tokens}
        if ultimo_erro is not None:
            raise ultimo_erro
        raise RuntimeError("A chamada não devolveu texto.")
