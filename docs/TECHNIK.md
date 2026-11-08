# broetje_neo – Technische Dokumentation

Stand: Version 0.1.0 (Branch `claude/elegant-einstein-wfeodh`). Zielgruppe: Fachleute,
die nachvollziehen wollen, **was die Integration liest, was sie schreibt, wann und unter
welchen Bedingungen**. Alle Angaben sind aus dem Quellcode abgeleitet. Fundstellen stehen
jeweils in Klammern.

Quellen der Registerbelegung und Grenzwerte:

| Kürzel | Dokument |
|--------|----------|
| RKM | Brötje NEO-RKM Montageanleitung 7734937-01 (05.07.2019), Kap. 7.1 Tab. 4/5, Kap. 7.2 |
| BA | Brötje BLW NEO 8–18 Bedienungsanleitung 7709599-04 (14.11.2019), Kap. 6 |
| IH | Brötje BLW(-C) NEO 8–18 B Installationsanleitung 7794774-03 (20.04.2023) |
| DUH | Deutsche Umwelthilfe, FactSheet „Ratgeber zur optimalen Einstellung der Wärmepumpe“ (01/2023) |

---

## 1. Überblick

```
NEO-RKM (Modbus TCP, Slave)
   ▲  FC 03/04 lesen (zyklisch)      FC 06 schreiben (nur freigegeben, Positivliste)
   │
BroetjeNeoCoordinator ── asyncio.Lock: ein Request zur Zeit
   │  ├─ Blockreads → RegisterData {input:{addr:word}, holding:{addr:word}}
   │  ├─ Netzbetreiber-Erkennung → PV-Vorrang
   │  ├─ PV-Watchdog
   │  ├─ Preissperren-Wächter
   │  └─ Effizienz-Check (Tracker + Regeln, persistent)
   ▼
Entitäten (sensor, binary_sensor, number, select, switch)
```

| Modul | Aufgabe |
|-------|---------|
| `registers.py` | einzige Quelle der Registerbelegung, Datentypen, Skalierung, Kennwerte für „ungültig“ (ohne HA-Abhängigkeit) |
| `safety.py` | einzige Quelle dafür, **was** geschrieben werden darf und in welchem Bereich |
| `coordinator.py` | gesamte Modbus-I/O, Schutzlogik, Effizienz-Check-Anbindung |
| `advisor.py` | Effizienz-Check: Datensammlung und Regeln (ohne HA-Abhängigkeit) |
| `sensor.py` … `switch.py` | Entitäten, lesen nur aus dem Coordinator |
| `config_flow.py` | Einrichtung und Optionen |
| `diagnostics.py` | Download mit Rohregistern |

Abhängigkeit: `pymodbus>=3.11` (AsyncModbusTcpClient), Home Assistant ab 2025.9.

---

## 2. Lesen

### 2.1 Zyklus

- Intervall: Option `scan_interval`, Standard 15 s (5–300 s).
- Pro Zyklus fünf Block-Reads, nacheinander, über eine TCP-Verbindung (`registers.READ_BLOCKS`):

| Block | Funktion | Register | Anzahl | Pflicht |
|-------|----------|----------|--------|---------|
| 1 | 04 Input | 10–41 | 32 | ja |
| 2 | 04 Input | 42–45 | 4 | nein (ältere Firmware) |
| 3 | 04 Input | 60–75 | 16 | ja |
| 4 | 03 Holding | 100–134 | 35 | ja |
| 5 | 03 Holding | 147–150 | 4 | nein |

- Ein **Pflichtblock** mit Fehler (`isError()`, falsche Länge, Timeout, Verbindungsfehler)
  führt zu `UpdateFailed`. Die Verbindung wird geschlossen, alle Entitäten werden
  `unavailable`, beim nächsten Zyklus folgt ein neuer Verbindungsaufbau.
- Ein **optionaler Block** mit Fehler wird übersprungen. Er wird einmalig auf Stufe INFO
  protokolliert, die zugehörigen Werte sind `unknown`.
- Lesen hat keine Wirkung auf die Anlage. Holding-Register werden gelesen, um die
  aktuellen Sollwerte anzuzeigen.

### 2.2 Dekodierung (`registers.decode`)

| Typ | Regel |
|-----|-------|
| INT16 | Zweierkomplement, dann × Skalierung |
| UINT16 | unverändert × Skalierung |
| UINT32 | High-Word zuerst (Reg. n = high, n+1 = low) |
| Temperatur-Kennwert | Rohwert −500 (= −50,0 °C) → `None` („Fühler nicht vorhanden“) |
| UINT32-Kennwert | 0xFFFFFFFF → `None` |
| Energiezähler | Rohwert 0 → `None` (verhindert falsche Resets in der Langzeitstatistik) |

### 2.3 Gelesene Register und Entitäten

Einheiten nach RKM Tab. 4. Alle Messwerte haben `state_class: measurement`, Zähler
`total_increasing`. Damit landen sie in der Langzeitstatistik.

