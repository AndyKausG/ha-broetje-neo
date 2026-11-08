# Brötje NEO (NEO-RKM) – Home Assistant Integration

Home-Assistant-Integration für Brötje-Wärmepumpen der Baureihe **BLW NEO** mit dem
Kommunikationsmodul **NEO-RKM** (Modbus TCP). Entwickelt und getestet für die
BLW NEO 18b.

> Nicht für IWR/GTW-08 oder ISR Plus. Für diese Module gibt es
> [ha-broetje](https://github.com/henrywiechert/ha-broetje).

## Funktionen

- Alle Lese- und Schreibregister laut NEO-RKM-Montageanleitung 7734937-01, Kap. 7.1
  (Tab. 4/5), inkl. Betriebsstunden (Reg. 42–45) und Overrides 147–150
- Langzeitstatistik für alle Messwerte (`state_class`), Energiezähler für das
  Energie-Dashboard
- Abgeleitete Werte: Spreizung VL/RL, Überhitzung, Temperaturhub,
  Kondensator-Grädigkeit, Spreizung Quelle, COP berechnet, Arbeitszahlen seit
  Inbetriebnahme (gesamt/Heizen/WW)
- Betriebsmodi als Binärsensoren (Heizen, Warmwasser, Kühlen) z.B. für die
  `lovelace-heat-pump-card`
- Schreibbar: Betriebsart (HKR, MKR1/2), Raumsoll, WW-Normal/-Min, RLT min Kühlen,
  PV-Leistung (Reg. 125); weitere Overrides standardmäßig deaktiviert
- Asynchroner Modbus-Zugriff, Wiederverbindung, Entitäten werden bei
  Kommunikationsfehlern `unavailable` statt Fehlwerte zu liefern
- Schreibschutz: Bereichsprüfung, mindestens 5 s zwischen Schreibzugriffen auf
  dasselbe Register (Herstellervorgabe)
- PV-Watchdog für Register 125
- Diagnose-Download mit Rohregister-Dump

## Installation

HACS → Integrationen → ⋮ → Benutzerdefinierte Repositories →
`https://github.com/AndyKausG/ha-broetje-neo` (Kategorie Integration) →
"Brötje NEO (NEO-RKM)" installieren → HA neu starten →
Einstellungen → Geräte & Dienste → Integration hinzufügen → "Brötje NEO".

Voraussetzung im NEO-RKM-Webinterface: Service → Grundbedienung → Modbus →
Modbus TCP aktivieren, RKM neu starten.

| Feld    | Default      | Hinweis                                          |
|---------|--------------|--------------------------------------------------|
| Name    | Brötje NEO   | bestimmt die Entity-IDs (`sensor.brotje_neo_*`)  |
| Host    | –            | IP des NEO-RKM                                   |
| Port    | 502          |                                                  |
| Unit-ID | 1            |                                                  |

Optionen: Abfrageintervall (Default 15 s), PV-Watchdog (Default 120 s, 0 = aus),
maximale PV-Leistungsvorgabe (Default 6000 W).

## Entitäten (Auszug)

| Plattform     | Entitäten |
|---------------|-----------|
| sensor        | Temperaturen (Außen, VL, RL, WW, Puffer, Quelle, Sauggas, Verdampfung, Kondensation, Heißgas), Drücke, Durchfluss (l/min), Verdichterdrehzahl %, Expansionsventil %, COP, el./th. Leistung, 6 Energiezähler, Betriebsstunden, Anforderung, Betriebsart-Status, abgeleitete Werte |
| binary_sensor | Heizkreispumpe, Pufferladepumpe, Verdichter, Ventilator, Störung, Abtauen, EVU-Freigabe, WW-Vorrang, Kühlen passiv, Heizen, Warmwasser, Kühlen |
| select        | Betriebsart, MKR1/MKR2-Betriebsart |
| number        | Raumsoll, WW-Normal/Min, Kühlen RLT min, PV-Leistung, (deaktiviert:) Rücklaufsoll, MKR-Sollwerte, Fühler-Vorgaben, Drehzahlvorgabe |
| switch        | (alle deaktiviert) "aktiv"-Flags der Vorgaben 103/110/115/117/127/130/132/134/147–150 |
| button        | Entstören (Reg. 128, Impuls) |

Hinweise:
- **EVU-Freigabe** (Reg. 32): `an` = Betrieb freigegeben, `aus` = EVU-Sperre.
- **Betriebsart 8–10** (Ausheizen, EVU-Sperre, Hauptschalter aus) ist nur lesbar:
  Das Select zeigt dann "unbekannt", der Sensor "Betriebsart Status" den Wert.
- **Overrides** (z.B. Rücklaufsoll aktiv, Reg. 103): Solange aktiv, ignoriert die WP
  den eigenen Regler bzw. das Raumsoll. Ausschalten schreibt immer 0.
- Fühler, die die Anlage nicht liefert (Rohwert −50,0 °C), sind `unbekannt`.
- Energiezähler mit Rohwert 0 werden verworfen (verhindert falsche Resets in der
  Statistik).

## PV-Überschuss

Das NEO-RKM kann den PV-Überschuss selbst nutzen (Kap. 7.2). Im RKM-Webinterface
unter Photovoltaik die PV-Auswahl **Modbus TCP** wählen und dort Leistungsschwelle,
Einschaltverzögerung, Mindestlaufzeit und Max-Begrenzung einstellen. HA schreibt
dann nur den verfügbaren Überschuss in W nach `number.brotje_neo_pv_leistung`
(Reg. 125). Start, Sollwertanhebung (WW-Max, HZ-Offset) und Modulation regelt
das RKM.

Schutzmechanismen:
1. Freigabe-Schalter im Package (`input_boolean.wpa_pv_vorgabe_freigabe`, Default aus)
2. Sicherheitsabzug (Default 200 W), Rundung auf 50 W
3. Ausfall von PV- oder Netzmesswerten → 0 W
4. Watchdog der Integration: Wird Reg. 125 nicht innerhalb der eingestellten Zeit
   neu geschrieben, setzt die Integration 0. Beim HA-Start (Altwert) und beim
   Stopp/Entladen wird ebenfalls 0 geschrieben.

Restrisiko: Stürzt HA ab, ohne sauber zu stoppen, bleibt der letzte Wert im RKM
stehen, bis HA wieder läuft. Deshalb im RKM eine sinnvolle Max-Begrenzung und
Mindestlaufzeit einstellen.

## Auswertung (`extras/`)

| Datei | Zweck |
|-------|-------|
| `extras/packages/broetje_neo_analytics.yaml` | HA-Package: Strom/Wärme fein integriert (Riemann) und nach Heizen/WW getrennt, Tages-/Monats-/Jahreszähler, Arbeitszahl Tag/Monat/Jahr, **PV-Anteil**, Verdichterstarts, Laufzeit pro Start, Abtauungen, EVU-Sperrzeit, PV-Überschuss-Automation |
| `extras/tools/analyze_heatpump.py` | Offline-Auswertung der HA-Datenbank: Monats-AZ, Takten, Abtauen über Außentemperatur, Heizkurve (Fit), Spreizung, Überhitzung, Bewertung gegen Richtwerte |
| `extras/lovelace/heat-pump-card.yaml` | Konfiguration für `lovelace-heat-pump-card` |

Package: Datei nach `/config/packages/` kopieren, in `configuration.yaml`
`homeassistant: packages: !include_dir_named packages` eintragen und die drei
Platzhalter `sensor.anpassen_*` (PV-Leistung, Netzbezug, Einspeisung in W)
ersetzen.

Skript (nur Python-Standardbibliothek, liest die DB nur lesend):

```bash
sqlite3 /config/home-assistant_v2.db ".backup /tmp/ha.db"
```

```bash
python3 analyze_heatpump.py /tmp/ha.db --since 2025-03-01
```

Mit `--profile heliotherm --prefix brotje_blw_neo18b` lassen sich die Daten der
bisherigen `ha_heliotherm`-Integration auswerten. Die Monats-AZ kommt aus der
Langzeitstatistik der Energiezähler. Takten, Heizkurve und Kältekreis gehen nur
über den Rohverlauf (Recorder `purge_keep_days`, Default 10 Tage).

## Umstieg von ha_heliotherm

Beide Integrationen können zum Vergleich parallel laufen, sofern das RKM mehrere
Modbus-Clients zulässt. Bei Verbindungsabbrüchen eine von beiden deaktivieren.
Die Entity-IDs sind neu, die Statistik beginnt neu. Die alte Historie bleibt in
der Datenbank und kann mit dem Skript (Profil `heliotherm`) ausgewertet werden.

## Entwicklung

```bash
pip install -r requirements_test.txt
```

```bash
ruff check . && ruff format --check . && pytest -q
```

Übersetzungen (`strings.json`, `translations/*.json`) werden aus
`scripts/gen_translations.py` erzeugt. Die Registerbelegung steht ausschließlich
in `custom_components/broetje_neo/registers.py`.

## Lizenz und Herkunft

MIT, siehe [LICENSE](LICENSE).

Die Registerbelegung stammt aus der öffentlichen Brötje-Dokumentation
(NEO-RKM-Montageanleitung 7734937-01). Die Herstellerdokumente sind nicht Teil
dieses Repos. Die Idee geht auf
[mbuchber/ha_heliotherm](https://github.com/mbuchber/ha_heliotherm) zurück, die
Architektur orientiert sich an
[henrywiechert/ha-broetje](https://github.com/henrywiechert/ha-broetje). Aus
beiden Projekten wurde kein Code übernommen.

Keine Verbindung zur BDR Thermea Group / August Brötje GmbH. Nutzung auf eigenes
Risiko: Über Modbus lässt sich die Regelung der Wärmepumpe übersteuern.
