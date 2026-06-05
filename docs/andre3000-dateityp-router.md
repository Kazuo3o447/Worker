# Andre3000 Dateityp-Router

**Projekt:** GEMA Azure Blob Storage Classification Worker „Andre3000"  
**Version:** pilot-v0.1  
**Stand:** 2026-06-05  
**Status:** Implementiert und getestet

---

## 1. Zweck

Der Dateityp-Router ist die Entscheidungsschicht zwischen **Blob-Erkennung** und **KI-Klassifikation**.

Er beantwortet für jeden gefundenen Blob vier Fragen:

1. **Welche Art Datei liegt vor?** (Strategie)
2. **Kann Text extrahiert werden?** (extraction_required)
3. **Braucht die Datei OCR oder Vision?** (ocr_required, vision_required)
4. **Darf sie überhaupt an die KI übergeben werden?** (ai_allowed)

Diese Entscheidung trifft Andre3000 **vor** der KI – ausschließlich anhand von Dateiendung, Größe und optionalem Content-Type. Keine Inhalte werden gelesen, keine Azure-Operationen durchgeführt.

---

## 2. Rolle im Gesamtprozess

```
Blob gefunden (Blob Storage)
        │
        ▼
┌─────────────────────────────┐
│     Dateityp-Router         │  ← app/file_type_router.py
│  route_blob(blob_name, ...) │
└─────────────────────────────┘
        │
        ▼  FileTypeRoute
┌─────────────────────────────┐
│  Extraktions-Router         │  ← app/extraction_router.py (noch nicht implementiert)
│  (Text / OCR / Vision)      │
└─────────────────────────────┘
        │
        ▼  Textauszug (begrenzt)
┌─────────────────────────────┐
│  KI-Klassifikation          │  ← app/ai_foundry_client.py
│  (nur wenn ai_allowed=True) │
└─────────────────────────────┘
        │
        ▼  KI-Antwort
┌─────────────────────────────┐
│  Validierung & Merge        │  ← app/ai_policy.py
│  (Andre3000 prüft KI-Output)│
└─────────────────────────────┘
        │
        ▼
┌─────────────────────────────┐
│  Tags & Metadata schreiben  │  ← app/worker.py
│  (nur Andre3000 schreibt)   │
└─────────────────────────────┘
```

Der Router ist **zustandslos** und **rein deterministisch**. Er trifft dieselbe Entscheidung für denselben Input, jederzeit reproduzierbar.

---

## 3. Was der Router macht

- Extension aus `blob_name` normalisieren (lowercase, mit Punkt)
- Extension auf bekannte Gruppen prüfen (Mapping)
- Dateigröße gegen `extraction_max_bytes` prüfen
- `ai_allowed`, `extraction_required`, `ocr_required`, `vision_required` ableiten
- `class_hint` setzen bei Dateien, die keine KI brauchen (z.B. `technical` für `.exe`)
- `skip_reason` und `reason_code` setzen für Reports
- `size_warning` setzen wenn die Datei zu groß für Extraktion ist
- Ein vollständiges `FileTypeRoute`-Objekt zurückgeben

---

## 4. Was der Router nicht macht

| Was | Warum nicht |
|---|---|
| Dateiinhalte lesen | Keine Downloads beim Routing |
| Azure Blob Tags schreiben | Nur Andre3000/worker.py darf schreiben |
| KI aufrufen | Nur nach Extraktion und Validierung |
| Dateien bewegen oder löschen | Keine Lifecycle-Logik im Router |
| Magic Bytes prüfen | Noch nicht implementiert (siehe §14) |
| Passwortschutz erkennen | Noch nicht implementiert |
| Content-Type als alleinige Grundlage | Extension hat Vorrang; Content-Type optional |

---

## 5. Unterstützte Routing-Strategien

### 1. `direct_text`

Einfache Textdateien, die direkt gelesen werden können.

**Erweiterungen:**
`.txt`, `.csv`, `.json`, `.xml`, `.log`, `.ini`, `.yaml`, `.yml`, `.md`, `.rst`, `.tsv`, `.nfo`, `.sql`, `.ps1`, `.sh`, `.bat`, `.cmd`, `.config`

