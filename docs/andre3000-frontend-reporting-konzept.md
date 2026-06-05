# Andre3000 Frontend- und Reporting-Konzept

**Datum:** 2026-06-05  
**Projekt:** GEMA Azure Blob Storage Classification Worker „Andre3000"  
**Status:** Umgesetzt (MVP)

---

## 1. Zielbild

Das Dashboard soll kein reiner Report-Viewer sein, sondern ein echtes **Admin-Cockpit**: ein Admin versteht innerhalb von 30 Sekunden, ob alles OK ist, was der letzte Lauf ergeben hat, und welcher nächste Schritt sinnvoll ist.

**Leitprinzipien:**
- Auswertung & Anpassung: Möglichkeit zur Anpassung über das Frontend und Erstellung von Reports
- KISS: Streamlit bleibt die Basis, kein Overengineering
- Deutsch: alle Menüpunkte und Beschriftungen auf Deutsch
- Maximal 10 Menüpunkte, keine Dopplungen

---

## 2. Ausgangslage

### Bisheriges Frontend (Ist-Stand vor Umbau)

| Menüpunkt | Inhalt | Problem |
|---|---|---|
| Übersicht | run-summary.json KPIs | unklar – kein Health-Status, kein "Was tun?" |
| Klassenverteilung | Balkendiagramm + Metriktabelle | doppelt zu Klassifizierungs-Details |
| Klassifizierungs-Details | Detailtabelle mit Filtern | ok, aber getrennt von Verteilung |
| KI Readiness | AI-Kandidaten, Extensions | gut, aber nicht mit Cockpit verbunden |
| Fehler | classification-errors.csv | ok, fehlt Risk-Cards |
| Ungetaggte Dateien | untagged-files.csv | unklar für Admins |
| Stichproben / Review | classification-samples.csv | zu versteckt |
| Logs | run-events.jsonl | ok, gehört in Run Detail |
| Konfiguration | Config-Felder | ok |
| Run Commands | Command Builder | ok |
| Exporte | PDF/JSON/CSV Downloads | ok |

**Probleme:**
- 11 lose Menüpunkte ohne klare Hierarchie
- Keine Cockpit-Seite mit Health-Status und nächster Aktion
- Keine Runs-Liste (nur Single-Run-Selektor)
- Kein Run Detail mit vollständiger Interpretation
- "Klassenverteilung" und "Klassifizierungs-Details" redundant
- "Ungetaggte Dateien" = Fachbegriff ohne Kontext
- Keine Risk Cards
- admin-report.json hatte kein `worker_version`, kein `risk_assessment`, kein `file_type_distribution`

---

## 3. Probleme im bisherigen Frontend

1. **Kein Cockpit**: Kein 30-Sekunden-Überblick, kein Health-Ampel
2. **Kein Runs-Vergleich**: Nur ein Run auswählbar, keine Tabelle aller Runs
3. **Redundante Menüpunkte**: Klassenverteilung + Klassifizierungs-Details
4. **Fehlende Interpretation**: Rohdaten ohne Kontext ("Was bedeutet unknown=50?")
5. **Kein Dateitypen-Router**: Dateitypverteilung nicht sichtbar
6. **Keine Risk Cards**: Fehler und Risiken getrennt, keine Ampel
7. **admin-report.json unvollständig**: Kein `risk_assessment`, kein `worker_version`, keine `file_type_distribution`

---

## 4. Neue Informationsarchitektur

### Navigation (10 Bereiche)

| # | Menüpunkt | Zweck | Run-abhängig |
|---|---|---|---|
| 1 | **Cockpit** | Startseite, Health, KPIs, nächste Aktion | automatisch (letzter Run) |
| 2 | **Runs** | Tabelle aller Läufe, Filter | nein |
| 3 | **Run Detail** | Vollständige Auswertung eines Laufs | ja (Selektor) |
| 4 | **Klassifizierung** | Klassen, Details, Stichproben (Tabs) | ja |
| 5 | **KI Readiness** | AI-Kandidaten, Empfehlungen | ja |
| 6 | **Dateien & Dateitypen** | Dateitypverteilung, Extension-Aggregation | ja |
| 7 | **Fehler & Risiken** | Fehlertabelle + Risk Cards | ja |
| 8 | **Reports & Exporte** | Download aller Reports | ja |
| 9 | **Konfiguration** | Read-only Config-Übersicht | nein |
| 10 | **Run Commands** | Command Builder | nein |

