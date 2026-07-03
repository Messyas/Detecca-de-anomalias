# Relatorio Periodico do Monitor

Gerado em: 2026-07-03T01:39:59.810969+00:00

## Periodo processado

- Nenhum log novo processado nesta execucao.

## Arquivos processados

- Nenhum arquivo novo processado.

## Alertas

- Nenhum alerta emitido.

## HITL

- Nenhum alerta enviado para revisao humana.

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