| Reg. | Bedeutung (RKM) | Skal. | Entität (de) |
|------|-----------------|-------|--------------|
| 10 | Temp. Außen | 0,1 °C | Außentemperatur |
| 11 | Temp. Brauchwasser | 0,1 °C | Warmwassertemperatur |
| 12 | Temp. Vorlauf | 0,1 °C | Vorlauftemperatur |
| 13 | Temp. Rücklauf | 0,1 °C | Rücklauftemperatur |
| 14 | Temp. Pufferspeicher | 0,1 °C | Puffertemperatur |
| 15 / 16 | Temp. EQ Eintritt / Austritt | 0,1 °C | Quelle Eintritt / Austritt |
| 17 | Temp. Sauggas | 0,1 °C | Sauggastemperatur |
| 18 | Temp. Verdampfung | 0,1 °C | Verdampfungstemperatur |
| 19 | Temp. Kondensation | 0,1 °C | Kondensationstemperatur |
| 20 | Temp. Heißgas | 0,1 °C | Heißgastemperatur |
| 21 / 22 | Nieder- / Hochdruck | 0,1 bar | Niederdruck / Hochdruck |
| 23 | Heizkreispumpe | ≠0 = an | Heizkreispumpe |
| 24 | Pufferladepumpe | ≠0 = an | Pufferladepumpe |
| 25 | Wärmepumpe läuft | ≠0 = an | Verdichter |
| 26 | Störung | ≠0 | Störung (problem) |
| 27 | Vierwegeventil: Abtau-/Reversierbetrieb | ≠0 | Abtauen (im Kühlbetrieb ebenfalls an, siehe 5.2) |
| 28 | Durchfluss | 0,1 l/min | Durchfluss |
| 29 | Verdichterdrehzahl | ‰ → % (×0,1) | Verdichterdrehzahl |
| 30 | COP | 0,1 | COP |
| 31 | Frischwassertemperatur | 0,1 °C | Frischwassertemperatur (standardmäßig deaktiviert) |
| 32 | **EVU-Freigabe** | ≠0 = freigegeben | EVU-Freigabe |
| 33 | Außentemperatur verzögert | 0,1 °C | Außentemperatur verzögert |
| 34 | Rücklauf-/Speichersoll (Heizkurve) | 0,1 °C | Rücklaufsolltemperatur |
| 35 / 36 | MKR1/2 VL-Soll | 0,1 °C | MKR1/2 Vorlaufsoll (MKR1 aktiv, MKR2 deaktiviert; unbekannt ohne aktiven Mischerkreis: R107/R112 ≠ 0 und Wert > 0) |
| 37 | EQ-Pumpe / Ventilator | ≠0 | Ventilator |
| 38 | WW-Vorrang | ≠0 | Warmwasservorrang |
| 39 | Kühlen UMV passiv | ≠0 | Kühlen passiv |
| 40 | Expansionsventil | ‰ → % | Expansionsventil |
| 41 | Anforderung 0/10/20/30 (40) | Enum | Anforderung (Attribut `raw`); binär: Heizen / Warmwasser / Kühlen |
| 42–43 / 44–45 | Betriebsstunden WW / Heizen | h | Betriebsstunden … (0 = ungültig, kein Reset in der Statistik) |
| 60–61 / 62–63 | Wärme / Strom Heizen | kWh | Wärmemenge / Strom Heizen |
| 64–65 / 66–67 | Wärme / Strom WW | kWh | … Warmwasser |
| 68–69 | Strom gesamt | kWh | Strom gesamt |
| 70–71 | el. Aufnahmeleistung | W | Elektrische Leistung |
| 72–73 | Wärme gesamt | kWh | Wärmemenge gesamt |
| 74–75 | Heizleistung | 0,1 kW | Heizleistung |
| 100 | Betriebsart 0–10 | Enum | Betriebsart Status (alle Werte, inkl. 8 Ausheizen, 9 EVU-Sperre, 10 Hauptschalter aus) |
| 107 / 112 | Betriebsart MKR1 / MKR2 | Enum | MKR1/MKR2 Betriebsart Status, nur lesend, auch ohne Schreiboption (MKR2 deaktiviert) |

Betriebsübersicht (aus Registern bzw. den Stundenwerten des Effizienz-Checks):

| Entität | Quelle |
|---------|--------|
| Status | `advisor.plant_state`: Störung > Preissperre > EVU-Sperre (R32 = 0 / R100 = 9) > Aus > Abtauen (R27, nicht bei Kühlen) > WW / Heizen (R25 + R41) > Kühlen > Verdichter läuft > Heiz-/WW-Anforderung ohne Verdichter > Sommer (R100 = 3) > Standby |
| Verdichter heizt | R25 ≠ 0 und R41 = 20 |
| Heizanforderung / Verdichter / Verdichter Heizen heute, gestern, 7 Tage | Zeitsumme je Stunde (Zustand zu Beginn jedes Abfrageintervalls, Lücken > 120 s zählen nicht) |
| Strom / Wärme heute | Integration R70 (W) bzw. R74 (kW) über die Zeit |
| Arbeitszahl heute | Wärme heute / Strom heute, ab 0,2 kWh |
| Heizanforderung zuletzt gestartet, Heizperiode gestartet | Flanke R41 → 20; neue Heizperiode nach > 14 Tagen ohne Heizanforderung |
| Verdichter Heizen zuletzt gestartet | Flanke „Verdichter heizt“ |

