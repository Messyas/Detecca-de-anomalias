from __future__ import annotations

# Este arquivo cuida da ingestao dos logs do monitor.
# Ele le arquivos .xlsx e .csv, valida colunas, normaliza datas e ordena os lotes.

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


class LogReadError(ValueError):
    """Erro usado quando um arquivo de log nao pode ser processado."""


@dataclass
class LogBatch:
    path: Path
    recordings: pd.DataFrame
    line_stops: pd.DataFrame
    data_dictionary: pd.DataFrame
    start_time: pd.Timestamp
    end_time: pd.Timestamp

    # Retorna a quantidade de linhas de gravacao no lote.
    @property
    def row_count(self) -> int:
        return len(self.recordings)


# Carrega o arquivo JSON de configuracao do monitor.
def load_config(config_path: Path) -> dict[str, Any]:
    with config_path.open("r", encoding="utf-8") as file:
        return json.load(file)


# Encontra arquivos de log aceitos dentro da pasta de entrada.
def find_log_files(input_dir: Path, config: dict[str, Any]) -> list[Path]:
    if not input_dir.exists():
        raise LogReadError(f"Pasta de entrada nao encontrada: {input_dir}")

    if not input_dir.is_dir():
        raise LogReadError(f"Caminho de entrada nao e uma pasta: {input_dir}")

    input_config = config.get("input", {})
    accepted_extensions = {
        extension.lower()
        for extension in input_config.get("accepted_extensions", [".xlsx", ".csv"])
    }

    files = [
        path
        for path in input_dir.iterdir()
        if path.is_file() and path.suffix.lower() in accepted_extensions
    ]
    return sorted(files, key=lambda path: path.name.lower())


# Le todos os arquivos e ordena os lotes pelo primeiro timestamp.
def load_batches_in_order(input_dir: Path, config: dict[str, Any]) -> list[LogBatch]:
    batches = []
    for path in find_log_files(input_dir, config):
        batches.append(read_log_file(path, config))

    # Ordena depois da leitura porque o primeiro timestamp esta dentro do arquivo.
    return sorted(batches, key=lambda batch: (batch.start_time, batch.path.name.lower()))


# Le um arquivo de log e devolve um lote normalizado.
def read_log_file(path: Path, config: dict[str, Any]) -> LogBatch:
    input_config = config.get("input", {})
    suffix = path.suffix.lower()

    if suffix == ".xlsx":
        recordings, line_stops, data_dictionary = _read_xlsx_file(path, input_config)
    elif suffix == ".csv":
        recordings, line_stops, data_dictionary = _read_csv_file(path)
    else:
        raise LogReadError(f"Tipo de arquivo nao suportado: {path.name}")

    recordings = _normalize_recordings(path, recordings, input_config)
    line_stops = _normalize_line_stops(line_stops)

    start_time = recordings["timestamp"].min()
    end_time = recordings["timestamp"].max()

    return LogBatch(
        path=path,
        recordings=recordings,
        line_stops=line_stops,
        data_dictionary=data_dictionary,
        start_time=start_time,
        end_time=end_time,
    )


# Monta um resumo dos lotes processados para auditoria inicial.
def build_ingestion_summary(batches: list[LogBatch]) -> pd.DataFrame:
    rows = []
    for position, batch in enumerate(batches, start=1):
        rows.append(
            {
                "order": position,
                "file": batch.path.name,
                "start_time": batch.start_time,
                "end_time": batch.end_time,
                "recording_rows": batch.row_count,
                "line_stop_rows": len(batch.line_stops),
            }
        )

    return pd.DataFrame(
        rows,
        columns=[
            "order",
            "file",
            "start_time",
            "end_time",
            "recording_rows",
            "line_stop_rows",
        ],
    )


# Junta as gravacoes de todos os lotes em uma unica tabela.
def combine_recordings(batches: list[LogBatch]) -> pd.DataFrame:
    if not batches:
        return pd.DataFrame()

    frames = [batch.recordings for batch in batches]
    return pd.concat(frames, ignore_index=True).sort_values("timestamp")


# Junta as paradas de linha de todos os lotes em uma unica tabela.
def combine_line_stops(batches: list[LogBatch]) -> pd.DataFrame:
    frames = [batch.line_stops for batch in batches if not batch.line_stops.empty]
    if not frames:
        return pd.DataFrame()

    line_stops = pd.concat(frames, ignore_index=True)
    if "stop_start" in line_stops.columns:
        return line_stops.sort_values("stop_start")

    return line_stops


# Le um arquivo Excel com abas de gravacao, paradas e dicionario.
def _read_xlsx_file(
    path: Path,
    input_config: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    recordings_sheet = input_config.get("recordings_sheet", "recordings")
    line_stops_sheet = input_config.get("line_stops_sheet", "line_stops")
    data_dictionary_sheet = input_config.get("data_dictionary_sheet", "data_dictionary")

    with pd.ExcelFile(path) as workbook:
        sheet_names = workbook.sheet_names

        if recordings_sheet in sheet_names:
            recordings = pd.read_excel(workbook, sheet_name=recordings_sheet)
        elif len(sheet_names) == 1:
            recordings = pd.read_excel(workbook, sheet_name=sheet_names[0])
        else:
            raise LogReadError(
                f"{path.name}: aba '{recordings_sheet}' nao encontrada"
            )

        line_stops = (
            pd.read_excel(workbook, sheet_name=line_stops_sheet)
            if line_stops_sheet in sheet_names
            else pd.DataFrame()
        )
        data_dictionary = (
            pd.read_excel(workbook, sheet_name=data_dictionary_sheet)
            if data_dictionary_sheet in sheet_names
            else pd.DataFrame()
        )

    return recordings, line_stops, data_dictionary


# Le um arquivo CSV tratado como tabela de gravacoes.
def _read_csv_file(path: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    recordings = pd.read_csv(path)
    return recordings, pd.DataFrame(), pd.DataFrame()


# Valida colunas obrigatorias e normaliza a coluna timestamp.
def _normalize_recordings(
    path: Path,
    recordings: pd.DataFrame,
    input_config: dict[str, Any],
) -> pd.DataFrame:
    required_columns = input_config.get("required_recording_columns", [])
    missing_columns = [
        column for column in required_columns if column not in recordings.columns
    ]

    if missing_columns:
        missing_text = ", ".join(missing_columns)
        raise LogReadError(f"{path.name}: colunas ausentes: {missing_text}")

    if recordings.empty:
        raise LogReadError(f"{path.name}: aba recordings vazia")

    normalized = recordings.copy()
    normalized["timestamp"] = pd.to_datetime(
        normalized["timestamp"],
        errors="coerce",
    )

    invalid_timestamps = normalized["timestamp"].isna().sum()
    if invalid_timestamps:
        raise LogReadError(
            f"{path.name}: linhas com timestamp invalido: {invalid_timestamps}"
        )

    return normalized.sort_values("timestamp").reset_index(drop=True)


# Normaliza datas da tabela de paradas de linha, quando existir.
def _normalize_line_stops(line_stops: pd.DataFrame) -> pd.DataFrame:
    if line_stops.empty:
        return line_stops

    normalized = line_stops.copy()
    for column in ["stop_start", "stop_end"]:
        if column in normalized.columns:
            normalized[column] = pd.to_datetime(normalized[column], errors="coerce")

    if "stop_start" in normalized.columns:
        normalized = normalized.sort_values("stop_start")

    return normalized.reset_index(drop=True)
