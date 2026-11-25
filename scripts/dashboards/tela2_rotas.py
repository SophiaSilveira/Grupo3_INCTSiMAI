import json
import math
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import networkx as nx
import pandas as pd
import pydeck as pdk
import shapely
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
ROUTES_PATH = ROOT / "dados/processados/rotas.parquet"
COTAS_PATH = ROOT / "dados/processados/cotas.parquet"
COTAS_MANIFEST = ROOT / "dados/originais/cotas_coleta.json"
STREETS_METADATA = ROOT / "dados/originais/logradouros/Shapefile_Logradouros.metadata.json"

OPEN_COLOR = [102, 187, 106]
BLOCKED_COLOR = [229, 57, 53]
FLOOD_COLOR = [66, 165, 245, 70]
ROUTE_COLOR = [21, 101, 192]
POINT_COLOR = [33, 33, 33]
CITY_VIEW = pdk.ViewState(latitude=-30.06, longitude=-51.18, zoom=10.6)

EVACUATION_DEFAULT = "Avenida Farrapos"
A_DEFAULT, B_DEFAULT = "Avenida Osvaldo Aranha", "Avenida Wenceslau Escobar"


@st.cache_resource(show_spinner="Montando a malha de ruas...")
def load_network():
    segments = gpd.read_parquet(ROUTES_PATH).reset_index(drop=True)
    everything = nx.from_pandas_edgelist(segments, "node_a", "node_b")
    main = max(nx.connected_components(everything), key=len)
    segments = segments[segments["node_a"].isin(main)].reset_index(drop=True)

    segments["path"] = [shapely.get_coordinates(line).round(5).tolist() for line in segments.geometry]
    ends = pd.concat([
        pd.DataFrame({"node": segments["node_a"], "xy": [p[0] for p in segments["path"]]}),
        pd.DataFrame({"node": segments["node_b"], "xy": [p[-1] for p in segments["path"]]}),
    ]).drop_duplicates("node")
    coords = dict(zip(ends["node"], ends["xy"]))

    repeated = segments.groupby("name")["street_code"].transform("nunique") > 1
    segments["label"] = segments["name"].where(~repeated, segments["name"] + " (cód. " + segments["street_code"].astype(str) + ")")
    return pd.DataFrame(segments.drop(columns="geometry")), coords


@st.cache_data(show_spinner="Carregando as manchas de inundação...")
def load_flood_areas():
    cotas = gpd.read_parquet(COTAS_PATH)
    cotas["geometry"] = cotas.geometry.simplify(10)
    cotas = cotas.to_crs(4326)
    return {level: json.loads(gpd.GeoSeries([geom]).to_json()) for level, geom in zip(cotas["level_m"], cotas.geometry)}


def is_blocked(segments, level):
    return segments["blocking_level_m"] <= level


def build_graph(segments):
    edges = segments.assign(u=segments[["node_a", "node_b"]].min(axis=1), v=segments[["node_a", "node_b"]].max(axis=1))
    edges = edges.reset_index(names="seg").sort_values("length_m").drop_duplicates(["u", "v"])
    return nx.from_pandas_edgelist(edges, "u", "v", ["length_m", "seg"])


@st.cache_resource(show_spinner="Calculando as ruas secas neste nível...")
def graphs_for(level):
    segments, _ = load_network()
    dry = segments[~is_blocked(segments, level)]
    return build_graph(segments), build_graph(dry), set(dry["node_a"]) | set(dry["node_b"])


@st.cache_data(show_spinner=False)
def distance_to_dry(level):
    full, _, dry_nodes = graphs_for(level)
    distances = nx.multi_source_dijkstra_path_length(full, dry_nodes, weight="length_m")
    return pd.Series({node: d for node, d in distances.items() if node not in dry_nodes}, dtype=float)


def central_node(nodes, coords):
    points = pd.DataFrame([coords[n] for n in nodes], index=list(nodes), columns=["x", "y"])
    gap = (points - points.mean()).pow(2).sum(axis=1)
    return gap.idxmin()


def route_segments(graph, path):
    return [graph[u][v]["seg"] for u, v in zip(path, path[1:])]


def street_nodes(segments, label):
    rows = segments[segments["label"] == label]
    return set(rows["node_a"]) | set(rows["node_b"])


def view_around(paths):
    points = pd.DataFrame([xy for path in paths for xy in path], columns=["lon", "lat"])
    span = max(points["lon"].max() - points["lon"].min(), points["lat"].max() - points["lat"].min(), 0.005)
    zoom = min(14, max(10, 8.1 - math.log2(span / 0.7)))
    return pdk.ViewState(latitude=points["lat"].mean(), longitude=points["lon"].mean(), zoom=zoom)