Abgeleitete Sensoren (nur Rechnung, keine Register):

| Entität | Formel |
|---------|--------|
| Spreizung VL/RL | R12 − R13 |
| Überhitzung | R17 − R18 |
| Temperaturhub | R19 − R18 |
| Kondensator-Grädigkeit | R19 − R12 |
| Spreizung Quelle | R15 − R16 |
| COP berechnet | R74 × 1000 / R70, nur wenn R70 ≥ 100 W |
| Arbeitszahl gesamt / Heizen / WW | R72/R68, R60/R62, R64/R66 (seit Inbetriebnahme) |

---

Zwei Kartenvarianten in `extras/lovelace/`: `heat-pump-card.yaml` (Heizkreis direkt, Vorlauf/Rücklauf der Wärmepumpe) und `heat-pump-card-mischer.yaml` (Puffer + Mischerkreis; Heizkreis zeigt den MKR1-Vorlaufsoll, kein Rücklauf, da der NEO-RKM keine gemessenen Mischerwerte liefert).

Wandtablet-Dashboard mit Status-Logik, Laufzeiten und animiertem Schema: `docs/DASHBOARD.md`.

## 3. Schreiben

### 3.1 Grundsatz

1. **Standard: nur lesend.** Alle drei Freigaben sind nach der Einrichtung `false`
   (`const.DEFAULT_ALLOW_*`). Ohne Freigabe werden keine schreibenden Entitäten angelegt,
   und **kein Codepfad schreibt**, auch Watchdog und Herunterfahren nicht.
   Das sichert der Test `test_readonly_default` ab.
2. Jeder Modbus-Schreibzugriff läuft durch genau eine Funktion
   (`coordinator._write_raw`). Diese ruft vor dem Senden `safety.check_write` auf.
   Damit greifen die Regeln auch bei Dienstaufrufen aus Automationen und Skripten.
3. Es gibt eine **Positivliste**. Jedes Register, das nicht darin steht, wird abgelehnt.
4. Ratenbegrenzung: höchstens ein Schreibzugriff alle 5 s pro Register (RKM Kap. 7.1).
   Ein zu früher Zugriff wartet, er wird nicht verworfen.
5. Funktionscode 06 (Write Single Register). Nach jedem Schreiben folgt ein Refresh.

### 3.2 Positivliste (`safety.py`)

| Freigabe | Reg. | Bedeutung | Erlaubter Bereich | Begründung |
|----------|------|-----------|-------------------|------------|
| Einstellungen | 100 | Betriebsart | 1–7 (**nicht 0 = Aus**) | Frostschutz; 8–10 sind laut RKM nur lesbar |
| Einstellungen | 101 | Raumsoll HKR | 15–25 °C | BA: 10–25 °C, „Parallelverschiebung der Heizkurve“ |
| Einstellungen | 104 | RLT min Kühlen | 18–25 °C | Kondensatschutz bei Flächenkühlung |
| Einstellungen | 105 | WW Normal | 40–50 °C | BA: Kundenebene bis 50 °C, darüber Fachmann (WW max) |
| Einstellungen | 106 | WW Min | 10–45 °C | BA: Frostschutz des Speichers, 5–45 °C, Werk 15 °C |
| Einstellungen | 107 / 112 | MKR1/2 Betriebsart | 1–7 | wie 100 |
| Einstellungen | 108 / 113 | MKR1/2 Raumsoll | 15–25 °C | wie 101 |
| Einstellungen | 111 / 116 | MKR1/2 RLT min Kühlen | 18–25 °C | wie 104 |
| PV | 125 | Vorgabe el. Aufnahmeleistung | 0 … Option `pv_max_power` (Standard 6000 W) | RKM Kap. 7.2 |
| Preissperre | 149 | EVU-Freigabe Wert | **nur 0** | Eine Freigabe darf nie erzwungen werden |
| Preissperre | 150 | EVU-Freigabe aktiv | 0 / 1 | Sperre setzen / an Hardware-Eingang zurückgeben |

Zusätzliche Plausibilitätsprüfung in `number.py`: WW Min ≤ WW Normal.

### 3.3 Bewusst nicht beschreibbar

Diese Register liest die Integration teilweise, schreibt sie aber nie. Sie stehen nicht
in der Positivliste, und es gibt keine Entität dafür.

