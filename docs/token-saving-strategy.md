# Token-Saving Strategy – Azure AI Foundry Integration

## Grundprinzip

GEMA hat Millionen von Blobs. Jeder AI-Aufruf kostet Zeit und Tokens.
Der Classifier verwendet deshalb ein **Conservative Policy**-Modell:
Regeln klassifizieren alles, was sie sicher erkennen. KI wird nur bei echten Unsicherheitsfällen aufgerufen.

---

## Wann wird KI NICHT aufgerufen?

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
| Extension in Blockliste | `.exe`, `.dll`, `.zip`, `.tar`, `.gz`, `.7z`, `.rar`, `.iso`, `.img`, `.jpg`, `.jpeg`, `.png`, `.gif`, `.bmp`, `.tiff`, `.svg`, `.mp3`, `.mp4`, `.avi`, `.mov`, `.mkv` |

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

## Zukünftige Token-Sparmaßnahmen (v1+)

- Textextraktion für Office/PDF: nur ersten 500 Zeichen des Dokuments senden
- Batch-Calls: mehrere Blobs in einem Prompt (wenn Modell unterstützt)
- Konfidenz-Cache: ähnliche Pfadmuster müssen nicht mehrfach klassifiziert werden
- Async-Calls: parallele AI-Aufrufe für Batch-Verarbeitung