### Entfernte / zusammengeführte Menüpunkte

| Alt | Neu |
|---|---|
| Übersicht | → aufgeteilt in **Cockpit** (letzte Lauf) + **Run Detail** (selektierter Lauf) |
| Klassenverteilung | → **Klassifizierung** Tab 1 |
| Klassifizierungs-Details | → **Klassifizierung** Tab 2 |
| Stichproben / Review | → **Klassifizierung** Tab 3 |
| Fehler | → **Fehler & Risiken** Tab 1 |
| Ungetaggte Dateien | → in **Fehler & Risiken** integriert |
| Logs | → Expander in **Run Detail** |
| Exporte | → **Reports & Exporte** (erweitert) |
| KI Readiness | → **KI Readiness** (erweitert) |
| Konfiguration | → **Konfiguration** (erweitert) |
| Run Commands | → **Run Commands** (angepasst) |

---

## 5. Seitenkonzept

### Cockpit (Seite 1)
- Header-Strip: Worker, Version, Storage, AI-Status, Source/Report Container
- Health-Ampel: Grün / Gelb / Rot
- Empfohlene nächste Aktion (aus admin-report.json oder berechnet)
- KPI-Karten: 12 Metriken in 3 Reihen
- Risk Cards aus admin-report.json
- Alle empfohlenen Maßnahmen (aufklappbar)

### Runs (Seite 2)
- Tabelle aller Runs mit: Run-ID, Datum, Modus, Dry Run, Force, Prefix, Max Files,
  Gesehen, Verarbeitet, Unknown, KI-Kandidaten, Fehler, Status
- Filter: Modus, Status, Fehler-Checkbox, Dry-Run-Checkbox, AI-Checkbox
- Hinweis: Run im Selektor auswählen → Run Detail öffnen

### Run Detail (Seite 3)
8 Abschnitte mit Interpretation:
1. Executive Summary (Health + nächste Aktion)
2. Azure-Kontext
3. Sicherheitsstatus (Dry Run? Force? AI?)
4. Verarbeitung (KPIs)
5. Klassifizierung (Verteilung)
6. KI Readiness (Kurzfassung)
7. Fehler (aus admin-report.json)
8. Report-Dateien (Dateiliste)

---

## 6. Cockpit-KPIs

| KPI | Quelle | Bedeutung |
|---|---|---|
| Letzter Run Status | run-summary.json.status | ok / partial / error |
| Mode | run-summary.json.mode | scan / classify |
| Gestartet | started_at | Zeitstempel |
| Dauer (s) | duration_seconds | Laufzeit |
| Dateien gesehen | files_seen | Alle gefundenen Blobs |
| Verarbeitet | files_processed | Tatsächlich verarbeitete Blobs |
| Klassifiziert | files_classified | Mit Klasse versehen |
| Unknown | files_unknown | Regelbasiert nicht erkannt |
| KI-Kandidaten | ai_candidates | Dateien, die KI brauchen |
| Fehler | files_error | Fehlgeschlagene Verarbeitungen |
| KI-Aufrufe | ai_calls_used | Tatsächliche LLM-Aufrufe |
| Durchsatz | throughput_files_per_hour | Effizienzmetrik |

### Health-Ampel-Logik

| Farbe | Bedingung |
|---|---|
| Grün | files_error=0 AND files_unknown=0 AND ai_candidates=0 |
| Gelb | files_unknown>0 OR ai_candidates>0 |
| Rot | files_error>0 |

---

## 7. Run Detail

Jeder Abschnitt interpretiert die Daten – nicht nur Rohdaten zeigen:

**Interpretation-Beispiel:**
- `files_unknown > 0` AND `ai_calls_used == 0` → "Diese Dateien wurden regelbasiert nicht erkannt. Nächster sinnvoller Schritt: Content Extraction + AI Dry Run."
- `dry_run == false` → "Dieser Lauf hat Tags/Metadata in Azure geschrieben."
- `force == true` → "Force-Modus war aktiv – bereits klassifizierte Dateien wurden neu verarbeitet."

