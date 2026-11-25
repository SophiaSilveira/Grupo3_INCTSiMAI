import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

DATA_PATH = Path(__file__).resolve().parents[2] / "dados/processados/inct_limpo.json"
RECORD_LEVEL = 5.35
GREEN = "#66bb6a"
AMBER = "#c27c0e"


@st.cache_data
def load_data():
    raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    levels = [round(raw["level_min"] + i * raw["level_step"], 1) for i in range(raw["level_count"])]
    rows = []
    for name, values in raw["neighborhoods"].items():
        for i, level in enumerate(levels):
            rows.append({
                "nivel": level,
                "bairro": name,
                "predios_afetados": values["affected_buildings"][i],
                "predios_total": values["total_buildings"],
                "pct_predios": values["percentage"][i],
                "populacao": values["population"],
                "pessoas_afetadas": values["affected_population"][i],
            })
    return pd.DataFrame(rows)


def fmt(number):
    return f"{number:,.0f}".replace(",", ".")


df = load_data()
city_population = df.groupby("bairro")["populacao"].first().sum()
by_level = df.groupby("nivel", as_index=False)[["pessoas_afetadas", "predios_afetados"]].sum()

st.title("Análise de bairros afetados por cota de nível d'água do Guaíba")
st.caption(
    "Simulação do INCT SiMAI para os 94 bairros de Porto Alegre, nível do Guaíba de 3,0 m a 10,0 m. "
    "Prédios: OpenStreetMap. População: Censo IBGE 2022."
)

level = st.slider("Nível do Guaíba (m)", 3.0, 10.0, 5.3, 0.1, format="%.1f m")
level = round(level, 1)
current = df[df["nivel"] == level]
hit = current[current["predios_afetados"] > 0]

with st.container(border=True):
    st.markdown(f"#### No nível de {level:.1f} m".replace(".", ","))
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Pessoas afetadas", fmt(current["pessoas_afetadas"].sum()))
    c2.metric("Prédios afetados", fmt(current["predios_afetados"].sum()))
    c3.metric("Bairros atingidos", f"{len(hit)} de {current['bairro'].nunique()}")
    c4.metric("Da população da cidade", f"{current['pessoas_afetadas'].sum() / city_population:.1%}".replace(".", ","))

left, right = st.columns([3, 2])

with left:
    st.subheader("População afetada conforme o rio sobe")
    curve = go.Figure()
    curve.add_trace(go.Scatter(
        x=by_level["nivel"], y=by_level["pessoas_afetadas"], mode="lines",
        line=dict(color=GREEN, width=3), name="Pessoas afetadas",
        hovertemplate="%{x:.1f} m: %{y:,.0f} pessoas<extra></extra>",
    ))
    curve.add_vline(x=RECORD_LEVEL, line=dict(color=AMBER, dash="dash"),
                    annotation_text="Recorde de maio/2024 (5,35 m)", annotation_position="top left")
    selected = by_level[by_level["nivel"] == level]
    curve.add_trace(go.Scatter(
        x=selected["nivel"], y=selected["pessoas_afetadas"], mode="markers",
        marker=dict(color=GREEN, size=12, line=dict(color="white", width=2)),
        hovertemplate="Nível escolhido: %{y:,.0f} pessoas<extra></extra>",
    ))
    curve.update_layout(
        xaxis_title="Nível do Guaíba (m)", yaxis_title="Pessoas afetadas",
        yaxis_rangemode="tozero", yaxis_tickformat=",.0f", separators=",.", showlegend=False,
        margin=dict(t=30, b=10), height=380,
    )
    st.plotly_chart(curve, width="stretch")

with right:
    st.subheader("Bairros com mais pessoas afetadas")
    ranking = hit.nlargest(10, "pessoas_afetadas")[["bairro", "pessoas_afetadas", "pct_predios"]]
    ranking["pessoas_afetadas"] = ranking["pessoas_afetadas"].round().astype(int)
    st.dataframe(
        ranking,
        hide_index=True,
        width="stretch",
        column_config={
            "bairro": "Bairro",
            "pessoas_afetadas": st.column_config.NumberColumn("Pessoas afetadas", format="localized"),
            "pct_predios": st.column_config.ProgressColumn(
                "% dos prédios", format="%.0f%%", min_value=0, max_value=100),
        },
    )

st.subheader("Ranking de bairros com prédios afetados")
if hit.empty:
    st.write("Nenhum bairro tem prédios afetados neste nível.")
else:
    bars = hit.sort_values(["pct_predios", "bairro"], ascending=[True, False])
    chart = px.bar(
        bars, x="pct_predios", y="bairro", orientation="h", text="pct_predios",
        custom_data=["predios_afetados", "predios_total"],
        color_discrete_sequence=[GREEN],
    )
    chart.update_traces(
        texttemplate="%{x:.0f}%", textposition="outside", cliponaxis=False,
        hovertemplate="%{y}: %{x:.0f}% (%{customdata[0]:,} de %{customdata[1]:,} prédios)<extra></extra>",
    )
    chart.update_layout(
        xaxis=dict(range=[0, 112], visible=False),
        yaxis=dict(title=None, showgrid=False),
        bargap=0.35, plot_bgcolor="rgba(0,0,0,0)", separators=",.",
        width=1000, height=max(300, 24 * len(bars)), margin=dict(t=10, b=10, l=10, r=10),
    )
    st.plotly_chart(chart, width="content")

st.caption("Fonte: INCT SiMAI, simulação de inundação de Porto Alegre (arquivo data.json fornecido à turma), após limpeza pelo nosso grupo.")
st.caption(
    "Limitações: os números são estimativas de uma simulação, não previsões nem contagens oficiais. "
    "A população afetada supõe que os moradores se distribuem igualmente entre todos os prédios do bairro, "
    "inclusive os não residenciais. O INCT arredonda a porcentagem para cima, o que deixa a população afetada "
    "um pouco acima do cálculo exato. Corrigimos 24 valores inconsistentes da base original."
)
