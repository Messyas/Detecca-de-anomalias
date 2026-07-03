from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from .ingestion import (
        LogReadError,
        build_ingestion_summary,
        load_batches_in_order,
        load_config,
    )
except ImportError:
    from ingestion import (
        LogReadError,
        build_ingestion_summary,
        load_batches_in_order,
        load_config,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Executa a etapa de ingestao do monitor de anomalias."
    )
    parser.add_argument(
        "--input",
        default="Logs",
        help="Pasta com arquivos de log .xlsx ou .csv.",
    )
    parser.add_argument(
        "--output",
        default="Output",
        help="Pasta onde as saidas da ingestao serao salvas.",
    )
    parser.add_argument(
        "--config",
        default="Monitor/config.json",
        help="Caminho do arquivo de configuracao do monitor.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_dir = Path(args.input)
    output_dir = Path(args.output)
    config_path = Path(args.config)

    try:
        config = load_config(config_path)
        batches = load_batches_in_order(input_dir, config)
    except (OSError, LogReadError) as error:
        print(f"Erro de entrada: {error}", file=sys.stderr)
        return 2

    output_dir.mkdir(parents=True, exist_ok=True)
    summary = build_ingestion_summary(batches)
    summary_path = output_dir / "ingestion_summary.csv"
    summary.to_csv(summary_path, index=False)

    if not batches:
        print("Nenhum arquivo de log encontrado.")
        print(f"Resumo salvo em: {summary_path}")
        return 0

    print("Arquivos de log processados em ordem cronologica:")
    for row in summary.itertuples(index=False):
        print(
            f"{row.order}. {row.file} | "
            f"{row.start_time} -> {row.end_time} | "
            f"{row.recording_rows} linhas"
        )

    print(f"Resumo salvo em: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
