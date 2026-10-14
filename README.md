# Hyundai Kia Genesis (Pleos)

[Deutsch](#deutsch) · [English](#english)

---

## Deutsch

Diese Integration holt die Daten deines Hyundai, Kia oder Genesis über die **offizielle Pleos Vehicle Data API** nach Home Assistant: Akkustand, Reichweite, Ladestatus, Kilometerstand, Türen und Schlösser, Reifendruck, Warnleuchten, Klima und Position.

> **Nur Daten, kein Steuern.** Die Pleos-Schnittstelle bietet keine Befehle (Klima starten, Laden, Verriegeln). Wer steuern möchte, nutzt dafür zusätzlich eine andere Integration.

### Voraussetzungen

- Das Auto ist in der App deiner Marke eingerichtet: **Hyundai Bluelink**, **Kia Connect** oder **Genesis Connected Services**.
- Du wohnst in **Europa** (u. a. Deutschland, Österreich, Schweiz). Andere Regionen bietet Pleos derzeit nicht an.
- Home Assistant 2026.3 oder neuer, HACS.

Getestet mit Hyundai. Kia und Genesis nutzen laut Pleos dieselbe Schnittstelle, sind aber **ungetestet** – Rückmeldungen sind willkommen.

### Installation

1. HACS öffnen › drei Punkte oben rechts › **Benutzerdefinierte Repositories**.
2. `https://github.com/Marcels-Custom-Coding/Hyundai-Kia-Genesis-Pleos-HA` eintragen, Typ **Integration**.
3. „Hyundai Kia Genesis (Pleos)“ herunterladen und Home Assistant neu starten.
4. **Einstellungen › Geräte & Dienste › Integration hinzufügen** › „Hyundai Kia Genesis (Pleos)“.

### API-Schlüssel holen

Jeder holt sich seinen eigenen, kostenlosen Schlüssel. Der Einrichtungsdialog zeigt dieselbe Anleitung.

1. [Pleos Playground](https://pleos.ai/playground) öffnen und kostenlos registrieren.
2. Oben rechts auf das **Personen-Symbol** › **My Vehicle Data API**. (Der Menüpunkt erscheint nur in Europa.)
3. Den Reiter deiner Marke wählen (Hyundai, Kia oder Genesis).
4. Beide Bedingungen abhaken und **Get API Key** drücken.
5. Im neuen Fenster mit dem Konto deiner Auto-App anmelden (dieselben Zugangsdaten wie auf dem Handy).
6. **Client-ID** und **Client-Secret** kopieren und in Home Assistant eintragen.

<!-- Screenshot: docs/images/playground-menu.png (Personen-Symbol › My Vehicle Data API) -->
<!-- Screenshot: docs/images/playground-key.png (Client-ID und Client-Secret) -->

Gut zu wissen:

- **Ein Schlüssel pro Marke.** Hast du einen Hyundai und einen Kia, richtest du die Integration zweimal ein.
- **Nur Autos, die beim Ausstellen in der App waren**, sind im Schlüssel. Kommt ein Auto dazu, brauchst du einen neuen Schlüssel (siehe unten).
- Neuen Schlüssel holen oder alten widerrufen: auf derselben Seite **Revoke API Key** und danach **Get API Key**. Der alte Schlüssel wird sofort ungültig; Home Assistant meldet sich dann unter **Einstellungen › Reparaturen** und fragt nach dem neuen.

### Einrichtung

1. **Marke wählen.**
2. **Schlüssel vorhanden?** – „Ja“ führt direkt zur Eingabe, „Nein“ zeigt erst die Anleitung.
3. **Schlüssel eingeben.** Die Integration prüft ihn sofort und sucht deine Autos.
4. **Autos wählen und benennen.** Der Name aus der App ist vorbefüllt. Nach ihm heißen alle Entitäten, z. B. `sensor.<name>_ev_battery_level`. Dazu das Abfrageintervall (Standard 10 Minuten).
5. **Alte Entitäten übernehmen?** – nur wenn du vorher „Hyundai / Kia Connect“ hattest (siehe unten).

Später, über die drei Punkte der Integration › **Neu konfigurieren**:

- **Neues Auto hinzufügen** – mit Anleitung: Auto in der App hinzufügen, alten Schlüssel widerrufen, neuen holen, eintragen. Nur die neuen Autos werden zum Benennen angezeigt; die bisherigen bleiben unverändert.
- **Schlüssel ändern**
- **Autos umbenennen / Intervall** (auch über das Zahnrad erreichbar)

### Umstieg von „Hyundai / Kia Connect“

Die Entitäten heißen genauso wie bei „Hyundai / Kia Connect“ (kia_uvo). Findet die Einrichtung dort ein Auto mit derselben Fahrgestellnummer, bietet sie an, die **Entity-IDs zu übernehmen**. Dann laufen Verlauf, Automationen und Dashboards weiter. Bereich, eigener Name und Symbol werden mitgenommen.

- Ohne deine Zustimmung wird nichts verändert.
- Entferne die alte Integration danach, sonst legt sie ihre Entitäten neu an.
- Schalter, Knöpfe, Schloss, Klima und Ladelimit-Regler gibt es hier nicht, weil Pleos keine Befehle kennt.
- Die Ladelimits heißen hier `sensor.<name>_ac_charge_limit` / `_dc_charge_limit` (in Prozent).

### Entitäten

Angelegt wird nur, was dein Auto wirklich liefert (ein E-Auto bekommt keinen Tank-Sensor). Meldet ein Wert erst später Daten, erscheint die Entität dann automatisch.

| Bereich | Entitäten |
|---|---|
| Akku & Laden | EV Battery Level, EV Battery Capacity, Estimated Charge Duration, Ladestatus, Ladelimit AC/DC, EV Battery Charge, EV Battery Plug, V2L/V2X status |
| Reichweite & Antrieb | EV Range, Fuel Driving Range, Total Driving Range, Fuel Level, Car Battery Level, Odometer |
| Fahrzustand | Engine, Accessory, IGN3, Sleep Mode Check, Transmission Condition |
| Türen & Schloss | Türen offen/verriegelt (je Tür), Locked, Hood, Trunk, Sunroof |
| Reifen | Tire Pressure (je Rad, Einheit wird umgerechnet), Reifendruck-Warnungen |
| Warnleuchten | Fuel Low Level, Washer Fluid, Brake Fluid, Oil Level, Smart Key Battery, Lampenfehler |
| Klima & Komfort | Air Conditioner, Set Temperature, Defrost, Steering Wheel Heater, Sitzheizung (Stufe und an/aus), Sitzbelüftung, Outside temperature |
| Sonstiges | Location (Gerätetracker), Last Updated At, Location Last Updated, Vehicle Identification Number |

### Häufige Fragen

**„Der Schlüssel enthält kein Auto.“** – Das Auto war beim Ausstellen des Schlüssels noch nicht in der App, oder der Schlüssel gehört zu einer anderen Marke. Schlüssel widerrufen, neu holen, eintragen.

**Manche Werte bleiben leer.** – Pleos liefert nur, was das Auto sendet; das hängt von Modell und Baujahr ab. Fehlende Werte kommen als `null` und werden nicht angelegt.

**Wie aktuell sind die Daten?** – So aktuell wie die letzte Meldung des Autos an Hyundai/Kia/Genesis. „Last Updated At“ zeigt den Zeitpunkt. Pleos bietet keine Push-Nachrichten; die Integration fragt im eingestellten Intervall.

**Ein Auto ist verschwunden.** – Wurde es verkauft oder aus der App entfernt, ist es nicht mehr im Schlüssel. Unter **Einstellungen › Reparaturen** erscheint dann „Auto … nicht mehr im Schlüssel“ mit einem Knopf zum Entfernen.

**Wo melde ich Fehler?** – [GitHub Issues](https://github.com/Marcels-Custom-Coding/Hyundai-Kia-Genesis-Pleos-HA/issues). Hilfreich ist die Diagnose-Datei (Integration › drei Punkte › Diagnose herunterladen); Schlüssel, Fahrgestellnummer und Position sind darin entfernt.

---

## English

This integration brings the data of your Hyundai, Kia or Genesis into Home Assistant via the **official Pleos Vehicle Data API**: battery level, range, charging state, odometer, doors and locks, tyre pressure, warning lights, climate and location.

> **Data only, no control.** The Pleos interface offers no commands (start climate, charging, locking). Use another integration in addition if you need control.

### Requirements

- The car is set up in your brand's app: **Hyundai Bluelink**, **Kia Connect** or **Genesis Connected Services**.
- You live in **Europe**. Pleos does not offer other regions at the moment.
- Home Assistant 2026.3 or newer, HACS.

Tested with Hyundai. According to Pleos, Kia and Genesis use the same interface but are **untested** – feedback is welcome.

### Installation

1. Open HACS › three dots top right › **Custom repositories**.
2. Add `https://github.com/Marcels-Custom-Coding/Hyundai-Kia-Genesis-Pleos-HA`, type **Integration**.
3. Download “Hyundai Kia Genesis (Pleos)” and restart Home Assistant.
4. **Settings › Devices & services › Add integration** › “Hyundai Kia Genesis (Pleos)”.

### Getting the API key

Everyone gets their own free key. The setup dialog shows the same instructions.

1. Open the [Pleos Playground](https://pleos.ai/playground) and sign up for free.
2. Top right **person icon** › **My Vehicle Data API**. (Only shown in Europe.)
3. Choose your brand's tab (Hyundai, Kia or Genesis).
4. Tick both terms and press **Get API Key**.
5. Sign in with your car app account in the new window (same credentials as on your phone).
6. Copy **Client ID** and **Client Secret** and enter them in Home Assistant.

Good to know:

- **One key per brand.** With a Hyundai and a Kia you set up the integration twice.
- **Only cars that were in the app when the key was issued** are part of it. For a new car you need a new key (see below).
- To renew or revoke: **Revoke API Key** on the same page, then **Get API Key**. The old key stops working right away; Home Assistant then shows a notice under **Settings › Repairs** and asks for the new one.

### Setup

1. **Choose the brand.**
2. **Do you have a key?** – “Yes” goes straight to the input, “No” shows the instructions first.
3. **Enter the key.** The integration checks it right away and looks for your cars.
4. **Choose and name your cars.** The name from the app is pre-filled. All entities are named after it, e.g. `sensor.<name>_ev_battery_level`. Plus the polling interval (default 10 minutes).
5. **Take over old entities?** – only if you used “Hyundai / Kia Connect” before (see below).

Later, via the integration's three dots › **Reconfigure**: add a new car (with instructions; only new cars are shown), change the key, rename cars / interval (also via the gear icon).

### Switching from “Hyundai / Kia Connect”

Entities are named exactly like in “Hyundai / Kia Connect” (kia_uvo). If setup finds a car with the same VIN there, it offers to **take over the entity IDs**, so history, automations and dashboards keep working. Area, custom name and icon are carried over. Nothing is changed without your consent. Remove the old integration afterwards. Switches, buttons, lock, climate and charge limit controls are not available because Pleos has no commands. Charge limits are `sensor.<name>_ac_charge_limit` / `_dc_charge_limit` (percent).

### Entities

Only values your car actually reports are created (an EV gets no fuel sensor). If a value shows up later, its entity appears automatically. See the table in the German section for the full list.

### FAQ

- **“The key does not contain any car.”** – The car was not in the app when the key was issued, or the key belongs to another brand. Revoke, get a new key, enter it.
- **Some values stay empty.** – Pleos only provides what the car sends; this depends on model and year.
- **How current is the data?** – As current as the car's last report. “Last Updated At” shows the time. Pleos has no push; the integration polls at the set interval.
- **A car disappeared.** – Sold or removed from the app: a repair notice offers to remove it.
- **Bug reports:** [GitHub Issues](https://github.com/Marcels-Custom-Coding/Hyundai-Kia-Genesis-Pleos-HA/issues), ideally with the diagnostics file (key, VIN and location are removed).

---

Not affiliated with Hyundai Motor Group, Hyundai, Kia, Genesis or Pleos. All trademarks belong to their owners.
