# Changelog

## [0.1.1] – 2026-10-14

### Behoben / Fixed
- Entitäten werden jetzt angelegt, sobald das Auto einen Wert liefert – nicht nur beim ersten Abruf. Einmal angelegte Entitäten bleiben erhalten, auch wenn ein Wert zeitweise fehlt.
  *Entities are now created as soon as the car reports a value, not only on the first refresh. Entities created once are kept even when a value is missing for a while.*

### Geändert / Changed
- Icon (Kia und Hyundai) für Home Assistant und HACS. / *Icon (Kia and Hyundai) for Home Assistant and HACS.*
- Länderliste in `hacs.json` (Europa, laut Pleos). / *Country list in `hacs.json` (Europe, per Pleos).*

## [0.1.0] – 2026-10-14

Erste Version. / First release.

### Neu / Added
- Fahrzeugdaten über die offizielle **Pleos Vehicle Data API** (nur lesen) für Hyundai, Kia und Genesis in Europa.
  *Vehicle data via the official Pleos Vehicle Data API (read only) for Hyundai, Kia and Genesis in Europe.*
- Geführte Einrichtung mit Schritt-für-Schritt-Anleitung zum API-Schlüssel, Auswahl und Benennung der Autos, Abfrageintervall.
  *Guided setup with a step-by-step API key guide, vehicle selection and naming, polling interval.*
- Sensoren, Binärsensoren und Device-Tracker: Akku, Laden, Ladelimits, Reichweite, Kilometerstand, Türen und Schlösser, Haube/Kofferraum/Schiebedach, Reifendruck, Warnungen inkl. Lampenfehler, Klima, Sitz- und Lenkradheizung, Außentemperatur, Position.
  *Sensors, binary sensors and device tracker for battery, charging, charge limits, range, odometer, doors and locks, hood/trunk/sunroof, tire pressure, warnings incl. lamp faults, climate, seat and steering wheel heating, outside temperature, location.*
- Gleiche Entitätsnamen wie „Hyundai / Kia Connect“ (kia_uvo) und optionale Übernahme der alten Entity-IDs samt Verlauf.
  *Same entity names as "Hyundai / Kia Connect" (kia_uvo) and optional takeover of old entity IDs including history.*
- Neu konfigurieren: Auto hinzufügen, Schlüssel ändern, umbenennen. Erneute Anmeldung bei ungültigem Schlüssel, Reparatur-Meldungen.
  *Reconfigure: add a car, change key, rename. Re-authentication for an invalid key, repair issues.*
- Diagnose mit geschwärzten Daten. / *Diagnostics with redacted data.*
