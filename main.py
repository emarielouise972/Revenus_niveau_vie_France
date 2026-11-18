import streamlit as st
import pandas as pd
import missingno as msno
import matplotlib.pyplot as plt
import plotly.express as px
import urllib.request
import json
st.title("TRAITEMENT DES DONNÉES")

def lire_insee(path):
    # Détecte automatiquement le séparateur de colonnes et de décimales
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        header = f.readline()
        premiere_ligne = f.readline()
    sep = ";" if ";" in header else ","
    decimal = "," if (sep == ";" and "," in premiere_ligne) else "."
    return pd.read_csv(
        path,
        sep=sep,
        decimal=decimal,
        dtype={"IRIS": str},
        na_values=["ns", "nd", "s", "so", ""]
    )

@st.cache_data
def charger_et_traiter():
    fichiers = [
        {"annee": 2018, "suffixe": "18", "dec": "data/BASE_TD_FILO_DEC_IRIS_2018.csv", "disp": "data/BASE_TD_FILO_DISP_IRIS_2018.csv"},
        {"annee": 2019, "suffixe": "19", "dec": "data/BASE_TD_FILO_DEC_IRIS_2019.csv", "disp": "data/BASE_TD_FILO_DISP_IRIS_2019.csv"},
        {"annee": 2020, "suffixe": "20", "dec": "data/BASE_TD_FILO_DEC_IRIS_2020.csv", "disp": "data/BASE_TD_FILO_DISP_IRIS_2020.csv"},
        {"annee": 2021, "suffixe": "21", "dec": "data/BASE_TD_FILO_IRIS_2021_DEC.csv", "disp": "data/BASE_TD_FILO_IRIS_2021_DISP.csv"}
    ]

    dataframes_annuels = []

    for config in fichiers:
        df_dec = lire_insee(config["dec"])
        df_disp = lire_insee(config["disp"])

        df_merged = pd.merge(df_dec, df_disp, on="IRIS", how="inner")

        # Retrait du suffixe d'année (ex: DEC_MED18 -> DEC_MED)
        colonnes_renommees = {
            col: col[:-2]
            for col in df_merged.columns
            if col != "IRIS" and col.endswith(config["suffixe"])
        }
        df_merged.rename(columns=colonnes_renommees, inplace=True)

        # Ajout de la colonne ANNEE en 2e position
        df_merged.insert(1, "ANNEE", config["annee"])
        dataframes_annuels.append(df_merged)

    df = pd.concat(dataframes_annuels, ignore_index=True)

    df.drop(columns=["DEC_INCERT", "DISP_INCERT"], errors="ignore", inplace=True)

    for col in df.columns:
        if col not in ["IRIS", "ANNEE"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # 3. Suppression d'éventuels doublons
    df.drop_duplicates(subset=["IRIS", "ANNEE"], inplace=True)

    df.insert(2, "DEP", df["IRIS"].str[:2])
    df["ECART_MED"] = df["DISP_MED"] - df["DEC_MED"]

    df.to_csv("INSEE_DEC_DISP_2018_2021_CLEAN.csv", sep=";", index=False)
    return df

df_final = charger_et_traiter()

st.write(f"**Dimensions après traitement :** {df_final.shape[0]} lignes × {df_final.shape[1]} colonnes")

col_data, col_msno = st.columns([3, 2])
with col_data:
    st.subheader("Aperçu des données traitées")
    st.dataframe(df_final.head(10))

with col_msno:
    st.subheader("Valeurs manquantes")
    msn = msno.matrix(df_final.sample(1000, random_state=42), sparkline=False, figsize=(6, 4), fontsize=8)
    st.pyplot(msn.figure)

st.subheader("KPIS")
annees_dispo = sorted(df_final["ANNEE"].unique())
annee_sel = st.selectbox("Année :", options=["Toutes (2018-2021)"] + list(annees_dispo))
if annee_sel == "Toutes (2018-2021)":
    df_kpi = df_final
    df_prev = None
else:
    df_kpi = df_final[df_final["ANNEE"] == annee_sel]
    df_prev = df_final[df_final["ANNEE"] == annee_sel - 1] if (annee_sel - 1) in annees_dispo else None

dec_med = df_kpi["DEC_MED"].nunique()
dec_med = df_kpi["DEC_MED"].median()
disp_med = df_kpi["DISP_MED"].median()
tp60_moy = df_kpi["DISP_TP60"].mean()
gini_moy = df_kpi["DISP_GI"].mean()
ecart_med = df_kpi["ECART_MED"].mean()

delta_dec = f"{((dec_med - df_prev['DEC_MED'].median()) / df_prev['DEC_MED'].median()) * 100:+.1f} %" if df_prev is not None else None
delta_disp = f"{((disp_med - df_prev['DISP_MED'].median()) / df_prev['DISP_MED'].median()) * 100:+.1f} %" if df_prev is not None else None
delta_tp60 = f"{(tp60_moy - df_prev['DISP_TP60'].mean()):+.1f} pts" if df_prev is not None else None
delta_em = f"{(ecart_med - df_prev['ECART_MED'].mean()):+.0f} €" if df_prev is not None else None

c1, c2, c3, c4, c5 = st.columns(5)

c1.metric("Revenu déclaré médian", f"{dec_med:,.0f} €".replace(",", " "), delta=delta_dec)
c2.metric("Revenu disponible médian", f"{disp_med:,.0f} €".replace(",", " "), delta=delta_disp)
c3.metric("Taux de pauvreté moyen", f"{tp60_moy:.1f} %", delta=delta_tp60, delta_color="inverse")
c4.metric("Indice de Gini moyen", f"{gini_moy:.3f}")
c5.metric("Écart moyen (DISP - DEC)", f"{ecart_med:+,.0f} €".replace(",", " "), delta=delta_em)

st.subheader("1. Évolution des revenus médians (2018 - 2021)")

df_evol = df_final.groupby("ANNEE", as_index=False)[["DEC_MED", "DISP_MED"]].median()

fig1 = px.line(
    df_evol,
    x="ANNEE",
    y=["DEC_MED", "DISP_MED"],
    markers=True,
    labels={"value": "Revenu médian (€)", "ANNEE": "Année", "variable": "Indicateur"},
    title="Évolution du revenu déclaré vs disponible médian"
)
fig1.update_xaxes(dtick=1)  # Force l'affichage des années entières
st.plotly_chart(fig1, use_container_width=True)

st.subheader("2. Effet de la redistribution fiscale et sociale")

# On filtre sur une année (ex: df_kpi) et on échantillonne pour garder le graphique fluide
df_sample = df_kpi.dropna(subset=["DEC_MED", "ECART_MED", "DISP_TP60"]).sample(
    min(3000, len(df_kpi)), random_state=42
)

fig2 = px.scatter(
    df_sample,
    x="DEC_MED",
    y="ECART_MED",
    color="DISP_TP60",
    hover_data=["IRIS", "DEP"],
    color_continuous_scale="RdYlGn_r",
    labels={
        "DEC_MED": "Revenu déclaré médian (€)",
        "ECART_MED": "Écart DISP - DEC (€)",
        "DISP_TP60": "Taux de pauvreté (%)"
    },
    title="Impact de la redistribution selon le niveau de revenu du quartier"
)
fig2.add_hline(y=0, line_dash="dash", line_color="gray")  # Ligne d'équilibre (0 €)
st.plotly_chart(fig2, use_container_width=True)

st.subheader("3. Disparités territoriales : Top 5 et Flop 5 des départements")

df_dep = df_kpi.groupby("DEP", as_index=False)["DISP_MED"].median().dropna()
top_flop = pd.concat([
    df_dep.nlargest(5, "DISP_MED").assign(Catégorie="Top 5 (Plus aisés)"),
    df_dep.nsmallest(5, "DISP_MED").assign(Catégorie="Flop 5 (Plus modestes)")
]).sort_values("DISP_MED")

fig3 = px.bar(
    top_flop,
    x="DISP_MED",
    y="DEP",
    color="Catégorie",
    orientation="h",
    text_auto=".0f",
    labels={"DISP_MED": "Revenu disponible médian (€)", "DEP": "Département"},
    title="Comparaison des 5 départements les plus aisés et les plus modestes"
)
fig3.update_layout(yaxis={"type": "category"})
st.plotly_chart(fig3, use_container_width=True)

def charger_geojson_france():
    url = "https://raw.githubusercontent.com/gregoiredavid/france-geojson/master/departements-version-simplifiee.geojson"
    with urllib.request.urlopen(url) as response:
        return json.loads(response.read().decode("utf-8"))
geojson_dep = charger_geojson_france()
indicateur = st.radio(
    "Indicateur à cartographier :",
    options=["DISP_MED", "DEC_MED"],
    format_func=lambda x: "Revenu disponible médian (€)" if x == "DISP_MED" else "Revenu déclaré médian (€)",
    horizontal=True
)

df_carte = df_kpi.groupby("DEP", as_index=False)[indicateur].median().dropna()

fig_carte = px.choropleth(
    df_carte,
    geojson=geojson_dep,
    locations="DEP",
    featureidkey="properties.code",
    color=indicateur,
    color_continuous_scale="YlGnBu",
    labels={indicateur: "Revenu médian (€)", "DEP": "Département"},
    title=f"Revenu médian par département ({annee_sel})"
)

fig_carte.update_geos(fitbounds="locations", visible=False)
fig_carte.update_layout(margin={"r": 0, "t": 40, "l": 0, "b": 0}, height=600)

st.plotly_chart(fig_carte, use_container_width=True)

