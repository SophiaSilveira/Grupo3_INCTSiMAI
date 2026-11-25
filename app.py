import logging
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)

logger = logging.getLogger("app")

INCT_RAW = Path("dados/originais/data.json")
INCT_ANOMALIES = Path("dados/processados/anomalies.csv")
INCT_CLEAN = Path("dados/processados/inct_limpo.json")

COTAS_RAW_DIR = Path("dados/originais/cotas")
COTAS_MANIFEST = Path("dados/originais/cotas_coleta.json")
COTAS_OUTPUT = Path("dados/processados/cotas.parquet")

STREETS_OUTPUT = Path("dados/processados/logradouros.geojson")
ROUTES_OUTPUT = Path("dados/processados/rotas.parquet")

DASHBOARD_PAGES = [
    (Path("scripts/dashboards/tela1_simulacao.py"), "Tela 1 - Simulação do INCT"),
    (Path("scripts/dashboards/tela2_rotas.py"), "Tela 2 - Rotas na enchente"),
]


def step_inct():
    from scripts.normalization.inct_cleaning import clean_inct_data

    return clean_inct_data(INCT_RAW, INCT_ANOMALIES, INCT_CLEAN)


def step_cotas():
    from scripts.normalization.cotas_collect import collect_all
    from scripts.normalization.cotas_prepare import prepare_cotas

    collect_all(COTAS_RAW_DIR, COTAS_MANIFEST)
    prepare_cotas(COTAS_RAW_DIR, COTAS_OUTPUT)
    return COTAS_OUTPUT


def step_logradouros():
    from scripts.normalization.logradouro_collect import collect_streets
    from scripts.normalization.logradouros_cleaning import clean_streets

    return clean_streets(collect_streets())


def step_rotas():
    from scripts.normalization.rotas_prepare import prepare_routes

    prepare_routes(COTAS_OUTPUT, STREETS_OUTPUT, ROUTES_OUTPUT)
    return ROUTES_OUTPUT


STEPS = {
    "inct": (step_inct, INCT_CLEAN),
    "cotas": (step_cotas, COTAS_OUTPUT),
    "logradouros": (step_logradouros, STREETS_OUTPUT),
    "rotas": (step_rotas, ROUTES_OUTPUT),
}


def run_pipeline():
    failures = {}
    for name, (step, output) in STEPS.items():
        if output.exists():
            logger.info("[%s] já pronto: %s", name, output)
            continue
        logger.info("[%s] executando...", name)
        try:
            logger.info("[%s] concluído: %s", name, step())
        except Exception as error:
            logger.exception("[%s] falhou", name)
            failures[name] = f"{type(error).__name__}: {error}"
    return failures


def running_in_streamlit():
    try:
        from streamlit import runtime
    except ImportError:
        return False
    return runtime.exists()


def launch_dashboard():
    try:
        import streamlit  # noqa: F401
    except ImportError:
        logger.error("Streamlit não está instalado. Rode: pip install -r requirements.txt")
        return 1
    try:
        return subprocess.call([sys.executable, "-m", "streamlit", "run", str(ROOT / "app.py")])
    except KeyboardInterrupt:
        return 0


def render_dashboard():
    import streamlit as st

    st.set_page_config(page_title="Enchentes em Porto Alegre", layout="wide")

    @st.cache_resource(show_spinner="Preparando os dados...")
    def prepare_data():
        return run_pipeline()

    for name, message in prepare_data().items():
        st.error(f"A etapa '{name}' falhou: {message}")

    pages = [st.Page(str(path), title=title) for path, title in DASHBOARD_PAGES if path.exists()]
    if not pages:
        st.title("Enchentes em Porto Alegre")
        st.info("Os dados estão prontos, mas as telas ainda não foram criadas.")
        return
    st.navigation(pages).run()


def main():
    failures = run_pipeline()
    if failures:
        logger.warning("Etapas com falha: %s", ", ".join(failures))
    return launch_dashboard()


logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

if running_in_streamlit():
    render_dashboard()
elif __name__ == "__main__":
    sys.exit(main())