| Reg. | Bedeutung | Warum nicht |
|------|-----------|-------------|
| 102/103, 109/110, 114/115 | RL-/VL-Soll-Vorgabe + aktiv | Umgeht Heizkurve und Regler. Ein vergessenes „aktiv“ sperrt das Raumsoll (vgl. ha_heliotherm Issue #68) |
| 117, 126 | ext. Drehzahlanforderung / Drehzahlvorgabe | direkter Eingriff in die Verdichterführung |
| 127 | Externe Anforderung | erzwingt Betrieb |
| 128 | Entstören | Störungen ohne Ursachenklärung quittieren |
| 129–134 | Außen-/Puffer-/WW-Temperatur vorgeben + aktiv | falsche Fühlerwerte vortäuschen |
| 147/148 | 2. Stufe Wert/aktiv | Heizstab schalten |
| 149 = 1 | EVU-Freigabe erzwingen | könnte eine echte Netzbetreiber-Sperre aufheben |

---

## 4. Schutzfunktionen im Detail

### 4.1 PV-Vorgabe (Register 125)

Voraussetzung im RKM: Webinterface *Photovoltaik → PV-Auswahl „Modbus TCP“*. Dann wertet
das RKM Reg. 125 als PV-Leistung. Schwelle, Einschaltverzögerung, Mindestlaufzeit und
Modulation regelt es selbst (RKM Kap. 7.2).

| Ereignis | Verhalten |
|----------|-----------|
| HA-Start, Reg. 125 ≠ 0 | wird auf 0 gesetzt (Altwert aus vorherigem Lauf) |
| Kein neuer Wert innerhalb `pv_watchdog` (Standard 120 s) | wird auf 0 gesetzt |
| Netzbetreiber steuert (4.3) | wird auf 0 gesetzt, neue Werte > 0 werden abgelehnt |
| HA-Stopp / Entladen | wird auf 0 gesetzt |
| PV-Freigabe aus | keine Entität, kein Watchdog, kein Schreiben |

### 4.2 Preissperre

Zustandsquelle: Modbus (149 = 0, 150 = 1) oder ein externer Schalter (Option
`price_lock_switch`, „an“ = Sperre).

Bedingungen für **Einschalten** (`async_set_price_lock(True)`):

| Prüfung | Grenze |
|---------|--------|
| Funktion verfügbar | Block 147–150 lesbar bzw. Schalter `on`/`off` |
| kein Netzbetreiber-Eingriff aktiv | 4.3 |
| keine erkannte Fehlverdrahtung | 4.2.1 |
| Pause seit Ende der letzten Sperre (eigene **oder** Netzbetreiber) | ≥ 60 min |
| Sperrzeit heute (eigene + Netzbetreiber) | < 6 h |
| Außentemperatur bekannt und | ≥ −10 °C |

**Automatisches Aufheben** (Prüfung bei jedem Zyklus):

| Auslöser | Grenze |
|----------|--------|
| Sperre ohne bekannten Start (Rest aus vorherigem HA-Lauf oder manuell geschaltet) | sofort |
| Dauer | > Option `price_lock_max_minutes` (30–120, Standard 120) |
| Tagessumme | ≥ 6 h |
| Außentemperatur | < −10 °C |
| HA-Stopp / Entladen | immer |

Die Grenzen 2 h / 6 h entsprechen den EVU-Sperrregeln aus RKM Kap. 2.3.2 (BTOElt).
Die Tageszähler liegen im Speicher. Nach einem HA-Neustart beginnt die Tagessumme bei 0,
eine laufende Sperre wird beim Start aber ohnehin aufgehoben.

#### 4.2.1 Externer Schalter (z.B. Shelly)

- Anschluss am **EVU-Eingang** der Wärmepumpe (IH: 230-V-Eingang; ohne EVU-Sperre
  überbrückt, also Spannung = Freigabe). Ausfallsicher über ein Koppelrelais mit
  **Öffner** in der Freigabeleitung, in Reihe zum Netzbetreiber-Kontakt. Shelly mit
  Auto-Aus 7200 s und „Zustand nach Stromausfall: Aus“. **Nur durch eine Elektrofachkraft.**
- **Wirkungskontrolle:** Nach dem Einschalten muss R32 (EVU-Freigabe) innerhalb von
  120 s auf 0 gehen (`safety.PRICE_LOCK_VERIFY_SECONDS`). Sonst schaltet die Integration
  den Schalter aus und sperrt die Funktion bis zum nächsten Neuladen. Im Effizienz-Check
  erscheint der Hinweis „Preissperre wirkt nicht“.

### 4.3 Netzbetreiber-Vorrang (EVU-Sperre, §14a EnWG)

Ein Eingriff des Netzbetreibers gilt als aktiv, wenn

- R32 = 0 (EVU-Freigabe fehlt) **und** keine eigene Preissperre aktiv ist, oder
- der optionale Binärsensor `grid_signal` „on“ meldet (für Signale, die über Modbus
  nicht sichtbar sind, z.B. eine Steuerbox an den SG-Ready-Eingängen des RKM).

Folgen: PV-Vorgabe 0 und Ablehnung neuer Vorgaben, keine eigene Sperre. Die Dauer zählt
zur Tagessumme der Sperren. Nach dem Ende beginnt die 60-min-Pause.
Entitäten: „Netzbetreiber steuert“, „Netzbetreiber-Steuerung heute“ (min).

**Nicht dokumentiert, bitte am Gerät beobachten:** ob R32 bei einer eigenen Sperre über
149/150 ebenfalls 0 meldet. Die Integration schließt eigene Sperren bei der Erkennung
deshalb immer aus.

---

## 5. Effizienz-Check (`advisor.py`)

Der Check schreibt nie. Er arbeitet unabhängig von allen Freigaben.

### 5.1 Datensammlung

- Bei jedem erfolgreichen Zyklus entsteht ein `Sample`. Einbezogen werden
  Außentemperatur (R10, R33), VL/RL (R12/R13), RL-Soll (R34), Verdichter (R25),
  Anforderung (R41), Vierwegeventil (R27), Überhitzung (R17 − R18), Raumsoll (R101),
  Energiezähler und der Mittelwert der Raumsensoren aus der Option `room_sensors`.
- **Gruppierung der Raumsensoren (Option `room_grouping`):** Bei `floor` (Standard) wird
  je Sensor der Bereich (Entitäts-Registry `area_id`, sonst `area_id` des Geräts), davon
  das Stockwerk (Bereichs-Registry `floor_id`) ermittelt. Sensoren mit Stockwerk werden
  pro Stockwerk gemittelt (Schlüssel `floor:<floor_id>`), Sensoren ohne Stockwerk bleiben
  einzeln (Schlüssel Entitäts-ID). Bei `sensor` wird jeder Sensor einzeln geführt. Der
  Coordinator ergänzt je Schlüssel `name`, `level` und `sensors` und sortiert `rooms`
  nach Stockwerksebene absteigend (wenn alle eine haben), sonst nach `avg_7d`
  aufsteigend. Attribut `coldest_room` = Name des Eintrags mit der kleinsten
  `dev_7d`. Der Advisor entscheidet weiter nach der kältesten Gruppe.
- **Mischerkreis 1 (MKR1):** Der Check erkennt MKR1 als aktiv, wenn R35 (VL-Soll MKR1)
  einen Wert > 0 liefert und R107 (Betriebsart MKR1, Holding) ≠ 0 ist. Dann kommen
  Raumsoll aus R108 statt R101 und zusätzlich das VL-Soll R35 ins `Sample`
  (`mkr_set`, Bucket-Felder `ms_*`). Der Kontext `circuit` ist `mkr1` (sonst `hkr`),
  sichtbar als Attribut `circuit` des Effizienz-Check-Sensors. Hintergrund: Räume
  hängen dann am Mischer 1 mit eigener Heizkurve („Hauptmenü → Mischer 1 →
  Heizkurve“) und eigenem Raumsoll (Grundbedienung M1); R34 ist nur das Ladeziel des
  Puffers. Die Messkurve wird mit demselben Verfahren wie `rl_set_*` gefittet
  (≥ 12 Stundenpunkte mit ≥ 10 Samples, ≥ 4 K Außentemperaturbereich, max. 10 K
  Extrapolation) und als `mkr_set_18`, `mkr_set_0`, `mkr_set_m15` ausgegeben.
- **Mischerkreis 2 und Option `heating_circuit`:** Werte `auto`, `hkr`, `mkr1`, `mkr2`
  (Standard `auto`). `auto` wählt MKR1 wie oben, sonst MKR2 (R36 > 0 und R112 ≠ 0), sonst
  HKR; feste Werte werden unverändert verwendet. Für MKR2 kommen `mkr_set` aus R36 und
  der Raumsoll aus R113; Texte nennen „Mischer 2“, „Heizkurve M2“, „Grundbedienung M2“
  und „MKR2 Raumsoll“. Die Sensoren `mkr_set_*` bleiben unverändert benannt und zeigen
  den gewählten Mischerkreis. Das Attribut `circuit` enthält den aufgelösten Wert,
  `circuit_setting` die Einstellung. `buffer_overheat` gilt für beide Mischerkreise.
- Die Daten werden zu **Stundenbuckets** verdichtet und 14 Tage behalten. Dazu kommen
  abgeschlossene Verdichterläufe (Ende, Dauer) und ein Zählerstand pro Tag
  (40 Tage behalten).
- Zeitlücken über 120 s zählen nicht als Laufzeit, etwa bei Kommunikationsausfall.
- Persistenz: HA-Storage `.storage/broetje_neo.<entry_id>.advisor`. Gespeichert wird
  verzögert (300 s) und beim Herunterfahren.

### 5.2 Kennzahlen

| Kennzahl | Berechnung |
|----------|------------|
| Starts 24 h | Flanken R25 0→1 |
| Laufzeit pro Start | Median abgeschlossener Läufe der letzten 24 h |
| Abtauungen 24 h | Flanken R27 0→1, **ohne Kühlbetrieb** (R41 = 10, da das Ventil dann reversiert) |
| Abtauungen mild / Tag | wie oben, bei Außentemperatur > +5 °C, Mittel über 7 Tage |
| Spreizung Heizen 7 d | Mittel (R12 − R13), nur wenn der Verdichter läuft und R41 = Heizen |
| Überhitzung 7 d | Mittel (R17 − R18) bei laufendem Verdichter, ab 50 Werten |
| Heizbetrieb mild | Stunden Heizbetrieb bei Stundenmittel Außen ≥ 16 °C, 7 d |
| **Heizkurve RL-Soll bei 18 / 0 / −15 °C** | lineare Regression R34 über R33 (sonst R10) aus Stundenmitteln (≥ 10 Werte je Stunde), mindestens 12 Stunden und 4 K Spanne; Ausgabe nur bis 10 K außerhalb des gemessenen Bereichs |
| Raumabweichung 7 d | Mittel (Raum − R101) |
| Raumabweichung kalt / mild | Stundenmittel bei Außen < 3 °C bzw. > 8 °C, jeweils ≥ 12 h |
| Arbeitszahl 30 d (gesamt/Heizen/WW) | Differenz der Tageszählerstände; mindestens 20 kWh Strom (WW 10 kWh) |
| **Heizgrenze beobachtet** | siehe unten |

Heizgrenze beobachtet (selbstlernend, nur lesend):

1. Bei jedem Start einer Heizanforderung (R41 wechselt auf 20) wird R33 (sonst R10)
   gespeichert, 60 Tage lang.
2. Kandidat = höchster gespeicherter Wert, ab 3 Starts. Er liegt um die Schalthysterese
   unter der eingestellten Heizgrenze.
3. Bestätigt, wenn es in den letzten 14 Tagen mindestens 6 Stunden gab, deren
   Stundenmittel ≥ Kandidat + 1 K lag und in denen keine Heizanforderung bestand.
4. Der Sensor zeigt den zuletzt bestätigten Wert. Er bleibt im Winter stehen (dann
   starten Anforderungen nur bei Kälte, der Kandidat sinkt, wird aber nicht bestätigt)
   und folgt einer Änderung am Bedienteil in der nächsten Übergangszeit: höher sofort
   nach Bestätigung, niedriger spätestens nach 60 Tagen.

Attribute: `candidate`, `confirmed_at`, `starts_60d`, `warm_hours_without_demand_14d`, `basis`,
`setting` (Option `heating_limit`, auch als Sensor „Heizgrenze eingestellt“).

Hinweis zur Heizkurve: Die Kurve der NEO-RWP besteht aus drei Stützpunkten (BA Kap. 6,
*Heizkreis → Heizkurve*). Die Regression ist eine Näherung. Sie enthält das Raumsoll
(Parallelverschiebung) und Zeitprogramme (Absenkung).

### 5.3 Regeln

Ausgabe je Hinweis: `id`, `severity` (info/warning), Titel, Befund, Vorschlag, wer handelt
(selbst / Fachbetrieb). Status des Sensors „Effizienz-Check“:

- `collecting`: weniger als 3 Tage Daten. Dann erscheinen nur sofort gültige Hinweise
  (Störung, kein Raumsensor, Raumsoll hoch, WW hoch).
- `check`: mindestens ein Hinweis mit `warning`.
- `improvable`: mindestens ein Hinweis, ohne „kein Raumsensor“.
- `good`: keine Hinweise.

| id | Bedingung | Vorschlag (Kurzform) | Quelle |
|----|-----------|----------------------|--------|
| fault | R26 ≠ 0 | Code ablesen, Fachbetrieb, nicht wiederholt quittieren | – |
| curve_lower | Raum > Soll + 0,5 K (bei MKR1 Texte und Menüpfad für Mischer 1: „Hauptmenü → Mischer 1 → Heizkurve M1“, Raumsoll Mischer 1 / Entität „MKR1 Raumsoll“) | kalt-mild > 0,7 K: „RL Soll −15°C“ −1…2 K; mild-kalt > 0,7 K: „RL Soll 18/0°C“ −1…2 K; sonst Raumsoll −0,5…1 K | BA Kap. 6 (Schritte 1–2 K, 1–2 Tage), DUH (≈ 2,5 %/K) |
| room_cold | Raum < Soll − 0,7 K | nicht senken, Ventile/Abgleich prüfen, dann +1 K | BA |
| rooms_uneven | ≥ 2 Raumsensoren, Unterschied der 7-Tage-Mittel > 1,5 K | Abgleich/Ventile, warme Etagen drosseln | – |
| curve_above_factory | nur HKR (nicht bei MKR1, Werkswerte gelten für den direkten Kreis); kein Raumsensor, Fußbodenheizung, RL-Soll(0 °C) > 30 °C | Raumsensor ergänzen, schrittweise senken | BA Werkseinstellung 22/27/30 °C |
| buffer_overheat | nur MKR1; `rl_set_0` − `mkr_set_0` > 3 K (Puffer-Ladeziel R34 deutlich über dem Bedarf von Mischer 1) | Heizkurve HKR bzw. Raumsoll HKR schrittweise senken, Puffer ca. 2–3 K über dem Bedarf von Mischer 1; Räume prüfen | DUH (≈ 2,5 %/K) |
| room_set_high | R101 (bei MKR1: R108) > 21,5 °C und kein Raumsensor | erst Raumsensor, nicht pauschal senken (R101 = Parallelverschiebung) | BA |
| heating_limit | > 6 h Heizbetrieb bei ≥ 16 °C in 7 d | „Heizgrenze“ prüfen, ca. 15 °C | DUH |
| heating_limit_mismatch | Heizgrenze beobachtet > Option `heating_limit` + 1 K | Bedienteil mit Option vergleichen, Übersteuerung prüfen | – |
| cycling | Median-Laufzeit < 20 min bei ≥ 5 Starts (warning) oder > 24 Starts/Tag und < 30 min (info) | Ventile offen, Kurve nicht zu hoch; Fachbetrieb: Hysterese, Mindestlaufzeit, Durchfluss | Faustregel |
| spread_high / spread_low | Spreizung > 6 K (FBH) / 8 K (HK) / 7 K (gemischt) bzw. < 2 K | Durchfluss/Abgleich bzw. Pumpe prüfen lassen | Faustregel |
| dhw_high | R105 > 52 °C | 45–50 °C, Legionellenschutz klären | BA Werk 45 °C |
| dhw_spf_low | Arbeitszahl WW 30 d < 2,3 | Temperatur, Zeitprogramm, Zirkulation | Faustregel |
| defrost_warm | ≥ 3 Abtauungen/Tag bei > +5 °C | Außeneinheit, Luftweg prüfen | – |
| superheat | Überhitzung 7 d außerhalb 2–12 K | nur Fachbetrieb | – |
| spf_below_plan | Arbeitszahl 30 d < geplante − 0,3 | Werte mit Fachbetrieb besprechen | DUH |
| spf_low | Arbeitszahl Heizen 30 d < 3,0 | Hauptstellhebel | Faustregel |
| no_room_sensor | keine Raumsensoren konfiguriert | Sensor wählen | – |
| price_lock_ineffective | Wirkungskontrolle 4.2.1 fehlgeschlagen | Verdrahtung prüfen lassen | – |

**Mehrere Raumsensoren:** Jeder Sensor wird pro Stunde einzeln gespeichert
(`Bucket.rooms`). Bei zwei oder mehr Sensoren entscheidet der **kälteste Raum**:
`curve_lower` nur, wenn dessen Abweichung > 0,5 K ist; `room_cold`, sobald sie < −0,7 K ist.
Steil/Fußpunkt wird mit dem Minimum der Kalt- bzw. Mild-Abweichungen aller Räume bewertet.
Die Raumliste steht im Attribut `rooms` des Sensors „Effizienz-Check“.

Alle Schwellen sind Richtwerte und stehen als Konstanten in `advisor.py`.

---

## 6. Lebenszyklus

| Phase | Ablauf |
|-------|--------|
| Einrichtung | Testlesen von R10 (FC 04). `unique_id` = `host:port:unit` |
| Start | Effizienzdaten laden → erster Refresh (bei Fehler: `SETUP_RETRY`) → Altwerte bereinigen (PV, Preissperre; nur bei Freigabe) → Plattformen. Entitäten, die nicht mehr existieren oder nicht mehr freigegeben sind, werden aus der Entity-Registry entfernt |
| Betrieb | Zyklus 2.1 → Netzbetreiber-Erkennung → PV-Vorrang → PV-Watchdog → Preissperren-Wächter → Effizienz-Check |
| Optionen geändert | Neuladen der Integration (Entladen + Start) |
| Stopp / Entladen | PV 0 und Preissperre aus (nur bei Freigabe), Effizienzdaten speichern, Verbindung schließen |
| HA-Absturz | keine Rücksetzung möglich. Beim nächsten Start werden PV-Vorgabe und Sperre zurückgesetzt. Beim Shelly-Aufbau greift zusätzlich dessen Auto-Aus |

---

## 7. Optionen

| Option | Schlüssel | Standard | Wirkung |
|--------|-----------|----------|---------|
| Heizsystem | `heating_system` | underfloor | Richtwerte Spreizung, Werkskurven-Vergleich |
| Heizkreis für den Effizienz-Check | `heating_circuit` | auto | auto / hkr / mkr1 / mkr2, 5.1 |
| Raumtemperatur-Sensoren | `room_sensors` | – | Werte für den Check |
| Raumsensoren zusammenfassen | `room_grouping` | floor | floor = Mittelwert pro Stockwerk, sensor = einzeln, 5.1 |
| Geplante JAZ | `expected_spf` | 0 | Vergleichswert |
| Heizgrenze laut Bedienteil | `heating_limit` | 0 | Vergleich mit der gelernten Heizgrenze, 0 = unbekannt |
| Signal des Netzbetreibers | `grid_signal` | – | Binärsensor, 4.3 |
| Einstellungen schreiben | `allow_write` | false | 3.2 |
| PV-Steuerung | `allow_pv` | false | 3.2, 4.1 |
| Preissperre | `allow_price_lock` | false | 3.2, 4.2 |
| Preissperre max. Dauer | `price_lock_max_minutes` | 120 | 30–120 |
| Preissperre externer Schalter | `price_lock_switch` | – | 4.2.1 |
| Abfrageintervall | `scan_interval` | 15 | 5–300 s |
| PV-Watchdog | `pv_watchdog` | 120 | 0 = aus |
| Max. PV-Vorgabe | `pv_max_power` | 6000 | W |

---

## 8. Erstinbetriebnahme: Prüfprogramm

Empfohlen in dieser Reihenfolge. Jede Stufe erst abschließen, dann die nächste.

**Stufe 1 – nur lesen (Standard).** Kein Risiko für die Anlage. Die Integration schreibt
nichts.

1. Integration einrichten, Intervall 30 s, falls `ha_heliotherm` parallel läuft.
2. Werte mit dem Display bzw. dem RKM-Webinterface vergleichen:
   Außen-, VL-, RL-, WW-Temperatur, Betriebsart, Anforderung, Zähler.
3. Plausibilisieren: Durchfluss in l/min, EVU-Freigabe = an (ohne Sperre), Betriebsstunden.
   Unbekannte Fühler sind `unknown`.
4. Diagnose herunterladen (Gerät → ⋮ → Diagnose). `optional_blocks_ok` zeigt, ob 42–45
   und 147–150 vorhanden sind.
5. Bei Verbindungsabbrüchen: Intervall erhöhen oder die zweite Integration abschalten.

**Stufe 2 – Einstellungen schreiben.**

1. Freigabe setzen. Raumsoll um 0,5 K ändern, am Display prüfen, zurückstellen.
2. Nach einigen Stunden prüfen, ob sich R34 (Rücklaufsolltemperatur) passend verschoben
   hat. Das bestätigt die Parallelverschiebung.

**Stufe 3 – PV** (nur wenn im RKM „Modbus TCP“ als PV-Auswahl gesetzt ist).

1. Freigabe setzen, `number.…_pv_leistung` von Hand auf einen kleinen Wert stellen und im
   RKM-Webinterface (PV/SG) prüfen. Nach 120 s ohne Erneuerung muss der Wert auf 0 gehen.
2. Danach die Package-Automation freigeben.

**Stufe 4 – Preissperre.**

1. Freigabe setzen, Sperre von Hand einschalten. Am Display muss „EVU-Sperre“ erscheinen,
   R100 Status ggf. 9. Ausschalten, Rückkehr prüfen.
2. Beobachten, wie sich R32 bei der eigenen Modbus-Sperre verhält (siehe 4.3), und das
   Ergebnis hier nachtragen.

---

## 9. Bekannte Grenzen und offene Punkte

- Die Registerbelegung basiert auf RKM 7734937-01 (2019). Neuere Firmware ist nicht
  geprüft. Reg. 41 = 40 („Externe Anforderung“) stammt aus Nutzerberichten zu
  Heliotherm, nicht aus der NEO-Doku.
- Heizkurve, Hysterese, Heizgrenze und Heizstab-Betrieb sind über Modbus nicht
  schreib- oder lesbar. Der Check gibt dafür Menühinweise. Heizkurve und Heizgrenze
  werden aus dem Betrieb abgeleitet (5.2).
- SG-Ready-Eingänge und PV-Status des RKM sind nicht über Modbus lesbar.
- Ob das RKM mehrere Modbus-Clients gleichzeitig bedient, ist nicht dokumentiert.
- Die Hinweistexte des Effizienz-Checks sind nur deutsch.
- Die Tagessumme der Sperren beginnt nach einem HA-Neustart bei 0.

---

## 10. Tests

`pytest` mit `pytest-homeassistant-custom-component` und einem simulierten Modbus-Client
(`tests/conftest.py`). Zusätzlich gab es einen manuellen Lauf gegen einen echten
`pymodbus`-Server. Abgedeckt sind unter anderem:

- Dekodierung, Kennwerte für „ungültig“, Blockabdeckung aller Register
- nur lesend: keine Entität und **kein einziger Schreibzugriff**, auch nicht durch
  Watchdog oder Entladen
- Ablehnung aller Werte außerhalb der Positivliste und aller nicht freigegebenen Register
- PV-Watchdog, Rücksetzung bei Start und Entladen
- Preissperre: Pause, Tageslimit, Frost, Maximaldauer, Altzustand, externer Schalter,
  Wirkungskontrolle
- Netzbetreiber-Vorrang (R32 und externer Sensor), eigene Sperre ≠ Netzbetreiber
- Effizienz-Check: Kennzahlen, alle Heizkurven-Fälle, Takten, WW, Persistenz,
  Kühlen ≠ Abtauen
- Package, Karte und Auswerteskript gegen die echten deutschen Entity-IDs

```bash
pip install -r requirements_test.txt
```

```bash
ruff check . && ruff format --check . && pytest -q
```
