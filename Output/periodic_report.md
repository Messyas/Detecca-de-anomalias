# Relatorio Periodico do Monitor

Gerado em: 2026-07-03T04:39:14.963175+00:00

## Periodo processado

- Inicio: 2022-09-12 06:00:06
- Fim: 2022-09-14 23:32:03

## Arquivos processados

- log_2022-09-12.xlsx: 6067 registros, 2022-09-12 06:00:06 ate 2022-09-12 23:32:50
- log_2022-09-13.xlsx: 5872 registros, 2022-09-13 06:00:06 ate 2022-09-13 23:14:01
- log_2022-09-14.xlsx: 5905 registros, 2022-09-14 06:00:24 ate 2022-09-14 23:32:03

## Alertas

- Total de alertas: 63

Por severidade:
- medium: 36
- critical: 27

Por regra:
- CYCLE_TIME_DRIFT: 36
- FIRMWARE_BATCH: 11
- MAC_DUPLICATE: 6
- REMOTE_API: 5
- JIG_STEP_CHRONIC: 5

## HITL

- Alertas pendentes de revisao: 27
- critical: 27

## Outliers ignorados

- Nenhum outlier isolado registrado.

## Limiares principais

- Janela: 30 min
- Passo: 15 min
- Minimo de tentativas por grupo: 20
- Minimo de falhas por grupo: 3
- Severidade media: taxa >= 10%
- Severidade alta: taxa >= 20%
- Severidade critica: taxa >= 30%
- JIG_STEP_CHRONIC: min_attempts=20, min_failures=3, min_rate=0.1
- REMOTE_API: min_attempts=20, min_failures=3, min_rate=0.08
- FIRMWARE_BATCH: min_attempts=30, min_failures=3, min_ppm=100000
- CYCLE_TIME_DRIFT: sem limiar explicito
- MAC_DUPLICATE: sem limiar explicito
- CABLE_ZERO_CHANNELS: min_attempts=20, min_failures=3, min_rate=0.1
- BLUETOOTH_FAILURE: min_attempts=20, min_failures=3, min_rate=0.1
- LINE_STOP_CONTEXT: sem limiar explicito

## Baseline

- Linhas de baseline: 85
- failure_rate: 47
- defect_distribution: 24
- cycle_time: 14

## Arquivos gerados

- baseline: `Output\baseline_summary.csv`
- alerts: `Output\alerts.csv`
- outliers: `Output\outliers_ignored.csv`
- hitl_queue: `Output\hitl_queue.csv`
- audit_log: `Output\audit_log.jsonl`
- ingestion_summary: `Output\ingestion_summary.csv`