def draw_map(segments, level, key, route=None, points=None):
    blocked = is_blocked(segments, level)
    columns = ["path", "name", "label"]
    layers = [
        pdk.Layer("GeoJsonLayer", load_flood_areas()[level], get_fill_color=FLOOD_COLOR, stroked=False),
        pdk.Layer("PathLayer", segments.loc[~blocked, columns], id="secas", get_path="path",
                  get_color=OPEN_COLOR, width_min_pixels=2, pickable=True, auto_highlight=True),
        pdk.Layer("PathLayer", segments.loc[blocked, columns], id="alagadas", get_path="path",
                  get_color=BLOCKED_COLOR, width_min_pixels=2, pickable=True, auto_highlight=True),
    ]
    view = CITY_VIEW
    if route is not None and len(route):
        layers.append(pdk.Layer("PathLayer", route[["path", "name"]], get_path="path",
                                get_color=ROUTE_COLOR, width_min_pixels=6, pickable=True))
        view = view_around(route["path"])
    if points is not None:
        layers.append(pdk.Layer("ScatterplotLayer", points, get_position="xy", get_fill_color=POINT_COLOR,
                                get_line_color=[255, 255, 255], stroked=True, line_width_min_pixels=2,
                                radius_min_pixels=7, pickable=True))
    deck = pdk.Deck(layers=layers, initial_view_state=view, map_style=None, tooltip={"text": "{name}"})
    st.pydeck_chart(deck, height=600, key=map_key(key), on_select="rerun", selection_mode="single-object")


def map_key(name):
    return f"{name}_{st.session_state.get(name + '_cliques', 0)}"


def street_from_click(map_name, select_key, allowed, refused_message):
    selection = (st.session_state.get(map_key(map_name)) or {}).get("selection") or {}
    picked = [obj.get("label") for objs in selection.get("objects", {}).values() for obj in objs]
    picked = next((label for label in picked if label), None)
    if picked is None:
        return
    # a new key draws a fresh map, so the clicked street does not stay highlighted with the rest faded
    st.session_state[map_name + "_cliques"] = st.session_state.get(map_name + "_cliques", 0) + 1
    if picked in allowed:
        st.session_state[select_key] = picked
    else:
        st.toast(refused_message.format(picked))


def keep_valid(select_key, options, default):
    if st.session_state.get(select_key) not in options:
        st.session_state[select_key] = default if default in options else options[0]


def legend(*items):
    swatch = '<span style="display:inline-block;width:14px;height:6px;background:rgb({});margin:0 6px 2px 0;margin-left:14px"></span>{}'
    st.markdown("".join(swatch.format(",".join(map(str, color[:3])), text) for color, text in items),
                unsafe_allow_html=True)


def small_metric(column, label, value):
    column.markdown(f'<div style="font-size:0.8rem;opacity:0.7">{label}</div>'
                    f'<div style="font-size:1.3rem">{value}</div>', unsafe_allow_html=True)


def km(meters):
    if abs(meters) < 1000:
        return f"{meters:.0f} m"
    return f"{meters / 1000:,.1f} km".replace(",", "X").replace(".", ",").replace("X", ".")


def br_date(iso_text):
    return datetime.fromisoformat(iso_text).astimezone().strftime("%d/%m/%Y")


segments, coords = load_network()
levels = sorted(load_flood_areas())

st.title("Rotas por Porto Alegre durante a enchente")
st.caption("Quais ruas ficam debaixo d'água em cada nível do Guaíba, como sair de uma área alagada "
           "e como ir de um ponto a outro só por ruas secas.")

controls, map_area = st.columns([1, 2.6], gap="medium")
route, points, map_name = None, None, "mapa_saida"

