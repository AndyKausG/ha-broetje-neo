# Dashboard (Puffer + Mischerkreis 1)

Wandtablet-Dashboard für Anlagen mit Puffer und Fußbodenheizung an MKR1.
Hauptfrage in der Übergangszeit: **Hat die Heizung schon eingeschaltet?**

| Datei | Inhalt |
|-------|--------|
| `extras/dashboard/broetje-neo-dashboard.yaml` | Dashboard (Ansicht „Abschnitte“, 4 Spalten) |

Alle Werte liefert die Integration (ab 0.6.0). Ein Package ist nicht nötig;
`extras/packages/broetje_neo_analytics.yaml` bleibt optional für PV-Auswertung und
Automationen (siehe README).

## Voraussetzungen

HACS → Frontend:

| Karte | Repository | Verwendung |
|-------|------------|------------|
| ApexCharts Card | `RomRider/apexcharts-card` | 30-Tage- und 24-h-Diagramm |
| button-card | `custom-cards/button-card` | Anlagenschema mit Animation |

Das 30-Tage-Diagramm liest die **Langzeitstatistik** (Tageszuwachs der „heute“-Zähler,
Tagesmittel Außentemperatur). Es braucht kein `purge_keep_days` > 10, füllt sich aber
erst ab der Version 0.6.0.

Dashboard anlegen (die Datei ist ein komplettes Dashboard, **keine Karte**; im Dialog
„Karte anpassen“ kommt „No card type configured“):

1. *Einstellungen → Dashboards → Dashboard hinzufügen → Neu von Grund auf*
2. Dashboard öffnen → Stift (Bearbeiten) → ⋮ → *Rohkonfigurationseditor*
3. Gesamten Inhalt durch die Datei ersetzen → Speichern

Heizgrenze: über Modbus nicht lesbar. Der Effizienz-Check lernt sie aus dem Betrieb
(`sensor.brotje_neo_heizgrenze_beobachtet`, siehe `docs/TECHNIK.md` 5.2). Optional den
Wert vom Bedienteil in den Optionen der Integration eintragen („Heizgrenze laut
Bedienteil“) -> `sensor.brotje_neo_heizgrenze_eingestellt`. Beide erscheinen als Linie
im 30-Tage-Diagramm; liegt die gelernte mehr als 1 K darüber, meldet der Effizienz-Check das.

## Status (`sensor.brotje_neo_status`)

Erste zutreffende Zeile gewinnt. Der Zustand ist ein sprachneutraler Schlüssel, HA
zeigt den übersetzten Text.

| Prio | Schlüssel | Anzeige | Bedingung |
|------|-----------|---------|-----------|
| 1 | `fault` | Störung | Störung an |
| 2 | `price_lock` | Preissperre | eigene Preissperre aktiv |
| 3 | `utility_lock` | EVU-Sperre | EVU-Freigabe aus oder Betriebsart `evu_lock` |
| 4 | `off` | Aus | Betriebsart `off` / `main_switch_off` |
| 5 | `defrost` | Abtauen | 4-Wege-Ventil an, keine Kühlanforderung, Kühlen passiv aus |
| 6 | `hot_water` | Warmwasser | Verdichter an + Anforderung WW |
| 7 | `heating` | Heizen | Verdichter an + Anforderung Heizen |
| 8 | `cooling` | Kühlen | Anforderung Kühlen oder Kühlen passiv |
| 9 | `compressor_running` | Verdichter läuft | Verdichter an ohne Anforderung (PV, extern) |
| 10 | `heating_demand` | Heizanforderung | Anforderung Heizen, Verdichter aus (Puffer reicht) |
| 11 | `dhw_demand` | WW-Anforderung | Anforderung WW, Verdichter aus |
| 12 | `summer` | Sommerbetrieb | Betriebsart `summer` |
| 13 | `standby` | Standby | sonst |

## Laufzeiten, Tageswerte, Heizstart

Aus den Stundenwerten des Effizienz-Checks (überstehen einen Neustart, 14 Tage).
Tagesgrenze = Mitternacht in der Zeitzone von HA.

| Entität | Bedeutung |
|---------|-----------|
| `binary_sensor.brotje_neo_verdichter_heizt` | Verdichter an **und** Anforderung Heizen |
| `sensor.brotje_neo_heizanforderung_zuletzt_gestartet` | Zeitpunkt letzte Heizanforderung |
| `sensor.brotje_neo_verdichter_heizen_zuletzt_gestartet` | Zeitpunkt letzter Verdichterstart fürs Heizen |
| `sensor.brotje_neo_heizperiode_gestartet` | Erste Heizanforderung nach > 14 Tagen Pause |
| `sensor.brotje_neo_heizanforderung_{heute,gestern,7_tage}` | h |
| `sensor.brotje_neo_verdichterlaufzeit_{heute,gestern,7_tage}` | h |
| `sensor.brotje_neo_verdichterlaufzeit_heizen_{heute,gestern,7_tage}` | h |
| `sensor.brotje_neo_strom_heute` / `…_warme_heute` | kWh, aus der Momentanleistung |
| `sensor.brotje_neo_arbeitszahl_heute` | Wärme / Strom heute, ab 0,2 kWh Strom |

