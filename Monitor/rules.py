from __future__ import annotations

# Este arquivo aplica as regras principais de anomalia.
# Ele gera alertas estruturados e registra outliers ignorados.

import hashlib
from datetime import datetime, timezone
from typing import Any

import pandas as pd


ALERT_COLUMNS = [
    "alert_id",
    "created_at",
    "rule_id",
    "rule_name",
    "window_start",
    "window_end",
    "severity",
    "status",
    "review_required",
    "what",
    "where_line",
    "where_station",
    "where_jig",
    "where_model",
    "where_firmware",
    "where_api_key",
    "evidence",
    "suggested_action",
    "total_attempts",
    "failures",
    "rate",
    "baseline_rate",
    "ppm",
    "baseline_ppm",
    "is_systematic",
]

OUTLIER_COLUMNS = [
    "rule_id",
    "window_start",
    "window_end",
    "what",
    "evidence",
    "samples",
    "observed_value",
    "threshold",
]


# Executa todas as regras principais e devolve alertas e outliers.
def run_main_rules(
    recordings: pd.DataFrame,
    baseline: pd.DataFrame,
    state: dict[str, Any],
    config: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    alerts = []
    outliers = []

    if recordings.empty:
        return _alerts_frame(alerts), _outliers_frame(outliers)

    data = recordings.copy()
    data["timestamp"] = pd.to_datetime(data["timestamp"], errors="coerce")
    data = data.dropna(subset=["timestamp"]).sort_values("timestamp")

    for window_start, window_end, window_data in _iter_windows(data, config):
        alerts.extend(
            _detect_jig_step_chronic(
                window_data,
                baseline,
                state,
                config,
                window_start,
                window_end,
            )
        )
        alerts.extend(
            _detect_remote_api(
                window_data,
                baseline,
                state,
                config,
                window_start,
                window_end,
            )
        )
        alerts.extend(
            _detect_firmware_batch(
                window_data,
                baseline,
                state,
                config,
                window_start,
                window_end,
            )
        )
        cycle_alerts, cycle_outliers = _detect_cycle_time_drift(
            window_data,
            baseline,
            state,
            config,
            window_start,
            window_end,
        )
        alerts.extend(cycle_alerts)
        outliers.extend(cycle_outliers)

    alerts.extend(_detect_mac_duplicate(data, state, config))
    return _alerts_frame(alerts), _outliers_frame(outliers)


# Detecta falha cronica por jig, etapa e codigo de erro.
def _detect_jig_step_chronic(
    window_data: pd.DataFrame,
    baseline: pd.DataFrame,
    state: dict[str, Any],
    config: dict[str, Any],
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
) -> list[dict[str, Any]]:
    rule_id = "JIG_STEP_CHRONIC"
    rule = config.get("rules", {}).get(rule_id, {})
    if not rule.get("enabled", True):
        return []

    needed = ["line", "station", "jig_id", "failed_step", "error_code"]
    if not _has_columns(window_data, needed):
        return []

    alerts = []
    failure_rows = window_data[window_data["failed_step"].notna()]
    group_columns = ["line", "station", "jig_id", "failed_step", "error_code"]

    for keys, failure_group in failure_rows.groupby(group_columns, dropna=False):
        values = _keys_to_dict(group_columns, keys)
        denominator = _count_attempts(window_data, values, ["line", "station", "jig_id"])
        failures = len(failure_group)
        if not _has_minimum_volume(denominator, failures, rule):
            continue

        rate = failures / denominator
        baseline_rate = max(
            _baseline_rate(baseline, "jig_id", values["jig_id"]),
            _baseline_ppm(baseline, "failed_step", values["failed_step"]) / 1_000_000,
            _baseline_ppm(baseline, "error_code", values["error_code"]) / 1_000_000,
            _overall_baseline_rate(baseline),
        )
        limit = max(rule.get("min_rate", 0.10), baseline_rate * rule.get("baseline_multiplier", 3.0))

        if rate < limit:
            continue

        is_systematic = rate >= rule.get("systematic_rate", 0.25)
        severity = _severity_from_rate(rate, config)
        alert = _new_alert(
            state=state,
            rule_id=rule_id,
            rule_name="Falha cronica por jig e etapa",
            window_start=window_start,
            window_end=window_end,
            severity=severity,
            what=f"{values['failed_step']} / {values['error_code']}",
            where_line=values["line"],
            where_station=values["station"],
            where_jig=values["jig_id"],
            where_model=None,
            where_firmware=None,
            where_api_key=None,
            evidence=f"{failures} falhas em {denominator} tentativas; taxa {rate:.2%}; limite {limit:.2%}",
            suggested_action=rule.get("suggested_action", ""),
            total_attempts=denominator,
            failures=failures,
            rate=rate,
            baseline_rate=baseline_rate,
            ppm=rate * 1_000_000,
            baseline_ppm=baseline_rate * 1_000_000,
            is_systematic=is_systematic,
            alert_parts=[
                rule_id,
                window_start,
                values["line"],
                values["station"],
                values["jig_id"],
                values["failed_step"],
                values["error_code"],
            ],
        )
        if alert:
            alerts.append(alert)

    return alerts


# Detecta falha remota ligada a API key ou download de firmware.
def _detect_remote_api(
    window_data: pd.DataFrame,
    baseline: pd.DataFrame,
    state: dict[str, Any],
    config: dict[str, Any],
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
) -> list[dict[str, Any]]:
    rule_id = "REMOTE_API"
    rule = config.get("rules", {}).get(rule_id, {})
    if not rule.get("enabled", True):
        return []

    needed = ["line", "api_key", "failed_step", "error_code"]
    if not _has_columns(window_data, needed):
        return []

    failed_steps = set(rule.get("failed_steps", ["fw_download"]))
    error_codes = set(rule.get("error_codes", ["ERR_AUTH"]))
    remote_mask = (
        window_data["failed_step"].isin(failed_steps)
        | window_data["error_code"].isin(error_codes)
    )
    remote_rows = window_data[remote_mask]
    affected_lines_by_key = remote_rows.groupby("api_key")["line"].nunique().to_dict()

    alerts = []
    group_columns = ["line", "api_key"]
    for keys, failure_group in remote_rows.groupby(group_columns, dropna=False):
        values = _keys_to_dict(group_columns, keys)
        denominator = _count_attempts(window_data, values, group_columns)
        failures = len(failure_group)
        if not _has_minimum_volume(denominator, failures, rule):
            continue

        rate = failures / denominator
        baseline_rate = max(
            _baseline_rate(baseline, "api_key", values["api_key"]),
            _overall_baseline_rate(baseline),
        )
        limit = max(rule.get("min_rate", 0.08), baseline_rate * rule.get("baseline_multiplier", 3.0))
        if rate < limit:
            continue

        affected_lines = affected_lines_by_key.get(values["api_key"], 1)
        severity = _severity_from_rate(rate, config)
        if rate >= rule.get("high_rate", 0.20) or affected_lines >= rule.get("affected_lines_for_high", 2):
            severity = _max_severity(severity, "high")

        alert = _new_alert(
            state=state,
            rule_id=rule_id,
            rule_name="Falha remota ou API key",
            window_start=window_start,
            window_end=window_end,
            severity=severity,
            what="fw_download / ERR_AUTH",
            where_line=values["line"],
            where_station=None,
            where_jig=None,
            where_model=None,
            where_firmware=None,
            where_api_key=values["api_key"],
            evidence=f"{failures} falhas remotas em {denominator} tentativas; taxa {rate:.2%}; linhas afetadas {affected_lines}",
            suggested_action=rule.get("suggested_action", ""),
            total_attempts=denominator,
            failures=failures,
            rate=rate,
            baseline_rate=baseline_rate,
            ppm=rate * 1_000_000,
            baseline_ppm=baseline_rate * 1_000_000,
            is_systematic=True,
            alert_parts=[rule_id, window_start, values["line"], values["api_key"]],
        )
        if alert:
            alerts.append(alert)

    return alerts


# Detecta firmware com defeito concentrado por modelo, etapa e codigo.
def _detect_firmware_batch(
    window_data: pd.DataFrame,
    baseline: pd.DataFrame,
    state: dict[str, Any],
    config: dict[str, Any],
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
) -> list[dict[str, Any]]:
    rule_id = "FIRMWARE_BATCH"
    rule = config.get("rules", {}).get(rule_id, {})
    if not rule.get("enabled", True):
        return []

    needed = ["firmware_version", "model", "failed_step", "error_code"]
    if not _has_columns(window_data, needed):
        return []

    alerts = []
    failure_rows = window_data[window_data["failed_step"].notna()]
    group_columns = ["firmware_version", "model", "failed_step", "error_code"]

    for keys, failure_group in failure_rows.groupby(group_columns, dropna=False):
        values = _keys_to_dict(group_columns, keys)
        denominator = _count_attempts(window_data, values, ["firmware_version", "model"])
        failures = len(failure_group)
        if not _has_minimum_volume(denominator, failures, rule):
            continue

        rate = failures / denominator
        ppm = rate * 1_000_000
        baseline_rate = max(
            _baseline_rate(baseline, "firmware_version", values["firmware_version"]),
            _baseline_ppm(baseline, "failed_step", values["failed_step"]) / 1_000_000,
            _baseline_ppm(baseline, "error_code", values["error_code"]) / 1_000_000,
        )
        baseline_ppm = baseline_rate * 1_000_000
        limit = max(rule.get("min_ppm", 100000), baseline_ppm * rule.get("baseline_multiplier", 3.0))
        if ppm < limit:
            continue

        severity = _severity_from_ppm(ppm, config)
        alert = _new_alert(
            state=state,
            rule_id=rule_id,
            rule_name="Firmware ou lote problematico",
            window_start=window_start,
            window_end=window_end,
            severity=severity,
            what=f"{values['failed_step']} / {values['error_code']}",
            where_line=None,
            where_station=None,
            where_jig=None,
            where_model=values["model"],
            where_firmware=values["firmware_version"],
            where_api_key=None,
            evidence=f"{failures} falhas em {denominator} tentativas; PPM {ppm:.0f}; limite {limit:.0f}",
            suggested_action=rule.get("suggested_action", ""),
            total_attempts=denominator,
            failures=failures,
            rate=rate,
            baseline_rate=baseline_rate,
            ppm=ppm,
            baseline_ppm=baseline_ppm,
            is_systematic=True,
            alert_parts=[
                rule_id,
                window_start,
                values["firmware_version"],
                values["model"],
                values["failed_step"],
                values["error_code"],
            ],
        )
        if alert:
            alerts.append(alert)

    return alerts


# Detecta drift de cycle time por etapa.
def _detect_cycle_time_drift(
    window_data: pd.DataFrame,
    baseline: pd.DataFrame,
    state: dict[str, Any],
    config: dict[str, Any],
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rule_id = "CYCLE_TIME_DRIFT"
    rule = config.get("rules", {}).get(rule_id, {})
    if not rule.get("enabled", True):
        return [], []

    alerts = []
    outliers = []
    suffix = rule.get("cycle_column_suffix", "_cycle_s")
    cycle_columns = [column for column in window_data.columns if column.endswith(suffix)]

    for column in cycle_columns:
        values = pd.to_numeric(window_data[column], errors="coerce").dropna()
        if len(values) < rule.get("min_samples", 20):
            continue

        step = column.removesuffix(suffix)
        baseline_row = _baseline_cycle_row(baseline, step)
        if baseline_row is None:
            continue

        baseline_p95 = float(baseline_row["p95_cycle_s"])
        baseline_median = float(baseline_row["median_cycle_s"])
        p95_limit = baseline_p95 * rule.get("p95_baseline_multiplier", 1.5)
        median_limit = baseline_median * rule.get("p95_baseline_multiplier", 1.5)
        window_p95 = float(values.quantile(0.95))
        window_median = float(values.median())

        if window_p95 <= p95_limit and window_median <= median_limit:
            continue

        extreme_points = int(values.gt(p95_limit).sum())
        if extreme_points <= rule.get("isolated_outlier_max_points", 2) and window_median <= median_limit:
            outliers.append(
                {
                    "rule_id": rule_id,
                    "window_start": _to_text(window_start),
                    "window_end": _to_text(window_end),
                    "what": step,
                    "evidence": f"{extreme_points} pontos acima do limite de p95",
                    "samples": int(len(values)),
                    "observed_value": window_p95,
                    "threshold": p95_limit,
                }
            )
            continue

        rate = min(window_p95 / p95_limit, 10.0) / 10.0
        severity = _severity_from_rate(rate, config)
        alert = _new_alert(
            state=state,
            rule_id=rule_id,
            rule_name="Drift de cycle time",
            window_start=window_start,
            window_end=window_end,
            severity=severity,
            what=step,
            where_line=_mode_or_none(window_data, "line"),
            where_station=_mode_or_none(window_data, "station"),
            where_jig=_mode_or_none(window_data, "jig_id"),
            where_model=_mode_or_none(window_data, "model"),
            where_firmware=None,
            where_api_key=None,
            evidence=f"p95 {window_p95:.2f}s contra limite {p95_limit:.2f}s; mediana {window_median:.2f}s",
            suggested_action=rule.get("suggested_action", ""),
            total_attempts=int(len(values)),
            failures=extreme_points,
            rate=rate,
            baseline_rate=None,
            ppm=None,
            baseline_ppm=None,
            is_systematic=True,
            alert_parts=[rule_id, window_start, step],
        )
        if alert:
            alerts.append(alert)

    return alerts, outliers


# Detecta MAC associado a mais de um serial no estado acumulado.
def _detect_mac_duplicate(
    recordings: pd.DataFrame,
    state: dict[str, Any],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    rule_id = "MAC_DUPLICATE"
    rule = config.get("rules", {}).get(rule_id, {})
    if not rule.get("enabled", True):
        return []

    if "mac_address" not in recordings.columns:
        return []

    alerts = []
    mac_map = state.get("mac_serial_map", {})
    for mac, serials in mac_map.items():
        unique_serials = sorted(set(serials))
        if len(unique_serials) <= 1:
            continue

        current_rows = recordings[recordings["mac_address"].astype(str).eq(str(mac))]
        if current_rows.empty:
            continue

        window_start = current_rows["timestamp"].min()
        window_end = current_rows["timestamp"].max()
        alert = _new_alert(
            state=state,
            rule_id=rule_id,
            rule_name="MAC duplicado em seriais diferentes",
            window_start=window_start,
            window_end=window_end,
            severity=rule.get("severity", "critical"),
            what=f"MAC {mac}",
            where_line=_mode_or_none(current_rows, "line"),
            where_station=_mode_or_none(current_rows, "station"),
            where_jig=_mode_or_none(current_rows, "jig_id"),
            where_model=_mode_or_none(current_rows, "model"),
            where_firmware=_mode_or_none(current_rows, "firmware_version"),
            where_api_key=None,
            evidence=f"MAC {mac} associado aos seriais: {', '.join(unique_serials)}",
            suggested_action=rule.get("suggested_action", ""),
            total_attempts=len(current_rows),
            failures=len(unique_serials),
            rate=1.0,
            baseline_rate=0.0,
            ppm=1_000_000,
            baseline_ppm=0.0,
            is_systematic=True,
            alert_parts=[rule_id, mac],
        )
        if alert:
            alerts.append(alert)

    return alerts


# Cria uma linha de alerta se ela ainda nao foi emitida.
def _new_alert(
    state: dict[str, Any],
    rule_id: str,
    rule_name: str,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
    severity: str,
    what: str,
    where_line: Any,
    where_station: Any,
    where_jig: Any,
    where_model: Any,
    where_firmware: Any,
    where_api_key: Any,
    evidence: str,
    suggested_action: str,
    total_attempts: int,
    failures: int,
    rate: float | None,
    baseline_rate: float | None,
    ppm: float | None,
    baseline_ppm: float | None,
    is_systematic: bool,
    alert_parts: list[Any],
) -> dict[str, Any] | None:
    alert_id = _make_alert_id(alert_parts)
    if alert_id in state.get("emitted_alerts", []):
        return None

    review_required = _needs_review(severity, is_systematic)
    return {
        "alert_id": alert_id,
        "created_at": _now_text(),
        "rule_id": rule_id,
        "rule_name": rule_name,
        "window_start": _to_text(window_start),
        "window_end": _to_text(window_end),
        "severity": severity,
        "status": "PENDING_REVIEW" if review_required else "OPEN",
        "review_required": review_required,
        "what": what,
        "where_line": _clean_value(where_line),
        "where_station": _clean_value(where_station),
        "where_jig": _clean_value(where_jig),
        "where_model": _clean_value(where_model),
        "where_firmware": _clean_value(where_firmware),
        "where_api_key": _clean_value(where_api_key),
        "evidence": evidence,
        "suggested_action": suggested_action,
        "total_attempts": int(total_attempts) if total_attempts is not None else None,
        "failures": int(failures) if failures is not None else None,
        "rate": rate,
        "baseline_rate": baseline_rate,
        "ppm": ppm,
        "baseline_ppm": baseline_ppm,
        "is_systematic": is_systematic,
    }


# Percorre janelas moveis usando o tamanho e passo da configuracao.
def _iter_windows(
    recordings: pd.DataFrame,
    config: dict[str, Any],
) -> list[tuple[pd.Timestamp, pd.Timestamp, pd.DataFrame]]:
    if recordings.empty:
        return []

    size_minutes = config.get("window", {}).get("size_minutes", 30)
    step_minutes = config.get("window", {}).get("step_minutes", 15)
    current_start = recordings["timestamp"].min().floor(f"{step_minutes}min")
    last_time = recordings["timestamp"].max()
    windows = []

    while current_start <= last_time:
        current_end = current_start + pd.Timedelta(minutes=size_minutes)
        mask = (
            recordings["timestamp"].ge(current_start)
            & recordings["timestamp"].lt(current_end)
        )
        window_data = recordings[mask]
        if not window_data.empty:
            windows.append((current_start, current_end, window_data))

        current_start = current_start + pd.Timedelta(minutes=step_minutes)

    return windows


# Verifica se as colunas necessarias existem.
def _has_columns(data: pd.DataFrame, columns: list[str]) -> bool:
    return all(column in data.columns for column in columns)


# Verifica se a regra tem volume minimo para alertar.
def _has_minimum_volume(total_attempts: int, failures: int, rule: dict[str, Any]) -> bool:
    return (
        total_attempts >= rule.get("min_attempts", 20)
        and failures >= rule.get("min_failures", 3)
    )


# Conta tentativas no grupo usado como denominador.
def _count_attempts(
    data: pd.DataFrame,
    values: dict[str, Any],
    columns: list[str],
) -> int:
    mask = pd.Series(True, index=data.index)
    for column in columns:
        mask = mask & data[column].astype(str).eq(str(values[column]))

    return int(mask.sum())


# Converte chaves do groupby em dicionario.
def _keys_to_dict(columns: list[str], keys: Any) -> dict[str, Any]:
    if not isinstance(keys, tuple):
        keys = (keys,)

    return {column: _clean_value(value) for column, value in zip(columns, keys)}


# Busca taxa historica por dimensao e valor.
def _baseline_rate(baseline: pd.DataFrame, dimension: str, value: Any) -> float:
    if baseline.empty:
        return 0.0

    rows = baseline[
        baseline["baseline_type"].eq("failure_rate")
        & baseline["dimension"].eq(dimension)
        & baseline["dimension_value"].astype(str).eq(str(_clean_value(value)))
    ]
    if rows.empty:
        return 0.0

    return float(rows.iloc[0]["failure_rate"])


# Busca PPM historico por dimensao e valor.
def _baseline_ppm(baseline: pd.DataFrame, dimension: str, value: Any) -> float:
    if baseline.empty:
        return 0.0

    rows = baseline[
        baseline["baseline_type"].eq("defect_distribution")
        & baseline["dimension"].eq(dimension)
        & baseline["dimension_value"].astype(str).eq(str(_clean_value(value)))
    ]
    if rows.empty:
        return 0.0

    return float(rows.iloc[0]["ppm"])


# Busca a taxa geral historica de falha.
def _overall_baseline_rate(baseline: pd.DataFrame) -> float:
    rows = baseline[
        baseline["baseline_type"].eq("failure_rate")
        & baseline["metric_name"].eq("overall_failure_rate")
    ]
    if rows.empty:
        return 0.0

    return float(rows.iloc[0]["failure_rate"])


# Busca baseline de cycle time de uma etapa.
def _baseline_cycle_row(baseline: pd.DataFrame, step: str) -> pd.Series | None:
    rows = baseline[
        baseline["baseline_type"].eq("cycle_time")
        & baseline["dimension_value"].astype(str).eq(str(step))
    ]
    if rows.empty:
        return None

    return rows.iloc[0]


# Calcula severidade a partir de uma taxa.
def _severity_from_rate(rate: float, config: dict[str, Any]) -> str:
    severity = config.get("severity", {})
    if rate >= severity.get("critical_rate", 0.30):
        return "critical"
    if rate >= severity.get("high_rate", 0.20):
        return "high"
    if rate >= severity.get("medium_rate", 0.10):
        return "medium"

    return "low"


# Calcula severidade a partir de PPM.
def _severity_from_ppm(ppm: float, config: dict[str, Any]) -> str:
    severity = config.get("severity", {})
    if ppm >= severity.get("critical_ppm", 300000):
        return "critical"
    if ppm >= severity.get("high_ppm", 200000):
        return "high"

    return "medium"


# Retorna a severidade mais alta entre duas.
def _max_severity(current: str, minimum: str) -> str:
    order = {"low": 1, "medium": 2, "high": 3, "critical": 4}
    return current if order.get(current, 0) >= order.get(minimum, 0) else minimum


# Decide se o alerta precisa de revisao humana.
def _needs_review(severity: str, is_systematic: bool) -> bool:
    return severity in {"high", "critical"} or not is_systematic


# Pega o valor mais comum de uma coluna, se existir.
def _mode_or_none(data: pd.DataFrame, column: str) -> str | None:
    if column not in data.columns:
        return None

    values = data[column].dropna()
    if values.empty:
        return None

    return _clean_value(values.mode().iloc[0])


# Cria um ID deterministico para o alerta.
def _make_alert_id(parts: list[Any]) -> str:
    text = "|".join(_clean_value(part) for part in parts)
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
    return f"ALERT-{digest}"


# Converte valor para texto estavel.
def _clean_value(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""

    return str(value).strip()


# Converte datas para texto.
def _to_text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None

    if hasattr(value, "isoformat"):
        return value.isoformat()

    return str(value)


# Retorna horario atual em UTC.
def _now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


# Cria DataFrame de alertas com colunas fixas.
def _alerts_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=ALERT_COLUMNS)


# Cria DataFrame de outliers com colunas fixas.
def _outliers_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=OUTLIER_COLUMNS)
