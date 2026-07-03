from __future__ import annotations

# Este arquivo avalia os alertas contra um gabarito de incidentes.
# Ele calcula precision, recall, falso alarme e latencia de deteccao.

import argparse
import sys
from pathlib import Path
from typing import Any

import pandas as pd


RULE_ALIASES = {
    "jig": "JIG_STEP_CHRONIC",
    "jig_step": "JIG_STEP_CHRONIC",
    "jig_step_chronic": "JIG_STEP_CHRONIC",
    "remote": "REMOTE_API",
    "api": "REMOTE_API",
    "api_key": "REMOTE_API",
    "firmware": "FIRMWARE_BATCH",
    "firmware_batch": "FIRMWARE_BATCH",
    "cycle": "CYCLE_TIME_DRIFT",
    "cycle_time": "CYCLE_TIME_DRIFT",
    "mac": "MAC_DUPLICATE",
    "mac_duplicate": "MAC_DUPLICATE",
    "cable": "CABLE_ZERO_CHANNELS",
    "bluetooth": "BLUETOOTH_FAILURE",
}


# Le os argumentos da avaliacao.
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Avalia alertas do monitor contra um gabarito de incidentes."
    )
    parser.add_argument(
        "--alerts",
        default="Output/alerts.csv",
        help="Arquivo CSV de alertas gerado pelo monitor.",
    )
    parser.add_argument(
        "--truth",
        default="Data/gabarito_incidentes.csv",
        help="Arquivo CSV com o gabarito de incidentes.",
    )
    parser.add_argument(
        "--output",
        default="Output/evaluation_report.md",
        help="Arquivo Markdown de relatorio da avaliacao.",
    )
    return parser.parse_args()