**Verhalten:**
- `ai_allowed=True`
- `extraction_required=True`
- Keine OCR, kein Vision

---

### 2. `office_text`

Moderne Office-Dateien (ZIP-basiert), aus denen Text extrahierbar ist.

**Erweiterungen:**
`.docx`, `.xlsx`, `.pptx`, `.odt`, `.ods`, `.odp`

**Verhalten:**
- `ai_allowed=True`
- `extraction_required=True`
- Keine OCR, kein Vision

**Wichtiger Hinweis zu PPTX:**  
Präsentationen können eingebettete Bilder enthalten. Der Router markiert `.pptx` als `office_text`, da Text aus Textboxen extrahierbar ist. Eingebettete Bilder/Screenshots in PPTX benötigen Vision oder OCR – dies ist in einem späteren Extraction-Router zu adressieren.

---

### 3. `legacy_office`

Ältere Office-Formate. Text-Extraktion ist technisch aufwändiger als bei modernen Formaten.

**Erweiterungen:**
`.doc`, `.xls`, `.ppt`, `.rtf`, `.wps`, `.wpd`

**Verhalten:**
- `ai_allowed=True`
- `extraction_required=True`
- Keine OCR, kein Vision

**Hinweis zur Implementierung des Extraction-Routers:**  
Für Legacy-Office-Formate existieren mehrere Optionen: LibreOffice (Konvertierung zu DOCX/XLSX), Apache Tika, Azure Document Intelligence, oder python-docx für `.doc`-Näherung. Im MVP ist die Extraktionsstrategie noch nicht implementiert – der Router markiert die Strategie korrekt, der Extraction-Router entscheidet später.

---

### 4. `pdf_text`

Digitale PDFs mit eingebettetem Text.

**Erweiterungen:**
`.pdf`

**Verhalten:**
- `ai_allowed=True`
- `extraction_required=True`
- Keine OCR, kein Vision

**Hinweis:**  
Gescannte PDFs (nur Bild, kein eingebetteter Text) werden erst nach einem Inhalts-Check erkennbar. Der Dateityp-Router kann dies anhand der Extension allein nicht unterscheiden. Im Extraction-Router wird PDF_TEXT Extraktionsergebnis leer sein → dann `ocr_required=True` nachträglich setzen.

---

### 5. `ocr_required`

Bilder oder gescannte Dokumente, bei denen Text per OCR erkannt werden muss.

**Erweiterungen:**
`.jpg`, `.jpeg`, `.png`, `.tif`, `.tiff`, `.bmp`, `.gif`, `.webp`

**Verhalten:**
- `ai_allowed=True` **nur wenn** `ALLOW_OCR=true` (Config-Parameter)
- `ocr_required=True` wenn OCR aktiviert
- Wenn OCR deaktiviert und Vision deaktiviert: `ai_allowed=False`, `skip_reason=ocr_and_vision_disabled`

---

### 6. `vision_required`

Bilder, bei denen ein visuelles Modell (Vision-LLM) eingesetzt werden soll.

**Erweiterungen:**
Identisch mit `ocr_required` (`.jpg`, `.png` etc.) – Unterschied liegt in der Config-Aktivierung.

**Priorität:** OCR hat Vorrang vor Vision, wenn beide aktiviert sind.

**Verhalten:**
- `ai_allowed=True` **nur wenn** `ALLOW_VISION=true`
- `vision_required=True`
- Keine traditionelle Extraktion nötig

---

### 7. `archive_container`

ZIP- und andere Container-Formate. Im MVP werden Archive **nicht entpackt**.

**Erweiterungen:**
`.zip`, `.7z`, `.rar`, `.tar`, `.gz`, `.bz2`, `.xz`, `.cab`, `.z`

**Verhalten:**
- `ai_allowed=False`
- `extraction_required=False`
- `skip_reason=archive_not_processed`

**Begründung:**  
Entpacken von Archiven ohne Kontrolle birgt Sicherheitsrisiken (Zip Bomb, nested archives, ausführbare Inhalte). Im MVP wird gemeldet, nicht verarbeitet.

