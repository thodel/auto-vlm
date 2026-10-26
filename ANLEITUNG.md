# Anleitung für Studierende

Mit diesem Werkzeug lässt du ein KI-Modell alle Bilder in einem Ordner „anschauen“. Alle Bilder bekommen dieselbe Anweisung (den Prompt). Die Antworten landen in einer Tabelle (CSV), die du in Excel oder LibreOffice öffnen kannst.

## 1. Vorbereitung (einmalig)

1. **Python installieren** (Version 3.9 oder neuer): https://www.python.org/downloads/
   Unter Windows bei der Installation **„Add Python to PATH“** anhaken.
2. **Projekt herunterladen:** Auf https://github.com/thodel/auto-vlm auf **Code → Download ZIP** klicken und das ZIP entpacken.
3. **Terminal im Projektordner öffnen:**
   - Windows: den Ordner im Explorer öffnen, oben in die Adresszeile `powershell` tippen und Enter drücken.
   - Mac: Rechtsklick auf den Ordner, dann **Dienste → Neues Terminal beim Ordner**.
4. **Pakete installieren:**
   ```
   pip install -r requirements.txt
   ```
   Klappt `pip` nicht, versuche es mit `python -m pip install -r requirements.txt` (Mac: `python3 -m pip …`).

## 2. API-Key eintragen

Du brauchst einen Schlüssel für den Dienst, der die Bilder auswertet:

- **GPUStack der Uni Bern:** Den Key bekommst du von der Kursleitung.
- **Gemini:** Einen kostenlosen Key erstellst du unter https://aistudio.google.com/apikey.

Den Key gibst du im Terminal so an. Er gilt nur, solange dieses Terminal-Fenster offen ist.

| | Windows (PowerShell) | Mac / Linux |
|---|---|---|
| GPUStack | `$env:GPUSTACK_API_KEY="dein-key"` | `export GPUSTACK_API_KEY="dein-key"` |
| Gemini | `$env:GEMINI_API_KEY="dein-key"` | `export GEMINI_API_KEY="dein-key"` |

Gib deinen Key nicht weiter und lade ihn nicht auf GitHub hoch.

## 3. Prompt festlegen

Öffne `prompt.txt` mit einem Texteditor und schreib hinein, was das Modell mit jedem Bild tun soll. Ein Beispiel:

> Beschreibe das Bild in 2–3 Sätzen. Nenne dann die dargestellten Personen, Orte und die vermutliche Entstehungszeit.

Tipps:
- Sei konkret. Sag, welche Informationen du willst und in welcher Form.
- Probier den Prompt zuerst an 2–3 Bildern aus, bevor du den ganzen Ordner verarbeitest.

## 4. Starten

Leg deine Bilder in einen Ordner, z.B. `bilder` im Projektordner. Dann im Terminal:

**Mit Gemini**
```
python bilder_zu_csv.py bilder ergebnisse.csv --provider gemini
```

**Mit GPUStack der Uni Bern** (Server `http://gpustack.unibe.ch/v1` und Modell `qwen3.8-27b` sind voreingestellt)
```
python bilder_zu_csv.py bilder ergebnisse.csv
```

Auf dem Mac `python3` statt `python` verwenden.

### Anderen Ordner verwenden

Der erste Wert nach `bilder_zu_csv.py` ist der Bildordner, der zweite die CSV-Datei. Pfade gelten vom Ordner aus, in dem das Terminal gerade steht (normalerweise der Projektordner).

| Wo liegen die Bilder? | Befehl |
|---|---|
| Ordner `vlm-test` im Projektordner | `python bilder_zu_csv.py vlm-test ergebnisse.csv` |
| Unterordner, z.B. `bilder/vlm-test` | `python bilder_zu_csv.py bilder/vlm-test ergebnisse.csv` |
| Woanders, z.B. auf dem Desktop | `python bilder_zu_csv.py "C:\Users\anna\Desktop\vlm test" ergebnisse.csv` |
| CSV im selben Ordner speichern | `python bilder_zu_csv.py vlm-test vlm-test/ergebnisse.csv` |

