from __future__ import annotations

# Este arquivo gera o baseline historico do monitor.
# Ele calcula taxas normais, PPM e estatisticas de cycle time.

from typing import Any

import pandas as pd


BASELINE_COLUMNS = [
    "baseline_type",
    "metric_name",
    "dimension",
    "dimension_value",
    "total_attempts",
    "failures",
    "failure_rate",
    "ppm",
    "cycle_step",
    "samples",
    "median_cycle_s",
    "p95_cycle_s",
]


# Gera todas as linhas do baseline historico.
def build_historical_baseline(
    recordings: pd.DataFrame,
    config: dict[str, Any],
) -> pd.DataFrame:
    rows = []
    rows.extend(_build_overall_failure_rows(recordings))
    rows.extend(_build_group_failure_rows(recordings))
    rows.extend(_build_defect_distribution_rows(recordings))
    rows.extend(_build_cycle_time_rows(recordings, config))

    return pd.DataFrame(rows, columns=BASELINE_COLUMNS)


# Calcula a taxa geral de falha da base historica.
def _build_overall_failure_rows(recordings: pd.DataFrame) -> list[dict[str, Any]]:
    total_attempts = len(recordings)
    failures = _count_failures(recordings)

    return [
        _new_baseline_row(
            baseline_type="failure_rate",
            metric_name="overall_failure_rate",
            dimension="all",
            dimension_value="all",
            total_attempts=total_attempts,
            failures=failures,
        )
    ]


# Calcula taxas de falha por dimensoes principais do processo.
def _build_group_failure_rows(recordings: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    dimensions = [
        "line",
        "station",
        "jig_id",
        "firmware_version",
        "api_key",
        "model",
    ]

    for dimension in dimensions:
        if dimension not in recordings.columns:
            continue

        for value, group in recordings.groupby(dimension, dropna=False):
            rows.append(
                _new_baseline_row(
                    baseline_type="failure_rate",
                    metric_name=f"failure_rate_by_{dimension}",
                    dimension=dimension,
                    dimension_value=_clean_value(value),
                    total_attempts=len(group),
                    failures=_count_failures(group),
                )
            )

    return rows


# Calcula distribuicao historica de defeitos por etapa e codigo.
def _build_defect_distribution_rows(recordings: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    total_attempts = len(recordings)

    for dimension in ["failed_step", "error_code"]:
        if dimension not in recordings.columns:
            continue

        values = recordings[dimension].dropna()
        for value, failures in values.value_counts().items():
            rows.append(
                _new_baseline_row(
                    baseline_type="defect_distribution",
                    metric_name=f"ppm_by_{dimension}",
                    dimension=dimension,
                    dimension_value=_clean_value(value),
                    total_attempts=total_attempts,
                    failures=int(failures),
                )
            )

    return rows


# Calcula mediana e p95 de cycle time para cada etapa.
def _build_cycle_time_rows(
    recordings: pd.DataFrame,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    rows = []
    suffix = (
        config.get("rules", {})
        .get("CYCLE_TIME_DRIFT", {})
        .get("cycle_column_suffix", "_cycle_s")
    )
    cycle_columns = [column for column in recordings.columns if column.endswith(suffix)]

    for column in cycle_columns:
        values = pd.to_numeric(recordings[column], errors="coerce").dropna()
        if values.empty:
            continue

        step = column.removesuffix(suffix)
        rows.append(
            {
                "baseline_type": "cycle_time",
                "metric_name": "cycle_time_by_step",
                "dimension": "cycle_step",
                "dimension_value": step,
                "total_attempts": None,
                "failures": None,
                "failure_rate": None,
                "ppm": None,
                "cycle_step": step,
                "samples": int(len(values)),
                "median_cycle_s": float(values.median()),
                "p95_cycle_s": float(values.quantile(0.95)),
            }
        )

    return rows


# Conta falhas usando a coluna result.
def _count_failures(recordings: pd.DataFrame) -> int:
    if "result" not in recordings.columns:
        return 0

    return int(recordings["result"].astype(str).str.upper().eq("FAIL").sum())


# Cria uma linha padrao para metricas de taxa e PPM.
def _new_baseline_row(
    baseline_type: str,
    metric_name: str,
    dimension: str,
    dimension_value: str,
    total_attempts: int,
    failures: int,
) -> dict[str, Any]:
    failure_rate = failures / total_attempts if total_attempts else 0
    ppm = failure_rate * 1_000_000

    return {
        "baseline_type": baseline_type,
        "metric_name": metric_name,
        "dimension": dimension,
        "dimension_value": dimension_value,
        "total_attempts": int(total_attempts),
        "failures": int(failures),
        "failure_rate": failure_rate,
        "ppm": ppm,
        "cycle_step": None,
        "samples": None,
        "median_cycle_s": None,
        "p95_cycle_s": None,
    }


# Converte valores vazios para um texto estavel no CSV.
def _clean_value(value: Any) -> str:
    if value is None or pd.isna(value):
        return "NA"

    return str(value).strip() or "NA"
