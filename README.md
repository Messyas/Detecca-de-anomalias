# Monitor de Anomalias - Setupbox

Projeto da Tarefa 02: monitoramento automatizado de anomalias no teste de gravacao de setupboxes.

O projeto evolui o dashboard exploratorio da Tarefa 01 para um monitor que le logs em janelas, calcula baseline, aplica regras de deteccao, gera alertas estruturados, registra auditoria, cria fila HITL e produz relatorios.

## Integrantes

- Andre Filipe Aloise
- Messyas Gois Franca
- Teodorio Ferreira Neto
- Gustavo Morais de Almada

## Estrutura principal

- `Monitor/monitor.py`: execucao principal do monitor.
- `Monitor/config.json`: janelas, limiares, severidades e regras.
- `Monitor/evaluator.py`: avaliacao contra gabarito de incidentes.
- `Data/recording_test_setupbox.xlsx`: base historica usada como baseline.
- `Logs/`: pasta de entrada para novos logs `.xlsx` ou `.csv`.
- `Output/`: saidas geradas pelo monitor.
- `Docs/monitor-to-be.bpmn`: BPMN to-be do monitor.
- `Docs/to-be.svg`: imagem do BPMN to-be.
- `Docs/pdd-deteccao.md`: PDD do monitor.

## Instalacao

```bash
pip install -r requirements.txt
```

## Como executar o monitor

Coloque os novos logs na pasta `Logs/`. O monitor aceita arquivos `.xlsx` e `.csv`.

```bash
python Monitor/monitor.py --input Logs --output Output --baseline Data/recording_test_setupbox.xlsx --config Monitor/config.json
```

O arquivo `.xlsx` pode conter as abas:

- `recordings`: obrigatoria;
- `line_stops`: opcional;
- `data_dictionary`: opcional.

Para `.csv`, o arquivo deve conter a tabela de `recordings`.

## Colunas obrigatorias em recordings

- `timestamp`
- `line`
- `station`
- `jig_id`
- `model`
- `firmware_version`
- `serial_number`
- `mac_address`
- `api_key`
- `attempt`
- `result`
- `failed_step`
- `error_code`
- `disposition`

## Saidas geradas

- `Output/baseline_summary.csv`: baseline historico com taxas, PPM e cycle time.
- `Output/ingestion_summary.csv`: arquivos processados e ordem cronologica.
- `Output/alerts.csv`: alertas estruturados.
- `Output/outliers_ignored.csv`: outliers isolados descartados.
- `Output/hitl_queue.csv`: alertas que exigem revisao humana.
- `Output/audit_log.jsonl`: trilha de auditoria.
- `Output/periodic_report.md`: relatorio periodico do monitor.
- `Output/monitor_state.json`: estado acumulado para evitar reprocessamento e alertas duplicados.

## Regras implementadas

- Falha cronica por jig e etapa.
- Falha remota por API key ou `fw_download`.
- Firmware/lote problematico.
- Drift de cycle time.
- MAC repetido em seriais diferentes.
- Cabo com zero canais ou falha de `cable_scan`.
- Falha de Bluetooth.
- Enriquecimento com paradas de linha quando houver `line_stops`.

## Avaliacao com gabarito

Quando o gabarito estiver disponivel em `Data/gabarito_incidentes.csv`, execute:

```bash
python Monitor/evaluator.py --alerts Output/alerts.csv --truth Data/gabarito_incidentes.csv --output Output/evaluation_report.md
```

O relatorio de avaliacao calcula:

- precision;
- recall;
- taxa de falso alarme;
- latencia de deteccao.

Se o gabarito ainda nao existir, o avaliador gera um relatorio pendente em `Output/evaluation_report.md`.

## Dashboard opcional

O dashboard da Tarefa 01 foi mantido como apoio visual:

```bash
streamlit run Dashboard/app.py
```

O monitor de anomalias e executado pela linha de comando com `Monitor/monitor.py`.
