import logging

from scripts.inct_cleaning import clean_inct_data

JSON_PATH = "dados/originais/data.json"
ANOMALIES_PATH = "dados/processados/anomalies.csv"
CLEAN_PATH = "dados/processados/inct_limpo.json"


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    clean_path = clean_inct_data(JSON_PATH, ANOMALIES_PATH, CLEAN_PATH)
    print(f"Arquivo limpo, base para o dashboard: {clean_path}")


if __name__ == "__main__":
    main()