# Executa a avaliacao por linha de comando.
def main() -> int:
    args = parse_args()
    alerts_path = Path(args.alerts)
    truth_path = Path(args.truth)
    output_path = Path(args.output)

    if not alerts_path.exists():
        print(f"Arquivo de alertas nao encontrado: {alerts_path}", file=sys.stderr)
        return 2

    if not truth_path.exists():
        report = build_missing_truth_report(alerts_path, truth_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")
        print(f"Gabarito nao encontrado: {truth_path}")
        print(f"Relatorio pendente salvo em: {output_path}")
        return 0

    alerts = pd.read_csv(alerts_path)
    truth = pd.read_csv(truth_path)
    result = evaluate_alerts(alerts, truth)
    report = build_evaluation_report(result, alerts_path, truth_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    print(f"Relatorio de avaliacao salvo em: {output_path}")
    return 0


# Calcula metricas principais de avaliacao.
def evaluate_alerts(alerts: pd.DataFrame, truth: pd.DataFrame) -> dict[str, Any]:
    alerts = _prepare_alerts(alerts)
    truth = _prepare_truth(truth)

    matches = _match_alerts_to_incidents(alerts, truth)
    total_alerts = len(alerts)
    total_incidents = len(truth)
    true_positives = len(matches)
    detected_incidents = len({match["incident_index"] for match in matches})
    false_positives = total_alerts - true_positives

    precision = true_positives / total_alerts if total_alerts else 0
    recall = detected_incidents / total_incidents if total_incidents else 0
    false_alarm_rate = false_positives / total_alerts if total_alerts else 0
    latencies = [match["latency_minutes"] for match in matches]

    return {
        "total_alerts": total_alerts,
        "total_incidents": total_incidents,
        "true_positives": true_positives,
        "false_positives": false_positives,
        "detected_incidents": detected_incidents,
        "precision": precision,
        "recall": recall,
        "false_alarm_rate": false_alarm_rate,
        "latency_mean": _safe_mean(latencies),
        "latency_median": _safe_median(latencies),
        "latency_max": max(latencies) if latencies else None,
        "matches": matches,
    }


# Monta relatorio Markdown da avaliacao.
def build_evaluation_report(
    result: dict[str, Any],
    alerts_path: Path,
    truth_path: Path,
) -> str:
    lines = [
        "# Relatorio de Avaliacao do Monitor",
        "",
        f"- Alertas avaliados: `{alerts_path}`",
        f"- Gabarito usado: `{truth_path}`",
        "",
        "## Metricas",
        "",
        f"- Total de alertas: {result['total_alerts']}",
        f"- Total de incidentes reais: {result['total_incidents']}",
        f"- Verdadeiros positivos: {result['true_positives']}",
        f"- Falsos positivos: {result['false_positives']}",
        f"- Incidentes detectados: {result['detected_incidents']}",
        f"- Precision: {result['precision']:.2%}",
        f"- Recall: {result['recall']:.2%}",
        f"- Taxa de falso alarme: {result['false_alarm_rate']:.2%}",
        "",
        "## Latencia",
        "",
        _latency_text(result),
        "",
        "## Pareamentos",
        "",
        _matches_text(result["matches"]),
        "",
    ]
    return "\n".join(lines)


# Monta relatorio quando o gabarito ainda nao foi fornecido.
def build_missing_truth_report(alerts_path: Path, truth_path: Path) -> str:
    lines = [
        "# Relatorio de Avaliacao do Monitor",
        "",
        "Status: pendente",
        "",
        f"- Alertas avaliaveis: `{alerts_path}`",
        f"- Gabarito esperado: `{truth_path}`",
        "",
        "## Metricas",
        "",
        "- Precision: nao calculado",
        "- Recall: nao calculado",
        "- Taxa de falso alarme: nao calculado",
        "- Latencia: nao calculado",
        "",
        "O gabarito de incidentes ainda nao foi fornecido. Quando o arquivo existir, execute:",
        "",
        "```bash",
        f"python Monitor/evaluator.py --alerts {alerts_path} --truth {truth_path} --output Output/evaluation_report.md",
        "```",
        "",
    ]
    return "\n".join(lines)


# Prepara alertas para pareamento.
def _prepare_alerts(alerts: pd.DataFrame) -> pd.DataFrame:
    prepared = alerts.copy()
    for column in ["window_start", "window_end", "created_at"]:
        if column in prepared.columns:
            prepared[column] = pd.to_datetime(prepared[column], errors="coerce")

    if "window_end" in prepared.columns:
        prepared["alert_time"] = prepared["window_end"]
    elif "created_at" in prepared.columns:
        prepared["alert_time"] = prepared["created_at"]
    else:
        prepared["alert_time"] = pd.NaT

    return prepared


# Prepara o gabarito para pareamento.
def _prepare_truth(truth: pd.DataFrame) -> pd.DataFrame:
    prepared = truth.copy()
    for column in ["start_time", "end_time"]:
        if column in prepared.columns:
            prepared[column] = pd.to_datetime(prepared[column], errors="coerce")

    if "incident_id" not in prepared.columns:
        prepared["incident_id"] = [f"INC-{index + 1}" for index in range(len(prepared))]

    return prepared


# Pareia alertas com incidentes sem reutilizar o mesmo incidente.
def _match_alerts_to_incidents(
    alerts: pd.DataFrame,
    truth: pd.DataFrame,
) -> list[dict[str, Any]]:
    matches = []
    used_incidents = set()

    for alert_index, alert in alerts.sort_values("alert_time").iterrows():
        incident_index = _find_matching_incident(alert, truth, used_incidents)
        if incident_index is None:
            continue

        used_incidents.add(incident_index)
        incident = truth.loc[incident_index]
        latency = _latency_minutes(alert, incident)
        matches.append(
            {
                "alert_index": int(alert_index),
                "alert_id": alert.get("alert_id", ""),
                "incident_index": int(incident_index),
                "incident_id": incident.get("incident_id", ""),
                "rule_id": alert.get("rule_id", ""),
                "latency_minutes": latency,
            }
        )

    return matches


# Encontra o primeiro incidente compativel com um alerta.
def _find_matching_incident(
    alert: pd.Series,
    truth: pd.DataFrame,
    used_incidents: set[int],
) -> int | None:
    for incident_index, incident in truth.iterrows():
        if incident_index in used_incidents:
            continue

        if not _windows_intersect(alert, incident):
            continue

        if not _type_matches(alert, incident):
            continue

        if not _dimensions_match(alert, incident):
            continue

        return int(incident_index)

    return None


# Verifica se a janela do alerta cruza a janela do incidente.
def _windows_intersect(alert: pd.Series, incident: pd.Series) -> bool:
    alert_start = alert.get("window_start")
    alert_end = alert.get("window_end")
    incident_start = incident.get("start_time")
    incident_end = incident.get("end_time")

    if pd.isna(alert_start) or pd.isna(alert_end):
        return True

    if pd.isna(incident_start):
        return True

    if pd.isna(incident_end):
        incident_end = incident_start

    return alert_start <= incident_end and alert_end >= incident_start


# Verifica se o tipo do incidente bate com a regra do alerta.
def _type_matches(alert: pd.Series, incident: pd.Series) -> bool:
    alert_rule = _clean(alert.get("rule_id", "")).upper()

    if "rule_id" in incident.index and _clean(incident.get("rule_id", "")):
        return alert_rule == _clean(incident.get("rule_id", "")).upper()

    if "incident_type" not in incident.index:
        return True

    incident_type = _clean(incident.get("incident_type", "")).lower()
    if not incident_type:
        return True

    expected_rule = RULE_ALIASES.get(incident_type, incident_type.upper())
    return alert_rule == expected_rule


# Compara dimensoes disponiveis entre alerta e incidente.
def _dimensions_match(alert: pd.Series, incident: pd.Series) -> bool:
    mapping = {
        "line": "where_line",
        "station": "where_station",
        "jig_id": "where_jig",
        "model": "where_model",
        "firmware_version": "where_firmware",
        "api_key": "where_api_key",
    }

    for incident_column, alert_column in mapping.items():
        if incident_column not in incident.index or alert_column not in alert.index:
            continue

        expected = _clean(incident.get(incident_column, ""))
        observed = _clean(alert.get(alert_column, ""))
        if expected and observed and expected != observed:
            return False

    for column in ["failed_step", "error_code"]:
        if column not in incident.index:
            continue
        expected = _clean(incident.get(column, ""))
        if expected and expected not in _clean(alert.get("what", "")):
            return False

    return True


# Calcula latencia em minutos.
def _latency_minutes(alert: pd.Series, incident: pd.Series) -> float | None:
    alert_time = alert.get("alert_time")
    incident_start = incident.get("start_time")

    if pd.isna(alert_time) or pd.isna(incident_start):
        return None

    return (alert_time - incident_start).total_seconds() / 60


# Formata resumo de latencia.
def _latency_text(result: dict[str, Any]) -> str:
    if result["latency_mean"] is None:
        return "- Nenhum incidente pareado para calcular latencia."

    return "\n".join(
        [
            f"- Media: {result['latency_mean']:.2f} min",
            f"- Mediana: {result['latency_median']:.2f} min",
            f"- Pior caso: {result['latency_max']:.2f} min",
        ]
    )


# Formata pareamentos encontrados.
def _matches_text(matches: list[dict[str, Any]]) -> str:
    if not matches:
        return "- Nenhum pareamento encontrado."

    lines = []
    for match in matches:
        latency = match["latency_minutes"]
        latency_text = "NA" if latency is None else f"{latency:.2f} min"
        lines.append(
            "- "
            f"alerta {match['alert_id']} -> incidente {match['incident_id']} "
            f"({match['rule_id']}, latencia {latency_text})"
        )
    return "\n".join(lines)


# Calcula media ignorando valores vazios.
def _safe_mean(values: list[float | None]) -> float | None:
    clean_values = [value for value in values if value is not None]
    if not clean_values:
        return None

    return float(pd.Series(clean_values).mean())


# Calcula mediana ignorando valores vazios.
def _safe_median(values: list[float | None]) -> float | None:
    clean_values = [value for value in values if value is not None]
    if not clean_values:
        return None

    return float(pd.Series(clean_values).median())


# Limpa valores para comparacao.
def _clean(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""

    return str(value).strip()


if __name__ == "__main__":
    raise SystemExit(main())
