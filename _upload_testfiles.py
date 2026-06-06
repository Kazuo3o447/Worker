"""Upload 3 AI test files to Azure Blob Storage under _ai_test/ prefix."""
import os, sys
from dotenv import load_dotenv
load_dotenv()

from app.config import load_config
from app.azure_blob_repository import AzureBlobRepository

TEST_FILES = {
    "_ai_test/finance_invoice_test.txt": """Rechnung Nr. 2024-0042
Datum: 15. März 2024

Von: Muster GmbH, Hauptstr. 1, 10115 Berlin
An:  GEMA Gesellschaft für musikalische Aufführungs- und mechanische Vervielfältigungsrechte
     Bayreuther Str. 37, 10787 Berlin

Leistung: Softwarelizenz Q1 2024 - Dokumentenmanagementsystem
Lizenzperiode: 01.01.2024 - 31.03.2024

Pos.  Beschreibung                     Menge    Einzelpreis    Gesamt
1     Software-Lizenz Enterprise          1      4.500,00 EUR   4.500,00 EUR
2     Support & Wartung                   1        500,00 EUR     500,00 EUR
3     Implementierung (8h à 120 EUR)      8        120,00 EUR     960,00 EUR

Nettobetrag:        5.960,00 EUR
Umsatzsteuer 19%:   1.132,40 EUR
Rechnungsbetrag:    7.092,40 EUR

Zahlungsziel: 30 Tage nach Rechnungseingang
Bankverbindung: DE89 3704 0044 0532 0130 00
BIC: COBADEFFXXX

Bitte überweisen Sie den Rechnungsbetrag unter Angabe der Rechnungsnummer.
""",

    "_ai_test/hr_personal_test.txt": """Personalakte - Vertraulich
Mitarbeiter: Max Mustermann
Personalnummer: 10042
Abteilung: Musiklizenzen
Eintrittsdatum: 01.04.2019

Lebenslauf:
- Abitur 2010, Gymnasium Berlin-Mitte
- Bachelor Betriebswirtschaft, FU Berlin, 2014
- Master Medienmanagement, HU Berlin, 2016
- GEMA seit April 2019

Gehaltsentwicklung:
2019: 42.000 EUR brutto/Jahr
2020: 44.000 EUR brutto/Jahr (Gehaltserhöhung +4.8%)
2021: 46.000 EUR brutto/Jahr (Gehaltserhöhung +4.5%)
2022: 48.500 EUR brutto/Jahr (Leistungsprämie)
2023: 50.000 EUR brutto/Jahr

Urlaubsanspruch: 30 Tage/Jahr
Resturlaub 2023: 5 Tage

Beurteilung 2023: Sehr gut - überdurchschnittliche Leistungen in der Lizenzabwicklung
Weiterbildung: Projektmanagement-Zertifikat IPMA Level D (2022)

Notfallkontakt: Maria Mustermann (Ehefrau), Tel. 0172-1234567
Krankenversicherung: AOK Berlin-Brandenburg
Steuerklasse: III

Diese Akte enthält personenbezogene Daten gemäß DSGVO.
Zugriff nur für autorisiertes HR-Personal.
""",

    "_ai_test/contract_test.txt": """LIZENZVERTRAG

zwischen

GEMA Gesellschaft für musikalische Aufführungs- und mechanische Vervielfältigungsrechte
Bayreuther Str. 37, 10787 Berlin
- nachfolgend "Lizenzgeber" -

und

Streaming GmbH
Potsdamer Platz 1, 10785 Berlin
- nachfolgend "Lizenznehmer" -

§ 1 Vertragsgegenstand

Der Lizenzgeber erteilt dem Lizenznehmer das nicht-exklusive, nicht-übertragbare Recht,
die im Repertoire der GEMA enthaltenen Musikwerke im Rahmen des Streaming-Dienstes
"StreamMax" zu nutzen.

§ 2 Lizenzgebühren

(1) Der Lizenznehmer verpflichtet sich zur Zahlung einer Lizenzgebühr von
    0,85 Cent je gestreamtem Titel.
(2) Die Mindestlizenzgebühr beträgt 5.000 EUR pro Quartal.
(3) Abrechnung erfolgt quartalsweise, Zahlung innerhalb von 30 Tagen.

§ 3 Laufzeit

Dieser Vertrag gilt ab 01.01.2024 und läuft auf unbestimmte Zeit.
Kündigung mit einer Frist von 6 Monaten zum Jahresende.

§ 4 Nutzungsmeldungen

Der Lizenznehmer ist verpflichtet, monatliche Nutzungsmeldungen einzureichen,
die alle gespielten Werke mit ISRC-Code, Titel, Interpret und Anzahl der Streams enthalten.

§ 5 Geheimhaltung

Beide Parteien verpflichten sich zur Vertraulichkeit über den Inhalt dieses Vertrages.

Ort, Datum: Berlin, 01.01.2024

Lizenzgeber:                    Lizenznehmer:
_____________________          _____________________
GEMA                           Streaming GmbH
"""
}

config = load_config()
print(f"Storage Account : {config.storage_account}")
print(f"Source Container: {config.source_container}")
print()

try:
    repo = AzureBlobRepository(config)
    ok = repo.ping()
    if not ok:
        print("ERROR: Azure ping failed.")
        sys.exit(1)
    print("Azure ping: OK")
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)

print()
print("Uploading test files to _ai_test/ ...")
for blob_name, content in TEST_FILES.items():
    try:
        data = content.encode("utf-8")
        repo.upload_bytes(config.source_container, blob_name, data, content_type="text/plain; charset=utf-8")
        print(f"  UPLOADED: {blob_name} ({len(data)} bytes)")
    except Exception as e:
        print(f"  ERROR uploading {blob_name}: {e}")
        sys.exit(1)

print()
print("Verifying uploads ...")
blobs = list(repo.list_source_blobs(prefix="_ai_test/"))
print(f"Found {len(blobs)} blob(s) under _ai_test/:")
for b in blobs:
    print(f"  {b.blob_name}  ({b.size_bytes} bytes)")

if len(blobs) >= 3:
    print()
    print("GATE PASSED: All 3 test files uploaded successfully.")
else:
    print()
    print(f"WARNING: Expected 3 files, found {len(blobs)}.")
