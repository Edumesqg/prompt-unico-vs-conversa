<div align="center">

# Prompt Único vs. Conversa

### A IA sabe resolver o problema. Mas será que consegue acompanhar a conversa?

**Um laboratório interativo para explorar como a forma de apresentar informações pode influenciar as respostas de modelos de inteligência artificial.**

[**Experimentar o laboratório**](https://prompt-unico-vs-conversa-copiar-fhqycdxtvfnb4husuzkn7g.streamlit.app/) · [**Ler o artigo original**](https://arxiv.org/abs/2505.06120) · [**Consultar o projeto de referência**](https://github.com/microsoft/lost_in_conversation)

</div>

---

## O projeto em 30 segundos

Imagine apresentar um problema completo para uma IA e receber a resposta correta. Agora imagine apresentar **o mesmo problema, com as informações chegando aos poucos**, ao longo de uma conversa. A resposta será a mesma?

**Prompt Único vs. Conversa** transforma essa pergunta em uma experiência prática. É possível comparar três formas de apresentar uma tarefa, registrar as respostas e verificar o resultado com um gabarito numérico.

O objetivo **não é eleger a melhor IA** nem defender que conversas sejam sempre piores que prompts únicos. É permitir que qualquer pessoa observe, em testes controlados, como a estrutura da interação pode afetar a resposta.

> **A mesma tarefa. Três formas de interação. Resultados que você pode conferir.**

## De onde veio a ideia?

O projeto foi inspirado em *[LLMs Get Lost in Multi-Turn Conversation](https://arxiv.org/abs/2505.06120)*, de Philippe Laban, Hiroaki Hayashi, Yingbo Zhou e Jennifer Neville (2025).

Em um estudo com **mais de 200 mil conversas simuladas**, envolvendo **15 modelos de IA** e diferentes tipos de tarefa, os pesquisadores observaram uma **queda média de 39% no desempenho** ao comparar a condição de conversa em etapas com a de instrução completa. Esse percentual **não** significa que 39% dos testes deram errado: trata-se de uma queda relativa na medida de desempenho do estudo.

Uma das observações centrais é que modelos podem começar a responder quando ainda não têm todas as informações, introduzir suposições e nem sempre corrigi-las depois.

**Importante:** esses números são resultados do **artigo original**, que analisa um conjunto muito maior de tarefas. Este aplicativo é um **recorte demonstrativo** com **10 problemas de matemática** da tarefa Math (GSM8K); suas execuções não reproduzem, por si só, a estatística de 39%.

## Como funciona a comparação?

O laboratório utiliza três condições do experimento original:

| Condição | Como a IA recebe o problema | O que permite observar |
| --- | --- | --- |
| **FULL — Prompt completo** | O enunciado original, com todas as informações, em uma mensagem. | O desempenho quando a tarefa já está totalmente especificada. |
| **CONCAT — Prompt organizado** | Os mesmos fragmentos reunidos em uma lista, enviados em uma mensagem. | A diferença entre a redação original e a versão fragmentada, sem distribuir informações em turnos. |
| **SHARDED — Conversa em etapas** | Os fragmentos chegam progressivamente, em uma mesma conversa. | O comportamento quando a IA precisa acompanhar informações que chegam ao longo de diferentes turnos. |

A condição CONCAT é essencial: ela ajuda a separar o efeito de **reformular o texto** do efeito de **distribuir o texto em turnos**.

Neste projeto, “conversa em etapas” não significa necessariamente uma conversa muito longa ou uma conversa humana espontânea. No teste automático, ela é produzida por um **simulador de usuário** do experimento original.

## Experimente de duas formas

### 1. Teste na sua IA — sem configurar uma API

Use a plataforma que você já conhece, como ChatGPT, Copilot, Gemini ou outra IA conversacional.

1. Abra a página **Na mão** (teste manual) no aplicativo.
2. Informe o nome da plataforma e escolha um dos dez problemas.
3. Selecione **FULL**, **CONCAT** ou **SHARDED**.
4. Inicie um **chat novo** na plataforma escolhida e copie a mensagem indicada pelo laboratório.
5. Cole a resposta completa da IA de volta no aplicativo.
6. Em **SHARDED**, continue **no mesmo chat**, enviando somente o próximo fragmento exibido, até a última etapa.
7. Ao terminar, registre **o número final respondido pela IA**. O laboratório o compara com o gabarito oficial.

Repita com as outras condições, sempre em **chats novos**, para comparar as tentativas.

**Atenção:** o teste manual usa as instruções internas da plataforma escolhida e segue um procedimento simplificado de registro e classificação. Por isso, **não é metodologicamente idêntico** à simulação automática do artigo.

A **análise adicional por IA é opcional**. Ela requer uma conexão de API, mas **não** é necessária para a comparação numérica manual.

### 2. Teste automático — com uma API

Na página **Um a um**, o laboratório executa as condições utilizando um endpoint compatível com a API de chat da OpenAI.

1. Informe a **URL base**, a **chave da API** e o **modelo avaliado**.
2. Opcionalmente, configure um **modelo de apoio** e um **modelo para o parecer adicional**.
3. Escolha o problema e a quantidade de repetições (**1 ou 3**).
4. Execute **FULL**, **CONCAT**, **SHARDED** ou **as três condições**.
5. Consulte os resultados, as transcrições, as métricas e o registro das chamadas.

No modo automático, o sistema emprega os procedimentos originais de simulação de usuário, classificação de turnos, extração da resposta numérica e avaliação Math. Um parecer adicional em português pode ser solicitado ao modelo configurado como juiz.

> **Custos:** o teste automático faz chamadas reais ao provedor configurado. O simulador, o classificador, o extrator e o parecer adicional podem gerar chamadas extras e, portanto, custos adicionais.

## Um exemplo do fenômeno

No exemplo apresentado no artigo, a IA recebe aos poucos os dados para calcular as calorias de **200 mini rolos de canela** e **300 mini muffins de mirtilo**. Cada mini doce tem um terço das calorias da versão normal; um rolo normal possui 600 calorias e um muffin normal, 450.

O total esperado é:

- Rolos: `200 × (600 ÷ 3) = 40.000` calorias.
- Muffins: `300 × (450 ÷ 3) = 45.000` calorias.
- **Total: 85.000 calorias.**

Em uma execução **SHARDED** ilustrada pelos pesquisadores, o modelo terminou com **45.000**: calculou o subtotal dos muffins, mas não incluiu o valor dos rolos de canela na resposta final.

O exemplo mostra que uma conta local pode estar correta e, ainda assim, **a resposta final não atender à tarefa completa**. Isso não significa que o mesmo erro sempre ocorrerá ou que todos os modelos terão esse comportamento.

*Fonte: Laban et al. (2025), Apêndice J, Figura 11.*

## O que o laboratório avalia?

A avaliação principal é a **correspondência numérica exata** (*exact match*) do GSM8K, conforme o avaliador utilizado no experimento:

- **Nota 1:** o número final corresponde ao gabarito.
- **Nota 0:** o número final é diferente do gabarito.

No **teste automático**, o número é identificado pelo extrator utilizado no fluxo experimental. No **teste manual**, o número é informado pela pessoa que realizou o teste.

### Análise adicional por IA

Opcionalmente, um segundo modelo lê a resposta gerada e a solução oficial para produzir um parecer em português sobre a correspondência dos números, o raciocínio e possíveis desvios.

Esse parecer **não substitui a nota numérica oficial** e também pode conter erros de interpretação. O objetivo é facilitar a leitura da transcrição, não estabelecer uma avaliação humana definitiva.

### Métricas de desempenho e consistência

| Métrica | Significado | Como interpretar |
| --- | --- | --- |
| **P** | Desempenho médio. | Média das notas nas tentativas. |
| **A90** | Percentil 90 por tarefa. | Desempenho próximo das melhores tentativas. |
| **U** | Percentil 90 menos percentil 10 por tarefa. | Variação entre tentativas da mesma tarefa. |

As métricas são calculadas **dentro de cada tarefa** e depois agregadas entre tarefas, conforme a metodologia descrita no artigo. Com apenas **uma execução por tarefa**, não existe variação entre tentativas para medir: nesse caso, **U = 0**. Com três repetições, a leitura de instabilidade ainda é exploratória.

O aplicativo também disponibiliza o histórico e as transcrições, incluindo a estratégia identificada em cada turno no fluxo automático.

## O que está incluído neste recorte?

- **10 problemas matemáticos** da tarefa **Math (GSM8K)**, selecionados entre os mais longos do recorte v2.
- As três condições experimentais: **FULL**, **CONCAT** e **SHARDED**.
- **Modo automático** por endpoint compatível com a API de chat da OpenAI.
- **Modo manual** para testar plataformas conversacionais por cópia e registro de respostas.
- **Gabarito e avaliação numérica** da implementação original.
- **Parecer adicional em português**, opcional.
- **Histórico das execuções**, transcrições, detalhes de chamadas e exportação em **JSONL** (`um_a_um.jsonl` e `na_mao.jsonl`).

Os enunciados, os fragmentos e os gabaritos permanecem em **inglês**, conforme o conjunto de dados original. A interface e o parecer adicional são apresentados em português.

## Tecnologias e origem dos componentes

| Componente | Uso no projeto |
| --- | --- |
| **Python + Streamlit** | Aplicação e interface interativa. |
| **API de chat compatível com OpenAI** | Acesso ao modelo testado e aos modelos auxiliares. |
| **`microsoft/lost_in_conversation`** | Simulador, prompts, fragmentos e avaliação numérica oficiais. |
| **JSONL** | Registro e exportação das execuções. |
| **Juiz em português** | Camada adicional de interpretação criada para este laboratório. |

**O que é adaptação deste projeto?** A interface em Streamlit, o fluxo de uso manual, a conexão configurável com APIs compatíveis e a camada de parecer em português.

**O que vem da pesquisa original?** O desenho das condições experimentais, os materiais Math, o simulador, os prompts auxiliares e o avaliador numérico.

## Execução local

**Pré-requisitos:** Python 3.10 ou superior.

```bash
git clone https://github.com/Edumesqg/prompt-unico-vs-conversa.git
cd prompt-unico-vs-conversa
pip install -r requirements.txt
python -m streamlit run laboratorio/app.py
```

Abra a URL local exibida pelo Streamlit e escolha **Teste na sua IA** ou **Teste automático**.

O avaliador numérico e os 14 problemas deste recorte já estão na pasta `lost_in_conversation`, com a licença MIT do projeto original. Não é preciso clonar o repositório da Microsoft para rodar este laboratório.

O modo **Na mão** não exige API para a comparação numérica. Para o modo automático ou o parecer adicional, informe a URL, a chave e o modelo na própria tela. Esses dados ficam na sessão do navegador. Se quiser preenchê-los automaticamente na sua máquina, copie `laboratorio/.env.example` para `laboratorio/.env`.

**Segurança:** não publique suas chaves de API no repositório e evite incluir segredos ou dados sensíveis nas transcrições exportadas. Em uma implantação pública, revise também o tratamento das credenciais e dos registros.

## Limitações importantes

Este projeto é uma **demonstração educacional e experimental**, não uma certificação de confiabilidade nem um ranking de modelos.

- O recorte contém somente **10 tarefas matemáticas**; não representa todas as atividades avaliadas pelo artigo nem as situações empresariais em geral.
- As simulações originais **não representam conversas espontâneas de usuários humanos**.
- O modo manual é uma **adaptação**: as instruções internas das plataformas e a forma de registro não são controladas como na simulação automática.
- Um erro isolado não demonstra que o formato da conversa foi sua causa; comparações mais robustas exigem mais repetições e controle das condições.
- Uma resposta numericamente correta pode apresentar raciocínio incompleto; uma avaliação qualitativa feita por outra IA também pode falhar.
- Compatibilidade de endpoints, parâmetros de geração e custos variam de acordo com o serviço utilizado.

### E o uso de IA nas empresas?

No trabalho, frequentemente começamos com um pedido, incluímos novos dados, mudamos critérios e retomamos informações anteriores. O experimento é relevante porque **nos convida a verificar se a resposta final continua atendendo ao objetivo completo**.

Ele não prova que prompts únicos sempre funcionam melhor. Seu valor está em tornar observável uma diferença que pode passar despercebida no uso cotidiano.

## Créditos e referência científica

Este é um **projeto independente de demonstração e adaptação**, baseado em código e materiais de pesquisa de terceiros. Não é um produto oficial da Microsoft, da Salesforce nem dos autores do artigo.

**Pesquisa:**

Laban, P.; Hayashi, H.; Zhou, Y.; Neville, J. (2025). *LLMs Get Lost in Multi-Turn Conversation*. arXiv:2505.06120.

- Artigo: https://arxiv.org/abs/2505.06120
- Projeto original: https://github.com/microsoft/lost_in_conversation
- Licença do código original: [MIT](https://github.com/microsoft/lost_in_conversation/blob/main/LICENSE)

```bibtex
@article{laban2025llms,
  title={LLMs Get Lost In Multi-Turn Conversation},
  author={Laban, Philippe and Hayashi, Hiroaki and Zhou, Yingbo and Neville, Jennifer},
  journal={arXiv preprint arXiv:2505.06120},
  year={2025}
}
```

**Licenciamento:** o repositório original disponibiliza seu código sob MIT, com os respectivos avisos de copyright. O licenciamento do código próprio deste laboratório deve ser definido em um arquivo `LICENSE` separado, preservando os avisos exigidos pelos componentes reutilizados.

---

<div align="center">

### Prompt Único vs. Conversa

**Não basta saber se uma IA consegue resolver o problema. Também vale observar como ela se comporta enquanto recebe as informações.**

[**Experimente o laboratório**](https://prompt-unico-vs-conversa-copiar-fhqycdxtvfnb4husuzkn7g.streamlit.app/)

</div>
