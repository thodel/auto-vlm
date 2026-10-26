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
Standardmodell ist `gemini-3.8-flash`. Mit `--model` wählst du ein anderes.

## Optionen

| Option | Bedeutung |
|---|---|
| `--provider gpustack\|gemini` | Anbieter (Standard: `gpustack`) |
| `--base-url`, `--api-key`, `--model` | überschreiben die Voreinstellungen des Anbieters |
| `--prompt-file` | Prompt-Datei (Standard: `prompt.txt`) |
| `--max-tokens` | Obergrenze für die Antwortlänge (Standard 4096) |
| `--max-kante` | Bilder mit längerer Kante über diesem Wert (Pixel) werden vor dem Senden verkleinert (Standard 2048, `0` = nie) |
| `--timeout` | Sekunden pro Anfrage (Standard 300; mit `--zusammen` 120 + 30 pro Bild) |
| `--workers` | Anzahl paralleler Anfragen (Standard 2) |
| `--retries` | Versuche pro Bild (Standard 3) |
| `--recursive` | durchsucht auch Unterordner; `datei` enthält dann den Pfad mit Unterordner, z.B. `band1/a.jpg` |
| `--zusammen` | alle Bilder in einer einzigen Anfrage schicken, eine CSV-Zeile (siehe unten) |
| `--semikolon` | Semikolon statt Komma als Trennzeichen, damit Excel mit deutschen/schweizer Einstellungen die CSV direkt öffnet |

## Bilder vergleichen (`--zusammen`)

Mit `--zusammen` gehen alle Bilder des Ordners in **einer** Anfrage an das Modell. Es sieht sie gleichzeitig und kann sie vergleichen, sortieren oder Gemeinsamkeiten benennen. Vor jedem Bild steht `Bild 1: name.jpg`, `Bild 2: …`, damit das Modell die Bilder in der Antwort benennen kann. Die CSV bekommt eine Zeile; in `datei` stehen alle Dateinamen mit ` | ` getrennt.

```bash
python3 bilder_zu_csv.py ./bilder vergleich.csv --zusammen
```

Der Server muss erst alle Bilder einlesen, bevor er zu antworten beginnt; bei 20 Bildern à 2048 px sind das rund 50 000 Eingabe-Tokens, was auch auf einer guten GPU einige Minuten dauern kann. Das Skript meldet die Vorbereitung jedes Bildes, das Absenden der Anfrage und alle 30 s ein Lebenszeichen. Dauert es zu lang: `--max-kante 1024` viertelt die Tokenzahl pro Bild.

Grenzen:
- Alle Bilder zusammen müssen ins Kontextfenster und ins Anfrage-Limit passen. Bei vielen Bildern `--max-kante 1024` setzen, das verkleinert die Anfrage deutlich.
- Manche GPUStack-Modelle erlauben nur eine begrenzte Zahl Bilder pro Anfrage (Server-Einstellung). Dann kommt eine `fehler`-Zeile mit der Meldung des Servers; bei Gemini sind bis zu 3600 Bilder pro Anfrage möglich.
- Eine nicht lesbare Datei lässt die ganze Anfrage scheitern; die Meldung nennt die Datei.

## Ausgabe

Die CSV hat die Spalten `datei, status, antwort, modell, dauer_s, prompt_tokens, completion_tokens`. Sie ist in UTF-8 gespeichert und so markiert, dass Excel Umlaute richtig anzeigt.

Mögliche Werte in `status`:
- `ok`: Antwort vollständig
- `abgeschnitten`: Token-Limit erreicht, Antwort unvollständig. `--max-tokens` erhöhen.
- `leer`: Das Modell hat nichts geantwortet (bei „Thinking“-Modellen z.B., wenn das Limit schon beim Nachdenken aufgebraucht war). `--max-tokens` erhöhen oder Prompt anpassen.
- `fehler`: Anfrage auch nach allen Versuchen gescheitert, oder die Bilddatei ist nicht lesbar. Die Fehlermeldung steht in `antwort`.

Abbrüche (auch mit Ctrl+C) sind unproblematisch: Jede Zeile wird sofort gespeichert. Bei einem neuen Start werden Bilder mit Status `ok` übersprungen; alle anderen werden erneut verarbeitet und bekommen eine neue Zeile, die alte bleibt stehen.

Wird der API-Key abgelehnt oder das Modell nicht gefunden, bricht das Skript sofort mit einer Meldung ab, statt für jedes Bild eine Fehlerzeile zu schreiben.

Unterstützte Formate sind jpg, png, webp, tif, bmp und gif. JPEG, PNG und WebP werden unverändert gesendet, solange die längere Kante höchstens `--max-kante` Pixel misst. Grössere Bilder werden verkleinert, TIFF/BMP/GIF nach JPEG gewandelt (Gemini nimmt diese Formate nicht an, und sehr grosse Scans überschreiten das Anfrage-Limit).
