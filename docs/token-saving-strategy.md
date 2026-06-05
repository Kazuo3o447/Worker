# Token-Saving Strategy – Azure AI Foundry Integration

## Grundprinzip

GEMA hat Millionen von Blobs. Jeder AI-Aufruf kostet Zeit und Tokens.
Der Classifier verwendet deshalb ein zweistufiges Schutzmodell:

1. **Dateityp-Router** (`app/file_type_router.py`): Entscheidet anhand der Dateierweiterung, ob eine Datei überhaupt an die KI übergeben werden darf (`ai_allowed=true/false`). Ausführbare Dateien, Archive, Medien und unbekannte Typen werden hart blockiert – ohne jeglichen KI-Aufruf.

2. **Conservative Policy** (`app/ai_policy.py`): Regeln klassifizieren alles, was sie sicher erkennen. KI wird nur bei echten Unsicherheitsfällen aufgerufen (class=unknown, niedrige Konfidenz).

Beide Stufen zusammen verhindern unnötige Tokenkosten.

---

## Wann wird KI NICHT aufgerufen?

### Stufe 1: Dateityp-Router (ai_allowed=False) – harte Blockierung

| Strategie | Dateitypen | Grund |
|---|---|---|
| `binary_technical` | .exe, .dll, .msi, .iso, .sys, .xlsm, .docm | Kein sinnvoller Text, Sicherheitsrisiko |
| `archive_container` | .zip, .7z, .rar, .tar, .gz | Im MVP nicht entpackt |
| `media_later` | .mp3, .wav, .mp4, .avi | Im MVP keine Transkription |
| `ocr_required` (OCR aus) | .jpg, .png, .tif | ALLOW_OCR=false (Standard) |
| `vision_required` (Vision aus) | .jpg, .png | ALLOW_VISION=false (Standard) |
| `unsupported` | .xyz, .psd, keine Erweiterung | Unbekannter Typ |

Für alle diese Typen gilt: `ai_allowed=False` – kein KI-Aufruf, unabhängig von allen anderen Einstellungen.

### Stufe 2: Conservative Policy (ai_policy.py) – regelbasierter Filter

| Bedingung | Grund |
|-----------|-------|
| `ENABLE_AI=false` | KI deaktiviert (Standard) |
| `AI_PROVIDER=none` | Kein Provider konfiguriert |
| `--mode scan` | Scan-Modus liest nur, klassifiziert nicht |
| `--dry-run` | Simulationslauf |
| `ai_calls_used >= AI_MAX_CALLS_PER_RUN` | Budget erschöpft |
| `rule_class=technical AND confidence >= 70` | Strukturdateien profitieren nicht von LLM |
| `rule_class=br AND confidence >= 90` | Betriebsrat-Erkennung durch Pfad ausreichend |
| `rule_class=dsgvo AND confidence >= 85` | Datenschutz-Keywords eindeutig |
| `rule_class=hr AND confidence >= 80` | HR-Pfade eindeutig |
| `rule_class=finance AND confidence >= 80` | Finance-Pfade eindeutig |
| `rule_class=contract AND confidence >= 75` | Vertrags-Keywords eindeutig |

**Hinweis:** Die frühere „Extension-Blockliste" in `ai_policy.py` ist jetzt durch den **Dateityp-Router** (Stufe 1) abgelöst. Der Router setzt `ai_allowed=False` für alle binären, archivierten und unbekannten Typen – bevor `ai_policy.py` überhaupt aufgerufen wird.

---

## Wann wird KI aufgerufen?

1. `class_label = "unknown"` – Kein Regel-Match
2. `reason_code = "no_rule_match"` – explizit kein Treffer
3. `confidence < 60` – sehr niedrige Regelkonfidenz
4. Unterhalb der klassenspezifischen Schwellenwerte (s. Tabelle oben)

---

## Token-Effizienz in v0

**Was wird an die KI gesendet:**
- Blob-Name (gekürzt auf 500 Zeichen)
- Dateiendung
- Dateigröße
- Regel-Klassifizierung (Klasse + Konfidenz)

**Was wird NICHT gesendet:**
- Dateiinhalt (kein Download in v0)
- Pfad-Komponenten über blob_name hinaus
- Andere Blob-Metadaten

**Max Input:** `AI_MAX_CHARS_PER_FILE=4000` (kürzbar, Standard reicht für Metadaten)

**Budget:** `AI_MAX_CALLS_PER_RUN=20` verhindert unkontrollierten Tokenverbrauch pro Lauf.

---

## Empfohlene Pilot-Einstellungen

```ini
ENABLE_AI=true
AI_PROVIDER=foundry
AI_MAX_CALLS_PER_RUN=50      # für größere Testläufe
AI_MAX_CHARS_PER_FILE=2000   # Metadaten brauchen keine 4000 chars
AI_MIN_CONFIDENCE_THRESHOLD=60
```

---

## Neue Config-Werte (zu ergänzen bei Extraction-Router-Implementierung)

```ini
# Extraktion
EXTRACTION_MAX_BYTES=5242880        # 5 MB – Dateien über Limit: size_warning=True
PDF_MAX_PAGES=3                     # Nur erste N PDF-Seiten extrahieren
PPTX_MAX_SLIDES=5                   # Nur erste N PPTX-Folien extrahieren
IMAGE_MAX_COUNT_PER_FILE=3          # Max. N Bilder aus PPTX/DOCX für Vision

# Token-Kostenschutz (global)
AI_MAX_TOTAL_CHARS_PER_RUN=50000    # Globales Zeichenlimit über alle Dateien eines Laufs

# Strategie-Freigaben (MVP-Standard: alle false)
ALLOW_OCR=false
ALLOW_VISION=false
ALLOW_ARCHIVE_EXTRACTION=false
```

---

## Zukünftige Token-Sparmaßnahmen (v1+)

- **Extraction-Router Light** (v0.5): `.docx` / `.pdf` / `.txt` extrahieren, ersten 500 Zeichen senden
- Batch-Calls: mehrere Blobs in einem Prompt (wenn Modell unterstützt)
- Konfidenz-Cache: ähnliche Pfadmuster müssen nicht mehrfach klassifiziert werden
- Async-Calls: parallele AI-Aufrufe für Batch-Verarbeitung
- `needs_ai`-Tag: `unknown`-Blobs gezielt markieren, zweite Stufe nur für diese starten

Siehe auch: [andre3000-dateityp-router.md](andre3000-dateityp-router.md) – vollständige Routing-Spezifikation
