from html import escape
import json
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st


DATA_FILE = Path(__file__).parent / "Data" / "consolidado_agregado.xlsx"
REQUIRED_COLUMNS = {
    "ESTADO POSICION",
    "HORARIO",
    "SOCIEDAD",
    "NEGOCIO ATENDIDO",
    "N1 - NEGOCIO/OFICINA",
    "N2-GERENCIA",
    "N3-DIVISION",
    "N4-AREA",
    "N5-DEPARTAMENTO",
    "PERIODO",
    "ALCANCE",
    "PAIS",
    "PERSONAL_DISTINTO",
}
FILTER_COLUMNS = (
    "PERIODO",
    "ESTADO POSICION",
    "HORARIO",
    "ALCANCE",
    "NEGOCIO ATENDIDO",
    "N1 - NEGOCIO/OFICINA",
    "N2-GERENCIA",
    "N3-DIVISION",
    "N4-AREA",
    "N5-DEPARTAMENTO",
)
SELECT_ALL = "__SELECT_ALL__"


st.set_page_config(page_title="Personal por período", layout="wide")


@st.cache_data
def load_data() -> pd.DataFrame:
    if not DATA_FILE.is_file():
        raise FileNotFoundError(f"No se encontró el archivo: {DATA_FILE}")

    data = pd.read_excel(DATA_FILE)
    missing_columns = REQUIRED_COLUMNS.difference(data.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Faltan columnas requeridas en el Excel: {missing}")

    return data


st.title("Comparativo mensual de headcount")

try:
    data = load_data()
except (FileNotFoundError, ValueError) as error:
    st.error(str(error))
    st.stop()

with st.sidebar:
    selected_filters = {}
    default_filters = {
        "ESTADO POSICION": "ACTIVO",
        "HORARIO": "FULL TIME",
    }
    for column in FILTER_COLUMNS:
        options = sorted(data[column].dropna().unique().tolist())
        default_value = default_filters.get(column)
        default_selection = [default_value] if default_value in options else []
        label = "ESTADO DE POSICION" if column == "ESTADO POSICION" else column
        selected_filters[column] = st.multiselect(
            label,
            options=[SELECT_ALL, *options],
            default=default_selection,
            format_func=lambda value: "Select all" if value == SELECT_ALL else str(value),
            key=f"filter_{column.lower().replace(' ', '_')}",
        )

filtered_data = data
for column, selected_options in selected_filters.items():
    selected_values = [value for value in selected_options if value != SELECT_ALL]
    if selected_values and SELECT_ALL not in selected_options:
        filtered_data = filtered_data[filtered_data[column].isin(selected_values)]

if filtered_data.empty:
    st.info("No hay datos para la combinación de filtros seleccionada.")
    st.stop()

chart_data = (
    filtered_data.groupby(["PERIODO", "PAIS"], as_index=False)["PERSONAL_DISTINTO"]
    .sum()
    .sort_values("PERIODO")
)
periods = sorted(chart_data["PERIODO"].unique().tolist())
countries = sorted(chart_data["PAIS"].dropna().unique().tolist())
country_colors = {
    "PERU": "#BED600",
    "COLOMBIA": "#00B0CA",
    "MEXICO": "#66008C",
}
if periods and countries:
    full_index = pd.MultiIndex.from_product([periods, countries], names=["PERIODO", "PAIS"])
    chart_data = (
        chart_data.set_index(["PERIODO", "PAIS"])["PERSONAL_DISTINTO"]
        .reindex(full_index, fill_value=0)
        .rename("PERSONAL_DISTINTO")
        .reset_index()
    )
period_positions = {period: index for index, period in enumerate(periods)}
country_positions = {country: index for index, country in enumerate(countries)}
chart_data["PERIODO_POS"] = chart_data["PERIODO"].map(period_positions)
chart_data["COUNTRY_ORDER"] = chart_data["PAIS"].map(country_positions)
period_totals = chart_data.groupby("PERIODO", as_index=False)["PERSONAL_DISTINTO"].sum()
period_totals["PERIODO_POS"] = period_totals["PERIODO"].map(period_positions)
period_totals["TOTAL_LABEL"] = period_totals["PERSONAL_DISTINTO"].map(lambda value: f"{int(value):,}")
max_total = int(period_totals["PERSONAL_DISTINTO"].max()) if not period_totals.empty else 0

segment_centers = {}
segment_tops = {}
for period in periods:
    cumulative = 0
    for country in countries:
        value = int(
            chart_data.loc[
                (chart_data["PERIODO"] == period) & (chart_data["PAIS"] == country),
                "PERSONAL_DISTINTO",
            ].iloc[0]
        )
        segment_centers[(period, country)] = cumulative + value / 2
        cumulative += value
        segment_tops[(period, country)] = cumulative

chart_data["SEGMENT_LABEL_Y"] = [
    max(
        segment_tops[(period, country)] - max(max_total, 1) * 0.018,
        segment_centers[(period, country)],
    )
    for period, country in zip(chart_data["PERIODO"], chart_data["PAIS"])
]

chart_data["VALUE_LABEL"] = chart_data["PERSONAL_DISTINTO"].map(
    lambda value: f"{int(value):,}" if value else ""
)
variation_rows = []
for index in range(1, len(periods)):
    previous_period, current_period = periods[index - 1 : index + 1]
    for country_index, country in enumerate(countries):
        country_values = chart_data[chart_data["PAIS"] == country].set_index("PERIODO")["PERSONAL_DISTINTO"]
        previous_value = int(country_values.get(previous_period, 0))
        current_value = int(country_values.get(current_period, 0))
        percentage = "N/D" if previous_value == 0 and current_value else (
            "0.0%" if previous_value == 0 else f"{(current_value - previous_value) / previous_value:+.1%}"
        )
        color, background = (
            ("#991b1b", "#fee2e2") if current_value > previous_value else
            ("#166534", "#dcfce7") if current_value < previous_value else
            ("#854d0e", "#fef9c3")
        )
        variation_rows.append({
            "MID_POS": index - 0.5, "LABEL": percentage, "PAIS": country,
            "COLOR": color, "BACKGROUND": background,
            "BOX_X": index - 0.86, "BOX_X2": index - 0.14,
            "BOX_Y": (segment_centers[(previous_period, country)] + segment_centers[(current_period, country)]) / 2 - max(max_total, 1) * 0.025,
            "BOX_Y2": (segment_centers[(previous_period, country)] + segment_centers[(current_period, country)]) / 2 + max(max_total, 1) * 0.025,
            "BOX_MID_Y": (segment_centers[(previous_period, country)] + segment_centers[(current_period, country)]) / 2,
        })
variations = pd.DataFrame(
    variation_rows,
    columns=[
        "MID_POS", "LABEL", "PAIS", "COLOR", "BACKGROUND", "BOX_X", "BOX_X2",
        "BOX_Y", "BOX_Y2", "BOX_MID_Y",
    ],
)
chart_top = max_total * 1.13 if max_total else 1
period_labels = [str(period) for period in periods]
axis_label_expr = "".join(
    f"datum.value == {index} ? {json.dumps(label)} : "
    for index, label in enumerate(period_labels)
) + "''"

bars = (
    alt.Chart(chart_data)
    .mark_bar(size=78)
    .encode(
        x=alt.X(
            "PERIODO_POS:Q",
            title="PERIODO",
            scale=alt.Scale(domain=[-0.5, max(len(periods) - 0.5, 0.5)]),
            axis=alt.Axis(
                values=list(range(len(periods))),
                labelExpr=axis_label_expr,
                labelColor="black",
                labelFontSize=12,
                labelPadding=8,
                labelLimit=100,
                labelOverlap=False,
                labelFlush=False,
                titleColor="black",
                domainColor="black",
                tickColor="black",
            ),
        ),
        y=alt.Y(
            "sum(PERSONAL_DISTINTO):Q",
            title="SUMA(PERSONAL_DISTINTO)",
            stack="zero",
        ),
        order=alt.Order("COUNTRY_ORDER:Q", sort="ascending"),
        color=alt.Color(
            "PAIS:N",
            title="PAIS",
            sort=countries,
            scale=alt.Scale(
                domain=countries,
                range=[country_colors.get(str(country).strip().upper(), "#7A7A7A") for country in countries],
            ),
        ),
        tooltip=[
            alt.Tooltip("PERIODO:O", title="PERIODO"),
            alt.Tooltip("PAIS:N", title="PAIS"),
            alt.Tooltip(
                "sum(PERSONAL_DISTINTO):Q",
                title="SUMA(PERSONAL_DISTINTO)",
                format=",",
            ),
        ],
    )
)
segment_labels = (
    alt.Chart(chart_data)
    .mark_text(fontSize=11, fontWeight="bold", color="white", stroke="#333333", strokeWidth=0.5)
    .encode(
        x=alt.X("PERIODO_POS:Q", scale=alt.Scale(domain=[-0.5, max(len(periods) - 0.5, 0.5)])),
        y=alt.Y("SEGMENT_LABEL_Y:Q", scale=alt.Scale(domain=[0, chart_top])),
        order=alt.Order("COUNTRY_ORDER:Q", sort="ascending"),
        text=alt.Text("PERSONAL_DISTINTO:Q", format=","),
        color=alt.value("#111111"),
        tooltip=[alt.Tooltip("PAIS:N", title="PAIS"), alt.Tooltip("PERSONAL_DISTINTO:Q", title="PERSONAL_DISTINTO", format=",")],
    )
)
total_labels = (
    alt.Chart(period_totals)
    .mark_text(fontSize=17, fontWeight="bold", color="black", dy=-10)
    .encode(
        x=alt.X("PERIODO_POS:Q", scale=alt.Scale(domain=[-0.5, max(len(periods) - 0.5, 0.5)])),
        y=alt.Y("PERSONAL_DISTINTO:Q", scale=alt.Scale(domain=[0, chart_top])),
        text="TOTAL_LABEL:N",
    )
)
box_rectangles = (
    alt.Chart(variations)
    .mark_rect(cornerRadius=6, strokeWidth=1)
    .encode(
        x=alt.X("BOX_X:Q", scale=alt.Scale(domain=[-0.5, max(len(periods) - 0.5, 0.5)])),
        x2="BOX_X2:Q",
        y=alt.Y("BOX_Y2:Q", scale=alt.Scale(domain=[0, chart_top]), axis=None),
        y2="BOX_Y:Q",
        color=alt.Color("BACKGROUND:N", scale=None, legend=None),
        tooltip=[alt.Tooltip("PAIS:N", title="PAIS"), alt.Tooltip("LABEL:N", title="Variación")],
    )
)
labels = (
    alt.Chart(variations)
    .mark_text(fontSize=12, fontWeight="bold")
    .encode(
        x=alt.X("MID_POS:Q", scale=alt.Scale(domain=[-0.5, max(len(periods) - 0.5, 0.5)])),
        y=alt.Y("BOX_MID_Y:Q", scale=alt.Scale(domain=[0, chart_top])),
        text="LABEL:N",
        color=alt.Color("COLOR:N", scale=None, legend=None),
    )
)
chart_layers = [bars, segment_labels, total_labels]
if not variations.empty:
    chart_layers.extend([box_rectangles, labels])

chart = (
    alt.layer(*chart_layers)
    .resolve_scale(color="independent")
    .properties(height=500, width=max(800, len(periods) * 150))
)

st.altair_chart(chart, use_container_width=True)

if len(periods) >= 2:
    previous_period, current_period = periods[-2:]
    st.subheader(f"Variación del último periodo por país {previous_period} → {current_period}")
    countries = sorted(chart_data["PAIS"].dropna().unique().tolist())
    country_columns = st.columns(len(countries))

    for country_column, country in zip(country_columns, countries):
        country_data = chart_data[chart_data["PAIS"] == country].set_index("PERIODO")[
            "PERSONAL_DISTINTO"
        ]
        previous_value = int(country_data.get(previous_period, 0))
        current_value = int(country_data.get(current_period, 0))

        if current_value < previous_value:
            color, background, indicator = "#166534", "#dcfce7", "Disminuyó"
        elif current_value == previous_value:
            color, background, indicator = "#854d0e", "#fef9c3", "Se mantuvo"
        else:
            color, background, indicator = "#991b1b", "#fee2e2", "Aumentó"

        percentage = (
            "N/D"
            if previous_value == 0 and current_value != 0
            else (
                "0.0%"
                if previous_value == 0
                else f"{(current_value - previous_value) / previous_value:+.1%}"
            )
        )
        country_column.markdown(
            f"""
            <div style="
                background-color: {background};
                border: 1px solid {color};
                border-radius: 10px;
                padding: 16px;
                text-align: center;
            ">
                <div style="color: {color}; font-weight: 700;">
                    {escape(str(country))}
                </div>
                <div style="color: {color}; font-size: 1.8rem; font-weight: 800;">
                    {percentage}
                </div>
                <div style="color: {color}; font-weight: 600;">
                    {indicator}
                </div>
                <div style="color: {color}; font-size: 0.8rem;">
                    {previous_value:,} → {current_value:,}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
elif periods:
    st.info("Se necesitan al menos dos períodos para calcular la variación.")