- Enthält ein Pfad Leerzeichen, setze ihn in Anführungszeichen.
- Du kannst den Ordner auch ins Terminal-Fenster ziehen, dann wird der Pfad automatisch eingefügt.
- **Unterordner mitnehmen:** Normalerweise werden nur die Bilder direkt im Ordner verarbeitet. Mit `--recursive` kommen auch die Bilder in Unterordnern dazu. In der Spalte `datei` steht dann der Pfad mit Unterordner, z.B. `band1/seite_001.jpg`.

Das Skript zeigt für jedes Bild an, ob es geklappt hat. Wird es unterbrochen, starte es einfach mit demselben Befehl neu. Bereits fertige Bilder werden übersprungen.

## 5. Ergebnis ansehen

Öffne `ergebnisse.csv` in Excel oder LibreOffice. Jede Zeile gehört zu einem Bild, die Antwort des Modells steht in der Spalte `antwort`.

Die Spalte `status` zeigt, ob alles geklappt hat:
- `ok`: Die Antwort ist vollständig.
- `abgeschnitten`: Die Antwort war zu lang und ist unvollständig. Starte das Skript erneut mit `--max-tokens 8000`.
- `leer`: Das Modell hat nichts geantwortet. Starte erneut mit `--max-tokens 8000` oder formuliere den Prompt anders.
- `fehler`: Die Anfrage ist gescheitert oder die Bilddatei ist kaputt. Die Fehlermeldung steht in `antwort`.

Beim erneuten Start werden Bilder mit `ok` übersprungen, alle anderen bekommen eine neue Zeile (die alte bleibt stehen). Mit **Ctrl+C** kannst du das Skript jederzeit abbrechen; was schon fertig ist, bleibt gespeichert.

**Alles in einer Spalte?** Excel mit deutschen oder schweizer Einstellungen erwartet ein Semikolon als Trennzeichen. Starte das Skript dann mit dem Zusatz `--semikolon`, z.B.:
```
python bilder_zu_csv.py bilder ergebnisse.csv --semikolon
```

**Wichtig:** KI-Modelle machen Fehler und erfinden manchmal Dinge. Prüfe die Ergebnisse stichprobenartig am Bild selbst.

## Häufige Probleme

| Meldung | Lösung |
|---|---|
| `python` oder `pip` wird nicht gefunden | Python ist nicht installiert oder nicht im PATH. Neu installieren und „Add Python to PATH“ anhaken. |
| `Paket fehlt …` | Schritt 4 der Vorbereitung (`pip install -r requirements.txt`) ausführen. |
| `Kein API-Key …` | Schritt 2 im selben Terminal-Fenster wiederholen. |
| `Abbruch: API-Key wurde abgelehnt` | Key falsch abgetippt oder beim falschen Anbieter verwendet (GPUStack-Key braucht kein `--provider gemini` und umgekehrt). |
| `Abbruch: Modell … nicht gefunden` | Modellname oder Server-Adresse stimmt nicht. Bei der Kursleitung nachfragen. |
| `Bildordner nicht gefunden` | Pfad prüfen, siehe „Anderen Ordner verwenden“. |
| `0 Bilder gefunden` | Ordnername prüfen. Unterstützt werden jpg, png, webp, tif, bmp und gif. |
| Viele `fehler` mit „429“ oder „rate limit“ | Zu viele Anfragen auf einmal. Mit `--workers 1` starten. |
| Alles in einer Spalte in Excel | Skript mit `--semikolon` starten oder über **Daten → Aus Text/CSV** importieren. |
| Umlaute in Excel kaputt | In Excel über **Daten → Aus Text/CSV** importieren und UTF-8 wählen. |
