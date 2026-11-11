import logging

from scripts.cotas_collect import collect_all
from scripts.cotas_prepare import prepare_cotas

RAW_DIR = "dados/originais/cotas"
MANIFEST_PATH = "dados/originais/cotas_coleta.json"
OUTPUT_PATH = "dados/processados/cotas.parquet"


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    collect_all(RAW_DIR, MANIFEST_PATH)
    prepare_cotas(RAW_DIR, OUTPUT_PATH)


if __name__ == "__main__":
    main()
