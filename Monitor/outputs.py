from __future__ import annotations

# Este arquivo gera as saidas finais do monitor.
# Ele cria fila HITL, trilha de auditoria e relatorio periodico.

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


HITL_COLUMNS = [
    "alert_id",
    "created_at",
    "rule_id",
    "rule_name",
    "window_start",
    "window_end",
    "severity",
    "what",
    "where_line",
    "where_station",
    "where_jig",
    "where_model",
    "where_firmware",
    "where_api_key",
    "evidence",
    "suggested_action",
    "review_status",
    "reviewer",
    "review_comment",
    "reviewed_at",
]


# Cria a fila de revisao humana a partir dos alertas.
def build_hitl_queue(alerts: pd.DataFrame) -> pd.DataFrame:
    if alerts.empty or "review_required" not in alerts.columns:
        return pd.DataFrame(columns=HITL_COLUMNS)

    review_alerts = alerts[alerts["review_required"].astype(bool)].copy()
    if review_alerts.empty:
        return pd.DataFrame(columns=HITL_COLUMNS)

    review_alerts["review_status"] = "PENDING"
    review_alerts["reviewer"] = ""
    review_alerts["review_comment"] = ""
    review_alerts["reviewed_at"] = ""

    return review_alerts.reindex(columns=HITL_COLUMNS)


# Escreve os eventos de auditoria em JSONL.
def write_audit_log(state: dict[str, Any], audit_path: Path) -> None:
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    events = state.get("audit_events", [])

    with audit_path.open("w", encoding="utf-8") as file:
        for event in events:
            file.write(json.dumps(event, ensure_ascii=False) + "\n")


# Monta o relatorio periodico em Markdown.
def build_periodic_report(
    alerts: pd.DataFrame,
    outliers: pd.DataFrame,
    hitl_queue: pd.DataFrame,
    baseline: pd.DataFrame,
    ingestion_summary: pd.DataFrame,
    config: dict[str, Any],
    output_paths: dict[str, Path],
) -> str:
    lines = [
        "# Relatorio Periodico do Monitor",
        "",
        f"Gerado em: {_now_text()}",
        "",
        "## Periodo processado",
        "",
        _period_text(ingestion_summary, alerts),
        "",
        "## Arquivos processados",
        "",
        _processed_files_text(ingestion_summary),
        "",
        "## Alertas",
        "",
        _alerts_summary_text(alerts),
        "",
        "## HITL",
        "",
        _hitl_text(hitl_queue),
        "",
        "## Outliers ignorados",
        "",
        _outliers_text(outliers),
        "",
        "## Limiares principais",
        "",
        _thresholds_text(config),
        "",
        "## Baseline",
        "",
        _baseline_text(baseline),
        "",
        "## Arquivos gerados",
        "",
        _paths_text(output_paths),
        "",
    ]
    return "\n".join(lines)


# Escreve o relatorio periodico em disco.
def write_periodic_report(report_text: str, report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_text, encoding="utf-8")


# Resume o periodo processado.
def _period_text(ingestion_summary: pd.DataFrame, alerts: pd.DataFrame) -> str:
    if not ingestion_summary.empty:
        start = ingestion_summary["start_time"].dropna().min()
        end = ingestion_summary["end_time"].dropna().max()
        return f"- Inicio: {start}\n- Fim: {end}"

    if not alerts.empty:
        start = alerts["window_start"].dropna().min()
        end = alerts["window_end"].dropna().max()
        return f"- Inicio: {start}\n- Fim: {end}"

    return "- Nenhum log novo processado nesta execucao."


# Lista arquivos processados.
def _processed_files_text(ingestion_summary: pd.DataFrame) -> str:
    if ingestion_summary.empty:
        return "- Nenhum arquivo novo processado."

    rows = []
    for row in ingestion_summary.itertuples(index=False):
        rows.append(
            f"- {row.file}: {row.recording_rows} registros, {row.start_time} ate {row.end_time}"
        )
    return "\n".join(rows)