---

## 8. KI Readiness

Ziel: Zeigen, welche Dateien durch KI klassifiziert werden sollten.

Quellen: `ai-candidates.csv`, `classification-details.csv`, `admin-report.json.ai_readiness`

Metriken: KI-Kandidaten, Unknown, Low Confidence (<60), KI-Aufrufe, KI-Übersprungen, needs_ai=true

Top-Dateiendungen unter KI-Kandidaten (Balkendiagramm).

**Nächste Aktionen:** Command-Vorschlag für KI-Dry-Run wird generiert (kein Start-Button).

---

## 9. Dateitypen / Router-Sicht

Quellen:
1. `admin-report.json.file_type_distribution` (bevorzugt)
2. `classification-details.csv` Extension-Aggregation (Fallback)

Anzeigen: Extension-Verteilung, Gesamt-Bytes, Ø Bytes, Lesbar/Unlesbar, Archiv-Kandidaten

Tabs: Übersicht | Dateidetails

Hinweis: `route_strategy` ist in classification-details.csv nicht vorhanden (nur im Dateityp-Router intern). Wird angezeigt wenn verfügbar.

---

## 10. Fehler & Risiken

**Tab 1 – Fehler:**
- Fehlertabelle aus classification-errors.csv
- Metriken: Fehler gesamt, Fehler-Stufen, Retry empfohlen, Unlesbar/Unsupported

**Tab 2 – Risiken:**
Risk Cards (dynamisch berechnet):
- KI-Kandidaten vorhanden, aber KI deaktiviert
- unknown > 80% der verarbeiteten Dateien
- Fehler vorhanden (Retry empfohlen)
- Reports nicht hochgeladen

Plus: `admin-report.json.risk_assessment` (Backend-berechnete Risiken)

---

## 11. Reports & Exporte

Downloads angeboten für:
- admin-report.pdf (Primär-Report)
- admin-report.json (Maschinenlesbar)
- run-summary.json
- classification-details.csv
- classification-summary.csv
- classification-errors.csv
- untagged-files.csv
- classification-samples.csv
- ai-candidates.csv
- run-events.jsonl

Wenn Report fehlt: "Dieser Run wurde vor Einführung der Admin-Reports erzeugt."

Dateiliste über `repo.list_report_files(run_id)`.

---

## 12. Admin-Report JSON

### Schema (`admin-report.json`)

```json
{
  "report_type": "admin-report",
  "generated_at": "ISO8601",
  "worker_name": "Andre3000",
  "worker_version": "pilot-v0.1",
  "run": {
    "run_id": "...",
    "mode": "classify",
    "dry_run": true,
    "force": false,
    "started_at": "...",
    "finished_at": "...",
    "duration_seconds": 42.0
  },
  "azure": {
    "storage_account": "...",
    "source_container": "...",
    "report_container": "...",
    "prefix": "..."
  },
  "safety": {
    "writes_enabled": false,
    "ai_enabled": false,
    "ai_provider": "none",
    "force": false,
    "max_files": 50
  },
  "metrics": {
    "files_seen": 50,
    "files_untagged": 50,
    "files_skipped": 0,
    "files_processed": 50,
    "files_classified": 0,
    "files_unknown": 50,
    "files_error": 0,
    "ai_candidates": 50,
    "ai_calls_used": 0,
    "ai_calls_skipped": 50,
    "ai_errors": 0,
    "rules_only_count": 50,
    "llm_used_count": 0
  },
  "classification_distribution": { "unknown": 50 },
  "file_type_distribution": [
    { "extension": ".doc", "count": 50, "total_bytes": 512000 }
  ],
  "ai_readiness": {
    "candidates_total": 50,
    "unknown_total": 50,
    "low_confidence_total": 50,
    "ai_disabled_total": 50,
    "needs_ai_total": 50,
    "top_extensions": [{ "ext": ".doc", "count": 50 }]
  },
  "errors_summary": [],
  "risk_assessment": [
    {
      "risk": "ai_candidates_but_ai_off",
      "message": "KI-Kandidaten vorhanden (50), aber KI deaktiviert",
      "severity": "warning"
    }
  ],
  "next_actions": [
    "KI-Dry-Run vorbereiten: 50 AI-Kandidaten gefunden ..."
  ],
  "report_files": ["run-summary.json", "classification-details.csv", "..."]
}
```

