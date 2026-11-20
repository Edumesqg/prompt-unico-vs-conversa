"""Exemplo documentado no Apêndice J / Figura 11 de Laban et al. (2025).

Os turnos abaixo registram o que o artigo descreve. O texto longo do modelo
não é reproduzido aqui: o artigo publica o desvio, os números inventados e o
resultado da extração. Gabarito: 85.000 calorias. Extraído: 45.000.
"""

from __future__ import annotations

EXEMPLO = {
    "fonte": "Laban, Hayashi, Zhou e Neville, 2025. Apêndice J, Figura 11.",
    "modelo": "Llama-3.1-8B-Instruct",
    "tarefa": "Math (GSM8K)",
    "gabarito": 85000,
    "extraido": 45000,
    "conta": "Mini rolo = 600 ÷ 3 = 200 calorias; 200 × 200 = 40.000. Mini muffin = 450 ÷ 3 = 150; 300 × 150 = 45.000. Soma = 85.000.",
    "fragmentos": [
        "Calcular o total de calorias dos doces de Andrew.",
        "Andrew fez 200 mini rolos de canela.",
        "Andrew também assou 300 mini muffins de mirtilo.",
        "Cada mini doce tem cerca de 1/3 das calorias da versão normal.",
        "Um rolo de canela de tamanho normal tem cerca de 600 calorias.",
        "Um muffin de mirtilo normal tem 450 calorias.",
    ],
    "turnos": [
        {
            "usuario": "calcule o total de calorias dos doces do Andrew",
            "leitura": "O usuário só diz o objetivo.",
            "desvio": "O modelo não pede os dados. Inventa quatro doces (croissant de chocolate 250 cal, mille-feuille de framboesa 320 cal, tira de tiramisu 84 cal, quadrado de maçã 125 cal) e calcula esses valores.",
        },
        {
            "usuario": "Andrew fez 200 mini rolos de canela.",
            "leitura": "Entra o primeiro dado real.",
            "desvio": "Incorpora os 200 rolos, assume por conta própria 85 calorias cada (17.000) e mantém os doces inventados no turno 1.",
        },
        {
            "usuario": "Ah, o Andrew também assou 300 mini muffins de mirtilo.",
            "leitura": "Entra o segundo doce.",
            "desvio": "Assume 120 calorias para cada mini muffin (36.000) e segue com o contexto anterior.",
        },
        {
            "usuario": "Cada mini doce tem cerca de um terço das calorias da versão de tamanho normal.",
            "leitura": "Chega a regra que corrige as suposições.",
            "desvio": "Aplica a fração de 1/3, e ainda gasta o turno recalculando os doces que ele mesmo inventou.",
        },
        {
            "usuario": "Um rolo de canela de tamanho normal tem cerca de 600 calorias.",
            "leitura": "Dado que fixa o rolo de canela.",
            "desvio": "Corrige o mini rolo para 200 calorias (200 × 200 = 40.000).",
        },
        {
            "usuario": "Informa que um muffin de mirtilo normal tem 450 calorias.",
            "leitura": "Último dado. Mini muffin = 150 calorias; 300 × 150 = 45.000.",
            "desvio": "Devolve só 45.000. Esquece a instrução original de somar rolos e muffins. O extrator lê 45000. O gabarito é 85000. Nota 0.",
        },
    ],
}

ILUSTRACAO = [
    {"Cenário": "FULL, esquema do Apêndice E", "P": 90, "A90": 90, "U": 0},
    {"Cenário": "SHARDED, perda só de aptidão", "P": 60, "A90": 60, "U": 0},
    {"Cenário": "SHARDED, perda só de confiabilidade", "P": 60, "A90": 90, "U": 90},
    {"Cenário": "SHARDED, o que o experimento mostra", "P": 60, "A90": 80, "U": 60},
]