# Resume alertas por severidade e regra.
def _alerts_summary_text(alerts: pd.DataFrame) -> str:
    if alerts.empty:
        return "- Nenhum alerta emitido."

    lines = [f"- Total de alertas: {len(alerts)}"]
    if "severity" in alerts.columns:
        lines.append("")
        lines.append("Por severidade:")
        lines.extend(_value_counts_lines(alerts, "severity"))

    if "rule_id" in alerts.columns:
        lines.append("")
        lines.append("Por regra:")
        lines.extend(_value_counts_lines(alerts, "rule_id"))

    return "\n".join(lines)


# Resume a fila HITL.
def _hitl_text(hitl_queue: pd.DataFrame) -> str:
    if hitl_queue.empty:
        return "- Nenhum alerta enviado para revisao humana."

    lines = [f"- Alertas pendentes de revisao: {len(hitl_queue)}"]
    lines.extend(_value_counts_lines(hitl_queue, "severity"))
    return "\n".join(lines)


# Resume outliers descartados.
def _outliers_text(outliers: pd.DataFrame) -> str:
    if outliers.empty:
        return "- Nenhum outlier isolado registrado."

    lines = [f"- Total de outliers ignorados: {len(outliers)}"]
    lines.extend(_value_counts_lines(outliers, "rule_id"))
    return "\n".join(lines)


# Descreve limiares principais do config.
def _thresholds_text(config: dict[str, Any]) -> str:
    window = config.get("window", {})
    processing = config.get("processing", {})
    severity = config.get("severity", {})
    rules = config.get("rules", {})

    lines = [
        f"- Janela: {window.get('size_minutes', 30)} min",
        f"- Passo: {window.get('step_minutes', 15)} min",
        f"- Minimo de tentativas por grupo: {processing.get('min_attempts_per_group', 20)}",
        f"- Minimo de falhas por grupo: {processing.get('min_failures_per_group', 3)}",
        f"- Severidade media: taxa >= {severity.get('medium_rate', 0.10):.0%}",
        f"- Severidade alta: taxa >= {severity.get('high_rate', 0.20):.0%}",
        f"- Severidade critica: taxa >= {severity.get('critical_rate', 0.30):.0%}",
    ]

    for rule_id, rule in rules.items():
        if not rule.get("enabled", True):
            continue
        detail = _rule_threshold_text(rule)
        lines.append(f"- {rule_id}: {detail}")

    return "\n".join(lines)


# Resume baseline gerado.
def _baseline_text(baseline: pd.DataFrame) -> str:
    if baseline.empty:
        return "- Baseline vazio."

    lines = [f"- Linhas de baseline: {len(baseline)}"]
    if "baseline_type" in baseline.columns:
        lines.extend(_value_counts_lines(baseline, "baseline_type"))
    return "\n".join(lines)


# Lista caminhos de saida gerados.
def _paths_text(output_paths: dict[str, Path]) -> str:
    lines = []
    for label, path in output_paths.items():
        lines.append(f"- {label}: `{path}`")
    return "\n".join(lines)


# Gera linhas de contagem por valor.
def _value_counts_lines(data: pd.DataFrame, column: str) -> list[str]:
    if column not in data.columns:
        return []

    counts = data[column].fillna("NA").value_counts()
    return [f"- {value}: {count}" for value, count in counts.items()]


# Resume limiares de uma regra.
def _rule_threshold_text(rule: dict[str, Any]) -> str:
    parts = []
    for key in ["min_attempts", "min_failures", "min_rate", "min_ppm"]:
        if key in rule:
            parts.append(f"{key}={rule[key]}")
    return ", ".join(parts) if parts else "sem limiar explicito"


# Retorna horario atual em UTC.
def _now_text() -> str:
    return datetime.now(timezone.utc).isoformat()