## Entitätszuordnung

Annahme: Gerätename „Brötje NEO“, HA-Sprache Deutsch → Präfix `brotje_neo_`.
Anderer Gerätename: in der Dashboard-Datei `brotje_neo_` per Suchen/Ersetzen ändern.
Die IDs werden in `tests/test_package.py` gegen die Integration geprüft.

| Anzeige | Entität | Reg. |
|---------|---------|------|
| Außen | `sensor.brotje_neo_aussentemperatur` | 10 |
| WP Vorlauf / Rücklauf (= Pufferladung) | `sensor.brotje_neo_vorlauftemperatur` / `…_rucklauftemperatur` | 12 / 13 |
| Puffer / Puffer Soll | `sensor.brotje_neo_puffertemperatur` / `…_rucklaufsolltemperatur` | 14 / 34 |
| Warmwasser | `sensor.brotje_neo_warmwassertemperatur` | 11 |
| FBH Vorlauf Soll | `sensor.brotje_neo_mkr1_vorlaufsoll` | 35 |
| Verdichter % | `sensor.brotje_neo_verdichterdrehzahl` | 29 |
| Heizanforderung / WW / Kühlen | `binary_sensor.brotje_neo_heizen` / `…_warmwasser` / `…_kuhlen` | 41 |
| Heizkreispumpe | `binary_sensor.brotje_neo_heizkreispumpe` | 23 |
| Pufferladepumpe | `binary_sensor.brotje_neo_pufferladepumpe` | 24 |
| Verdichter / Ventilator | `binary_sensor.brotje_neo_verdichter` / `…_ventilator` | 25 / 37 |
| Abtauen | `binary_sensor.brotje_neo_abtauen` | 27 |
| COP live | `sensor.brotje_neo_cop_berechnet` | 74 / 70 |
| Betriebsart / MKR1-Betriebsart | `sensor.brotje_neo_betriebsart_status` / `…_mkr1_betriebsart_status` | 100 / 107 |
| Kältekreis | `sensor.brotje_neo_niederdruck` / `…_hochdruck` / `…_verdampfungstemperatur` / `…_kondensationstemperatur` / `…_expansionsventil` | 21 / 22 / 18 / 19 / 40 |
| Heizkurve MKR1 (gemessen) | `sensor.brotje_neo_mischer_1_heizkurve_vl_soll_bei_{18,0,minus_15}_grad` | Effizienz-Check |

Nicht verfügbar (NEO-RKM): Mischer-Vorlauf/-Rücklauf Ist, Mischerpumpe,
Mischerstellung, Heizkurve, Heizgrenze. Ob Reg. 23 „Heizkreispumpe“ bei einer
reinen MKR1-Anlage schaltet, ist anlagenabhängig: im 24-h-Verlauf prüfen. Bleibt
sie dauerhaft aus, im Schema (`mkr = on('binary_sensor.brotje_neo_heizkreispumpe')`)
z. B. `binary_sensor.brotje_neo_heizen` eintragen.

## Schema

Bewegung nur bei Aktivität:

| Element | Animation |
|---------|-----------|
| Lüfter | dreht bei Ventilator an, Tempo nach Verdichterdrehzahl |
| Verdichter | pulsiert bei Lauf |
| Pufferkreis | fließt bei Pufferladepumpe an; beim Abtauen rückwärts |
| WW-Kreis | fließt bei Verdichter an + WW-Anforderung |
| MKR1 / FBH | fließt bei Heizkreispumpe an |
| Kältekreis | fließt bei Verdichterlauf (kalt → Verdichter → heiß → Expansionsventil) |
| Umschaltventil | zeigt, welcher Speicher geladen wird (Text „Ventil: Puffer/Warmwasser“) |
| Speicher | Farbe nach Temperatur (20 °C blau → 60 °C rot) |

Im Ruhezustand sind alle Leitungen grau und statisch. Im Stillstand zeigen Nieder- und
Hochdruck denselben Wert (Druckausgleich), das Schema sagt das ausdrücklich.

Weitere Elemente:

- **Klartext**: ein Satz je Zustand (z. B. „Das Haus braucht Wärme. Der Puffer ist noch
  warm genug, die Wärmepumpe wartet.“) und eine Zeile zur Fußbodenheizung.
- **Heizkurve MKR1**: Linie aus den vom Effizienz-Check gemessenen Stützpunkten
  (+18 / 0 / −15 °C), Punkt = aktuelle Außentemperatur und Vorlaufsoll. Solange der
  Check noch sammelt, fehlt die Linie.
