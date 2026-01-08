# 🚗 Verkehrsdaten Dashboard - Rosengartenbrücke Zürich

Interaktives Dashboard zur Analyse der Verkehrszähldaten an der Rosengartenstrasse in Zürich.

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://trafficdata-zurich.streamlit.app/)

## 📊 Übersicht

Dieses Dashboard visualisiert die stündlichen Verkehrszähldaten der Rosengartenbrücke in Zürich seit Januar 2020. Die Daten werden mit dem Profiling-System TIC501 der Firma SICK erfasst. An der nördlichen Seite der Rosengartenbrücke Richtung Bucheggplatz sind 2D LiDAR Sensoren montiert, die den Verkehr auf sieben Spuren erfassen.

## 🚙 Erfasste Fahrzeugklassen

Die Fahrzeuge werden nach dem SWISS10-Klassierungssystem des ASTRA eingeteilt:

| ID | Fahrzeugklasse |
|----|----------------|
| 0 | Unbekannt |
| 1 | Bus |
| 2 | Motorrad |
| 3 | Personenwagen |
| 4 | Personenwagen mit Anhänger |
| 5 | Lieferwagen |
| 6 | Lieferwagen mit Anhänger |
| 7 | Lieferwagen mit Auflieger |
| 8 | Lastwagen |
| 9 | Lastenzug |
| 10 | Sattelzug |
| 11 | Trolleybus (seit 19.02.2020) |

## 📈 Features

- **Zeitreihenanalyse**: Tägliche, wöchentliche und monatliche Verkehrsentwicklung
- **Fahrzeugklassenverteilung**: Analyse nach Fahrzeugtypen
- **Richtungsanalyse**: Verkehrsfluss nach Fahrtrichtung
- **Spurenauswertung**: Detaillierte Spurenstatistiken
- **Saisonale Muster**: Wochentags- und Stundenanalyse (Heatmaps)
- **Interaktive Filter**: Zeitraum, Fahrzeugklassen, Richtung, Spuren

## 🔗 Datenquelle

Die Daten stammen vom Open Government Data Portal der Stadt Zürich:

**[Verkehrszähldaten an der Rosengartenstrasse nach Fahrzeugtypen, seit 2020](https://data.stadt-zuerich.ch/dataset/ugz_verkehrsdaten_stundenwerte_rosengartenbruecke)**

- **Lizenz**: [Creative Commons CCZero](http://www.opendefinition.org/licenses/cc-zero)
- **Aktualisierung**: Täglich
- **Datenowner**: Messung Luftqualität, Umwelt- und Gesundheitsschutz, Gesundheits- und Umweltdepartement

## 🚀 Lokale Installation

### Voraussetzungen

- Python 3.9+
- pip

### Installation

```bash
# Repository klonen
git clone https://github.com/rederlechner/verkehrsdatenanalyse_rosengartenstrasse.git
cd verkehrsdatenanalyse_rosengartenstrasse

# Abhängigkeiten installieren
pip install -r requirements.txt

# Dashboard starten
streamlit run dashboard_ogd.py
```

Alternativ unter Windows:
```bash
start_dashboard_ogd.bat
```

## 📦 Abhängigkeiten

- `streamlit` - Web-Framework für das Dashboard
- `pandas` - Datenverarbeitung
- `plotly` - Interaktive Visualisierungen
- `numpy` - Numerische Berechnungen
- `requests` - HTTP-Requests zum OGD Portal

## 📁 Projektstruktur

```
├── dashboard_ogd.py          # Haupt-Dashboard-Anwendung
├── requirements.txt          # Python-Abhängigkeiten
├── start_dashboard_ogd.bat   # Windows-Startskript
├── data/
│   └── ogd/
│       └── uzg_ogd_metadaten.json  # Metadaten (Stationen, Klassen, Spuren)
└── README.md
```

## ⏰ Hinweise zu den Daten

- **Zeitzone**: Alle Daten werden in Winterzeit (UTC+1) angegeben
- **Zeitangabe**: Entspricht der Startzeit der Zählperiode
- **Trolleybusse**: Erfassung erst seit 19.02.2020 aktiv
- **Datenstatus**: 
  - `provisorisch`: Vorläufige Messwerte
  - `bereinigt`: Endgültige, bereinigte Messwerte

## 📜 Lizenz

Dieses Projekt ist unter der MIT-Lizenz lizenziert.

Die verwendeten Verkehrsdaten stehen unter der [CC0-Lizenz](http://www.opendefinition.org/licenses/cc-zero) und können frei verwendet werden.
