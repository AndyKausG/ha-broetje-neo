# Brötje NEO (NEO-RKM) für Home Assistant

Zeigt die Werte deiner Brötje-Wärmepumpe **BLW NEO** in Home Assistant an und hilft
dir, die Anlage mit echten Messwerten zu verstehen und zu optimieren. Optional nutzt
sie PV-Überschuss und pausiert bei hohen Strompreisen.

Voraussetzung: Kommunikationsmodul **NEO-RKM** mit Netzwerkanschluss (Modbus TCP).
Entwickelt mit einer BLW NEO 18b. Für die Module IWR/GTW-08 oder ISR Plus gibt es
[ha-broetje](https://github.com/henrywiechert/ha-broetje).

---

## ⚠️ Haftungsausschluss und Sicherheit – bitte lesen

- Dies ist ein **privates, kostenloses Hobbyprojekt**. Es ist **kein Produkt von
  Brötje** und steht in keiner Verbindung zur August Brötje GmbH / BDR Thermea.
- Die Software wird **„wie besehen“, ohne jede Gewährleistung** bereitgestellt (MIT-Lizenz,
  siehe [LICENSE](LICENSE)). **Die Nutzung erfolgt auf eigene Gefahr.** Soweit
  gesetzlich zulässig, übernimmt der Autor **keine Haftung** für Schäden an der Anlage,
  am Gebäude, für Energiekosten oder Folgeschäden.
- Eingriffe in die Regelung können Garantie- oder Gewährleistungsansprüche gegenüber
  Hersteller oder Installateur berühren. Im Zweifel den Fachbetrieb fragen.
- **Nach der Einrichtung ist die Integration nur lesend.** Steuern musst du in den
  Optionen ausdrücklich freischalten.

### So schützt die Integration deine Anlage

| Schutz | Wirkung |
|--------|---------|
| Nur lesend als Standard | Ohne Freigabe wird nichts an die Wärmepumpe gesendet |
| Kurze Positivliste | Geschrieben werden darf nur das, was du auch am Bedienteil einstellen kannst, plus PV-Leistung und Sperre |
| Sichere Grenzen | Raum 15–25 °C, Warmwasser 40–55 °C (Minimum 35–50 °C), Kühlen Rücklauf min. 18–25 °C (Schutz vor Kondenswasser an der Fußbodenheizung) |
| Kein „Aus“ | Die Betriebsart „Aus“ lässt sich nicht aus HA setzen (Frostgefahr) |
| Nicht enthalten | Falsche Fühlerwerte vorgeben, Verdichterdrehzahl vorgeben, Vorlauf/Rücklauf erzwingen, 2. Stufe/Heizstab schalten, Störungen quittieren, EVU-Freigabe erzwingen |
| Prüfung im Kern | Jeder Schreibbefehl wird zentral geprüft, auch aus Automationen und Skripten. Die Grenzen lassen sich nicht umgehen |
| Schonend schreiben | Höchstens alle 5 s auf dasselbe Register (Herstellervorgabe) |
| Rückfall in den Normalbetrieb | Bei HA-Start, -Stopp und Entfernen der Integration werden PV-Vorgabe und Preissperre zurückgesetzt |

Restrisiko: Stürzt Home Assistant ab, ohne sauber zu beenden, bleibt eine aktive
PV-Vorgabe oder Preissperre bestehen, bis HA wieder läuft. Beim nächsten Start setzt
die Integration beides sofort zurück. Nutze die Preissperre deshalb nur, wenn HA
zuverlässig läuft.

---

## Was du siehst

- **Temperaturen**: Außen, Vorlauf, Rücklauf, Warmwasser, Puffer, Luft ein/aus,
  Kältekreis (Sauggas, Verdampfung, Kondensation, Heißgas)
- **Leistung & Energie**: Stromaufnahme, Heizleistung, Zähler für Strom und Wärme
  (getrennt Heizen/Warmwasser), Betriebsstunden. Passt zum Energie-Dashboard
- **Effizienz**: COP der Anlage, berechneter COP, **Arbeitszahl** seit Inbetriebnahme
- **Hilfswerte zum Optimieren** (Erklärung unten): Spreizung, Überhitzung,
  Temperaturhub
- **Zustände**: Verdichter, Pumpen, Ventilator, Abtauen, Störung, EVU-Freigabe,
  aktuelle Anforderung (Heizen/Warmwasser/Kühlen)

Alle Werte landen in der Langzeitstatistik von HA. So siehst du auch nach Monaten
noch Verläufe.

### Kurz erklärt: Woran erkenne ich eine gut eingestellte Anlage?

| Wert | Richtwert | Bedeutung |
|------|-----------|-----------|
| Arbeitszahl (Jahr) | ≥ 3,5 bei Fußbodenheizung | kWh Wärme pro kWh Strom. Höher ist besser |
| Vorlauftemperatur bei −10 °C | ≤ 35 °C Fußbodenheizung | Jedes Grad weniger spart ca. 2–3 % Strom (Heizkurve) |
| Spreizung Vorlauf/Rücklauf | 3–5 K Fußbodenheizung | Zu groß: zu wenig Durchfluss |
| Laufzeit pro Verdichterstart | ≥ 20–30 min | Kürzer: Anlage „taktet“, das kostet Effizienz und Lebensdauer |
| Starts pro Tag | ≤ 10–12 | wie oben |
| Überhitzung | ca. 4–8 K | Kältekreis-Kennwert. Dauerhaft auffällig: Fachbetrieb fragen |

Werte nicht passend? Ändere die Einstellungen am besten mit dem Fachbetrieb, vor
allem die Heizkurve. Die Integration liefert dir die Zahlen dafür.

---

## Installation

1. HACS → Integrationen → ⋮ → Benutzerdefinierte Repositories →
   `https://github.com/AndyKausG/ha-broetje-neo`, Kategorie *Integration*.
2. „Brötje NEO (NEO-RKM)“ installieren, Home Assistant neu starten.
3. Einstellungen → Geräte & Dienste → Integration hinzufügen → „Brötje NEO“.
4. Name (bestimmt die Entitätsnamen, z.B. `sensor.brotje_neo_…`), IP-Adresse des
   NEO-RKM, Port 502, Unit-ID 1.

Im NEO-RKM muss Modbus TCP eingeschaltet sein: Webinterface → Service →
Grundbedienung → Modbus → TCP aktivieren → RKM neu starten.

## Optionen

Integration → **Konfigurieren**:

| Option | Standard | Was passiert |
|--------|----------|--------------|
| Einstellungen schreiben erlauben | aus | Betriebsart (ohne „Aus“) und Sollwerte in den sicheren Grenzen |
| PV-/Leistungssteuerung erlauben | aus | PV-Überschuss an die Wärmepumpe melden |
| Preissperre erlauben | aus | Wärmepumpe bei hohem Strompreis pausieren |
| Preissperre max. Dauer | 120 min | höchstens 180 min |
| Abfrageintervall | 15 s | 5–300 s |
| PV-Watchdog | 120 s | PV-Vorgabe verfällt, wenn sie nicht erneuert wird (0 = aus) |
| Max. PV-Leistungsvorgabe | 6000 W | Obergrenze |

Schaltest du eine Freigabe wieder aus, verschwinden die zugehörigen Bedienelemente.

## PV-Überschuss nutzen

Das NEO-RKM kann PV-Strom selbst verwerten. Die Integration meldet ihm nur, wie viel
Überschuss gerade da ist. **Ob und wie stark die Wärmepumpe läuft, entscheidet das
RKM selbst**, mit den Schutzgrenzen des Herstellers.

1. Im RKM-Webinterface unter *Photovoltaik* die PV-Auswahl **Modbus TCP** wählen und
   Leistungsschwelle, Einschaltverzögerung, Mindestlaufzeit und Max-Begrenzung
   einstellen (Handbuch NEO-RKM Kap. 7.2, ggf. mit dem Fachbetrieb).
2. In der Integration *PV-/Leistungssteuerung erlauben* einschalten.
3. Das Package aus `extras/` einbinden (siehe unten) und den Schalter
   *WP PV-Vorgabe freigegeben* einschalten.

## Preissperre bei hohen Strompreisen

Mit einem dynamischen Stromtarif (z.B. Tibber) kann die Wärmepumpe in teuren Stunden
pausieren. Die Integration nutzt dafür denselben Mechanismus wie eine Sperre durch
den Netzbetreiber (EVU-Sperre). Damit kommt die Wärmepumpe von Haus aus zurecht.

Schutzgrenzen, fest eingebaut:
- höchstens **120 min** am Stück (einstellbar bis 180 min), dann automatisch Ende
- mindestens **60 min Pause** bis zur nächsten Sperre
- **keine Sperre unter −10 °C** außen, eine laufende Sperre endet bei Frost sofort
- eine **echte Sperre des Netzbetreibers wird nie aufgehoben**: Die Integration kann
  nur sperren, nicht freigeben

Bedienung: Schalter *Preissperre* von Hand oder automatisch über das Package
(Preisgrenze einstellen, *WP Preissperre automatisch* einschalten).

Hinweis: Nicht jede RKM-Firmware bietet die nötigen Register (147–150). Dann ist der
Schalter „nicht verfügbar“.

---

## Auswertung und Dashboard (`extras/`)

| Datei | Zweck |
|-------|-------|
| `extras/packages/broetje_neo_analytics.yaml` | Arbeitszahl pro Tag/Monat/Jahr, **PV-Anteil**, Starts und Laufzeiten, Abtauungen, EVU-Sperrzeit, Automationen für PV und Preissperre |
| `extras/tools/analyze_heatpump.py` | Auswertung der HA-Datenbank am PC: Monats-Arbeitszahl, Takten, Heizkurve, Spreizung, Überhitzung mit Bewertung |
| `extras/lovelace/heat-pump-card.yaml` | Anlagenbild mit der `lovelace-heat-pump-card` |

**Package einbinden:** Datei nach `/config/packages/` kopieren, in
`configuration.yaml` eintragen:

```yaml
homeassistant:
  packages: !include_dir_named packages
```

Danach in der Datei die Platzhalter `sensor.anpassen_…` durch deine Sensoren
ersetzen: PV-Leistung, Netzbezug, Einspeisung (in W), optional Strompreis.

**Auswertungsskript** (benötigt nur Python):

```bash
sqlite3 /config/home-assistant_v2.db ".backup /tmp/ha.db"
```

```bash
python3 analyze_heatpump.py /tmp/ha.db --since 2025-03-01
```

Mit `--profile heliotherm --prefix brotje_blw_neo18b` werden die Daten der älteren
Integration `ha_heliotherm` ausgewertet.

## Umstieg von ha_heliotherm

Beide Integrationen können eine Zeit lang parallel laufen:

1. Diese Integration einrichten (nur lesend), Abfrageintervall auf 30 s.
2. Ein paar Tage Werte vergleichen, steuern weiter über die alte Integration.
3. Dann hier die gewünschten Freigaben setzen und `ha_heliotherm` entfernen.

Nicht in beiden gleichzeitig steuern. Im Energie-Dashboard nur eine Quelle eintragen.
Treten Verbindungsabbrüche auf, verkraftet das RKM vermutlich keine zwei
Verbindungen. Dann eine Integration deaktivieren.

---

## Technik

<details>
<summary>Entitäten, Register, Entwicklung</summary>

Register laut NEO-RKM-Montageanleitung 7734937-01, Kap. 7.1 (Tab. 4/5). Die Belegung
steht nur in `custom_components/broetje_neo/registers.py`, die Schreib-Positivliste
mit Grenzen nur in `safety.py`.

| Plattform | Entitäten |
|-----------|-----------|
| sensor | Temperaturen, Drücke, Durchfluss (l/min), Verdichterdrehzahl %, Expansionsventil %, COP, Leistungen, Energiezähler, Betriebsstunden, Anforderung, Betriebsart-Status, abgeleitete Werte |
| binary_sensor | Pumpen, Verdichter, Ventilator, Störung, Abtauen, EVU-Freigabe (an = freigegeben), WW-Vorrang, Kühlen passiv, Heizen/Warmwasser/Kühlen |
| select | Betriebsart (HKR, MKR1/2) ohne „Aus“ |
| number | Raumsoll, WW-Normal/-Minimum, Kühlen RLT min, MKR-Raumsoll, PV-Leistung |
| switch | Preissperre |

Fühler, die die Anlage nicht hat (Rohwert −50,0 °C), werden als „unbekannt“
angezeigt. Energiezähler mit Rohwert 0 werden verworfen, damit die Statistik keine
falschen Sprünge bekommt. Diagnose-Download mit allen Rohregistern unter
Gerät → ⋮ → Diagnose herunterladen.

Entwicklung:

```bash
pip install -r requirements_test.txt
```

```bash
ruff check . && ruff format --check . && pytest -q
```

Übersetzungen werden mit `scripts/gen_translations.py` erzeugt.
</details>

## Lizenz und Herkunft

MIT, siehe [LICENSE](LICENSE). Die Registerbelegung stammt aus der Brötje-Dokumentation
(NEO-RKM-Montageanleitung 7734937-01). Herstellerdokumente sind nicht Teil des Repos.
Die Idee geht auf [mbuchber/ha_heliotherm](https://github.com/mbuchber/ha_heliotherm)
zurück, die Architektur orientiert sich an
[henrywiechert/ha-broetje](https://github.com/henrywiechert/ha-broetje). Aus beiden
Projekten wurde kein Code übernommen.
