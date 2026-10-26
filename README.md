# auto-vlm

Für die Veranstaltung "Bilderflut".

**Studierende:** Eine Schritt-für-Schritt-Anleitung findet ihr in [ANLEITUNG.md](ANLEITUNG.md).

Verarbeitet alle Bilder in einem Ordner mit einem Vision-Modell und einem festen Prompt und schreibt die Antworten in eine CSV-Datei.

Es gibt zwei Anbieter:
- **GPUStack** der Uni Bern mit `qwen3.8-27b` (Standard)
- **Google Gemini API**

## Installation

```bash
pip install -r requirements.txt
```

## Prompt

Der Prompt steht in `prompt.txt` neben dem Skript. Diese Datei bearbeiten oder mit `--prompt-file andere_datei.txt` eine andere angeben.

## Verwendung

**GPUStack der Uni Bern** (Standard: `http://gpustack.unibe.ch/v1`, Modell `qwen3.8-27b`)
```bash
export GPUSTACK_API_KEY="gpustack_..."
python3 bilder_zu_csv.py ./bilder ergebnisse.csv
```
Einen anderen Server oder ein anderes Modell wählst du mit `--base-url` und `--model`.

**Gemini**
```bash
export GEMINI_API_KEY="..."
python3 bilder_zu_csv.py ./bilder ergebnisse.csv --provider gemini
```
Standardmodell ist `gemini-2.5-flash`. Mit `--model` wählst du ein anderes.

## Optionen

| Option | Bedeutung |
|---|---|
| `--provider gpustack\|gemini` | Anbieter (Standard: `gpustack`) |
| `--base-url`, `--api-key`, `--model` | überschreiben die Voreinstellungen des Anbieters |
| `--prompt-file` | Prompt-Datei (Standard: `prompt.txt`) |
| `--max-tokens` | Obergrenze für die Antwortlänge (Standard 4096) |
| `--workers` | Anzahl paralleler Anfragen (Standard 2) |
| `--retries` | Versuche pro Bild (Standard 3) |
| `--recursive` | durchsucht auch Unterordner; `datei` enthält dann den Pfad mit Unterordner, z.B. `band1/a.jpg` |

## Ausgabe

Die CSV hat die Spalten `datei, status, antwort, modell, dauer_s, prompt_tokens, completion_tokens`. Sie ist in UTF-8 gespeichert und so markiert, dass Excel Umlaute richtig anzeigt.

Mögliche Werte in `status`:
- `ok`: Antwort vollständig
- `abgeschnitten`: Token-Limit erreicht, Antwort unvollständig. `--max-tokens` erhöhen.
- `fehler`: Anfrage auch nach allen Versuchen gescheitert. Die Fehlermeldung steht in `antwort`.

Abbrüche sind unproblematisch: Jede Zeile wird sofort gespeichert. Bei einem neuen Start werden Bilder mit Status `ok` übersprungen.

Unterstützte Formate sind jpg, png, webp, tif, bmp und gif. TIFF wird vor dem Senden in PNG umgewandelt.