---

## 13. Admin-Report PDF & Dynamische Bericht-Generierung

Erzeugt mit ReportLab (best-effort – PDF-Fehler blockieren keinen Lauf). 

### Layout & Orientierungswechsel (Portrait/Landscape)
Der PDF-Bericht verwendet nun abwechselnde Seitenausrichtungen (Dual-Page-Design mit `BaseDocTemplate`):
- **Hochformat (A4 Portrait):** Titelseite, Run Information, Azure-Kontext, KPIs, Klassenverteilung und Fehlerübersicht.
- **Querformat (A4 Landscape / Längsseite):** Verwendet für den Bereich **Stichproben**. Hier steht das gesamte A4-Querformat (25,7 cm bedruckbare Breite) zur Verfügung, sodass 15 representative Dateien übersichtlich mit allen Details gelistet werden.
- **Spalten der Stichproben-Tabelle (A4 Landscape):**
  1. Blob-Name (gekürzt auf max. 65 Zeichen, um ein sauberes Druckbild zu garantieren)
  2. Klasse
  3. Konfidenzwert (Conf.)
  4. DSGVO-Relevanz
  5. Archivierungs-Kandidat
  6. LLM-Einsatz
  7. Grundcode / Pfad-Regel
- **Rückkehr zum Hochformat:** Nach den Stichproben wird zurück auf das Portrait-Layout geschaltet.

### Native Vektor-Kreisdiagramme
Integrierte, hochauflösende Vektor-Kreisdiagramme nebeneinander (Side-by-Side) mit den Daten-Tabellen für:
- **Klassenverteilung**
- **Dateitypenverteilung** (die Top-5-Dateiendungen einzeln aufgelistet, kleinere Mengen aggregiert unter „Andere“)

### On-The-Fly-PDF-Compiler im Frontend
Um zu verhindern, dass Benutzer beim Auswerten älterer Läufe veraltete PDF-Dateien aus Azure herunterladen, wurde im Frontend-Dashboard ein **Live-HTML/PDF-Compiler** implementiert:
- Bei jedem Klick auf den Download-Button des PDF-Berichts kompiliert das Streamlit-Dashboard die rohen CSV-Ergebnisdaten des Laufs live im Arbeitsspeicher zu einem topaktuellen PDF-Bericht (mit den neuen Vektordiagrammen und Längsseiten-Querformaten).
- Sollten rohe CSV-Daten fehlen, erfolgt ein automatischer Fallback auf den statisch hochgeladenen PDF-Bericht in Azure.

---

## 14. GEMA-konformes Enterprise Design & Seriöse Optik

Um dem professionellen Anspruch der GEMA gerecht zu werden, wurde das gesamte Frontend-Design überarbeitet:
- **Keine bunten/verspielten Emojis:** Alle Emoticons (wie `📊`, `🏷️`, `📁`, `🔐`, `🎯`, `🤖`, `📤`, `⬇`, `⚠️` etc.) wurden konsequent aus allen Titeln, Menüs, Sektionen, KPIs und Aktions-Bannern eliminiert.
- **Farblich harmonisches Interface:** Sämtliche Diagramme (sowohl Altair-Donut-Diagramme im Cockpit als auch ReportLab-Kuchendiagramme im PDF) nutzen eine perfekt aufeinander abgestimmte, sachliche Farbpalette auf Basis von GEMA-nahen Blau-, Teal- und Grautönen.
- **Korrektur von Altair-Diagrammen:** Bei Single-Class- oder Single-Extension-Zuständen (z. B. wenn alle Dateien als `unknown` erfasst wurden) wird die Altair-Theta-Achse jetzt sauber gestapelt (`stack=True`), um Fehler wie „Infinite extent“ im Browser vollständig auszuschließen.

---

## 15. Sicherheitsregeln

### Schreib- und Anpassungsrechte (Frontend)
- Schreiboperationen und Report-Anpassungen sind über das Frontend möglich (nicht mehr rein lesend)
- Worker-Start und AI-Aufrufe können bei Bedarf integriert und gesteuert werden

### Secret-Schutz (Konfigurationsseite)
Nie anzeigen:
- `AZURE_STORAGE_CONNECTION_STRING`
- API Keys
- Account Keys

