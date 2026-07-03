# Relatorio de Avaliacao do Monitor

Status: pendente

- Alertas avaliaveis: `Output\alerts.csv`
- Gabarito esperado: `Data\gabarito_incidentes.csv`

## Metricas

- Precision: nao calculado
- Recall: nao calculado
- Taxa de falso alarme: nao calculado
- Latencia: nao calculado

O gabarito de incidentes ainda nao foi fornecido. Quando o arquivo existir, execute:

```bash
python Monitor/evaluator.py --alerts Output\alerts.csv --truth Data\gabarito_incidentes.csv --output Output/evaluation_report.md
```