---

### 8. `binary_technical`

Ausführbare Dateien, Systemdateien, kompilierter Code. Werden **niemals** an die KI gesendet.

**Erweiterungen:**
`.exe`, `.dll`, `.msi`, `.bin`, `.iso`, `.sys`, `.so`, `.com`, `.scr`, `.vbs`, `.jar`, `.class`, `.pyc`, `.pyd`, `.o`, `.obj`, `.lib`, `.a`

**Auch betroffen:** Makro-fähige Office-Dateien (`.xlsm`, `.xlsb`, `.docm`, `.pptm`)

**Verhalten:**
- `ai_allowed=False`
- `class_hint="technical"` → direkte Klassifikation ohne KI
- `skip_reason=binary_not_sent_to_ai`

---

### 9. `media_later`

Audio- und Videodateien. Im MVP nicht verarbeitet, später per Transkription möglich.

**Erweiterungen:**
`.mp3`, `.wav`, `.flac`, `.aac`, `.ogg`, `.mp4`, `.mov`, `.avi`, `.mkv`, `.wmv`, `.flv`

**Verhalten:**
- `ai_allowed=False`
- `skip_reason=media_not_processed_in_mvp`

---

### 10. `unsupported`

Alle Erweiterungen, die keiner anderen Gruppe zugeordnet werden können.

**Verhalten:**
- `ai_allowed=False`
- `skip_reason=unsupported_file_type`

---

### 11. `unreadable`

Für beschädigte, verschlüsselte oder nicht lesbare Dateien.  
**Noch nicht im Router implementiert** – wird im Extraction-Router gesetzt, wenn die Extraktion scheitert.

---

## 6. Dateityp-Matrix

| Erweiterung | Strategie | ai_allowed | extraction_required | ocr_required | vision_required | class_hint |
|---|---|---|---|---|---|---|
| .txt, .csv, .log | direct_text | ✅ True | ✅ True | ❌ | ❌ | — |
| .json, .xml, .yaml | direct_text | ✅ True | ✅ True | ❌ | ❌ | — |
| .ps1, .sql, .ini | direct_text | ✅ True | ✅ True | ❌ | ❌ | — |
| .docx, .xlsx, .pptx | office_text | ✅ True | ✅ True | ❌ | ❌ | — |
| .odt, .ods, .odp | office_text | ✅ True | ✅ True | ❌ | ❌ | — |
| .doc, .xls, .ppt | legacy_office | ✅ True | ✅ True | ❌ | ❌ | — |
| .rtf, .wps | legacy_office | ✅ True | ✅ True | ❌ | ❌ | — |
| .pdf | pdf_text | ✅ True | ✅ True | ❌ | ❌ | — |
| .jpg, .png, .tif (OCR=on) | ocr_required | ✅ True | ✅ True | ✅ | ❌ | — |
| .jpg, .png (Vision=on) | vision_required | ✅ True | ❌ | ❌ | ✅ | — |
| .jpg, .png (beide aus) | ocr_required | ❌ False | ❌ | ❌ | ❌ | — |
| .zip, .7z, .rar, .tar | archive_container | ❌ False | ❌ | ❌ | ❌ | — |
| .exe, .dll, .msi | binary_technical | ❌ False | ❌ | ❌ | ❌ | technical |
| .xlsm, .docm (Makros) | binary_technical | ❌ False | ❌ | ❌ | ❌ | technical |
| .mp3, .wav, .mp4 | media_later | ❌ False | ❌ | ❌ | ❌ | — |
| .xyz, .psd, (unbekannt) | unsupported | ❌ False | ❌ | ❌ | ❌ | — |

---

## 7. Ergebnisobjekt

