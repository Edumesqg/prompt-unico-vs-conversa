# Laboratório local — Lost in Conversation (Math)

App para ver e repetir, no seu computador, o experimento de Laban, Hayashi, Zhou e Neville (2025), *LLMs Get Lost in Multi-Turn Conversation* ([arXiv:2505.06120](https://arxiv.org/abs/2505.06120)).

O avaliador numérico vem do repositório oficial [microsoft/lost_in_conversation](https://github.com/microsoft/lost_in_conversation), licença MIT. Os enunciados, os fragmentos, os gabaritos e os prompts que o laboratório envia estão em português: `dados/tarefas_pt.json` e `prompts/`. O número depois de `####` é o mesmo do arquivo oficial. Este laboratório acrescenta a tela e um cliente para qualquer endpoint compatível com a API de chat da OpenAI.

## O que dá para fazer

- **Observatório.** O exemplo documentado no Apêndice J (doces do Andrew, gabarito 85.000 calorias) e a leitura de P, A90 e U. Não chama API.
- **Um a um.** As 10 tarefas de `v2/10_tarefas_math.md`. Abre um problema, mostra os três prompts (FULL, CONCAT e SHARDED) e roda a condição que você escolher. A nota oficial é o exact match GSM8K. Em seguida, uma chamada separada lê a resposta gerada e o gabarito oficial. Cada execução fica em `resultados/um_a_um.jsonl` e em `resultados/um_a_um/<run_id>.json`, com os turnos, as duas avaliações e o texto de cada chamada.
- **Laboratório.** Três problemas de demonstração, nas três condições, para uma rodada em lote.
- **Na mão.** As mesmas 10 tarefas, sem API no modelo avaliado: você copia a fala, cola no sistema de IA que já usa e traz a resposta de volta. A nota usa o último número do texto, com o avaliador oficial. No fim, dá para pedir a mesma chamada do juiz.

A escala do laboratório em lote é 3 problemas × 3 repetições × 3 condições = 27 conversas. A tela abre com 1 repetição (9 conversas) para a primeira execução ser menor. Na página Um a um, o recorte é o problema aberto.

## Como rodar

Na pasta `laboratorio`:

```powershell
pip install -r requirements.txt
streamlit run app.py
```

O clone oficial precisa estar em `../lost_in_conversation`.

Informe a URL base, a chave e o nome do modelo. A chave fica só na sessão do navegador. A tarefa de código do artigo não entra nesta versão: a avaliação dela não roda no Windows.

Se você usar o código ou os dados, cite o artigo:

```
@article{laban2025llms,
  title={LLMs Get Lost In Multi-Turn Conversation},
  author={Laban, Philippe and Hayashi, Hiroaki and Zhou, Yingbo and Neville, Jennifer},
  journal={arXiv preprint arXiv:2505.06120},
  year={2025}
}
```