Stattdessen: "Secret-Konfiguration aktiv – Wert wird nicht angezeigt."

### Command Builder (Run Commands)
- Erzeugt nur Shell-Befehle (kein Ausführen)
- Warnhinweise für echte Classify-Läufe, --force, AI-Aktivierung, max-files > 50

---

## 15. AdminLTE vs Streamlit – Bewertung

### Option A: Streamlit (Gewählt für MVP)

**Vorteile:**
- Bestehendes Setup, keine Umbauzeit
- Auth-Logik (Device Code, DefaultAzureCredential) bleibt erhalten
- Azure Blob Repository bleibt nutzbar
- 10 Seiten mit Tabs realisierbar
- Pandas DataFrames + st.bar_chart reichen für MVP-Visualisierungen

**Nachteile:**
- Navigation: sidebar radio (kein echtes Routing)
- Tabellen: kein Server-Side Paging für sehr große DataFrames
- Layout: begrenzte Flexibilität

### Option B: AdminLTE + FastAPI/Jinja

**Vorteile:**
- Professionelle Admin-Optik
- Echte Navigation mit URLs
- Bessere Tabellen (DataTables, Server-Side Sorting/Filtering)
- Sidebar-Layout nativ vorhanden

**Nachteile:**
- Kompletter Umbau (2-3 Tage Entwicklungszeit)
- Auth-Logik muss neu implementiert werden
- Azure SDK bleibt gleich, aber API-Layer nötig

### Empfehlung

**MVP: Streamlit behalten.** Das überarbeitete Dashboard ist funktional vollständig für den Pilotbetrieb.

**Mittelfristig (nach KI-Integration):** AdminLTE als statischer Prototyp evaluieren. Wenn die Datenmenge wächst und echte Reports mit vielen Zeilen kommen, lohnt sich der Umbau.

Entscheidungskriterien für AdminLTE-Migration:
- Mehr als 3 gleichzeitige Admin-User
- DataFrames mit >10.000 Zeilen
- Bedarf für echte URL-Navigation / Deep Links
- Bedarf für Dashboards die außerhalb von Streamlit eingebettet werden

---

## 16. Offene Punkte

1. **route_strategy** ist nicht in classification-details.csv verfügbar (nur intern im Dateityp-Router). Wenn dieser Wert in Reports geschrieben werden soll, muss `_DETAIL_COLS` in `reports.py` erweitert werden.
2. **Content Extraction**: Noch nicht implementiert. Dateien mit `class=unknown` bleiben KI-Kandidaten bis Content Extraction + AI Dry Run durchgeführt wird.
3. **OCR/Vision**: Bilder und gescannte PDFs werden noch nicht verarbeitet. Sichtbar in "Dateien & Dateitypen".
4. **Admin-Report PDF**: Wird best-effort erzeugt. Wenn ReportLab nicht installiert ist, wird kein PDF erzeugt (kein Fehler im Worker-Lauf).
5. **`_all_summaries()` Performance**: Lädt alle run-summary.json sequenziell. Bei vielen Runs (>20) könnte dies die "Runs"-Seite verlangsamen. Lösung: Parallelisierung oder Run-Metadaten in Blob-Metadata cachen.

---

## 17. Nächste Schritte

### Prio 1 (direkt umsetzbar)
- [ ] Content Extraction Light (`--mode extract`) implementieren
- [ ] AI Dry Run mit 5-10 Dateien durchführen
- [ ] `route_strategy` in classification-details.csv schreiben

### Prio 2 (nach erfolgreichem AI Dry Run)
- [ ] AI Full Run mit `--max-files 50`
- [ ] `needs_ai`-Tag in Azure schreiben (Pilot-Entscheidung nötig)
- [ ] Admin-Report PDF: Dateitypverteilung hinzufügen

### Prio 3 (mittelfristig)
- [ ] AdminLTE Prototyp evaluieren (wenn User-Bedarf steigt)
- [ ] Server-Side Filtering für große classification-details.csv
- [ ] Authentifizierung: Dashboard-Zugriff beschränken (Managed Identity)

---

*Dokument erstellt: 2026-06-05 · Andre3000 pilot-v0.1*