```python
@dataclass
class FileTypeRoute:
    blob_name: str          # Voller Blob-Pfad
    extension: str          # Normalisierte Extension (z.B. ".docx")
    content_type: Optional[str]  # Azure Content-Type, falls vorhanden
    size_bytes: int         # Dateigröße in Bytes (0 = unbekannt)

    strategy: str           # Eine der STRATEGY_*-Konstanten
    ai_allowed: bool        # Darf die KI diese Datei verarbeiten?
    extraction_required: bool  # Muss Text extrahiert werden?
    ocr_required: bool      # Braucht Bildinhalt OCR?
    vision_required: bool   # Braucht Bildinhalt Vision-LLM?

    class_hint: Optional[str]  # Direkte Klasse ohne KI ("technical", "unknown")
    skip_reason: Optional[str] # Warum KI nicht aufgerufen wird
    reason_code: str        # Maschinenlesbarer Code für Reports
    size_warning: bool      # True wenn Datei zu groß für Extraktion
```

### Beispiel: Verarbeitbare Datei

```json
{
  "blob_name": "_root_part000/vertrag_2024.docx",
  "extension": ".docx",
  "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "size_bytes": 45000,
  "strategy": "office_text",
  "ai_allowed": true,
  "extraction_required": true,
  "ocr_required": false,
  "vision_required": false,
  "class_hint": null,
  "skip_reason": null,
  "reason_code": "route_office_text",
  "size_warning": false
}
```

### Beispiel: Blockierte Datei

```json
{
  "blob_name": "tools/setup.exe",
  "extension": ".exe",
  "content_type": null,
  "size_bytes": 1048576,
  "strategy": "binary_technical",
  "ai_allowed": false,
  "extraction_required": false,
  "ocr_required": false,
  "vision_required": false,
  "class_hint": "technical",
  "skip_reason": "binary_not_sent_to_ai",
  "reason_code": "route_binary_executable",
  "size_warning": false
}
```

### Beispiel: Zu große Datei

```json
{
  "blob_name": "berichte/jahresabschluss_2023_komplett.pdf",
  "extension": ".pdf",
  "content_type": "application/pdf",
  "size_bytes": 52428800,
  "strategy": "pdf_text",
  "ai_allowed": true,
  "extraction_required": true,
  "ocr_required": false,
  "vision_required": false,
  "class_hint": null,
  "skip_reason": "file_too_large_for_extraction",
  "reason_code": "route_pdf_text",
  "size_warning": true
}
```

---

## 8. Beispiele

### .docx → office_text

```
blob_name: "vertraege/rahmenvertrag_2024.docx"
extension: .docx
→ strategy:            office_text
→ ai_allowed:          true
→ extraction_required: true
→ reason_code:         route_office_text
```

### .exe → binary_technical

```
blob_name: "tools/deploy_helper.exe"
extension: .exe
→ strategy:   binary_technical
→ ai_allowed: false
→ class_hint: technical
→ skip_reason: binary_not_sent_to_ai
→ reason_code: route_binary_executable
```

### .jpg (OCR=false, Vision=false)

```
blob_name: "scans/eingangspost_001.jpg"
extension: .jpg
→ strategy:   ocr_required
→ ai_allowed: false
→ skip_reason: ocr_and_vision_disabled
→ reason_code: route_image_no_extractor
```

### .jpg (OCR=true)

```
blob_name: "scans/eingangspost_001.jpg"
extension: .jpg
allow_ocr: true
→ strategy:      ocr_required
→ ai_allowed:    true
→ ocr_required:  true
→ reason_code:   route_ocr_required
```

### .zip → archive_container

```
blob_name: "backup_2024_Q1.zip"
extension: .zip
→ strategy:   archive_container
→ ai_allowed: false
→ skip_reason: archive_not_processed
→ reason_code: route_archive_container
```

### .doc (Pilot-Testdaten)

```
blob_name: "_root_part000/100001_24042013 155126.doc"
extension: .doc
→ strategy:            legacy_office
→ ai_allowed:          true
→ extraction_required: true
→ reason_code:         route_legacy_office
```

**Hinweis:** Die aktuellen Pilotdaten (numerische `.doc`-Dateien) werden als `legacy_office` geroutet. Wenn eine Extraktions-Strategie für Legacy-Office implementiert wird, können diese Dateien erstmals textbasiert klassifiziert werden. Das würde die aktuelle 100%-`unknown`-Quote deutlich reduzieren.

