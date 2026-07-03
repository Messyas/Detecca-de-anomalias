from __future__ import annotations

# Este arquivo cuida do estado acumulado do monitor.
# Ele guarda arquivos processados, mapa de MAC, alertas emitidos e auditoria.

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

try:
    from .ingestion import LogBatch
except ImportError:
    from ingestion import LogBatch


# Cria um estado vazio com a estrutura padrao.
def create_empty_state() -> dict[str, Any]:
    return {
        "version": "1.0",
        "processed_files": {},
        "mac_serial_map": {},
        "emitted_alerts": [],
        "audit_events": [],
    }


# Carrega o estado salvo ou cria um novo se ele ainda nao existir.
def load_state(state_path: Path) -> dict[str, Any]:
    if not state_path.exists():
        return create_empty_state()

    with state_path.open("r", encoding="utf-8") as file:
        state = json.load(file)

    return _ensure_state_shape(state)


# Salva o estado acumulado em JSON legivel.
def save_state(state: dict[str, Any], state_path: Path) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with state_path.open("w", encoding="utf-8") as file:
        json.dump(state, file, ensure_ascii=False, indent=2)


# Verifica se um arquivo ja foi registrado como processado.
def was_file_processed(state: dict[str, Any], file_name: str) -> bool:
    return file_name in state["processed_files"]


# Registra um lote processado e atualiza os dados acumulados.
def register_processed_batch(state: dict[str, Any], batch: LogBatch) -> None:
    file_name = batch.path.name
    state["processed_files"][file_name] = {
        "path": str(batch.path),
        "start_time": _to_text(batch.start_time),
        "end_time": _to_text(batch.end_time),
        "recording_rows": batch.row_count,
        "line_stop_rows": len(batch.line_stops),
        "processed_at": _now_text(),
    }

    update_mac_serial_map(state, batch.recordings)
    add_audit_event(
        state,
        event_type="file_processed",
        file=file_name,
        details={
            "start_time": _to_text(batch.start_time),
            "end_time": _to_text(batch.end_time),
            "recording_rows": batch.row_count,
            "line_stop_rows": len(batch.line_stops),
        },
    )


# Atualiza o mapa de MAC para seriais vistos no log.
def update_mac_serial_map(state: dict[str, Any], recordings: pd.DataFrame) -> None:
    if recordings.empty:
        return

    for _, row in recordings.iterrows():
        mac = _clean_value(row.get("mac_address"))
        serial = _clean_value(row.get("serial_number"))

        if not mac or not serial:
            continue

        serials = state["mac_serial_map"].setdefault(mac, [])
        if serial not in serials:
            serials.append(serial)


# Registra um alerta emitido para evitar duplicidade futura.
def register_emitted_alert(state: dict[str, Any], alert_id: str) -> None:
    if not alert_id:
        return

    if alert_id not in state["emitted_alerts"]:
        state["emitted_alerts"].append(alert_id)
        add_audit_event(
            state,
            event_type="alert_registered",
            alert_id=alert_id,
            details={},
        )


# Verifica se um alerta ja foi emitido antes.
def was_alert_emitted(state: dict[str, Any], alert_id: str) -> bool:
    return alert_id in state["emitted_alerts"]


# Adiciona um evento simples na trilha de auditoria do estado.
def add_audit_event(
    state: dict[str, Any],
    event_type: str,
    file: str | None = None,
    alert_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    state["audit_events"].append(
        {
            "event_time": _now_text(),
            "event_type": event_type,
            "file": file,
            "alert_id": alert_id,
            "details": details or {},
        }
    )


# Garante que um estado antigo tenha todos os campos atuais.
def _ensure_state_shape(state: dict[str, Any]) -> dict[str, Any]:
    empty_state = create_empty_state()
    for key, value in empty_state.items():
        state.setdefault(key, value)

    return state


# Converte datas e valores do pandas para texto JSON.
def _to_text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None

    if hasattr(value, "isoformat"):
        return value.isoformat()

    return str(value)


# Limpa valores vazios antes de salvar no estado.
def _clean_value(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None

    text = str(value).strip()
    return text or None


# Retorna o horario atual em UTC para auditoria.
def _now_text() -> str:
    return datetime.now(timezone.utc).isoformat()