with controls:
    level = st.select_slider("Nível do Guaíba (m)", options=levels, value=5.35,
                             format_func=lambda v: f"{v:.2f} m".replace(".", ","))
    blocked = is_blocked(segments, level)
    full_graph, dry_graph, dry_nodes = graphs_for(level)
    distances = distance_to_dry(level)

    mode = st.radio("O que você quer ver?", ["Sair da área alagada", "Ir de A até B sem passar pela água"])

    if mode == "Sair da área alagada":
        flooded_streets = sorted(segments.loc[blocked, "label"].unique())
        street_from_click("mapa_saida", "rua_saida", flooded_streets, "{} está seca neste nível. Clique numa rua vermelha.")
        keep_valid("rua_saida", flooded_streets, EVACUATION_DEFAULT)
        start = st.selectbox("Rua alagada de onde sair", flooded_streets, key="rua_saida",
                             help="Também dá para clicar numa rua vermelha no mapa.")
        origin = central_node(street_nodes(segments, start) - dry_nodes or street_nodes(segments, start), coords)
        if origin in dry_nodes:
            st.info("Esta rua ainda tem trechos secos neste nível: basta seguir por eles.")
        else:
            length, path = nx.multi_source_dijkstra(full_graph, dry_nodes, target=origin, weight="length_m")
            path = path[::-1]
            route = segments.loc[route_segments(full_graph, path)]
            exit_street = segments.loc[(segments["node_a"] == path[-1]) | (segments["node_b"] == path[-1])]
            exit_name = exit_street.loc[~is_blocked(exit_street, level), "name"].iloc[0]
            st.metric("Até a rua seca mais próxima", km(length))
            st.markdown(f"Saída por **{exit_name}**.")
            points = pd.DataFrame({"xy": [coords[path[0]], coords[path[-1]]], "name": [f"Partida: {start}", f"Rua seca: {exit_name}"]})

    else:
        map_name = "mapa_ab"
        labels = sorted(segments["label"].unique())
        target_key = "rua_a" if st.session_state.get("clique_define", "Partida (A)") == "Partida (A)" else "rua_b"
        street_from_click("mapa_ab", target_key, labels, "{} não pode ser escolhida.")
        keep_valid("rua_a", labels, A_DEFAULT)
        keep_valid("rua_b", labels, B_DEFAULT)
        a = st.selectbox("Partida (A)", labels, key="rua_a")
        b = st.selectbox("Chegada (B)", labels, key="rua_b")
        st.radio("Clique no mapa escolhe a", ["Partida (A)", "Chegada (B)"], key="clique_define", horizontal=True)
        a_nodes, b_nodes = street_nodes(segments, a) & dry_nodes, street_nodes(segments, b) & dry_nodes
        if not a_nodes or not b_nodes:
            st.warning(f"{a if not a_nodes else b} está totalmente alagada neste nível. Escolha outra rua ou um nível menor.")
        else:
            source, target = central_node(a_nodes, coords), central_node(b_nodes, coords)
            try:
                length, path = nx.single_source_dijkstra(dry_graph, source, target, weight="length_m")
            except nx.NetworkXNoPath:
                st.error("Não existe caminho só por ruas secas entre esses pontos neste nível.")
            else:
                normal = nx.shortest_path_length(full_graph, source, target, weight="length_m")
                route = segments.loc[route_segments(dry_graph, path)]
                st.metric("Rota sem água", km(length))
                left, right = st.columns(2)
                small_metric(left, "Desvio", km(length - normal))
                small_metric(right, "Sem enchente", km(normal))
                points = pd.DataFrame({"xy": [coords[source], coords[target]], "name": [f"A: {a}", f"B: {b}"]})

with map_area:
    legend((FLOOD_COLOR, "área alagada"), (BLOCKED_COLOR, "rua alagada"), (OPEN_COLOR, "rua seca"), (ROUTE_COLOR, "rota"))
    draw_map(segments, level, map_name, route, points)

if mode == "Sair da área alagada":
    st.caption("Limitação: ainda não temos os limites dos bairros, então a rota leva até a rua seca mais próxima, "
               "que pode estar no mesmo bairro. A distância é medida pelas ruas, não em linha reta.")
else:
    st.caption("Para escolher pelo mapa, marque se o clique define A ou B e clique numa rua. Aproximar o mapa ajuda a acertar a rua. "
               "A e B são o ponto mais central de cada rua que ainda está seco. Ruas que só encostam na mancha "
               "de inundação já contam como bloqueadas.")

with st.container(border=True):
    st.markdown(f"#### Resumo no nível de {level:.2f} m".replace(".", ","))
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ruas alagadas", km(segments.loc[blocked, "length_m"].sum()))
    c2.metric("Da malha viária", f"{segments.loc[blocked, 'length_m'].sum() / segments['length_m'].sum():.1%}".replace(".", ","))
    c3.metric("Logradouros atingidos", f"{segments.loc[blocked, 'label'].nunique():,}".replace(",", "."))
    c4.metric("Maior distância até rua seca", km(distances.max()) if len(distances) else "-")

cotas_date = br_date(json.loads(COTAS_MANIFEST.read_text(encoding="utf-8"))["files"]["objectid_1.geojson"]["collected_at"])
streets_meta = json.loads(STREETS_METADATA.read_text(encoding="utf-8"))
st.caption(f"Fontes: manchas de inundação de 3,00 m a 5,35 m, Prefeitura de Porto Alegre (SMAMUS, ArcGIS), coletadas em {cotas_date}. "
           f"Eixos de logradouros, Prefeitura de Porto Alegre (SMAMUS, Mapas Digitais), coletados em {br_date(streets_meta['collected_at'])}.")
st.caption("Limitações: as manchas mostram o terreno abaixo de cada cota e não consideram diques, comportas ou bombas, "
           "por isso áreas protegidas, como o Centro, aparecem alagadas já em 3,00 m. Não há dados abaixo de 3,00 m nem acima de 5,35 m.")
