"""
Verkehrsdaten Dashboard - Rosengartenbrücke Zürich (OGD Version)
Stündliche Verkehrszählung nach Fahrzeugtypen (seit 2020)
Datenquelle: Open Government Data Stadt Zürich
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import numpy as np
import requests
from io import BytesIO
import urllib3

# SSL-Warnungen unterdrücken (für OGD-Server mit Zertifikatsproblemen)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Seiten-Konfiguration
st.set_page_config(
    page_title="Verkehr Rosengartenbrücke (OGD)",
    layout="wide",
    initial_sidebar_state="expanded"
)

# OGD Base URL
OGD_BASE_URL = "https://data.stadt-zuerich.ch/dataset/ugz_verkehrsdaten_stundenwerte_rosengartenbruecke/download/"

# Farbschema für Fahrzeugklassen
FARBEN = {
    'Personenwagen': '#3498db',
    'Lieferwagen': '#2ecc71',
    'Motorrad': '#e74c3c',
    'Lastwagen': '#9b59b6',
    'Bus': '#f39c12',
    'Trolleybus': '#1abc9c',
    'Sattelzug': '#e67e22',
    'Lastenzug': '#8e44ad',
    'Personenwagen mit Anhänger': '#5dade2',
    'Lieferwagen mit Anhänger': '#58d68d',
    'Lieferwagen mit Auflieger': '#27ae60',
    'Unbekannt': '#95a5a6'
}


def get_ogd_url(year):
    """Generiert die Download-URL für ein bestimmtes Jahr."""
    return f"{OGD_BASE_URL}ugz_ogd_traffic_rosengartenbruecke_h1_{year}.csv"


@st.cache_data(ttl=86400)  # 24h Cache für historische Jahre
def load_year_from_ogd(year):
    """Lädt Daten für ein Jahr direkt vom OGD Portal."""
    url = get_ogd_url(year)
    try:
        response = requests.get(url, timeout=60, verify=False)
        response.raise_for_status()
        return pd.read_csv(BytesIO(response.content), encoding='utf-8-sig')
    except requests.exceptions.RequestException as e:
        st.warning(f"Fehler beim Laden der Daten für {year}: {e}")
        return None


@st.cache_data(ttl=3600)  # 1h Cache für aktuelles Jahr
def load_current_year_from_ogd(year):
    """Lädt Daten für das aktuelle Jahr vom OGD Portal (kürzerer Cache)."""
    url = get_ogd_url(year)
    try:
        response = requests.get(url, timeout=60, verify=False)
        response.raise_for_status()
        return pd.read_csv(BytesIO(response.content), encoding='utf-8-sig')
    except requests.exceptions.RequestException as e:
        st.warning(f"Fehler beim Laden der Daten für {year}: {e}")
        return None


@st.cache_data(ttl=3600)
def load_data_for_years(selected_years):
    """
    Lädt nur die ausgewählten Jahresdaten vom OGD Portal.
    """
    current_year = datetime.now().year
    
    dfs = []
    
    for year in selected_years:
        if year == current_year:
            # Aktuelles Jahr: kürzerer Cache (1h)
            df = load_current_year_from_ogd(year)
        else:
            # Historische Jahre: längerer Cache (24h)
            df = load_year_from_ogd(year)
        
        if df is not None and not df.empty:
            dfs.append(df)
    
    if not dfs:
        return None
    
    data = pd.concat(dfs, ignore_index=True)
    
    # Datum parsen (ISO-Format: 2025-01-01T00:00+0100)
    data['Datum'] = pd.to_datetime(data['Datum'], format='ISO8601')
    
    # Zusätzliche Zeitspalten
    data['Jahr'] = data['Datum'].dt.year
    data['Monat'] = data['Datum'].dt.month
    data['Tag'] = data['Datum'].dt.day
    data['Wochentag'] = data['Datum'].dt.dayofweek
    data['Wochentag_Name'] = data['Datum'].dt.day_name()
    data['Stunde'] = data['Datum'].dt.hour
    data['Kalenderwoche'] = data['Datum'].dt.isocalendar().week
    data['Datum_Tag'] = data['Datum'].dt.date
    
    
    # Fahrzeugkategorien (zusammengefasst)
    kategorie_mapping = {
        'Motorrad': 'Motorrad',
        'Personenwagen': 'Personenwagen',
        'Personenwagen mit Anhänger': 'Personenwagen',
        'Lieferwagen': 'Lieferwagen',
        'Lieferwagen mit Anhänger': 'Lieferwagen',
        'Lieferwagen mit Auflieger': 'Lieferwagen',
        'Lastwagen': 'Lastwagen',
        'Sattelzug': 'Lastwagen',
        'Lastenzug': 'Lastwagen',
        'Bus': 'Bus/Trolleybus',
        'Trolleybus': 'Bus/Trolleybus',
        'Unbekannt': 'Unbekannt'
    }
    data['Kategorie'] = data['Klasse.Text'].map(kategorie_mapping)
    
    return data


def format_number(num):
    """Formatiert große Zahlen mit Schweizer Tausendertrennzeichen (')."""
    num = int(round(num))
    return f"{num:,}".replace(',', "'")


def format_number_ch(num):
    """Formatiert Zahlen im Schweizer Format für Plotly customdata."""
    if pd.isna(num):
        return "–"
    return f"{int(round(num)):,}".replace(',', "'")


@st.cache_data(ttl=3600)
def analyze_data_gaps(data):
    """Analysiert Datenlücken in den Verkehrsdaten (Stundenbasis)."""
    start = data['Datum'].min()
    end = data['Datum'].max()
    full_range = pd.date_range(start=start, end=end, freq='h')
    
    vorhanden = set(data['Datum'].unique())
    fehlend = sorted(set(full_range) - vorhanden)
    
    gaps = []
    if fehlend:
        gap_start = fehlend[0]
        gap_end = fehlend[0]
        
        for ts in fehlend[1:]:
            if ts - gap_end <= timedelta(hours=1):
                gap_end = ts
            else:
                duration_h = (gap_end - gap_start).total_seconds() / 3600 + 1
                gaps.append({
                    'start': gap_start,
                    'end': gap_end,
                    'duration_h': duration_h,
                    'is_dst': gap_start.month == 3 and gap_start.hour == 2 and duration_h <= 1
                })
                gap_start = ts
                gap_end = ts
        
        duration_h = (gap_end - gap_start).total_seconds() / 3600 + 1
        gaps.append({
            'start': gap_start,
            'end': gap_end,
            'duration_h': duration_h,
            'is_dst': gap_start.month == 3 and gap_start.hour == 2 and duration_h <= 1
        })
    
    yearly_stats = []
    for jahr in sorted(data['Jahr'].unique()):
        jahr_data = data[data['Jahr'] == jahr]
        jahr_start = jahr_data['Datum'].min()
        jahr_end = jahr_data['Datum'].max()
        
        expected = pd.date_range(start=jahr_start, end=jahr_end, freq='h')
        actual = jahr_data['Datum'].unique()
        missing = len(expected) - len(actual)
        
        gap_hours = sum(g['duration_h'] for g in gaps 
                       if g['start'].year == jahr and g['duration_h'] > 1 and not g['is_dst'])
        
        yearly_stats.append({
            'jahr': jahr,
            'start': jahr_start,
            'end': jahr_end,
            'expected': len(expected),
            'actual': len(actual),
            'missing': missing,
            'completeness': 100 * len(actual) / len(expected) if len(expected) > 0 else 0,
            'gap_hours': gap_hours,
            'gap_days': gap_hours / 24
        })
    
    return {
        'gaps': gaps,
        'yearly_stats': yearly_stats,
        'total_missing': len(fehlend)
    }


def main():
    # Header
    st.title("Verkehrsdaten Rosengartenbrücke (OGD)")
    st.markdown("**Stündliche Verkehrszählung nach Fahrzeugtypen** | Datenquelle: [Open Data Zürich](https://data.stadt-zuerich.ch/dataset/ugz_verkehrsdaten_stundenwerte_rosengartenbruecke) | [Sensorpositionen (Karte)](https://s.geo.admin.ch/6cr2y1s13xwp)")
    
    # --- SIDEBAR: Filter ---
    st.sidebar.header("Filter")
    
    # Verfügbare Jahre (2020 bis aktuelles Jahr)
    current_year = datetime.now().year
    available_years = list(range(2020, current_year + 1))
    
    # Jahresfilter - ZUERST wählen, dann laden
    selected_jahre = st.sidebar.multiselect(
        "Jahre",
        options=available_years,
        default=[current_year],
        help="Wählen Sie die Jahre aus, die geladen werden sollen"
    )
    
    if not selected_jahre:
        st.warning("Bitte wählen Sie mindestens ein Jahr aus.")
        return
    
    # Daten nur für ausgewählte Jahre laden
    with st.spinner(f"Daten für {', '.join(map(str, selected_jahre))} werden geladen..."):
        data = load_data_for_years(tuple(sorted(selected_jahre)))
    
    if data is None or data.empty:
        st.error("Keine Daten verfügbar.")
        return
    
    # Richtungsfilter
    richtungen = data['Richtung'].unique().tolist()
    selected_richtungen = st.sidebar.multiselect(
        "Richtung",
        options=richtungen,
        default=richtungen
    )
    
    # Fahrzeugklassen-Filter
    klassen_sorted = data.groupby('Klasse.Text')['Anzahl'].sum().sort_values(ascending=False).index.tolist()
    selected_klassen = st.sidebar.multiselect(
        "Fahrzeugklassen",
        options=klassen_sorted,
        default=klassen_sorted
    )
    
    # Wochentag-Filter
    wochentage = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag']
    wochentag_map = {d: i for i, d in enumerate(wochentage)}
    selected_wochentage = st.sidebar.multiselect(
        "Wochentage",
        options=wochentage,
        default=wochentage
    )
    selected_wochentag_ids = [wochentag_map[w] for w in selected_wochentage]
    
    # Daten filtern
    if not selected_richtungen or not selected_klassen or not selected_wochentage:
        st.warning("Bitte wählen Sie mindestens einen Wert für jeden Filter.")
        return
    
    filtered = data[
        (data['Richtung'].isin(selected_richtungen)) &
        (data['Klasse.Text'].isin(selected_klassen)) &
        (data['Wochentag'].isin(selected_wochentag_ids))
    ]
    
    if filtered.empty:
        st.warning("Keine Daten für die gewählten Filter gefunden.")
        return
    
    # === KPI KACHELN ===
    st.markdown("---")
    col1, col2, col3, col4 = st.columns(4)
    
    total_vehicles = filtered['Anzahl'].sum()
    avg_daily = filtered.groupby('Datum_Tag')['Anzahl'].sum().mean()
    peak_hour_data = filtered.groupby('Stunde')['Anzahl'].sum()
    peak_hour = peak_hour_data.idxmax()
    days_count = filtered['Datum_Tag'].nunique()
    
    with col1:
        st.metric(label="Fahrzeuge gesamt", value=format_number(total_vehicles))
    with col2:
        st.metric(label="Ø Tagesverkehr (DTV)", value=format_number(avg_daily))
    with col3:
        st.metric(label="Spitzenstunde", value=f"{peak_hour}:00 - {peak_hour+1}:00")
    with col4:
        st.metric(label="Tage im Datensatz", value=f"{days_count:,}".replace(',', "'"))
    
    # === LETZTE 7 TAGE: Verlauf Personenwagen, Lastwagen, Lieferwagen ===
    st.markdown("---")
    st.subheader("Letzte 7 Tage: Personenwagen, Lastwagen & Lieferwagen (Stundenwerte)")
    
    # Daten für die letzten 7 Tage (aus Gesamtdaten, unabhängig von Filterung)
    max_datum = data['Datum'].max()
    start_7_tage = max_datum - timedelta(days=7)
    
    data_7_tage = data[
        (data['Datum'] >= start_7_tage) &
        (data['Kategorie'].isin(['Personenwagen', 'Lastwagen', 'Lieferwagen']))
    ]
    
    if not data_7_tage.empty:
        # Aggregieren nach Stunde und Kategorie (stündliche Werte)
        hourly_7_tage = data_7_tage.groupby(['Datum', 'Kategorie'])['Anzahl'].sum().reset_index()
        hourly_7_tage['Anzahl_fmt'] = hourly_7_tage['Anzahl'].apply(lambda x: format_number_ch(x))
        hourly_7_tage['Datum_Label'] = hourly_7_tage['Datum'].dt.strftime('%a %d.%m. %H:%M')
        
        kategorie_farben_7t = {
            'Personenwagen': '#3498db',
            'Lieferwagen': '#2ecc71', 
            'Lastwagen': '#9b59b6'
        }
        
        # Liniendiagramm mit Stundenwerten
        fig_7_tage = px.line(
            hourly_7_tage, 
            x='Datum', 
            y='Anzahl', 
            color='Kategorie',
            labels={'Datum': 'Datum/Zeit', 'Anzahl': 'Fahrzeuge/Stunde', 'Kategorie': 'Kategorie'},
            color_discrete_map=kategorie_farben_7t,
            custom_data=['Anzahl_fmt', 'Kategorie', 'Datum_Label']
        )
        fig_7_tage.update_traces(
            hovertemplate='%{customdata[2]}<br>%{customdata[1]}: %{customdata[0]}<extra></extra>',
            line=dict(width=2)
        )
        fig_7_tage.update_layout(
            hovermode='x unified',
            xaxis=dict(
                tickformat='%a %d.%m.',
                dtick='D1'
            ),
            legend=dict(
                orientation='h',
                yanchor='bottom',
                y=1.02,
                xanchor='left',
                x=0
            ),
            height=400
        )
        
        col_chart, col_stats = st.columns([3, 1])
        
        with col_chart:
            st.plotly_chart(fig_7_tage, use_container_width=True)
        
        with col_stats:
            # Statistiken für die letzten 7 Tage
            st.markdown("**Ø pro Stunde (7 Tage)**")
            for kategorie in ['Personenwagen', 'Lieferwagen', 'Lastwagen']:
                kat_data = hourly_7_tage[hourly_7_tage['Kategorie'] == kategorie]
                if not kat_data.empty:
                    avg_val = kat_data['Anzahl'].mean()
                    color = kategorie_farben_7t[kategorie]
                    st.markdown(f"<span style='color:{color};font-weight:bold;'>{kategorie}:</span> {format_number(avg_val)}", 
                               unsafe_allow_html=True)
            
            st.markdown("---")
            st.markdown("**Ø pro Tag (7 Tage)**")
            daily_totals = data_7_tage.groupby(['Datum_Tag', 'Kategorie'])['Anzahl'].sum().reset_index()
            for kategorie in ['Personenwagen', 'Lieferwagen', 'Lastwagen']:
                kat_data = daily_totals[daily_totals['Kategorie'] == kategorie]
                if not kat_data.empty:
                    avg_val = kat_data['Anzahl'].mean()
                    color = kategorie_farben_7t[kategorie]
                    st.markdown(f"<span style='color:{color};font-weight:bold;'>{kategorie}:</span> {format_number(avg_val)}", 
                               unsafe_allow_html=True)
            
            st.markdown("---")
            st.markdown("**Zeitraum**")
            st.caption(f"{start_7_tage.strftime('%d.%m.%Y')} – {max_datum.strftime('%d.%m.%Y')}")
    else:
        st.info("Keine Daten für die letzten 7 Tage verfügbar.")
    
    # === CHARTS ===
    st.markdown("---")
    
    # Zeile 1a: Tagesverlauf und Wochenverlauf nach Richtung
    st.subheader("Tages- und Wochenverlauf nach Richtung")
    col_left, col_right = st.columns(2)
    
    with col_left:
        # Tagesverlauf nach Richtung
        hourly_dir = filtered.groupby(['Richtung', 'Stunde'])['Anzahl'].mean().reset_index()
        hourly_dir['Anzahl_fmt'] = hourly_dir['Anzahl'].apply(lambda x: format_number_ch(x))
        fig_hourly_dir = px.line(
            hourly_dir, x='Stunde', y='Anzahl', color='Richtung',
            labels={'Stunde': 'Uhrzeit', 'Anzahl': 'Ø Fahrzeuge/Stunde', 'Richtung': 'Richtung'},
            markers=True, color_discrete_sequence=['#3498db', '#e74c3c'],
            custom_data=['Anzahl_fmt']
        )
        fig_hourly_dir.update_traces(hovertemplate='%{customdata[0]}<extra></extra>')
        fig_hourly_dir.update_layout(xaxis=dict(tickmode='linear', tick0=0, dtick=2), hovermode='x unified', title='Tagesverlauf')
        st.plotly_chart(fig_hourly_dir, use_container_width=True)
    
    with col_right:
        # Wochenverlauf nach Richtung
        daily_totals_dir = filtered.groupby(['Datum_Tag', 'Wochentag', 'Richtung'])['Anzahl'].sum().reset_index()
        weekly_dir = daily_totals_dir.groupby(['Richtung', 'Wochentag'])['Anzahl'].mean().reset_index()
        weekly_dir['Wochentag_Name'] = weekly_dir['Wochentag'].map({i: d for i, d in enumerate(['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'])})
        weekly_dir['Anzahl_fmt'] = weekly_dir['Anzahl'].apply(lambda x: format_number_ch(x))
        fig_weekly_dir = px.bar(
            weekly_dir, x='Wochentag_Name', y='Anzahl', color='Richtung', barmode='group',
            labels={'Wochentag_Name': 'Wochentag', 'Anzahl': 'Ø Fahrzeuge/Tag', 'Richtung': 'Richtung'},
            category_orders={'Wochentag_Name': ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']},
            color_discrete_sequence=['#3498db', '#e74c3c'], custom_data=['Anzahl_fmt']
        )
        fig_weekly_dir.update_traces(hovertemplate='%{customdata[0]}<extra></extra>')
        fig_weekly_dir.update_layout(title='Wochenverlauf')
        st.plotly_chart(fig_weekly_dir, use_container_width=True)
    
    # Zeile 1b: Tagesverlauf und Wochenverlauf nach Jahr
    if len(selected_jahre) > 1:
        st.subheader("Tages- und Wochenverlauf nach Jahr")
        col_left_yr, col_right_yr = st.columns(2)
        
        with col_left_yr:
            hourly_yr = filtered.groupby(['Jahr', 'Stunde'])['Anzahl'].mean().reset_index()
            hourly_yr['Anzahl_fmt'] = hourly_yr['Anzahl'].apply(lambda x: format_number_ch(x))
            fig_hourly_yr = px.line(
                hourly_yr, x='Stunde', y='Anzahl', color='Jahr',
                labels={'Stunde': 'Uhrzeit', 'Anzahl': 'Ø Fahrzeuge/Stunde', 'Jahr': 'Jahr'},
                markers=True, custom_data=['Anzahl_fmt']
            )
            fig_hourly_yr.update_traces(hovertemplate='%{customdata[0]}<extra></extra>')
            fig_hourly_yr.update_layout(xaxis=dict(tickmode='linear', tick0=0, dtick=2), hovermode='x unified', title='Tagesverlauf')
            st.plotly_chart(fig_hourly_yr, use_container_width=True)
        
        with col_right_yr:
            daily_totals_yr = filtered.groupby(['Datum_Tag', 'Wochentag', 'Jahr'])['Anzahl'].sum().reset_index()
            weekly_yr = daily_totals_yr.groupby(['Jahr', 'Wochentag'])['Anzahl'].mean().reset_index()
            weekly_yr['Wochentag_Name'] = weekly_yr['Wochentag'].map({i: d for i, d in enumerate(['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'])})
            weekly_yr['Anzahl_fmt'] = weekly_yr['Anzahl'].apply(lambda x: format_number_ch(x))
            weekly_yr['Jahr'] = weekly_yr['Jahr'].astype(str)  # Als String für diskrete Farben
            fig_weekly_yr = px.bar(
                weekly_yr, x='Wochentag_Name', y='Anzahl', color='Jahr', barmode='group',
                labels={'Wochentag_Name': 'Wochentag', 'Anzahl': 'Ø Fahrzeuge/Tag', 'Jahr': 'Jahr'},
                category_orders={'Wochentag_Name': ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']},
                custom_data=['Anzahl_fmt']
            )
            fig_weekly_yr.update_traces(hovertemplate='%{customdata[0]}<extra></extra>')
            fig_weekly_yr.update_layout(title='Wochenverlauf')
            st.plotly_chart(fig_weekly_yr, use_container_width=True)
    
    # === TAGESVERLAUF PRO WOCHENTAG ===
    st.markdown("---")
    st.subheader("Tagesverlauf pro Wochentag (Gesamtzeitraum)")
    st.caption("Durchschnittlicher Stundenverlauf für jeden Wochentag über alle ausgewählten Jahre")
    
    wochentag_namen_full = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag']
    
    # Erste Reihe: Mo-Do
    col_mo, col_di, col_mi, col_do = st.columns(4)
    wochentag_cols_row1 = [col_mo, col_di, col_mi, col_do]
    
    for idx, col in enumerate(wochentag_cols_row1):
        with col:
            wt_data = filtered[filtered['Wochentag'] == idx]
            if not wt_data.empty:
                hourly_wt_avg = wt_data.groupby('Stunde')['Anzahl'].mean().reset_index()
                hourly_wt_avg['Anzahl_fmt'] = hourly_wt_avg['Anzahl'].apply(lambda x: format_number_ch(x))
                fig_wt = px.line(hourly_wt_avg, x='Stunde', y='Anzahl', markers=True,
                                 color_discrete_sequence=['#2c3e50'], custom_data=['Anzahl_fmt'])
                fig_wt.update_traces(hovertemplate='%{customdata[0]}<extra></extra>')
                fig_wt.update_layout(
                    title=dict(text=wochentag_namen_full[idx], font=dict(size=14)),
                    xaxis=dict(tickmode='linear', tick0=0, dtick=4, title=''),
                    yaxis=dict(title='Ø Fz/h'), height=250,
                    margin=dict(l=40, r=20, t=40, b=30), hovermode='x unified'
                )
                st.plotly_chart(fig_wt, use_container_width=True)
            else:
                st.info(f"Keine Daten für {wochentag_namen_full[idx]}")
    
    # Zweite Reihe: Fr-So + Vergleich
    col_fr, col_sa, col_so, col_empty = st.columns(4)
    wochentag_cols_row2 = [(4, col_fr), (5, col_sa), (6, col_so)]
    
    for idx, col in wochentag_cols_row2:
        with col:
            wt_data = filtered[filtered['Wochentag'] == idx]
            if not wt_data.empty:
                hourly_wt_avg = wt_data.groupby('Stunde')['Anzahl'].mean().reset_index()
                hourly_wt_avg['Anzahl_fmt'] = hourly_wt_avg['Anzahl'].apply(lambda x: format_number_ch(x))
                fig_wt = px.line(hourly_wt_avg, x='Stunde', y='Anzahl', markers=True,
                                 color_discrete_sequence=['#2c3e50'], custom_data=['Anzahl_fmt'])
                fig_wt.update_traces(hovertemplate='%{customdata[0]}<extra></extra>')
                fig_wt.update_layout(
                    title=dict(text=wochentag_namen_full[idx], font=dict(size=14)),
                    xaxis=dict(tickmode='linear', tick0=0, dtick=4, title=''),
                    yaxis=dict(title='Ø Fz/h'), height=250,
                    margin=dict(l=40, r=20, t=40, b=30), hovermode='x unified'
                )
                st.plotly_chart(fig_wt, use_container_width=True)
            else:
                st.info(f"Keine Daten für {wochentag_namen_full[idx]}")
    
    # Vergleichsdiagramm
    with col_empty:
        st.markdown("**Vergleich**")
        hourly_all_wt_avg = filtered.groupby(['Wochentag', 'Stunde'])['Anzahl'].mean().reset_index()
        hourly_all_wt_avg['Wochentag_Name'] = hourly_all_wt_avg['Wochentag'].map(
            {i: d for i, d in enumerate(['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'])}
        )
        hourly_all_wt_avg['Anzahl_fmt'] = hourly_all_wt_avg['Anzahl'].apply(lambda x: format_number_ch(x))
        fig_compare = px.line(
            hourly_all_wt_avg, x='Stunde', y='Anzahl', color='Wochentag_Name',
            category_orders={'Wochentag_Name': ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']},
            custom_data=['Anzahl_fmt', 'Wochentag_Name']
        )
        fig_compare.update_traces(hovertemplate='%{customdata[1]}: %{customdata[0]}<extra></extra>')
        fig_compare.update_layout(
            title=dict(text='Alle Wochentage', font=dict(size=14)),
            xaxis=dict(tickmode='linear', tick0=0, dtick=4, title=''),
            yaxis=dict(title='Ø Fz/h'), height=250,
            margin=dict(l=40, r=20, t=40, b=30), hovermode='x unified',
            legend=dict(font=dict(size=9), orientation='h', yanchor='bottom', y=-0.4, xanchor='center', x=0.5)
        )
        st.plotly_chart(fig_compare, use_container_width=True)
    
    # Zeile 2: Fahrzeugklassen und Richtungen
    col_left2, col_right2 = st.columns(2)
    
    with col_left2:
        st.subheader("Fahrzeugklassen (%)")
        tab_detail, tab_kategorie = st.tabs(["Detailliert", "Kategorien"])
        
        with tab_detail:
            by_class = filtered.groupby('Klasse.Text')['Anzahl'].sum().reset_index()
            total = by_class['Anzahl'].sum()
            by_class['Prozent'] = (by_class['Anzahl'] / total * 100).round(1)
            by_class = by_class.sort_values('Prozent', ascending=True)
            by_class['Prozent_fmt'] = by_class['Prozent'].apply(lambda x: f"{x:.1f}%")
            by_class['Anzahl_fmt'] = by_class['Anzahl'].apply(lambda x: format_number_ch(x))
            fig_classes = px.bar(
                by_class, x='Prozent', y='Klasse.Text', orientation='h',
                labels={'Klasse.Text': '', 'Prozent': 'Anteil (%)'},
                color='Klasse.Text', color_discrete_map=FARBEN, text='Prozent',
                custom_data=['Prozent_fmt', 'Anzahl_fmt']
            )
            fig_classes.update_traces(texttemplate='%{text:.1f}%', textposition='outside',
                                       hovertemplate='%{y}: %{customdata[0]} (%{customdata[1]} Fz.)<extra></extra>')
            fig_classes.update_layout(showlegend=False, xaxis=dict(range=[0, 100]))
            st.plotly_chart(fig_classes, use_container_width=True)
        
        with tab_kategorie:
            kategorie_farben = {
                'Personenwagen': '#3498db', 'Lieferwagen': '#2ecc71', 'Motorrad': '#e74c3c',
                'Lastwagen': '#9b59b6', 'Bus/Trolleybus': '#f39c12', 'Unbekannt': '#95a5a6'
            }
            by_kategorie = filtered.groupby('Kategorie')['Anzahl'].sum().reset_index()
            total_kat = by_kategorie['Anzahl'].sum()
            by_kategorie['Prozent'] = (by_kategorie['Anzahl'] / total_kat * 100).round(1)
            by_kategorie = by_kategorie.sort_values('Prozent', ascending=True)
            by_kategorie['Prozent_fmt'] = by_kategorie['Prozent'].apply(lambda x: f"{x:.1f}%")
            by_kategorie['Anzahl_fmt'] = by_kategorie['Anzahl'].apply(lambda x: format_number_ch(x))
            fig_kategorien = px.bar(
                by_kategorie, x='Prozent', y='Kategorie', orientation='h',
                labels={'Kategorie': '', 'Prozent': 'Anteil (%)'},
                color='Kategorie', color_discrete_map=kategorie_farben, text='Prozent',
                custom_data=['Prozent_fmt', 'Anzahl_fmt']
            )
            fig_kategorien.update_traces(texttemplate='%{text:.1f}%', textposition='outside',
                                          hovertemplate='%{y}: %{customdata[0]} (%{customdata[1]} Fz.)<extra></extra>')
            fig_kategorien.update_layout(showlegend=False, xaxis=dict(range=[0, 100]))
            st.plotly_chart(fig_kategorien, use_container_width=True)
    
    with col_right2:
        st.subheader("↔️ Richtungsvergleich")
        by_direction = filtered.groupby('Richtung')['Anzahl'].sum().reset_index()
        by_direction['Anzahl_fmt'] = by_direction['Anzahl'].apply(lambda x: format_number_ch(x))
        by_direction['Prozent'] = (by_direction['Anzahl'] / by_direction['Anzahl'].sum() * 100).round(1)
        fig_direction = px.pie(
            by_direction, values='Anzahl', names='Richtung', hole=0.4,
            color_discrete_sequence=['#3498db', '#e74c3c'],
            custom_data=['Anzahl_fmt', 'Prozent']
        )
        fig_direction.update_traces(textposition='inside', textinfo='percent+label',
                                     hovertemplate='%{label}: %{customdata[0]} (%{customdata[1]:.1f}%)<extra></extra>')
        st.plotly_chart(fig_direction, use_container_width=True)
    
    # Zeile 2b: Fahrzeugkategorien im Zeitverlauf
    if len(selected_jahre) > 1:
        st.markdown("---")
        st.subheader("Fahrzeugkategorien im Jahresverlauf (%)")
        
        kategorie_farben_verlauf = {
            'Personenwagen': '#3498db', 'Lieferwagen': '#2ecc71', 'Motorrad': '#e74c3c',
            'Lastwagen': '#9b59b6', 'Bus/Trolleybus': '#f39c12', 'Unbekannt': '#95a5a6'
        }
        
        yearly_by_cat = filtered.groupby(['Jahr', 'Kategorie'])['Anzahl'].sum().reset_index()
        yearly_totals = yearly_by_cat.groupby('Jahr')['Anzahl'].sum().reset_index()
        yearly_totals.columns = ['Jahr', 'Total']
        yearly_by_cat = yearly_by_cat.merge(yearly_totals, on='Jahr')
        yearly_by_cat['Prozent'] = (yearly_by_cat['Anzahl'] / yearly_by_cat['Total'] * 100).round(2)
        yearly_by_cat['Prozent_fmt'] = yearly_by_cat['Prozent'].apply(lambda x: f"{x:.1f}%")
        yearly_by_cat['Anzahl_fmt'] = yearly_by_cat['Anzahl'].apply(lambda x: format_number_ch(x))
        
        cat_order = yearly_by_cat.groupby('Kategorie')['Prozent'].mean().sort_values(ascending=False).index.tolist()
        
        fig_cat_trend = make_subplots(specs=[[{"secondary_y": True}]])
        
        for kategorie in cat_order:
            df_kat = yearly_by_cat[yearly_by_cat['Kategorie'] == kategorie]
            is_pw = kategorie == 'Personenwagen'
            fig_cat_trend.add_trace(
                go.Scatter(
                    x=df_kat['Jahr'], y=df_kat['Prozent'], name=kategorie,
                    mode='lines+markers',
                    line=dict(color=kategorie_farben_verlauf.get(kategorie, '#666'), width=3 if is_pw else 2),
                    marker=dict(size=10 if is_pw else 6),
                    customdata=df_kat[['Prozent_fmt', 'Anzahl_fmt', 'Kategorie']].values,
                    hovertemplate='%{customdata[2]}: %{customdata[0]} (%{customdata[1]} Fz.)<extra></extra>'
                ),
                secondary_y=is_pw
            )
        
        fig_cat_trend.update_layout(xaxis=dict(tickmode='linear', dtick=1), hovermode='x unified',
                                     legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0))
        fig_cat_trend.update_yaxes(title_text="Anteil andere Kategorien (%)", secondary_y=False, range=[0, 15])
        fig_cat_trend.update_yaxes(title_text="Anteil Personenwagen (%)", secondary_y=True, range=[80, 95])
        
        fig_cat_area = px.area(
            yearly_by_cat, x='Jahr', y='Prozent', color='Kategorie',
            labels={'Jahr': '', 'Prozent': 'Anteil (%)', 'Kategorie': 'Kategorie'},
            color_discrete_map=kategorie_farben_verlauf, category_orders={'Kategorie': cat_order},
            custom_data=['Prozent_fmt', 'Kategorie']
        )
        fig_cat_area.update_traces(hovertemplate='%{customdata[1]}: %{customdata[0]}<extra></extra>')
        fig_cat_area.update_layout(xaxis=dict(tickmode='linear', dtick=1), yaxis=dict(range=[0, 100]),
                                    hovermode='x unified',
                                    legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0))
        
        tab_line, tab_area = st.tabs(["Liniendiagramm", "Flächendiagramm"])
        with tab_line:
            st.plotly_chart(fig_cat_trend, use_container_width=True, key="cat_line")
        with tab_area:
            st.plotly_chart(fig_cat_area, use_container_width=True, key="cat_area")
    
    # Zeile 3: Monatstrend
    st.markdown("---")
    st.subheader("Monatlicher Verkehrstrend (Ø Tagesverkehr)")
    
    import calendar
    daily_totals_monthly = filtered.groupby(['Jahr', 'Monat', 'Datum_Tag', 'Richtung'])['Anzahl'].sum().reset_index()
    monthly_stats = daily_totals_monthly.groupby(['Jahr', 'Monat', 'Richtung']).agg(
        Anzahl=('Anzahl', 'mean'), Tage=('Datum_Tag', 'nunique')
    ).reset_index()
    monthly_stats['Erwartete_Tage'] = monthly_stats.apply(
        lambda row: calendar.monthrange(int(row['Jahr']), int(row['Monat']))[1], axis=1
    )
    monthly_stats['Abdeckung'] = monthly_stats['Tage'] / monthly_stats['Erwartete_Tage']
    monthly = monthly_stats[monthly_stats['Abdeckung'] >= 0.9].copy()
    monthly['Datum'] = pd.to_datetime(monthly['Jahr'].astype(str) + '-' + monthly['Monat'].astype(str) + '-15')
    monthly['Anzahl_fmt'] = monthly['Anzahl'].apply(lambda x: format_number_ch(x))
    
    fig_trend = px.bar(
        monthly, x='Datum', y='Anzahl', color='Richtung', barmode='group',
        labels={'Datum': '', 'Anzahl': 'Ø Fahrzeuge/Tag', 'Richtung': 'Richtung'},
        color_discrete_sequence=['#3498db', '#e74c3c'], custom_data=['Anzahl_fmt']
    )
    fig_trend.update_traces(hovertemplate='%{customdata[0]}<extra></extra>')
    
    shapes, annotations = [], []
    jahre_im_datensatz = monthly['Jahr'].unique()
    
    if 2020 in jahre_im_datensatz:
        shapes.append(dict(type="rect", xref="x", yref="paper", x0="2020-03-01", x1="2020-06-01",
                           y0=0, y1=1, fillcolor="rgba(255, 0, 0, 0.1)", line=dict(width=0), layer="below"))
        annotations.append(dict(x="2020-04-15", y=1.02, xref="x", yref="paper", text="Lockdown",
                                showarrow=False, font=dict(size=10, color="#e74c3c"), bgcolor="rgba(255,255,255,0.8)"))
    
    for jahr in jahre_im_datensatz:
        shapes.append(dict(type="rect", xref="x", yref="paper", x0=f"{jahr}-07-01", x1=f"{jahr}-09-01",
                           y0=0, y1=1, fillcolor="rgba(255, 193, 7, 0.1)", line=dict(width=0), layer="below"))
    
    if len(jahre_im_datensatz) > 0:
        first_year = min(jahre_im_datensatz)
        annotations.append(dict(x=f"{first_year}-08-01", y=1.02, xref="x", yref="paper", text="Sommerferien",
                                showarrow=False, font=dict(size=10, color="#f39c12"), bgcolor="rgba(255,255,255,0.8)"))
    
    for jahr in sorted(jahre_im_datensatz)[1:]:
        shapes.append(dict(type="line", xref="x", yref="paper", x0=f"{jahr}-01-01", x1=f"{jahr}-01-01",
                           y0=0, y1=1, line=dict(color="rgba(0,0,0,0.3)", width=1, dash="dash")))
    
    fig_trend.update_layout(hovermode='x unified', bargap=0.1, shapes=shapes, annotations=annotations, margin=dict(t=40))
    st.plotly_chart(fig_trend, use_container_width=True)
    st.caption("Rot = COVID-19 Lockdown (März-Mai 2020) | Gelb = Sommerferien Zürich (Juli/August)")
    
    # Zeile 3b: Jahresverlauf (Wochenschnitt)
    st.markdown("---")
    st.subheader("Jahresverlauf (Wochendurchschnitt)")
    
    daily_totals_weekly = filtered.groupby(['Jahr', 'Kalenderwoche', 'Datum_Tag'])['Anzahl'].sum().reset_index()
    
    kw53_data = daily_totals_weekly[daily_totals_weekly['Kalenderwoche'] == 53].copy()
    if not kw53_data.empty:
        kw53_data['Jahr'] = kw53_data['Jahr'] + 1
        kw53_data['Kalenderwoche'] = 1
        daily_totals_weekly = pd.concat([daily_totals_weekly, kw53_data], ignore_index=True)
    
    daily_totals_weekly = daily_totals_weekly[daily_totals_weekly['Kalenderwoche'] <= 52]
    
    weekly_stats_kw = daily_totals_weekly.groupby(['Jahr', 'Kalenderwoche']).agg(
        Anzahl=('Anzahl', 'mean'), Tage=('Datum_Tag', 'nunique')
    ).reset_index()
    weekly_stats_kw.loc[weekly_stats_kw['Tage'] < 5, 'Anzahl'] = np.nan
    weekly_stats_kw.loc[(weekly_stats_kw['Jahr'] == 2020) & (weekly_stats_kw['Kalenderwoche'] < 4), 'Anzahl'] = np.nan
    
    weekly_avg = weekly_stats_kw[['Jahr', 'Kalenderwoche', 'Anzahl']].copy()
    weekly_avg['Anzahl_fmt'] = weekly_avg['Anzahl'].apply(lambda x: format_number_ch(x) if pd.notna(x) else '–')
    weekly_avg['Jahr'] = weekly_avg['Jahr'].astype(str)
    
    fig_weekly = px.line(
        weekly_avg, x='Kalenderwoche', y='Anzahl', color='Jahr',
        labels={'Kalenderwoche': 'Kalenderwoche', 'Anzahl': 'Ø Fahrzeuge/Tag', 'Jahr': 'Jahr'},
        markers=True, custom_data=['Anzahl_fmt', 'Jahr']
    )
    fig_weekly.update_traces(hovertemplate='KW %{x}: %{customdata[0]}<extra>%{customdata[1]}</extra>', connectgaps=False)
    
    weekly_shapes = []
    weekly_annotations = []
    
    if '2020' in weekly_avg['Jahr'].values:
        weekly_shapes.append(dict(type="rect", xref="x", yref="paper", x0=11, x1=20,
                                  y0=0, y1=1, fillcolor="rgba(255, 0, 0, 0.1)", line=dict(width=0), layer="below"))
        weekly_annotations.append(dict(x=15, y=1.02, xref="x", yref="paper", text="Lockdown",
                                       showarrow=False, font=dict(size=10, color="#e74c3c"), bgcolor="rgba(255,255,255,0.8)"))
    
    weekly_shapes.append(dict(type="rect", xref="x", yref="paper", x0=28, x1=33,
                              y0=0, y1=1, fillcolor="rgba(255, 193, 7, 0.1)", line=dict(width=0), layer="below"))
    weekly_annotations.append(dict(x=30.5, y=1.02, xref="x", yref="paper", text="Ferien",
                                   showarrow=False, font=dict(size=10, color="#f39c12"), bgcolor="rgba(255,255,255,0.8)"))
    
    weekly_shapes.extend([
        dict(type="rect", xref="x", yref="paper", x0=51, x1=52.5, y0=0, y1=1,
             fillcolor="rgba(76, 175, 80, 0.1)", line=dict(width=0), layer="below"),
        dict(type="rect", xref="x", yref="paper", x0=0.5, x1=2, y0=0, y1=1,
             fillcolor="rgba(76, 175, 80, 0.1)", line=dict(width=0), layer="below")
    ])
    weekly_annotations.append(dict(x=52, y=1.02, xref="x", yref="paper", text="",
                                   showarrow=False, font=dict(size=10), bgcolor="rgba(255,255,255,0.8)"))
    
    fig_weekly.update_layout(xaxis=dict(tickmode='linear', tick0=1, dtick=4, range=[0.5, 52.5]),
                              hovermode='x unified', shapes=weekly_shapes, annotations=weekly_annotations, margin=dict(t=40))
    st.plotly_chart(fig_weekly, use_container_width=True)
    st.caption("Rot = COVID-19 Lockdown (KW 12-20, 2020) | Gelb = Sommerferien (KW 28-33) |  Grün = Weihnachten/Neujahr")
    
    # Zeile 4: Heatmap
    st.markdown("---")
    st.subheader("🗓️ Verkehrsmuster: Stunde × Wochentag")
    
    wochentag_labels = {0: 'Mo', 1: 'Di', 2: 'Mi', 3: 'Do', 4: 'Fr', 5: 'Sa', 6: 'So'}
    heatmap_data = filtered.groupby(['Wochentag', 'Stunde'])['Anzahl'].mean().reset_index()
    
    daily_totals_wt = filtered.groupby(['Datum_Tag', 'Wochentag'])['Anzahl'].sum().reset_index()
    avg_daily_by_wt = daily_totals_wt.groupby('Wochentag')['Anzahl'].mean().round(0).astype(int)
    wochentag_labels_mit_summe = {
        i: f"{wochentag_labels[i]} (Ø {avg_daily_by_wt.get(i, 0):,}/Tag)".replace(',', "'") for i in range(7)
    }
    
    all_combinations = pd.MultiIndex.from_product([range(7), range(24)], names=['Wochentag', 'Stunde']).to_frame(index=False)
    heatmap_complete = all_combinations.merge(heatmap_data, on=['Wochentag', 'Stunde'], how='left')
    heatmap_complete['Anzahl'] = heatmap_complete['Anzahl'].fillna(0)
    heatmap_pivot = heatmap_complete.pivot(index='Wochentag', columns='Stunde', values='Anzahl')
    heatmap_pivot.index = [wochentag_labels_mit_summe[i] for i in heatmap_pivot.index]
    heatmap_hover = heatmap_pivot.map(lambda x: f"Ø {format_number_ch(x)} Fz./h")
    
    fig_heatmap = px.imshow(
        heatmap_pivot, labels=dict(x="Stunde", y="Wochentag", color="Ø Fahrzeuge/h"),
        aspect="auto", color_continuous_scale="YlOrRd"
    )
    fig_heatmap.update_traces(hovertemplate='%{y}<br>%{x}:00 Uhr<br>%{customdata}<extra></extra>',
                               customdata=heatmap_hover.values)
    fig_heatmap.update_layout(height=350)
    st.plotly_chart(fig_heatmap, use_container_width=True)
    
    # Zeile 5: Jahresvergleich
    if len(selected_jahre) > 1:
        st.markdown("---")
        st.subheader("Jahresvergleich (Ø Tagesverkehr)")
        
        gap_analysis = analyze_data_gaps(data)
        
        daily_by_year_total = filtered.groupby(['Jahr', 'Datum_Tag'])['Anzahl'].sum().reset_index()
        yearly_total = daily_by_year_total.groupby('Jahr')['Anzahl'].mean().reset_index()
        
        yearly_corrected = []
        for _, row in yearly_total.iterrows():
            jahr = row['Jahr']
            avg_dtv = row['Anzahl']
            days_with_data = daily_by_year_total[daily_by_year_total['Jahr'] == jahr]['Datum_Tag'].nunique()
            year_stat = next((s for s in gap_analysis['yearly_stats'] if s['jahr'] == jahr), None)
            gap_days = year_stat['gap_days'] if year_stat else 0
            vollst = year_stat['completeness'] if year_stat else 100
            yearly_corrected.append({
                'Jahr': jahr, 'DTV': avg_dtv, 'Tage_Daten': days_with_data,
                'Tage_Lücken': gap_days, 'Vollständigkeit': vollst
            })
        
        cols_yearly = st.columns(len(selected_jahre))
        for i, jahr in enumerate(sorted(selected_jahre)):
            with cols_yearly[i]:
                corr_data = next((c for c in yearly_corrected if c['Jahr'] == jahr), None)
                if corr_data:
                    formatted_val = format_number(corr_data['DTV'])
                    gap_days = corr_data['Tage_Lücken']
                    vollst = corr_data['Vollständigkeit']
                    if gap_days > 1:
                        st.metric(label=f"{jahr}", value=formatted_val,
                                  help=f"Ø Fahrzeuge/Tag | Vollständigkeit: {vollst:.1f}% | {gap_days:.0f} Tage fehlen")
                        st.caption(f"⚠️ {gap_days:.0f} Tage fehlen")
                    else:
                        st.metric(label=f"{jahr}", value=formatted_val,
                                  help=f"Ø Fahrzeuge/Tag | Vollständigkeit: {vollst:.1f}%")
        
        years_with_gaps = [c for c in yearly_corrected if c['Tage_Lücken'] > 7]
        if years_with_gaps:
            st.info("ℹ️ **Hinweis:** Einige Jahre haben grössere Datenlücken. "
                    "Der Ø Tagesverkehr (DTV) basiert nur auf den verfügbaren Tagen.")
        
        daily_by_year = filtered.groupby(['Jahr', 'Datum_Tag', 'Richtung'])['Anzahl'].sum().reset_index()
        yearly = daily_by_year.groupby(['Jahr', 'Richtung'])['Anzahl'].mean().reset_index()
        yearly['Anzahl_fmt'] = yearly['Anzahl'].apply(lambda x: format_number_ch(x))
        
        tab_dtv, tab_total = st.tabs(["Ø Tagesverkehr (DTV)", "Gesamtanzahl"])
        
        with tab_dtv:
            fig_yearly = px.bar(
                yearly, x='Jahr', y='Anzahl', color='Richtung', barmode='group',
                labels={'Jahr': '', 'Anzahl': 'Ø Fahrzeuge/Tag', 'Richtung': 'Richtung'},
                text='Anzahl_fmt', color_discrete_sequence=['#3498db', '#e74c3c'], custom_data=['Anzahl_fmt']
            )
            fig_yearly.update_traces(textposition='outside', hovertemplate='%{customdata[0]}<extra></extra>')
            st.plotly_chart(fig_yearly, use_container_width=True)
        
        with tab_total:
            yearly_sum = filtered.groupby(['Jahr', 'Richtung'])['Anzahl'].sum().reset_index()
            yearly_sum['Anzahl_fmt'] = yearly_sum['Anzahl'].apply(lambda x: format_number_ch(x))
            yearly_total_sum = filtered.groupby('Jahr')['Anzahl'].sum().reset_index()
            
            cols_total = st.columns(len(selected_jahre))
            for i, jahr in enumerate(sorted(selected_jahre)):
                with cols_total[i]:
                    corr_data = next((c for c in yearly_corrected if c['Jahr'] == jahr), None)
                    total_val = yearly_total_sum[yearly_total_sum['Jahr'] == jahr]['Anzahl'].values
                    if len(total_val) > 0 and corr_data:
                        formatted_total = format_number(total_val[0])
                        gap_days = corr_data['Tage_Lücken']
                        tage_daten = corr_data['Tage_Daten']
                        if gap_days > 1:
                            schaetzung = total_val[0] * (365 / tage_daten) if tage_daten > 0 else total_val[0]
                            st.metric(label=f"{jahr}", value=formatted_total,
                                      help=f"Gemessene Fahrzeuge | {tage_daten} Tage mit Daten")
                            st.caption(f"Hochrechnung: ~{format_number(schaetzung)}")
                        else:
                            st.metric(label=f"{jahr}", value=formatted_total,
                                      help=f"Gemessene Fahrzeuge | {tage_daten} Tage mit Daten")
            
            fig_yearly_sum = px.bar(
                yearly_sum, x='Jahr', y='Anzahl', color='Richtung', barmode='group',
                labels={'Jahr': '', 'Anzahl': 'Fahrzeuge gesamt', 'Richtung': 'Richtung'},
                text='Anzahl_fmt', color_discrete_sequence=['#3498db', '#e74c3c'], custom_data=['Anzahl_fmt']
            )
            fig_yearly_sum.update_traces(textposition='outside', hovertemplate='%{customdata[0]}<extra></extra>')
            st.plotly_chart(fig_yearly_sum, use_container_width=True)
            st.caption("💡 **Hinweis:** Die Gesamtzahlen sind bei Datenlücken nicht direkt vergleichbar.")
    
    # Zeile 6: Datenqualität
    st.markdown("---")
    st.subheader("⚠️ Datenqualität & Lücken")
    
    gap_analysis = analyze_data_gaps(data)
    significant_gaps = [g for g in gap_analysis['gaps'] if g['duration_h'] > 1 and not g['is_dst']]
    total_gap_hours = sum(g['duration_h'] for g in significant_gaps)
    
    col_gap1, col_gap2, col_gap3 = st.columns(3)
    with col_gap1:
        st.metric("Datenlücken (>1h)", f"{len(significant_gaps)}")
    with col_gap2:
        st.metric("Fehlende Stunden", format_number(total_gap_hours))
    with col_gap3:
        st.metric("Fehlende Tage", f"{total_gap_hours/24:.1f}")
    
    tab_gaps, tab_yearly = st.tabs(["Datenlücken", "Vollständigkeit pro Jahr"])
    
    with tab_gaps:
        if significant_gaps:
            gap_df = pd.DataFrame([{
                'Von': g['start'].strftime('%d.%m.%Y %H:%M'),
                'Bis': g['end'].strftime('%d.%m.%Y %H:%M'),
                'Dauer': f"{g['duration_h']:.1f}h" if g['duration_h'] < 24 else f"{g['duration_h']/24:.1f} Tage",
                'Jahr': g['start'].year
            } for g in significant_gaps])
            st.dataframe(gap_df, use_container_width=True, hide_index=True)
        else:
            st.success("Keine signifikanten Datenlücken gefunden.")
        
        dst_gaps = [g for g in gap_analysis['gaps'] if g['is_dst']]
        if dst_gaps:
            st.info(f"ℹ️ {len(dst_gaps)} Lücken durch Zeitumstellung (Sommerzeit) – diese sind normal.")
    
    with tab_yearly:
        yearly_df = pd.DataFrame([{
            'Jahr': s['jahr'],
            'Zeitraum': f"{s['start'].strftime('%d.%m.')} – {s['end'].strftime('%d.%m.')}",
            'Vollständigkeit': f"{s['completeness']:.1f}%",
            'Fehlende Tage': f"{s['gap_days']:.1f}" if s['gap_days'] > 0 else "–"
        } for s in gap_analysis['yearly_stats']])
        st.dataframe(yearly_df, use_container_width=True, hide_index=True)
        
        if significant_gaps:
            biggest = max(significant_gaps, key=lambda x: x['duration_h'])
            st.warning(f"⚠️ Grösste Datenlücke: **{biggest['start'].strftime('%d.%m.%Y')} – "
                       f"{biggest['end'].strftime('%d.%m.%Y')}** ({biggest['duration_h']/24:.0f} Tage)")
    
    # Footer
    st.markdown("---")
    st.caption(
        f"Datenquelle: [Open Data Zürich](https://data.stadt-zuerich.ch/dataset/ugz_verkehrsdaten_stundenwerte_rosengartenbruecke) | "
        f"Standort: Rosengartenstrasse 18, 8037 Zürich | "
        f"Intervall: 1 Stunde | "
        f"Letzte Aktualisierung: {filtered['Datum'].max().strftime('%d.%m.%Y')}"
    )


if __name__ == "__main__":
    main()
