# Dashboard de Anomalias - Setupbox

Projeto da tarefa de dashboard de anomalias no teste de gravação de setupboxes.

## Integrantes

- André Filipe Aloise
- Messyas Gois França
- Teodorio Ferreira Neto
- Gustavo Morais de Almada

## Arquivos principais

- EDA: [Notebooks/1-EDA.ipynb](Notebooks/1-EDA.ipynb)
- Dashboard: [Dashboard/app.py](Dashboard/app.py)
- Dataset: [Data/recording_test_setupbox.xlsx](Data/recording_test_setupbox.xlsx)
- Enunciado: [Docs/Tarefa01-Dashboard-de-Anomalias.pdf](Docs/Tarefa01-Dashboard-de-Anomalias.pdf)
- BPMN as-is: [BPMN-as-is.png](BPMN-as-is.png)
- PDD: [pdd-setupbox.md](pdd-setupbox.md)

## Como rodar

1. Instale as dependências:

```bash
pip install -r requirements.txt
```

2. Para abrir a análise exploratória:

```bash
jupyter notebook Notebooks/1-EDA.ipynb
```

3. Para rodar o dashboard:

```bash
streamlit run Dashboard/app.py
```
