# Dashboard (Puffer + Mischerkreis 1)

Wandtablet-Dashboard für Anlagen mit Puffer und Fußbodenheizung an MKR1.
Hauptfrage in der Übergangszeit: **Hat die Heizung schon eingeschaltet?**

| Datei | Inhalt |
|-------|--------|
| `extras/dashboard/broetje-neo-dashboard.yaml` | Dashboard (Ansicht „Abschnitte“, 4 Spalten) |
| `extras/packages/broetje_neo_dashboard.yaml` | Status, Laufzeiten, Heizstart, Heizperiode, Heizgrenze (`wpd_*`) |
| `extras/packages/broetje_neo_analytics.yaml` | Tages-Arbeitszahl u.a. (`wpa_*`), siehe README |

## Voraussetzungen

HACS → Frontend:

| Karte | Repository | Verwendung |
|-------|------------|------------|
| ApexCharts Card | `RomRider/apexcharts-card` | 30-Tage- und 24-h-Diagramm |
| button-card | `custom-cards/button-card` | Anlagenschema mit Animation |

Packages nach `/config/packages/` kopieren:

```yaml
homeassistant:
  packages: !include_dir_named packages
```

Recorder: Das 30-Tage-Diagramm liest die **Langzeitstatistik** (Tagesmaximum der
„heute“-Laufzeiten, Tagesmittel Außentemperatur). Es braucht daher kein
`purge_keep_days` > 10, füllt sich aber erst ab Installation des Packages.

Dashboard anlegen: *Einstellungen → Dashboards → Dashboard hinzufügen → Neu von
Grund auf → Bearbeiten → ⋮ → Rohkonfigurationseditor*, Datei einfügen.

Heizgrenze: über Modbus nicht lesbar. Der Effizienz-Check lernt sie aus dem Betrieb
(`sensor.brotje_neo_heizgrenze_beobachtet`, siehe `docs/TECHNIK.md` 5.2). Optional zum
Vergleich den Wert vom Bedienteil in `input_number.wpd_heizgrenze` (`initial`) eintragen.
Beide erscheinen als Linie im 30-Tage-Diagramm.

## Status-Logik (`sensor.wpd_status`)

Erste zutreffende Zeile gewinnt. `sensor.wpd_status_code` liefert den
sprachneutralen Code, `sensor.wpd_status` den Anzeigetext.

| Prio | Code | Anzeige | Bedingung |
|------|------|---------|-----------|
| 1 | `stoerung` | Störung | Störung an |
| 2 | `evu_sperre` | EVU-Sperre | EVU-Freigabe aus oder Betriebsart `evu_lock` |
| 3 | `aus` | Aus | Betriebsart `off` / `main_switch_off` |
| 4 | `abtauen` | Abtauen | 4-Wege-Ventil an, keine Kühlanforderung, Kühlen passiv aus |
| 5 | `warmwasser` | Warmwasser | Verdichter an + Anforderung WW |
| 6 | `heizen` | Heizen | Verdichter an + Anforderung Heizen |
| 7 | `kuehlen` | Kühlen | Anforderung Kühlen oder Kühlen passiv |
| 8 | `verdichter` | Verdichter läuft | Verdichter an ohne Anforderung (PV, extern) |
| 9 | `heizanforderung` | Heizanforderung | Anforderung Heizen, Verdichter aus (Puffer reicht) |
| 10 | `ww_anforderung` | WW-Anforderung | Anforderung WW, Verdichter aus |
| 11 | `sommer` | Sommerbetrieb | Betriebsart `summer` |
| 12 | `standby` | Standby | sonst |

## Weitere Hilfssensoren

| Entität | Bedeutung |
|---------|-----------|
| `binary_sensor.wpd_verdichter_heizen` | Verdichter an **und** Anforderung Heizen |
| `sensor.wpd_heizanforderung_zuletzt_gestartet` | Zeitpunkt letzte Heizanforderung (timestamp) |
| `sensor.wpd_verdichter_heizen_zuletzt_gestartet` | Zeitpunkt letzter Verdichterstart fürs Heizen |
| `sensor.wpd_heizperiode_gestartet` | Erste Heizanforderung nach > 14 Tagen Pause (Wert `pause_tage` im Package) |
| `sensor.wpd_heizanforderung_{heute,gestern,7_tage}` | history_stats, h |
| `sensor.wpd_verdichterlaufzeit_{heute,gestern,7_tage}` | history_stats, h |
| `sensor.wpd_verdichterlaufzeit_heizen_{heute,gestern,7_tage}` | history_stats, h |

Trigger-Template-Sensoren überstehen einen Neustart (Zustand wird wiederhergestellt).

## Entitätszuordnung

Annahme: Gerätename „Brötje NEO“, HA-Sprache Deutsch → Präfix `brotje_neo_`.
Anderer Gerätename: in beiden YAML-Dateien `brotje_neo_` per Suchen/Ersetzen ändern.
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
