from scripts.inct_cleaning import generate_anomaly_report

JSON_PATH = "dados/originais/data.json"
CSV_PATH = "dados/processados/anomalies.csv"


def main():
    generate_anomaly_report(JSON_PATH, CSV_PATH)


if __name__ == "__main__":
    main()