---

## 9. Token- und Kostenschutz

Der Router schützt vor unnötigen KI-Kosten durch folgende Regeln:

### Hartcodierte Schutzregeln (Router-Ebene)

| Regel | Beschreibung |
|---|---|
| Keine Binärdateien | `.exe`, `.dll` etc. niemals an KI |
| Keine Archive entpacken (MVP) | `.zip`, `.rar` etc. blockiert |
| Keine Medien (MVP) | `.mp3`, `.mp4` etc. blockiert |
| Makro-Office blockiert | `.xlsm`, `.docm` etc. als `binary_technical` |
| Unbekannte Typen blockiert | `unsupported` → kein KI-Aufruf |

### Konfigurierbare Schutzregeln (Config-Ebene)

| Config-Variable | Bedeutung |
|---|---|
| `AI_MAX_CHARS_PER_FILE` | Max. Zeichen pro Datei, die an KI übergeben werden |
| `AI_MAX_CALLS_PER_RUN` | Max. KI-Aufrufe pro Lauf |
| `EXTRACTION_MAX_BYTES` | Dateien über diesem Limit: `size_warning=True` |
| `ALLOW_OCR` | OCR-Strategie aktivieren |
| `ALLOW_VISION` | Vision-Strategie aktivieren |

### Empfohlene neue Config-Werte (noch nicht implementiert)

| Variable | Empfohlener Wert | Beschreibung |
|---|---|---|
| `AI_MAX_TOTAL_CHARS_PER_RUN` | 50000 | Globales Zeichenlimit pro Lauf (alle Dateien zusammen) |
| `EXTRACTION_MAX_BYTES` | 5242880 (5 MB) | Max. Dateigröße für Extraktion |
| `PDF_MAX_PAGES` | 3 | Nur erste N Seiten einer PDF extrahieren |
| `PPTX_MAX_SLIDES` | 5 | Nur erste N Folien einer PPTX extrahieren |
| `IMAGE_MAX_COUNT_PER_FILE` | 3 | Max. N Bilder aus PPTX/DOCX für Vision |
| `ALLOW_ARCHIVE_EXTRACTION` | false | Archiv-Entpackung freigeben (MVP: false) |
| `ALLOW_VISION` | false | Vision-Strategie freigeben (MVP: false) |
| `ALLOW_OCR` | false | OCR-Strategie freigeben (MVP: false) |

Diese Werte sollten in `app/config.py` ergänzt werden, wenn die entsprechenden Extractors implementiert werden.

---

## 10. Sicherheitsregeln

### Ausführbare Dateien

- Dateien mit den Erweiterungen `.exe`, `.dll`, `.msi`, `.bin`, `.iso`, `.sys`, `.so`, `.com`, `.scr`, `.vbs`, `.jar`, `.class` werden **niemals** an die KI übergeben.
- `ai_allowed=False` ist dauerhaft für diese Typen gesetzt.
- Sie erhalten `class_hint="technical"` für die direkte Klassifikation ohne KI.

### Makro-Office

- `.xlsm`, `.xlsb`, `.docm`, `.pptm` enthalten potenziell ausführbaren VBA-Code.
- Behandlung wie `binary_technical`: `ai_allowed=False`, `class_hint="technical"`.
- Können in Zukunft auf einer Whitelist freigeschaltet werden (nach expliziter Prüfung).

### Archive

- Archive werden nicht entpackt.
- Keine Inhaltsanalyse ohne explizite Freigabe (`ALLOW_ARCHIVE_EXTRACTION=false`).
- **Zip Bomb Protection** ist beim Entpacken (wenn je implementiert) Pflicht.

### Größenlimits

- Dateien über `EXTRACTION_MAX_BYTES` werden mit `size_warning=True` markiert.
- Der Extraction-Router (nächste Stufe) entscheidet dann über Sampling oder Ablehnung.
- Der KI-Input wird zusätzlich durch `AI_MAX_CHARS_PER_FILE` begrenzt.

### Trennungsprinzip (KI-Sicherheit)

