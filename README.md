# Hyundai Kia Genesis (Pleos) - EU

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Validate](https://github.com/Marcels-Custom-Coding/Hyundai-Kia-Genesis-Pleos-HA/actions/workflows/validate.yml/badge.svg)](https://github.com/Marcels-Custom-Coding/Hyundai-Kia-Genesis-Pleos-HA/actions/workflows/validate.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Home Assistant integration for Hyundai, Kia and Genesis vehicles using the official **Pleos Vehicle Data API**.

## Schnellinstallation / Quick install

Die Integration ist (noch) nicht im HACS-Standardkatalog. Du fügst dieses Repository einmalig als **benutzerdefiniertes Repository** hinzu.
*Not (yet) in the default HACS store – add this repository once as a **custom repository**.*

**1. Repository in HACS öffnen / Open the repository in HACS**

[![In HACS öffnen / Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Marcels-Custom-Coding&repository=Hyundai-Kia-Genesis-Pleos-HA&category=integration)

Der Button öffnet dein Home Assistant und fragt, ob das Repository zu HACS hinzugefügt werden soll. Dann **Herunterladen** klicken.
*The button opens your Home Assistant and asks to add the repository to HACS. Then click **Download**.*

<details>
<summary>Ohne Button / Without the button</summary>

1. HACS öffnen › oben rechts **⋮** › **Benutzerdefinierte Repositories**
   *Open HACS › top right **⋮** › **Custom repositories***
2. Repository: `https://github.com/Marcels-Custom-Coding/Hyundai-Kia-Genesis-Pleos-HA` · Typ / Type: **Integration** › **Hinzufügen / Add**
3. In HACS nach „Hyundai Kia Genesis (Pleos) - EU“ suchen › **Herunterladen / Download**

</details>

**2. Home Assistant neu starten / Restart Home Assistant**

**3. Integration einrichten / Set up the integration**

[![Integration hinzufügen / Add integration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=hkg_pleos)

Oder / Or: **Einstellungen › Geräte & Dienste › Integration hinzufügen** › „Hyundai Kia Genesis (Pleos) - EU“. Der Dialog erklärt dir, wie du den API-Schlüssel bekommst. *The dialog explains how to get your API key.*

---

**[Schnellinstallation / Quick install](#schnellinstallation--quick-install)** · **[Deutsch](#deutsch)** · **[English](#english)** · **[Entitäten / Entities](#entitäten--entities)**

---

## Deutsch

- [Was macht die Integration?](#was-macht-die-integration)
- [Voraussetzungen](#voraussetzungen)
- [API-Schlüssel holen](#api-schlüssel-holen)
- [Schlüssel widerrufen und erneuern](#schlüssel-widerrufen-und-erneuern)
- [Installation](#installation)
- [Einrichtung](#einrichtung)
- [Zweites Auto hinzufügen](#zweites-auto-hinzufügen)
- [Diagnose und Fehlersuche](#diagnose-und-fehlersuche)
- [FAQ](#faq)

### Was macht die Integration?

Die Integration zeigt die Daten deines Autos in Home Assistant: Akkustand, Ladezustand, Reichweite, Kilometerstand, Türen und Schlösser, Reifendruck, Warnungen, Klima, Sitzheizung und Position.

- **Nur lesen.** Die Pleos Vehicle Data API liefert ausschließlich Daten. Steuern (Klima starten, Laden, Ver-/Entriegeln) ist über diesen Weg **nicht möglich**. Wenn du Befehle brauchst und die Integration „Hyundai / Kia Connect“ bei dir noch funktioniert, kannst du sie parallel weiter nutzen.
- **Marken:** Hyundai (getestet), Kia und Genesis (**ungetestet, Rückmeldung willkommen** – bitte ein [Issue](https://github.com/Marcels-Custom-Coding/Hyundai-Kia-Genesis-Pleos-HA/issues) öffnen).
- **Region:** nur Europa.
- Entitätsnamen wie bei „Hyundai / Kia Connect“ (kia_uvo), damit Umsteiger ihre Automationen und Dashboards behalten können.

### Voraussetzungen

- Home Assistant **2025.1.0** oder neuer
- [HACS](https://hacs.xyz/) (empfohlen)
- Ein Konto der Marken-App, in dem dein Auto eingetragen ist:
  - Hyundai: **Bluelink**
  - Kia: **Kia Connect**
  - Genesis: **Genesis Connected Services**
- Wohnsitz/Fahrzeug in Europa
- Ein kostenloses Konto bei [pleos.ai/playground](https://pleos.ai/playground) (siehe unten)

### API-Schlüssel holen

Jeder Nutzer holt sich seinen eigenen, kostenlosen Schlüssel (Weg „Private Users“). Das dauert etwa fünf Minuten.

1. [pleos.ai/playground](https://pleos.ai/playground) öffnen und kostenlos **registrieren**.
2. Oben rechts auf das **Personen-Symbol** › **My Vehicle Data API** klicken.
   <!-- Screenshot: playground-menu.png -->
3. Den Reiter deiner Marke wählen (**Hyundai**, **Kia** oder **Genesis**).
4. Die **Bedingungen annehmen**.
5. Auf **Get API Key** klicken.
   <!-- Screenshot: playground-get-api-key.png -->
6. Mit den Zugangsdaten deiner Marken-App anmelden (Bluelink / Kia Connect / Genesis Connected Services).
   <!-- Screenshot: playground-brand-login.png -->
7. **Client-ID** und **Client-Secret** kopieren und sicher aufbewahren.
   <!-- Screenshot: playground-api-key.png -->

> **Wichtig**
> - In den Schlüssel kommen nur die Autos, die **zum Zeitpunkt der Ausgabe** in deinem App-Konto sind. Neues Auto? → Auto in der App hinzufügen, alten Schlüssel widerrufen und einen neuen holen.
> - Ein Schlüssel gilt **pro Marke**. Wer z. B. einen Hyundai und einen Kia hat, holt zwei Schlüssel und richtet die Integration **einmal pro Marke** ein.

### Schlüssel widerrufen und erneuern

1. Auf [pleos.ai/playground](https://pleos.ai/playground) › Personen-Symbol › **My Vehicle Data API** den Reiter der Marke öffnen.
2. Den bestehenden Schlüssel **widerrufen** (Revoke).
3. Mit **Get API Key** einen neuen Schlüssel holen.
4. In Home Assistant: **Einstellungen › Geräte & Dienste › Hyundai Kia Genesis (Pleos) - EU** › Menü (⋮) › **Neu konfigurieren** › „Schlüssel ändern“ und die neuen Daten eingeben.

Wird der alte Schlüssel ungültig, startet Home Assistant automatisch den Erneuerungs-Dialog und zeigt eine Meldung unter **Einstellungen › Reparaturen**.

### Installation

**Über HACS (empfohlen)**

1. HACS öffnen › Menü (⋮) oben rechts › **Benutzerdefinierte Repositories**.
2. URL `https://github.com/Marcels-Custom-Coding/Hyundai-Kia-Genesis-Pleos-HA` eintragen, Typ **Integration**, hinzufügen.
3. „Hyundai Kia Genesis (Pleos) - EU“ suchen und **herunterladen**.
4. Home Assistant **neu starten**.

[![In HACS öffnen](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Marcels-Custom-Coding&repository=Hyundai-Kia-Genesis-Pleos-HA&category=integration)

**Manuell**

1. Den Ordner `custom_components/hkg_pleos` aus diesem Repository in deinen Home-Assistant-Ordner `config/custom_components/` kopieren.
2. Home Assistant neu starten.

### Einrichtung

**Einstellungen › Geräte & Dienste › Integration hinzufügen › „Hyundai Kia Genesis (Pleos) - EU“**

[![Integration hinzufügen](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=hkg_pleos)

1. **Marke wählen:** Hyundai, Kia oder Genesis.
2. **Hast du schon einen API-Schlüssel?** „Ja, eingeben“ oder „Nein, zeig mir wie“.
3. **Anleitung** (nur bei „Nein“): dieselben Schritte wie oben, passend zur Marke.
4. **Schlüssel eingeben:** Client-ID und Client-Secret. Die Integration prüft die Anmeldung sofort und holt die Autos.
5. **Autos und Namen:** Jedes gefundene Auto (Modell + letzte 4 Stellen der VIN) mit Häkchen und Namen. Der Name ist mit dem App-Namen vorbefüllt – so heißen danach alle Entitäten. Hattest du vorher „Hyundai / Kia Connect“, nimm **denselben Namen**.
6. **Abfrageintervall:** wie oft Daten geholt werden (Standard 10 Minuten, 5–1440).
7. **Übernahme** (nur wenn ein „Hyundai / Kia Connect“-Gerät mit gleicher VIN gefunden wird): „Alte Entitäten übernehmen?“ – bei „Ja“ bleiben Entity-IDs, Verlauf, Automationen und Dashboards erhalten. Ohne Zustimmung wird nichts angefasst.

<!-- Screenshot: setup-vehicles.png -->

Intervall und Namen lassen sich später über **Konfigurieren** bzw. **Neu konfigurieren** ändern.

### Zweites Auto hinzufügen

Da nur Autos im Schlüssel sind, die beim Ausstellen in der App waren:

1. Auto in der Marken-App hinzufügen.
2. Im Playground › **My Vehicle Data API** den alten Schlüssel widerrufen.
3. **Get API Key** für einen neuen Schlüssel.
4. In Home Assistant: Integration › Menü (⋮) › **Neu konfigurieren** › „Neues Auto hinzufügen“ und Client-ID + Secret eingeben.

Danach werden nur die **neuen** Autos zur Benennung angezeigt. Bestehende Autos und Entitäten bleiben unverändert, weil die IDs an der VIN hängen.

### Diagnose und Fehlersuche

**Diagnose:** Integration › Menü (⋮) › **Diagnose herunterladen**. VIN, Client-Secret und Position werden darin geschwärzt.

**Debug-Logging** in `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.hkg_pleos: debug
```

Alternativ: Integration › Menü (⋮) › **Debug-Protokollierung aktivieren**.

### FAQ

**„Keine Fahrzeuge gefunden“**
Der Schlüssel enthält nur Autos, die beim Ausstellen in deinem App-Konto waren. Prüfe, ob das Auto in der App (Bluelink / Kia Connect / Genesis) sichtbar ist, und hol dann einen neuen Schlüssel (alten widerrufen, „Get API Key“). Achte auch auf den richtigen Marken-Reiter.

**„Client-ID oder Secret stimmen nicht“**
Beide Werte neu kopieren – ohne Leerzeichen am Anfang/Ende. Wurde der Schlüssel widerrufen, einen neuen holen. Prüfe außerdem, ob du die richtige Marke gewählt hast.

**„Region nicht unterstützt“**
Der Weg „Private Users“ ist nur in Europa verfügbar. Konto und Auto müssen in einem unterstützten europäischen Land registriert sein.

**Wie oft werden die Daten aktualisiert?**
Die Integration fragt im eingestellten Intervall ab (Standard 10 Minuten). Es gibt keine Push-Daten. Die Werte sind so aktuell, wie das Auto sie zuletzt an den Hersteller gesendet hat – meist nach dem Abstellen oder während des Ladens. Der Sensor „Last Updated At“ zeigt den Zeitpunkt.

**Warum kann ich nicht verriegeln oder die Klimaanlage starten?**
Die Pleos Vehicle Data API ist rein lesend und kennt keine Befehle. Für Befehle kannst du „Hyundai / Kia Connect“ parallel nutzen, solange es bei dir funktioniert. Der Schlosszustand erscheint deshalb als Binärsensor „Locked“ statt als Schloss-Entität.

**Ich komme von „Hyundai / Kia Connect“ – bleiben meine Automationen?**
Ja, wenn du beim Einrichten **denselben Gerätenamen** verwendest und die **Übernahme** bestätigst. Dann bekommen die neuen Entitäten genau die alten Entity-IDs, Verlauf und Automationen laufen weiter. Werte, die Pleos nicht liefert (Schalter, Knöpfe, Klima-/Schloss-Steuerung), entfallen.

**Manche Entitäten fehlen.**
Entitäten werden nur angelegt, wenn das Auto beim ersten Abruf einen Wert liefert (ein E-Auto bekommt z. B. keinen Tank-Sensor). Nach einem Neuladen der Integration wird erneut geprüft.

---

## English

- [What does it do?](#what-does-it-do)
- [Requirements](#requirements)
- [Get your API key](#get-your-api-key)
- [Revoke and renew the key](#revoke-and-renew-the-key)
- [Installation](#installation-1)
- [Setup](#setup)
- [Adding a second car](#adding-a-second-car)
- [Diagnostics and troubleshooting](#diagnostics-and-troubleshooting)
- [FAQ](#faq-1)

### What does it do?

The integration shows your car's data in Home Assistant: battery level, charging state, range, odometer, doors and locks, tire pressure, warnings, climate, seat heating and location.

- **Read only.** The Pleos Vehicle Data API only provides data. Controlling the car (start climate, charging, lock/unlock) is **not possible** this way. If you need commands and the "Hyundai / Kia Connect" integration still works for you, keep using it in parallel.
- **Brands:** Hyundai (tested), Kia and Genesis (**untested, feedback welcome** – please open an [issue](https://github.com/Marcels-Custom-Coding/Hyundai-Kia-Genesis-Pleos-HA/issues)).
- **Region:** Europe only.
- Entity names match "Hyundai / Kia Connect" (kia_uvo), so people switching over can keep their automations and dashboards.

### Requirements

- Home Assistant **2025.1.0** or newer
- [HACS](https://hacs.xyz/) (recommended)
- An account of the brand app with your car in it:
  - Hyundai: **Bluelink**
  - Kia: **Kia Connect**
  - Genesis: **Genesis Connected Services**
- Account/vehicle in Europe
- A free account at [pleos.ai/playground](https://pleos.ai/playground) (see below)

### Get your API key

Every user gets their own free key ("Private Users" path). It takes about five minutes.

1. Open [pleos.ai/playground](https://pleos.ai/playground) and **register** for free.
2. Click the **person icon** (top right) › **My Vehicle Data API**.
   <!-- Screenshot: playground-menu.png -->
3. Choose the tab of your brand (**Hyundai**, **Kia** or **Genesis**).
4. **Accept the terms**.
5. Click **Get API Key**.
   <!-- Screenshot: playground-get-api-key.png -->
6. Log in with your brand app account (Bluelink / Kia Connect / Genesis Connected Services).
   <!-- Screenshot: playground-brand-login.png -->
7. Copy the **Client ID** and **Client Secret** and keep them safe.
   <!-- Screenshot: playground-api-key.png -->

> **Important**
> - The key only contains the cars that are in your app account **at the time the key is issued**. New car? → add it in the app, revoke the old key and get a new one.
> - A key is valid **per brand**. If you own e.g. a Hyundai and a Kia, get two keys and set up the integration **once per brand**.

### Revoke and renew the key

1. On [pleos.ai/playground](https://pleos.ai/playground) › person icon › **My Vehicle Data API**, open your brand's tab.
2. **Revoke** the existing key.
3. Get a new one with **Get API Key**.
4. In Home Assistant: **Settings › Devices & services › Hyundai Kia Genesis (Pleos) - EU** › menu (⋮) › **Reconfigure** › "Change key" and enter the new values.

If the old key stops working, Home Assistant starts the re-authentication dialog automatically and shows a notice under **Settings › Repairs**.

### Installation

**Via HACS (recommended)**

1. Open HACS › menu (⋮) top right › **Custom repositories**.
2. Enter `https://github.com/Marcels-Custom-Coding/Hyundai-Kia-Genesis-Pleos-HA`, type **Integration**, add.
3. Search for "Hyundai Kia Genesis (Pleos) - EU" and **download** it.
4. **Restart** Home Assistant.

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Marcels-Custom-Coding&repository=Hyundai-Kia-Genesis-Pleos-HA&category=integration)

**Manual**

1. Copy the folder `custom_components/hkg_pleos` from this repository into your Home Assistant `config/custom_components/` folder.
2. Restart Home Assistant.

### Setup

**Settings › Devices & services › Add integration › "Hyundai Kia Genesis (Pleos) - EU"**

[![Add integration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=hkg_pleos)

1. **Choose the brand:** Hyundai, Kia or Genesis.
2. **Do you already have an API key?** "Yes, enter it" or "No, show me how".
3. **Guide** (only for "No"): the same steps as above, adapted to your brand.
4. **Enter the key:** Client ID and Client Secret. The integration tests the login right away and fetches your cars.
5. **Cars and names:** every car found (model + last 4 characters of the VIN) with a checkbox and a name. The name is pre-filled with the name from the app – all entities are named after it. If you used "Hyundai / Kia Connect" before, use **the same name**.
6. **Polling interval:** how often data is fetched (default 10 minutes, 5–1440).
7. **Takeover** (only if a "Hyundai / Kia Connect" device with the same VIN is found): "Take over old entities?" – with "Yes", entity IDs, history, automations and dashboards are kept. Nothing is touched without your consent.

<!-- Screenshot: setup-vehicles.png -->

Interval and names can be changed later via **Configure** or **Reconfigure**.

### Adding a second car

Because the key only contains cars that were in the app when it was issued:

1. Add the car in the brand app.
2. In the playground › **My Vehicle Data API**, revoke the old key.
3. Click **Get API Key** for a new key.
4. In Home Assistant: integration › menu (⋮) › **Reconfigure** › "Add a new car" and enter Client ID + Secret.

Only the **new** cars are then shown for naming. Existing cars and entities stay unchanged, because their IDs are based on the VIN.

### Diagnostics and troubleshooting

**Diagnostics:** integration › menu (⋮) › **Download diagnostics**. VIN, client secret and location are redacted.

**Debug logging** in `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.hkg_pleos: debug
```

Or: integration › menu (⋮) › **Enable debug logging**.

### FAQ

**"No vehicles found"**
The key only contains cars that were in your app account when it was issued. Check that the car is visible in the app (Bluelink / Kia Connect / Genesis), then get a new key (revoke the old one, "Get API Key"). Also make sure you used the right brand tab.

**"Client ID or secret is wrong"**
Copy both values again – without leading/trailing spaces. If the key was revoked, get a new one. Also check that you selected the right brand.

**"Region not supported"**
The "Private Users" path is only available in Europe. Account and car must be registered in a supported European country.

**How often is the data updated?**
The integration polls at the configured interval (default 10 minutes). There is no push. Values are as fresh as the car last sent them to the manufacturer – usually after parking or while charging. The "Last Updated At" sensor shows when.

**Why can't I lock the car or start the climate control?**
The Pleos Vehicle Data API is read only and has no commands. For commands you can keep "Hyundai / Kia Connect" running in parallel as long as it works for you. The lock state is therefore a binary sensor "Locked" instead of a lock entity.

**I'm switching from "Hyundai / Kia Connect" – will my automations keep working?**
Yes, if you use **the same device name** during setup and confirm the **takeover**. The new entities then get exactly the old entity IDs, and history and automations continue. Things Pleos does not provide (switches, buttons, climate/lock control) are dropped.

**Some entities are missing.**
Entities are only created if the car reports a value on the first refresh (an EV gets no fuel sensor, for example). Reloading the integration checks again.

---

## Entitäten / Entities

Entity IDs follow the pattern `<platform>.<device name>_<entity name>`, e.g. `sensor.ioniq_5_ev_battery_level`. Entities are only created when the car reports a value. /
Entity-IDs folgen dem Muster `<plattform>.<gerätename>_<entitätsname>`. Entitäten werden nur angelegt, wenn das Auto einen Wert liefert.

### Sensors

| Entity | Source (Pleos) | Note |
|---|---|---|
| EV Battery Level | `batteries.charge.stateOfCharge` | % |
| EV Battery Capacity | `batteries.charge.batteryCapacity` | kJ (shown as kWh), diagnostic |
| AC Charge Limit | `batteries.charge.targetStateOfCharge.standard` | % |
| DC Charge Limit | `batteries.charge.targetStateOfCharge.quick` | % |
| Estimated Charge Duration | `batteries.charge.remainTime` | minutes |
| Charging Status | `batteries.charge.status` | text, e.g. `charging`, `fastCharging` |
| EV Range | `powertrains.distanceToEmpties` (EV) | km / mi |
| Fuel Driving Range | `powertrains.distanceToEmpties` (ICE) | km / mi |
| Total Driving Range | `powertrains.distanceToEmpties` (PHEV/HEV/FCEV, else the only one) | km / mi |
| Fuel Level | `powertrains.engine.fuelLevel` | %, not for EV/FCEV |
| EV Battery Remaining Ratio | `powertrains.batteries[main].remainRatio` | %, disabled by default |
| Odometer | `driving.odometer` | km / mi |
| Tire Pressure - Front Left / Front Right / Rear Left / Rear Right | `status.tire` | kPa / bar / psi |
| Set Temperature | `status.climateControl.temperature` | °C / °F |
| Outside temperature | `status.outsideTemperature` | °C / °F |
| Steering Wheel Heat Level | `status.steeringWheelHeat` | text, diagnostic |
| Warnings | `status.warnings` | comma-separated list or `none`, diagnostic |
| Last Updated At | newest `timestamp` of all endpoints | timestamp |
| Location Last Updated | `locations.timestamp` | timestamp, diagnostic |
| Vehicle Identification Number | VIN | diagnostic |

### Binary sensors

| Entity | Source (Pleos) | Note |
|---|---|---|
| EV Battery Charge | `batteries.charge.charging` | on = charging |
| EV Battery Plug | `batteries.charge.plugin` | on = connected |
| V2L status / V2X status | `batteries.charge.status` (`v2lOperating` / `v2xOperating`) | EV / PHEV |
| Engine | `driving.ignition` (ign1) | on = running |
| Accessory | `driving.ignition` (acc) | |
| IGN3 | `driving.ignition` (ign3) | |
| Sleep Mode Check | `driving.sleepMode` | |
| Transmission Condition | `driving.transmission.parkingPosition` | on = in park |
| Front Left / Front Right / Back Left / Back Right Door | `status.doors` | on = open |
| Front Left / … / Back Right Door Lock | `status.doors` | lock class: on = unlocked |
| Locked | `status.doors` (all) | lock class: on = at least one door unlocked |
| Hood / Trunk / Sunroof | `status.hood` / `trunk` / `sunroof` | on = open |
| Fuel Low Level, Washer Fluid Warning, Smart Key Battery Warning, Brake Fluid Warning, Oil Level Warning | `status.warnings` | problem; fuel/oil not for EV/FCEV |
| Tire Pressure - All / Front Left / Front Right / Rear Left / Rear Right | `status.warnings` | problem |
| Headlamp Status, Turn Signal Left/Right Front, Turn Signal Left/Right Rear, Rear Left / Rear Right Lamp Fault (stop lamps) | `status.warnings` (`frontHeadLamp`, `…TurnSignal`, `…StopLamp`) | problem |
| Air Conditioner | `status.climateControl.status` | |
| Defrost | `status.windshield.defrost` | |
| Steering Wheel Heater | `status.steeringWheelHeat` | |
| Front Left / Front Right / Rear Left / Rear Right Seat Heater | `status.seats` | |

### Device tracker

| Entity | Source (Pleos) | Note |
|---|---|---|
| Location | `locations.location` | attributes: altitude, heading, speed, last_update |

---

## Images / Bilder

Screenshots referenced above (`<!-- Screenshot: … -->`) belong in [`docs/images/`](docs/images/). /
Die oben markierten Screenshots gehören nach `docs/images/`.

## License / Lizenz

[MIT](LICENSE) © 2026 Marcels-Custom-Coding

Hyundai, Kia, Genesis, Bluelink, Kia Connect and Pleos are trademarks of their respective owners. This project is not affiliated with or endorsed by Hyundai Motor Group. /
Dieses Projekt steht in keiner Verbindung zur Hyundai Motor Group.
