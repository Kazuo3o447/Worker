"""Content Extraction Light – AP2.

Modules:
  models       – ExtractionResult dataclass (safe, no raw text in serialization)
  safety       – Safety layer against raw text persistence
  direct_text  – Extractor for text-based formats (.txt, .csv, .log, ...)
  legacy_office– Extractor for Office formats (.docx / .doc)
  router       – Dispatches blobs to the right extractor
"""