- Die KI erhält **nur aufbereitete Textauszüge** – niemals direkten Blob-Zugriff.
- Die KI schreibt **keine Tags** und **keine Metadata** – das tut nur Andre3000.
- Die KI kann **keine Azure-Operationen** auslösen.

---

## 11. Zusammenspiel mit KI

```
FileTypeRoute (ai_allowed=True)
        │
        ▼
Extraction-Router (noch nicht implementiert)
→ Text extrahieren (begrenzt auf AI_MAX_CHARS_PER_FILE)
→ Extrakt als String
        │
        ▼
KI-Klassifikation
→ Input: { blob_name, extension, extracted_text, size_bytes }
→ Output: { class_label, confidence, dsgvo, reason }
        │
        ▼
Andre3000 validiert KI-Antwort (app/ai_policy.py)
→ Mindest-Confidence prüfen
→ Erlaubte Klassen prüfen
→ Bei Zweifel: Fallback auf Regelbasiert
        │
        ▼
Tags & Metadata schreiben (app/worker.py)
```

**Wenn `ai_allowed=False`:**

```
FileTypeRoute (ai_allowed=False, class_hint="technical")
        │
        ▼
Direkte Klassifikation ohne KI:
→ class_label = class_hint
→ confidence = 70
→ reason_code = route_binary_executable
        │
        ▼
Tags & Metadata schreiben (app/worker.py)
```

---

## 12. Zusammenspiel mit Reports

Alle Routing-Entscheidungen sollen in zukünftige Report-Dateien einfließen. Empfohlene Felder in `classified-blobs.csv` und `run-summary.json`:

| Feld | Beschreibung |
|---|---|
| `extension` | Normalisierte Dateierweiterung |
| `content_type` | Azure Blob Content-Type |
| `route_strategy` | z.B. `office_text`, `binary_technical` |
| `extraction_required` | true / false |
| `extraction_status` | success / failed / skipped / size_limit |
| `ai_allowed` | true / false |
| `ai_used` | true / false |
| `ai_skipped_reason` | ai_disabled / ai_not_allowed / size_limit / … |
| `skip_reason` | binary_not_sent_to_ai / archive_not_processed / … |
| `reason_code` | route_office_text / route_binary_executable / … |
| `extracted_chars` | Anzahl extrahierter Zeichen |
| `estimated_tokens` | Geschätzte Token-Zahl (chars / 4) |
| `estimated_cost` | Geschätzte Kosten in EUR/USD |
| `pages_sampled` | Verarbeitete Seiten (PDF) |
| `slides_sampled` | Verarbeitete Folien (PPTX) |
| `vision_used` | true / false |
| `ocr_used` | true / false |
| `size_warning` | true / false |

Diese Felder ermöglichen ein vollständiges Audit: Was wurde geroutet, was extrahiert, was an KI gegeben, was hat gekostet.

---

## 13. Empfohlene Konfigurationswerte

### Bereits in `.env` vorhanden

```env
ENABLE_AI=false
AI_PROVIDER=none
AI_MAX_CALLS_PER_RUN=20
AI_MAX_CHARS_PER_FILE=4000
AI_MIN_CONFIDENCE_THRESHOLD=60
```

### Zu ergänzen in `.env.example` und `app/config.py`

```env
# Extraktion
EXTRACTION_MAX_BYTES=5242880        # 5 MB
PDF_MAX_PAGES=3
PPTX_MAX_SLIDES=5
IMAGE_MAX_COUNT_PER_FILE=3

# Token-Kostenschutz
AI_MAX_TOTAL_CHARS_PER_RUN=50000

# Strategie-Freigaben (alle MVP-Standard: false)
ALLOW_OCR=false
ALLOW_VISION=false
ALLOW_ARCHIVE_EXTRACTION=false
```

---

## 14. Offene Punkte

