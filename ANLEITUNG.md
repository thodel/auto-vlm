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

- **GPUStack (Qwen3-VL):** Den Key und die Server-Adresse bekommst du von der Kursleitung.
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

**Mit GPUStack** (Adresse und Modellname von der Kursleitung)
```
python bilder_zu_csv.py bilder ergebnisse.csv --base-url http://SERVER/v1 --model MODELLNAME
```

Auf dem Mac `python3` statt `python` verwenden.

Das Skript zeigt für jedes Bild an, ob es geklappt hat. Wird es unterbrochen, starte es einfach mit demselben Befehl neu. Bereits fertige Bilder werden übersprungen.

## 5. Ergebnis ansehen

Öffne `ergebnisse.csv` in Excel oder LibreOffice. Jede Zeile gehört zu einem Bild, die Antwort des Modells steht in der Spalte `antwort`.

Die Spalte `status` zeigt, ob alles geklappt hat:
- `ok`: Die Antwort ist vollständig.
- `abgeschnitten`: Die Antwort war zu lang und ist unvollständig. Starte das Skript erneut mit `--max-tokens 8000`.
- `fehler`: Die Anfrage ist gescheitert. Die Fehlermeldung steht in `antwort`.

**Wichtig:** KI-Modelle machen Fehler und erfinden manchmal Dinge. Prüfe die Ergebnisse stichprobenartig am Bild selbst.

## Häufige Probleme

| Meldung | Lösung |
|---|---|
| `python` oder `pip` wird nicht gefunden | Python ist nicht installiert oder nicht im PATH. Neu installieren und „Add Python to PATH“ anhaken. |
| `Kein API-Key …` | Schritt 2 im selben Terminal-Fenster wiederholen. |
| `0 Bilder gefunden` | Ordnername prüfen. Unterstützt werden jpg, png, webp, tif, bmp und gif. |
| Viele `fehler` mit „429“ oder „rate limit“ | Zu viele Anfragen auf einmal. Mit `--workers 1` starten. |
| Umlaute in Excel kaputt | In Excel über **Daten → Aus Text/CSV** importieren und UTF-8 wählen. |
