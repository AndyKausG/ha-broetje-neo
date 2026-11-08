# Dashboard

Die Integration bringt ihr Dashboard selbst mit. **Kein Package, keine YAML zum Einfügen,
`button-card` wird nicht gebraucht.** Hauptfrage in der Übergangszeit: **Hat die Heizung
schon eingeschaltet?**

| Teil | Typ | Inhalt |
|------|-----|--------|
| Dashboard-Strategie | `strategy: type: custom:broetje-neo` | Komplettes Dashboard (Ansicht „Abschnitte“, 4 Spalten): Status, „Heizt sie schon?“, Temperaturen, Effizienz, Laufzeiten, Anlagenschema, 30 Tage Übergangszeit, 24 h |
| Karte | `type: custom:broetje-neo-card` | Animiertes Anlagenschema, auch in eigenen Dashboards nutzbar |

Beides lädt die Integration automatisch (Datei `custom_components/broetje_neo/frontend/broetje-neo.js`).
Die Entitäten werden über die Integration gefunden, Gerätename und HA-Sprache spielen keine Rolle.

## Einrichten

1. Integration auf mindestens 0.6.0 aktualisieren, HA neu starten, Browser neu laden
   (in der Companion-App: *Einstellungen → Companion-App → Fehlerbehebung → Frontend-Cache leeren*).
2. *Einstellungen → Dashboards → Dashboard hinzufügen*. Wird „Brötje NEO“ angeboten, das
   wählen. Sonst „Neu von Grund auf“ → Dashboard öffnen → Stift → ⋮ → *Rohkonfigurationseditor*,
   gesamten Inhalt ersetzen durch:

```yaml
strategy:
  type: custom:broetje-neo
```

Optionen der Strategie:

| Option | Werte | Standard |
|--------|-------|----------|
| `charts` | `auto`, `apexcharts`, `core` | `auto`: ApexCharts, wenn installiert, sonst die eingebauten Statistik-/Verlaufskarten |
| `title` | Text | „Wärmepumpe“ |
| `device_id` | Geräte-ID | erstes Brötje-NEO-Gerät |

Anpassen: Im Dashboard *⋮ → Kontrolle übernehmen*. HA wandelt die Strategie dann in
normale, editierbare Karten um (die automatische Anpassung an neue Versionen endet damit).

Karte einzeln (Karte hinzufügen → „Brötje NEO“ oder YAML):

```yaml
type: custom:broetje-neo-card
# optional:
# device_id: <Geräte-ID>
# heating_pump_entity: binary_sensor.brotje_neo_heizen   # wenn Reg. 23 bei dir nicht schaltet
```

Optional für schönere Diagramme (Balken + Linie mit zwei Achsen): HACS → Frontend →
`apexcharts-card` (RomRider). Ohne sie nutzt das Dashboard die eingebauten Karten.

Das 30-Tage-Diagramm liest die **Langzeitstatistik** (Tageszuwachs der „heute“-Zähler,
Tagesmittel Außentemperatur). Es braucht kein `purge_keep_days` > 10, füllt sich aber
erst ab der Version 0.6.0.

Heizgrenze: über Modbus nicht lesbar. Der Effizienz-Check lernt sie aus dem Betrieb
(„Heizgrenze beobachtet“, siehe `docs/TECHNIK.md` 5.2). Optional den Wert vom Bedienteil
in den Optionen der Integration eintragen („Heizgrenze laut Bedienteil“). Beide erscheinen
im 30-Tage-Diagramm; liegt die gelernte mehr als 1 K darüber, meldet der Effizienz-Check das.

Ob Reg. 23 „Heizkreispumpe“ bei einer reinen MKR1-Anlage schaltet, ist anlagenabhängig:
im 24-h-Verlauf prüfen. Bleibt sie dauerhaft aus, in der Karte `heating_pump_entity` setzen.

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

Bei aktivierter Einstellung „Bewegung reduzieren“ (Betriebssystem/Browser) bleiben alle
Animationen aus; Farben und Werte bleiben.