| # | Punkt | Priorität | Beschreibung |
|---|---|---|---|
| 1 | **Magic Bytes / Datei-Signatur** | Mittel | Extension kann gefälscht sein. Für sensible Dateien (`exe`, `pdf`) Header-Signatur prüfen (z.B. `MZ` für PE-Executables, `%PDF` für PDF). Erste 16 Bytes aus Blob-Header lesen – ohne vollen Download möglich. |
| 2 | **Passwortschutz-Erkennung** | Mittel | Verschlüsselte Office-Dateien (OOXML-Encryption) und PDFs können nicht extrahiert werden. Der Extraction-Router muss bei Exception die Strategie auf `unreadable` umstellen. |
| 3 | **Content-Type Integration** | Niedrig | Azure Blob Content-Type als zusätzliches Signal nutzen, wenn Extension fehlt oder leer ist. |
| 4 | **Gescannte PDFs erkennen** | Mittel | PDFs ohne eingebetteten Text werden erst beim Extraktionsversuch erkannt. Der Extraction-Router setzt dann `ocr_required=True` nachträglich. |
| 5 | **Zip Bomb Protection** | Hoch (wenn Archiv-Extraktion implementiert) | Beim Entpacken: Max. Entpack-Tiefe 1, Max. Entpack-Größe limitieren, keine nested archives. |
| 6 | **PPTX-Bilder** | Niedrig | Bilder in PPTX können nicht per `office_text`-Strategie extrahiert werden. Für spätere Vision-Stufe vormerken. |
| 7 | **Legacy .doc ohne LibreOffice** | Mittel | `python-docx` unterstützt `.doc` nicht (nur `.docx`). Optionen: LibreOffice CLI, Azure Document Intelligence, Apache Tika. |
| 8 | **needs_ai-Tag** | Mittel | Blobs mit `class=unknown` und `extraction_required=True` sollten `needs_ai=true` als Tag bekommen, damit eine zweite Stufe gezielt diese Dateien verarbeiten kann. |

---

## 15. Nächste Ausbaustufe

### Empfohlene Reihenfolge

```
Stufe 1 (JETZT): Dateityp-Router  ← bereits implementiert ✅
        │
        ▼
Stufe 2: Extraction-Router Light
         app/extraction_router.py
         → .txt / .csv / .json direkt lesen
         → .docx Text extrahieren (python-docx)
         → .pdf Text extrahieren (pypdf / pdfplumber)
         → begrenzen auf AI_MAX_CHARS_PER_FILE
         │
         ▼
Stufe 3: needs_ai-Tag
         Blobs mit class=unknown + extraction_failed → needs_ai=true
         │
         ▼
Stufe 4: AI Dry Run
         Ersten 5 Dateien mit extrahiertem Text an KI schicken
         ENABLE_AI=true, AI_PROVIDER=foundry, max-files=5, dry-run=true
         │
         ▼
Stufe 5: Report-Erweiterung
         route_strategy, extracted_chars, estimated_tokens in Reports
         │
         ▼
Stufe 6: OCR / Vision (Optional)
         ALLOW_OCR=true, Azure Document Intelligence
         ALLOW_VISION=true, GPT-4o Vision
```

### Konkrete nächste Aufgabe

**Extraction-Router Light** für `.docx` und `.pdf`:

```python
# app/extraction_router.py (Stufe 2)
def extract_text(blob_bytes: bytes, route: FileTypeRoute, max_chars: int) -> ExtractionResult:
    if route.strategy == STRATEGY_OFFICE_TEXT and route.extension == ".docx":
        # python-docx: Document(BytesIO(blob_bytes)).paragraphs
        ...
    elif route.strategy == STRATEGY_PDF_TEXT:
        # pypdf: PdfReader(BytesIO(blob_bytes)).pages[:PDF_MAX_PAGES]
        ...
    elif route.strategy == STRATEGY_DIRECT_TEXT:
        # direkt: blob_bytes.decode("utf-8", errors="replace")[:max_chars]
        ...
```

Dieser Schritt würde die `legacy_office`-`.doc`-Dateien aus dem Pilottest erstmals inhaltlich klassifizierbar machen.

---

*Dokumentation erstellt: 2026-06-05*  
*Implementiert in: `app/file_type_router.py`*  
*Tests in: `tests/test_file_type_router.py`*
