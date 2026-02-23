"""
Verkehrsdaten Dashboard - Rosengartenbrücke Zürich (DuckDB Version)
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
import duckdb
import os
import tempfile
import urllib3

# SSL-Warnungen unterdrücken
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Seiten-Konfiguration
st.set_page_config(
    page_title="Verkehr Rosengartenbrücke (DuckDB)",
    layout="wide",
    initial_sidebar_state="expanded"
)

# OGD Parquet URL
OGD_PARQUET_URL = "https://data.stadt-zuerich.ch/dataset/ugz_verkehrsdaten_stundenwerte_rosengartenbruecke/download/ugz_ogd_traffic_rosengartenbruecke_h1.parquet"

# Farbschema
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
    'Unbekannt': '#95a5a6',
    'Bus/Trolleybus': '#f39c12'
}

@st.cache_resource
def get_db_connection():
    """Erstellt eine persistente DuckDB-Verbindung im Speicher."""
    con = duckdb.connect(database=':memory:')
    return con

@st.cache_data(ttl=3600)
def download_parquet_file():
    """Lädt die Parquet-Datei herunter und gibt den Pfad zurück."""
    try:
        response = requests.get(OGD_PARQUET_URL, timeout=120, verify=False)
        response.raise_for_status()
        
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, "traffic_data.parquet")
        
        with open(temp_path, 'wb') as f:
            f.write(response.content)
            
        return temp_path
    except Exception as e:
        st.error(f"Download Fehler: {e}")
        return None

def init_duckdb(con, parquet_path):
    """Initialisiert die DuckDB Tabellen."""
    # Prüfen ob Tabelle schon existiert
    tables = con.execute("SHOW TABLES").fetchall()
    if ('traffic',) in tables:
        return

    # Datum processing: 
    # The 'Datum' column in the Parquet file is stored as a Timestamp with Timezone Etc/GMT-1 (UTC+1, fixed CET).
    # It does NOT account for DST (Summer time).
    # To get correct local time for Zurich (Europe/Zurich), we need to convert the timezone.
    # However, since DuckDB's time zone handling can be complex with 'Etc/GMT-1', and to match the original pandas logic
    # (which likely just took the hour component of the provided timestamp), we'll read it as is.
    # If explicit conversion to local time (DST aware) is needed:
    #   CAST(Datum AS TIMESTAMPTZ) AT TIME ZONE 'Europe/Zurich'
    # For now, we respect the user's note about the data format.
    con.execute(f"""
        CREATE OR REPLACE TABLE traffic AS 
        SELECT 
            *,
            CAST(Datum AS TIMESTAMP) as Datum_Obs,
            year(Datum) as Jahr,
            month(Datum) as Monat,
            day(Datum) as Tag,
            dayofweek(Datum) as Wochentag_ISO,
            hour(Datum) as Stunde,
            week(Datum) as Kalenderwoche,
            strftime(Datum, '%Y-%m-%d') as Datum_Tag_Str,
            CASE 
                WHEN "Klasse.Text" IN ('Motorrad') THEN 'Motorrad'
                WHEN "Klasse.Text" IN ('Personenwagen', 'Personenwagen mit Anhänger') THEN 'Personenwagen'
                WHEN "Klasse.Text" IN ('Lieferwagen', 'Lieferwagen mit Anhänger', 'Lieferwagen mit Auflieger') THEN 'Lieferwagen'
                WHEN "Klasse.Text" IN ('Lastwagen', 'Sattelzug', 'Lastenzug') THEN 'Lastwagen'
                WHEN "Klasse.Text" IN ('Bus', 'Trolleybus') THEN 'Bus/Trolleybus'
                ELSE 'Unbekannt'
            END as Kategorie
        FROM read_parquet('{parquet_path.replace(os.sep, '/')}')
    """)
    
    con.execute("""
        ALTER TABLE traffic ADD COLUMN Wochentag INTEGER;
        UPDATE traffic SET Wochentag = CASE 
            WHEN Wochentag_ISO = 0 THEN 6 
            ELSE Wochentag_ISO - 1 
        END;
    """)

def format_number(num):
    if num is None: return "0"
    num = int(round(num))
    return f"{num:,}".replace(',', "'")

def format_number_ch(num):
    if pd.isna(num) or num is None:
        return "–"
    return f"{int(round(num)):,}".replace(',', "'")

def main():
    st.title("Verkehrsdaten Rosengartenbrücke (OGD)")
    st.markdown("Stündliche Verkehrszählung nach Fahrzeugtypen | Datenquelle: [Open Data Zürich](https://data.stadt-zuerich.ch/dataset/ugz_verkehrsdaten_stundenwerte_rosengartenbruecke) | [Sensorpositionen (Karte)](https://s.geo.admin.ch/6cr2y1s13xwp)")
    
    # Init DB
    parquet_path = download_parquet_file()
    if not parquet_path:
        return

    con = get_db_connection()
    init_duckdb(con, parquet_path)
    
    # --- FILTERS ---
    st.sidebar.header("Filter")
    
    # Jahre abfragen
    years_df = con.execute("SELECT DISTINCT Jahr FROM traffic ORDER BY Jahr DESC").df()
    available_years = years_df['Jahr'].tolist()
    
    selected_jahre = st.sidebar.multiselect(
        "Jahre",
        options=available_years,
        default=[available_years[0]] if available_years else [],
    )
    
    if not selected_jahre:
        st.warning("Bitte wählen Sie mindestens ein Jahr aus.")
        return

    # Base Filter Condition
    years_str = ",".join(map(str, selected_jahre))
    where_clause = f"Jahr IN ({years_str})"
    
    # Richtungen
    richt_df = con.execute(f"SELECT DISTINCT Richtung FROM traffic WHERE {where_clause}").df()
    selected_richtungen = st.sidebar.multiselect(
        "Richtung",
        options=richt_df['Richtung'].tolist(),
        default=richt_df['Richtung'].tolist()
    )
    
    # Klassen
    klassen_df = con.execute(f"""
        SELECT "Klasse.Text", SUM(Anzahl) as Total 
        FROM traffic 
        WHERE {where_clause} 
        GROUP BY 1 ORDER BY 2 DESC
    """).df()
    selected_klassen = st.sidebar.multiselect(
        "Fahrzeugklassen",
        options=klassen_df['Klasse.Text'].tolist(),
        default=klassen_df['Klasse.Text'].tolist()
    )
    
    # Wochentage
    wochentage = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag']
    selected_wochentage = st.sidebar.multiselect("Wochentage", options=wochentage, default=wochentage)
    selected_wt_ids = [wochentage.index(w) for w in selected_wochentage]
    
    if not selected_richtungen or not selected_klassen or not selected_wochentage:
        st.warning("Bitte wählen Sie Filter.")
        return

    # Build WHERE clause
    richt_list = "'" + "','".join(selected_richtungen) + "'"
    klass_list = "'" + "','".join(selected_klassen) + "'"
    wt_list = ",".join(map(str, selected_wt_ids))
    
    final_where = f"""
        {where_clause} 
        AND Richtung IN ({richt_list})
        AND "Klasse.Text" IN ({klass_list})
        AND Wochentag IN ({wt_list})
    """
    
    # === DATA QUALITY CHECK / VALID DAYS ===
    # A "valid day" is defined as having at least 22 hours of data in BOTH directions.
    # We calculate this once to use in multiple charts.
    
    con.execute("""
        CREATE OR REPLACE TEMP TABLE valid_days AS
        WITH hourly_counts AS (
            SELECT 
                Datum_Tag_Str,
                Richtung,
                COUNT(DISTINCT Stunde) as HoursPresent
            FROM traffic
            GROUP BY 1, 2
        ),
        valid_directions AS (
            SELECT Datum_Tag_Str
            FROM hourly_counts
            WHERE HoursPresent >= 22
        )
        SELECT Datum_Tag_Str
        FROM valid_directions
        GROUP BY 1
        HAVING COUNT(*) >= 2
    """)
    
    # === KPI ===
    st.markdown("---")
    col1, col2, col3, col4 = st.columns(4)
    
    # Single Query for KPIs is usually faster
    kpi_df = con.execute(f"""
        SELECT 
            SUM(Anzahl) as Total,
            COUNT(DISTINCT Datum_Tag_Str) as Days
        FROM traffic
        WHERE {final_where}
    """).df()
    
    # DTV Query (Average Sum per Day)
    dtv_df = con.execute(f"""
        WITH daily_sums AS (
            SELECT Datum_Tag_Str, SUM(Anzahl) as DayTotal
            FROM traffic
            WHERE {final_where}
            GROUP BY Datum_Tag_Str
        )
        SELECT AVG(DayTotal) as DTV FROM daily_sums
    """).df()
    
    # Peak Hour
    peak_df = con.execute(f"""
        SELECT Stunde, SUM(Anzahl) as Val 
        FROM traffic 
        WHERE {final_where}
        GROUP BY 1 ORDER BY 2 DESC LIMIT 1
    """).df()
    
    total_vehicles = kpi_df['Total'][0] if not kpi_df.empty else 0
    days_count = kpi_df['Days'][0] if not kpi_df.empty else 0
    avg_daily = dtv_df['DTV'][0] if not dtv_df.empty else 0
    peak_hour = peak_df['Stunde'][0] if not peak_df.empty else 0
    
    with col1: st.metric("Fahrzeuge gesamt", format_number(total_vehicles))
    with col2: st.metric("Ø Tagesverkehr (DTV)", format_number(avg_daily))
    with col3: st.metric("Spitzenstunde", f"{peak_hour}:00 - {peak_hour+1}:00")
    with col4: st.metric("Tage im Datensatz", format_number(days_count))

    # === LETZTE 7 TAGE ===
    st.markdown("---")
    st.subheader("Letzte 7 Tage: Personenwagen, Lastwagen & Lieferwagen (Stundenwerte)")
    
    # Get Max Date first
    max_date_df = con.execute("SELECT MAX(Datum_Obs) as MaxDatum FROM traffic").df()
    if not max_date_df.empty and pd.notna(max_date_df['MaxDatum'][0]):
        max_datum = max_date_df['MaxDatum'][0]
        start_7_tage = max_datum - timedelta(days=7)
        
        # Query last 7 days
        # Note: categories are hardcoded as in original dashboard
        last7_df = con.execute(f"""
            SELECT 
                Datum_Obs as Datum, 
                Kategorie, 
                SUM(Anzahl) as Anzahl
            FROM traffic
            WHERE Datum_Obs >= ? 
            AND Kategorie IN ('Personenwagen', 'Lastwagen', 'Lieferwagen')
            GROUP BY 1, 2
            ORDER BY 1
        """, [start_7_tage]).df()
        
        if not last7_df.empty:
            last7_df['Anzahl_fmt'] = last7_df['Anzahl'].apply(format_number_ch)
            last7_df['Datum_Label'] = last7_df['Datum'].dt.strftime('%a %d.%m. %H:%M')
            
            kategorie_farben_7t = {
                'Personenwagen': '#3498db',
                'Lieferwagen': '#2ecc71', 
                'Lastwagen': '#9b59b6'
            }
            
            fig_7 = px.line(
                last7_df, x='Datum', y='Anzahl', color='Kategorie',
                labels={'Datum': 'Datum/Zeit', 'Anzahl': 'Fahrzeuge/Stunde'},
                color_discrete_map=kategorie_farben_7t,
                custom_data=['Anzahl_fmt', 'Kategorie', 'Datum_Label']
            )
            fig_7.update_traces(
                hovertemplate='%{customdata[2]}<br>%{customdata[1]}: %{customdata[0]}<extra></extra>',
                line=dict(width=2)
            )
            fig_7.update_layout(
                hovermode='x unified',
                xaxis=dict(tickformat='%a %d.%m.', dtick='D1'),
                legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0),
                height=400
            )
            
            col_chart, col_stats = st.columns([3, 1])
            with col_chart:
                st.plotly_chart(fig_7, use_container_width=True)
            
            with col_stats:
                st.markdown("**Ø pro Stunde (7 Tage)**")
                avg_hourly = last7_df.groupby('Kategorie')['Anzahl'].mean()
                for cat in ['Personenwagen', 'Lieferwagen', 'Lastwagen']:
                    if cat in avg_hourly:
                        st.markdown(f"<span style='color:{kategorie_farben_7t[cat]};font-weight:bold;'>{cat}:</span> {format_number(avg_hourly[cat])}", unsafe_allow_html=True)

                st.markdown("---")
                st.markdown("**Ø pro Tag (7 Tage)**")
                # Daily average calc
                daily_sums = last7_df.copy()
                daily_sums['Tag'] = daily_sums['Datum'].dt.date
                avg_daily_7 = daily_sums.groupby(['Tag', 'Kategorie'])['Anzahl'].sum().reset_index().groupby('Kategorie')['Anzahl'].mean()
                
                for cat in ['Personenwagen', 'Lieferwagen', 'Lastwagen']:
                    if cat in avg_daily_7:
                        st.markdown(f"<span style='color:{kategorie_farben_7t[cat]};font-weight:bold;'>{cat}:</span> {format_number(avg_daily_7[cat])}", unsafe_allow_html=True)
                
                st.markdown("---")
                st.caption(f"{start_7_tage.strftime('%d.%m.%Y')} – {max_datum.strftime('%d.%m.%Y')}")
        else:
            st.info("Keine Daten für die letzten 7 Tage.")
    else:
        st.info("Keine Daten verfügbar.")

    # === DIAGRAMME ===
    st.markdown("---")
    
    # === NEU: Täglicher Gesamtverkehr (Chronologie) mit Auswahl ===
    st.subheader("Täglicher Verkehr (Chronologie)")

    # Auswahl für die Aufteilung
    split_daily = st.radio(
        "Aufteilung nach:",
        ["Fahrzeugklasse", "Richtung"],
        horizontal=True,
        key="daily_split_radio"
    )

    # Je nach Auswahl gruppieren wir anders
    if split_daily == "Fahrzeugklasse":
        group_col = "Kategorie"
        color_col = "Kategorie"
        title_suffix = "nach Fahrzeugklasse"
    else:
        group_col = "Richtung"
        color_col = "Richtung"
        title_suffix = "nach Richtung"
    
    # Für diese Grafik ignorieren wir den Jahresfilter, aber behalten die anderen Filter bei
    # Use "1=1" as base to append other filters without Year restriction
    timeline_where = f"""
        1=1
        AND Richtung IN ({richt_list})
        AND "Klasse.Text" IN ({klass_list})
        AND Wochentag IN ({wt_list})
    """
    
    query_daily = f"""
        SELECT 
            Datum_Tag_Str as Datum, 
            {group_col} as Grouping, 
            SUM(Anzahl) as Anzahl
        FROM traffic
        WHERE {timeline_where}
        GROUP BY 1, 2
        ORDER BY 1
    """

    daily_data = con.execute(query_daily).df()
    
    if not daily_data.empty:
        # Convert Datum to datetime for better axis handling
        daily_data['Datum'] = pd.to_datetime(daily_data['Datum'])
        
        # Calculate initial range (last 30 days of the dataset)
        max_date_val = daily_data['Datum'].max()
        min_date_val = max_date_val - timedelta(days=30)
        
        # Determine color map
        if split_daily == "Fahrzeugklasse":
            color_map = FARBEN
        else:
            # Simple color map for directions if not defined globally
            color_map = None 

        fig_daily = px.bar(
            daily_data, x='Datum', y='Anzahl', color='Grouping',
            color_discrete_map=color_map,
            labels={'Datum': 'Datum', 'Anzahl': 'Fahrzeuge pro Tag', 'Grouping': split_daily},
            title=f'Täglicher Gesamtverkehr - Gesamter Zeitraum ({title_suffix})'
        )
        
        fig_daily.update_layout(
            barmode='stack',
            xaxis=dict(
                rangeselector=dict(
                    buttons=list([
                        dict(count=7, label="1w", step="day", stepmode="backward"),
                        dict(count=1, label="1m", step="month", stepmode="backward"),
                        dict(count=6, label="6m", step="month", stepmode="backward"),
                        dict(count=1, label="YTD", step="year", stepmode="todate"),
                        dict(count=1, label="1y", step="year", stepmode="backward"),
                        dict(step="all")
                    ])
                ),
                rangeslider=dict(visible=True),
                type="date",
                range=[min_date_val, max_date_val] # Set initial view range to last 30 days
            ),
            yaxis=dict(fixedrange=False),
            height=500,
            dragmode="pan" # Optimize interaction for scrolling
        )
        st.plotly_chart(fig_daily, use_container_width=True)

    # Zeile 1a: Tagesverlauf und Wochenverlauf nach Richtung
    st.subheader("Tages- und Wochenverlauf nach Richtung")
    col_left, col_right = st.columns(2)
    
    with col_left:
        hourly_dir = con.execute(f"""
            SELECT Richtung, Stunde, AVG(Anzahl) as Anzahl
            FROM traffic
            WHERE {final_where}
            GROUP BY 1, 2
            ORDER BY 2, 1
        """).df()
        
        fig_hourly_dir = px.line(
            hourly_dir, x='Stunde', y='Anzahl', color='Richtung',
            labels={'Stunde': 'Uhrzeit', 'Anzahl': 'Ø Fahrzeuge/Stunde'},
            markers=True, color_discrete_map={'Bucheggplatz': '#3498db', 'Hardbrücke': '#e74c3c'}
        )
        st.plotly_chart(fig_hourly_dir, use_container_width=True)
        
    with col_right:
        weekly_dir = con.execute(f"""
            SELECT Richtung, Wochentag, AVG(DaySum) as Anzahl
            FROM (
                SELECT Richtung, Wochentag, Datum_Tag_Str, SUM(Anzahl) as DaySum
                FROM traffic
                WHERE {final_where}
                GROUP BY 1, 2, 3
            )
            GROUP BY 1, 2
            ORDER BY 2
        """).df()
        
        wt_map = {0: 'Mo', 1: 'Di', 2: 'Mi', 3: 'Do', 4: 'Fr', 5: 'Sa', 6: 'So'}
        weekly_dir['Wochentag_Name'] = weekly_dir['Wochentag'].map(wt_map)
        
        fig_weekly_dir = px.bar(
            weekly_dir, x='Wochentag_Name', y='Anzahl', color='Richtung', barmode='group',
            labels={'Wochentag_Name': 'Wochentag', 'Anzahl': 'Ø Fahrzeuge/Tag'},
            color_discrete_map={'Bucheggplatz': '#3498db', 'Hardbrücke': '#e74c3c'}
        )
        st.plotly_chart(fig_weekly_dir, use_container_width=True)

    # Zeile 1b: Nach Jahr (falls > 1 Jahr)
    if len(selected_jahre) > 1:
        st.subheader("Tages- und Wochenverlauf nach Jahr")
        col_ly, col_ry = st.columns(2)
        with col_ly:
            hourly_yr = con.execute(f"""
                SELECT Jahr, Stunde, AVG(Anzahl) as Anzahl 
                FROM traffic
                WHERE {final_where}
                GROUP BY 1, 2 ORDER BY 2
            """).df()
            hourly_yr['Jahr'] = hourly_yr['Jahr'].astype(str)
            fig_yr = px.line(hourly_yr, x='Stunde', y='Anzahl', color='Jahr', markers=True, title='Tagesverlauf')
            st.plotly_chart(fig_yr, use_container_width=True)
        
        with col_ry:
            weekly_yr = con.execute(f"""
                SELECT Jahr, Wochentag, AVG(DaySum) as Anzahl
                FROM (
                    SELECT Jahr, Wochentag, Datum_Tag_Str, SUM(Anzahl) as DaySum
                    FROM traffic
                    WHERE {final_where}
                    GROUP BY 1, 2, 3
                )
                GROUP BY 1, 2
                ORDER BY 2
            """).df()
            weekly_yr['Wochentag_Name'] = weekly_yr['Wochentag'].map(wt_map)
            weekly_yr['Jahr'] = weekly_yr['Jahr'].astype(str)
            
            fig_w_yr = px.bar(weekly_yr, x='Wochentag_Name', y='Anzahl', color='Jahr', barmode='group', title='Wochenverlauf')
            st.plotly_chart(fig_w_yr, use_container_width=True)

    # === TAGESVERLAUF PRO WOCHENTAG ===
    st.markdown("---")
    st.subheader("Tagesverlauf pro Wochentag")
    
    # Query all at once for efficiency
    all_wt_hourly = con.execute(f"""
        SELECT Wochentag, Stunde, AVG(Anzahl) as Anzahl
        FROM traffic
        WHERE {final_where}
        GROUP BY 1, 2
        ORDER BY 1, 2
    """).df()
    
    wt_names = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag']
    
    # Row 1 (Mo-Do)
    cols1 = st.columns(4)
    for i in range(4):
        with cols1[i]:
            df_w = all_wt_hourly[all_wt_hourly['Wochentag'] == i]
            if not df_w.empty:
                fig = px.line(df_w, x='Stunde', y='Anzahl', markers=True, title=wt_names[i])
                fig.update_layout(height=200, margin=dict(l=20, r=20, t=30, b=20))
                st.plotly_chart(fig, use_container_width=True)
    
    # Row 2 (Fr-So + Comp)
    cols2 = st.columns(4)
    for i in range(3):
        with cols2[i]:
            idx = i + 4
            df_w = all_wt_hourly[all_wt_hourly['Wochentag'] == idx]
            if not df_w.empty:
                fig = px.line(df_w, x='Stunde', y='Anzahl', markers=True, title=wt_names[idx])
                fig.update_layout(height=200, margin=dict(l=20, r=20, t=30, b=20))
                st.plotly_chart(fig, use_container_width=True)
    
    with cols2[3]:
        # Comparison
        all_wt_hourly['WtName'] = all_wt_hourly['Wochentag'].map(lambda x: wt_names[x][:2])
        fig_comp = px.line(all_wt_hourly, x='Stunde', y='Anzahl', color='WtName', title='Vergleich')
        fig_comp.update_layout(height=200, margin=dict(l=20, r=20, t=30, b=20), showlegend=True)
        st.plotly_chart(fig_comp, use_container_width=True)
        
    # === FAHRZEUGKLASSEN & RICHTUNG ===
    st.markdown("---")
    c_l, c_r = st.columns(2)
    
    with c_l:
        st.subheader("Fahrzeugklassen (%)")
        tab1, tab2 = st.tabs(["Detailliert", "Kategorien"])
        
        with tab1:
            classes = con.execute(f"""
                SELECT "Klasse.Text", SUM(Anzahl) as Anzahl 
                FROM traffic 
                WHERE {final_where}
                GROUP BY 1 ORDER BY 2 ASC
            """).df()
            total = classes['Anzahl'].sum()
            classes['Prozent'] = (classes['Anzahl'] / total * 100).round(1)
            
            fig_c = px.bar(classes, x='Prozent', y='Klasse.Text', orientation='h', text='Prozent',
                           color='Klasse.Text', color_discrete_map=FARBEN)
            fig_c.update_traces(texttemplate='%{text:.1f}%')
            fig_c.update_layout(showlegend=False)
            st.plotly_chart(fig_c, use_container_width=True)
            
        with tab2:
            cats = con.execute(f"""
                SELECT Kategorie, SUM(Anzahl) as Anzahl 
                FROM traffic 
                WHERE {final_where}
                GROUP BY 1 ORDER BY 2 ASC
            """).df()
            total_c = cats['Anzahl'].sum()
            cats['Prozent'] = (cats['Anzahl'] / total_c * 100).round(1)
            
            fig_k = px.bar(cats, x='Prozent', y='Kategorie', orientation='h', text='Prozent',
                           color='Kategorie', color_discrete_map=FARBEN)
            fig_k.update_traces(texttemplate='%{text:.1f}%')
            fig_k.update_layout(showlegend=False)
            st.plotly_chart(fig_k, use_container_width=True)
            
    with c_r:
        st.subheader("↔️ Richtungsvergleich")
        dirs = con.execute(f"""
            SELECT Richtung, SUM(Anzahl) as Anzahl 
            FROM traffic 
            WHERE {final_where}
            GROUP BY 1 ORDER BY 2 DESC
        """).df()
        fig_p = px.pie(dirs, values='Anzahl', names='Richtung', hole=0.4, 
                       color='Richtung', color_discrete_map={'Bucheggplatz': '#3498db', 'Hardbrücke': '#e74c3c'})
        st.plotly_chart(fig_p, use_container_width=True)

    # 3. Kategorien Verlauf (Nur anzeigen wenn mehrere Jahre ausgewählt sind)
    if len(selected_jahre) > 1:
        st.markdown("---")
        st.subheader("Entwicklung der Fahrzeugkategorien")
        
        # DuckDB Pivot-like aggregation using creating list/struct not standard SQL
        # Standard SQL approach: Group by Year, Category
        
        # Qualify columns in WHERE clause to avoid ambiguity in JOINs
        final_where_qualified = final_where.replace("Jahr", "t.Jahr").replace("Richtung", "t.Richtung").replace('"Klasse.Text"', 't."Klasse.Text"').replace("Wochentag", "t.Wochentag")

        cat_trend = con.execute(f"""
            WITH year_totals AS (
                SELECT Jahr, SUM(Anzahl) as YearTotal
                FROM traffic
                WHERE {final_where}
                GROUP BY 1
            )
            SELECT 
                t.Jahr, 
                t.Kategorie, 
                SUM(t.Anzahl) as CatSum,
                (SUM(t.Anzahl) / ANY_VALUE(y.YearTotal) * 100) as Prozent
            FROM traffic t
            JOIN year_totals y ON t.Jahr = y.Jahr
            WHERE {final_where_qualified}
            GROUP BY 1, 2
            ORDER BY 1
        """).df()
        
        tab_area, tab_line = st.tabs(["Flächendiagramm", "Liniendiagramm"])
        
        with tab_area:
            fig_cat = px.area(cat_trend, x='Jahr', y='Prozent', color='Kategorie', 
                              color_discrete_map=FARBEN)
            st.plotly_chart(fig_cat, use_container_width=True)
            
        with tab_line:
            fig_cat_line = px.line(cat_trend, x='Jahr', y='Prozent', color='Kategorie', markers=True,
                                   color_discrete_map=FARBEN)
            st.plotly_chart(fig_cat_line, use_container_width=True)
    
    # 4. Monatlicher Verkehrstrend
    st.markdown("---")
    st.subheader("Monatlicher Verkehrstrend (Ø Tagesverkehr)")
    
    # Check current year/month for filtering rules
    now = datetime.now()
    curr_y, curr_m = now.year, now.month
    
    # Filter only fully measured days (>= 22h per direction)
    monthly_trend = con.execute(f"""
        WITH daily_agg AS (
            SELECT t.Jahr, t.Monat, t.Datum_Tag_Str, t.Richtung, SUM(t.Anzahl) as DaySum
            FROM traffic t
            WHERE {final_where}
            AND t.Datum_Tag_Str IN (SELECT Datum_Tag_Str FROM valid_days)
            GROUP BY 1, 2, 3, 4
        )
        SELECT 
            Jahr, Monat, Richtung,
            AVG(DaySum) as Anzahl,
            COUNT(DISTINCT Datum_Tag_Str) as Tage,
            (
                (Jahr < {curr_y} AND COUNT(DISTINCT Datum_Tag_Str) >= 20) OR 
                (Jahr = {curr_y} AND Monat < {curr_m} AND COUNT(DISTINCT Datum_Tag_Str) >= 20) OR
                (Jahr = {curr_y} AND Monat = {curr_m} AND COUNT(DISTINCT Datum_Tag_Str) >= 3)
            ) as pass_filter
        FROM daily_agg
        GROUP BY 1, 2, 3
    """).df()
    
    # Filter valid months
    monthly_valid = monthly_trend[monthly_trend['pass_filter']].copy()
    if not monthly_valid.empty:
        # Create a dummy date for plotting
        monthly_valid['Datum'] = pd.to_datetime(
            monthly_valid['Jahr'].astype(str) + '-' + monthly_valid['Monat'].astype(str) + '-15'
        )
        
        fig_trend = px.bar(
            monthly_valid, x='Datum', y='Anzahl', color='Richtung', barmode='group',
            color_discrete_map={'Bucheggplatz': '#3498db', 'Hardbrücke': '#e74c3c'}
        )
        
        # Add background shapes for context
        shapes = []
        # Lockdown 2020
        if 2020 in selected_jahre:
            shapes.append(dict(type="rect", xref="x", yref="paper", x0="2020-03-01", x1="2020-06-01",
                               y0=0, y1=1, fillcolor="rgba(255, 0, 0, 0.1)", line=dict(width=0), layer="below"))
        
        # Summer Holidays (approx July-Aug)
        for y in selected_jahre:
            shapes.append(dict(type="rect", xref="x", yref="paper", x0=f"{y}-07-01", x1=f"{y}-09-01",
                               y0=0, y1=1, fillcolor="rgba(255, 193, 7, 0.1)", line=dict(width=0), layer="below"))
            
            # Annual separator line (dashed)
            shapes.append(dict(type="line", xref="x", yref="paper", x0=f"{y}-01-01", x1=f"{y}-01-01",
                               y0=0, y1=1, line=dict(color="rgba(0,0,0,0.3)", width=1, dash="dash"), layer="below"))
            
        # Range festlegen: Beginn kleinstes Jahr bis Ende grösstes aktuelles Jahr
        min_jahr = min(selected_jahre)
        max_jahr = max(selected_jahre)
        datum_range = [f"{min_jahr}-01-01", f"{max_jahr}-12-31"]

        fig_trend.update_layout(
            shapes=shapes, 
            xaxis=dict(
                dtick="M1", 
                tickformat="%b %Y",
                range=datum_range
            )
        )
        st.plotly_chart(fig_trend, use_container_width=True)
    else:
        st.info("Keine ausreichenden Daten für Monatstrend.")

    # 5. Jahresverlauf (Wochenschnitt)
    st.markdown("---")
    st.subheader("Jahresverlauf (Wochendurchschnitt)")
    
    # Also apply the valid_days filter
    weekly_trend = con.execute(f"""
        WITH daily_agg AS (
            SELECT t.Jahr, t.Kalenderwoche, t.Datum_Tag_Str, SUM(t.Anzahl) as DaySum
            FROM traffic t
            WHERE {final_where}
            AND t.Datum_Tag_Str IN (SELECT Datum_Tag_Str FROM valid_days)
            GROUP BY 1, 2, 3
        )
        SELECT Jahr, Kalenderwoche, AVG(DaySum) as Anzahl
        FROM daily_agg
        WHERE Kalenderwoche <= 52
        GROUP BY 1, 2
        HAVING COUNT(DISTINCT Datum_Tag_Str) >= 5
        ORDER BY 1, 2
    """).df()
    
    weekly_trend['Jahr'] = weekly_trend['Jahr'].astype(str)
    
    if not weekly_trend.empty:
        fig_wk = px.line(weekly_trend, x='Kalenderwoche', y='Anzahl', color='Jahr', markers=True)
        
        # Add shapes for context
        wk_shapes = []
        wk_annotations = []
        
        # Lockdown approx KW11-KW20 (Red)
        if '2020' in weekly_trend['Jahr'].values:
            wk_shapes.append(dict(type="rect", xref="x", yref="paper", x0=11, x1=20,
                                  y0=0, y1=1, fillcolor="rgba(255, 0, 0, 0.1)", line=dict(width=0), layer="below"))
            wk_annotations.append(dict(x=15, y=1.02, xref="x", yref="paper", text="Lockdown",
                                    showarrow=False, font=dict(size=10, color="#e74c3c"), bgcolor="rgba(255,255,255,0.8)"))
        
        # Summer approx KW28-33 (Yellow)
        wk_shapes.append(dict(type="rect", xref="x", yref="paper", x0=28, x1=33,
                              y0=0, y1=1, fillcolor="rgba(255, 193, 7, 0.1)", line=dict(width=0), layer="below"))
        wk_annotations.append(dict(x=30.5, y=1.02, xref="x", yref="paper", text="Ferien",
                                   showarrow=False, font=dict(size=10, color="#f39c12"), bgcolor="rgba(255,255,255,0.8)"))
        
        # Christmas / New Year (Green)
        # Start of year (KW 0.5-2) and End of year (KW 51-52.5)
        wk_shapes.extend([
            dict(type="rect", xref="x", yref="paper", x0=51, x1=53, y0=0, y1=1,
                 fillcolor="rgba(76, 175, 80, 0.1)", line=dict(width=0), layer="below"),
            dict(type="rect", xref="x", yref="paper", x0=0, x1=2, y0=0, y1=1,
                 fillcolor="rgba(76, 175, 80, 0.1)", line=dict(width=0), layer="below")
        ])

        fig_wk.update_layout(
            shapes=wk_shapes, 
            annotations=wk_annotations,
            xaxis=dict(range=[0, 53], dtick=5)
        )
        st.plotly_chart(fig_wk, use_container_width=True)
        st.caption("Rot = COVID-19 Lockdown (KW 12-20, 2020) | Gelb = Sommerferien (KW 28-33) | Grün = Weihnachten/Neujahr")

    # 6. Heatmap
    st.markdown("---")
    st.subheader("🗓️ Verkehrsmuster: Stunde × Wochentag")
    
    heatmap_df = con.execute(f"""
        SELECT Wochentag, Stunde, AVG(Anzahl) as Anzahl
        FROM traffic
        WHERE {final_where}
        GROUP BY 1, 2
    """).df()
    
    if not heatmap_df.empty:
        # Full grid to ensure all cells exist
        idx = pd.MultiIndex.from_product([range(7), range(24)], names=['Wochentag', 'Stunde'])
        heatmap_full = heatmap_df.set_index(['Wochentag', 'Stunde']).reindex(idx, fill_value=0).reset_index()
        
        # Pivot for plotting
        pivot = heatmap_full.pivot(index='Wochentag', columns='Stunde', values='Anzahl')
        pivot.index = [wt_map[i] for i in pivot.index]
        
        fig_heat = px.imshow(pivot, labels=dict(x="Stunde", y="Wochentag", color="Ø Fz/h"),
                             aspect="auto", color_continuous_scale="YlOrRd")
        st.plotly_chart(fig_heat, use_container_width=True)

    # 7. Jahresvergleich (DTV) mit Validierung
    st.markdown("---")
    st.subheader("Jahresvergleich (Ø Tagesverkehr)")

    # Analyze Gaps / Completeness per Year
    # We use the full dataset (filtered by year only) to determine availability
    quality_stats = con.execute(f"""
        WITH range_stats AS (
            SELECT 
                Jahr,
                MIN(Datum_Obs) as MinDate,
                MAX(Datum_Obs) as MaxDate,
                COUNT(DISTINCT Datum_Obs) as ActualHours
            FROM traffic
            WHERE Jahr IN ({years_str})
            GROUP BY Jahr
        )
        SELECT 
            Jahr,
            ActualHours,
            date_diff('hour', MinDate, MaxDate) + 1 as TotalHoursSpan,
            (date_diff('hour', MinDate, MaxDate) + 1) - ActualHours as MissingHours
        FROM range_stats
        ORDER BY Jahr
    """).df()
    
    # Calculate Metrics and Display
    yearly_completeness = []
    
    if not quality_stats.empty:
        cols_yearly = st.columns(len(quality_stats))
        for i, row in quality_stats.iterrows():
            jahr = int(row['Jahr'])
            missing = row['MissingHours']
            total = row['TotalHoursSpan']
            completeness = (1 - (missing / total)) * 100 if total > 0 else 0
            gap_days = missing / 24.0
            
            # Save for later use
            yearly_completeness.append({
                'Jahr': jahr, 
                'Completeness': completeness, 
                'GapDays': gap_days
            })

            # Get DTV for Display Label
            # Warning: Taking simple average of daily sums for the metric label to match original roughly
            dtv_val = con.execute(f"""
                SELECT AVG(DaySum) 
                FROM (SELECT Datum_Tag_Str, SUM(Anzahl) as DaySum FROM traffic WHERE Jahr = {jahr} GROUP BY 1)
            """).fetchone()[0]
            
            with cols_yearly[i]:
                formatted_val = format_number(dtv_val) if dtv_val else "-"
                if gap_days > 1:
                    st.metric(label=f"{jahr}", value=formatted_val,
                              help=f"Ø Fahrzeuge/Tag | Vollständigkeit: {completeness:.1f}% | {gap_days:.1f} Tage fehlen")
                    st.caption(f"⚠️ {gap_days:.1f} Tage fehlen")
                else:
                    st.metric(label=f"{jahr}", value=formatted_val,
                              help=f"Ø Fahrzeuge/Tag | Vollständigkeit: {completeness:.1f}%")
    
    # Check for big gaps
    if any(x['GapDays'] > 7 for x in yearly_completeness):
        st.info("ℹ️ **Hinweis:** Einige Jahre haben grössere Datenlücken. "
                "Der Ø Tagesverkehr (DTV) basiert nur auf den verfügbaren Tagen.")

    # --- Valid Days Calculation ---
    # We use the pre-calculated 'valid_days' table which enforces:
    # 1. >= 22 hours of data per direction
    # 2. Both directions must be valid on the same day
    
    # Tab Layout
    tab1, tab2, tab_total = st.tabs(["Gesamtverkehr", "Nach Richtung", "Gesamtanzahl"])
    
    with tab1:
        # Gesamt: Sum of both directions
        stats_total = con.execute(f"""
            WITH RawSums AS (
                SELECT t.Jahr, t.Datum_Tag_Str, SUM(t.Anzahl) as DaySum
                FROM traffic t
                -- Apply User Filters
                WHERE {final_where}
                -- Filter for Valid Days (Both Directions Valid)
                AND t.Datum_Tag_Str IN (SELECT Datum_Tag_Str FROM valid_days)
                GROUP BY 1, 2
            )
            SELECT 
                Jahr, 
                AVG(DaySum) as DTV, 
                MIN(DaySum) as MinVal, 
                MAX(DaySum) as MaxVal,
                arg_min(Datum_Tag_Str, DaySum) as MinDate,
                arg_max(Datum_Tag_Str, DaySum) as MaxDate
            FROM RawSums 
            GROUP BY 1 ORDER BY 1
        """).df()
        
        if not stats_total.empty:
            fig_yr = go.Figure()

            # Error bars (asymmetric)
            error_minus = stats_total['DTV'] - stats_total['MinVal']
            error_plus = stats_total['MaxVal'] - stats_total['DTV']

            # Format dates nicely? Datum_Tag_Str is usually YYYY-MM-DD.
            # We can keep it as is or format. DuckDB arg_min returns the value.

            fig_yr.add_trace(go.Bar(
                x=stats_total['Jahr'], 
                y=stats_total['DTV'],
                error_y=dict(
                    type='data',
                    symmetric=False,
                    array=error_plus,
                    arrayminus=error_minus,
                    color='#555',
                    thickness=1.5,
                    width=4
                ),
                text=stats_total['DTV'].apply(format_number),
                textposition='auto',
                marker_color='#85c1e9', # Match OGD color
                name='DTV',
                hovertemplate='Ø: %{y:.0f}<br>Min: %{customdata[0]} am %{customdata[2]}<br>Max: %{customdata[1]} am %{customdata[3]}<extra></extra>',
                customdata=np.stack((stats_total['MinVal'], stats_total['MaxVal'], stats_total['MinDate'], stats_total['MaxDate']), axis=-1)
            ))
            fig_yr.update_layout(
                yaxis_title="Fahrzeuge / Tag", 
                hovermode="x unified",
                xaxis=dict(tickmode='linear')
            )
            st.plotly_chart(fig_yr, use_container_width=True)
            st.caption("📊 Gesamtverkehr (beide Richtungen). Die Fehlerbalken zeigen das minimale und maximale Tagesmittel pro Jahr (nur vollständig erfasste Tage).")
        else:
            st.warning("Keine vollständigen Tage für diese Auswahl.")

    with tab2:
        # Per Direction: Filter also by ValidDays (Both directions valid per day required by user)
        stats_dir = con.execute(f"""
            WITH RawSumsDir AS (
                SELECT t.Jahr, t.Datum_Tag_Str, t.Richtung, SUM(t.Anzahl) as DaySum
                FROM traffic t
                WHERE {final_where}
                -- Filter for Valid Days (Both Directions Valid)
                AND t.Datum_Tag_Str IN (SELECT Datum_Tag_Str FROM valid_days)
                GROUP BY 1, 2, 3
                HAVING SUM(t.Anzahl) > 0
            )
            SELECT 
                Jahr, Richtung,
                AVG(DaySum) as DTV, 
                MIN(DaySum) as MinVal, 
                MAX(DaySum) as MaxVal,
                arg_min(Datum_Tag_Str, DaySum) as MinDate,
                arg_max(Datum_Tag_Str, DaySum) as MaxDate
            FROM RawSumsDir 
            GROUP BY 1, 2 ORDER BY 1, 2
        """).df()
        
        if not stats_dir.empty:
            # We construct the figure manually to support error bars per group
            fig_dir = go.Figure()
            
            richt_colors = {'Bucheggplatz': '#3498db', 'Hardbrücke': '#e74c3c'}
            
            for richtung in stats_dir['Richtung'].unique():
                df_r = stats_dir[stats_dir['Richtung'] == richtung]
                err_min = df_r['DTV'] - df_r['MinVal']
                err_plus = df_r['MaxVal'] - df_r['DTV']
                
                fig_dir.add_trace(go.Bar(
                    x=df_r['Jahr'], y=df_r['DTV'],
                    name=richtung,
                    marker_color=richt_colors.get(richtung, '#95a5a6'),
                    text=df_r['DTV'].apply(format_number),
                    textposition='auto',
                    error_y=dict(
                        type='data', symmetric=False,
                        array=err_plus, arrayminus=err_min,
                        thickness=1.5, width=4
                    ),
                    hovertemplate='Ø: %{y:.0f}<br>Min: %{customdata[0]} am %{customdata[2]}<br>Max: %{customdata[1]} am %{customdata[3]}<extra></extra>',
                    customdata=np.stack((df_r['MinVal'], df_r['MaxVal'], df_r['MinDate'], df_r['MaxDate']), axis=-1)
                ))
            
            fig_dir.update_layout(barmode='group', yaxis_title="Fahrzeuge / Tag", hovermode="x unified")
            st.plotly_chart(fig_dir, use_container_width=True)
            st.caption("Aufsplittung nach Fahrtrichtung (Min/Max Tageswerte basierend auf vollständig erfassten Tagen).")
    
    with tab_total:
        # Simple Sum
        total_sums = con.execute(f"""
            SELECT Jahr, SUM(Anzahl) as Total 
            FROM traffic 
            WHERE {final_where} 
            GROUP BY 1 ORDER BY 1
        """).df()
        
        fig_tot = px.bar(total_sums, x='Jahr', y='Total', text_auto='.2s')
        fig_tot.update_traces(marker_color='#9b59b6')
        st.plotly_chart(fig_tot, use_container_width=True)
        st.caption("Summe aller gezählten Fahrzeuge (ohne Hochrechnung bei Lücken oftmals ungenau).")

    # 8. Data Quality Detail
    st.markdown("---")
    st.subheader("Details: Datenqualität & Lücken")
    
    # Gap Analysis Table
    gap_df = con.execute(f"""
        WITH timestamps AS (
            SELECT DISTINCT Datum_Obs 
            FROM traffic 
            WHERE Jahr IN ({years_str})
        ),
        gaps AS (
            SELECT 
                Datum_Obs as GapStart,
                LEAD(Datum_Obs) OVER (ORDER BY Datum_Obs) as GapEnd,
                date_diff('minute', Datum_Obs, LEAD(Datum_Obs) OVER (ORDER BY Datum_Obs)) as GapMinutes
            FROM timestamps
        )
        SELECT 
            GapStart, 
            GapEnd, 
            GapMinutes / 60.0 as GapHours 
        FROM gaps 
        WHERE GapMinutes > 60 
        ORDER BY GapHours DESC
    """).df()
    
    dq_tab1, dq_tab2 = st.tabs(["Datenlücken", "Vollständigkeit pro Jahr"])
    
    with dq_tab1:
        col_metrics, col_table = st.columns([1, 2])
        
        with col_metrics:
            matches_gaps = len(gap_df)
            total_missing_hours = gap_df['GapHours'].sum()
            total_missing_days = total_missing_hours / 24.0
            
            st.metric("Datenlücken (>1h)", matches_gaps)
            st.metric("Fehlende Stunden Total", f"{total_missing_hours:.1f} h")
            st.metric("Fehlende Tage Total", f"{total_missing_days:.1f} d")
        
        with col_table:
            if not gap_df.empty:
                gap_show = gap_df.copy()
                gap_show['Dauer'] = gap_show['GapHours'].apply(lambda x: f"{x:.1f} h" if x < 24 else f"{x/24:.1f} Tage")
                st.dataframe(gap_show[['GapStart', 'GapEnd', 'Dauer']], height=300, hide_index=True)
            else:
                st.success("Keine Lücken > 1 Stunde gefunden.")

    with dq_tab2:
        # Yearly completeness table
        if not quality_stats.empty:
            qs_show = quality_stats.copy()
            qs_show['Vollständigkeit'] = qs_show.apply(
                lambda r: (1 - (r['MissingHours'] / r['TotalHoursSpan'])) * 100, axis=1
            ).map('{:.2f}%'.format)
            st.dataframe(qs_show[['Jahr', 'ActualHours', 'MissingHours', 'Vollständigkeit']], hide_index=True)



    # Footer
    st.markdown("---")
    
    # Get max date for display
    max_date_label = con.execute("SELECT MAX(Datum_Obs) FROM traffic").fetchone()[0]
    last_update_str = max_date_label.strftime('%d.%m.%Y') if max_date_label else "Unbekannt"
    
    st.caption(
        f"Datenquelle: [Open Data Zürich](https://data.stadt-zuerich.ch/dataset/ugz_verkehrsdaten_stundenwerte_rosengartenbruecke) | "
        f"Standort: Rosengartenstrasse 18, 8037 Zürich | "
        f"Intervall: 1 Stunde | "
        f"Letzte Aktualisierung im Datensatz: {last_update_str}"
    )


if __name__ == "__main__":
    main()
