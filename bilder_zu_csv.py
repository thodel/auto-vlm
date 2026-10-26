#!/usr/bin/env python3
"""
Alle Bilder eines Ordners mit einem Vision-Modell und einem festen Prompt
verarbeiten und die Antworten in eine CSV-Datei schreiben.

Zwei Anbieter stehen zur Wahl (--provider):
  gpustack  GPUStack der Uni Bern (Standard: qwen3.8-27b)
  gemini    Google Gemini API

Beide bieten eine OpenAI-kompatible API, daher nutzen wir für beide das
offizielle `openai`-Paket:

    pip install -r requirements.txt

Der Prompt wird aus prompt.txt (neben dem Skript) gelesen.

Beispiele:
    export GPUSTACK_API_KEY="gpustack_..."
    python3 bilder_zu_csv.py ./scans ergebnisse.csv   # GPUStack der Uni Bern

    export GEMINI_API_KEY="..."
    python3 bilder_zu_csv.py ./scans ergebnisse.csv --provider gemini

Das Skript ist wiederaufnehmbar: Bilder, die schon (erfolgreich) in der CSV
stehen, werden beim nächsten Lauf übersprungen.
"""

import argparse
import base64
import csv
import os
import re
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from io import BytesIO
from pathlib import Path

try:
    import openai
    from openai import OpenAI
    from PIL import Image, ImageOps
except ImportError as e:
    sys.exit(f"Paket fehlt ({e.name}). Bitte zuerst ausführen:  pip install -r requirements.txt")

# Der Prompt steht in prompt.txt neben diesem Skript (oder per --prompt-file).
STANDARD_PROMPT_DATEI = Path(__file__).resolve().parent / "prompt.txt"

# Voreinstellungen je Anbieter; alles lässt sich per Kommandozeile überschreiben.
ANBIETER = {
    "gpustack": {
        "base_url": os.environ.get("GPUSTACK_BASE_URL", "http://gpustack.unibe.ch/v1"),
        "key_env": "GPUSTACK_API_KEY",
        "model": "qwen3.8-27b",
        "temperature": 0,  # deterministisch
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "key_env": "GEMINI_API_KEY",
        "model": "gemini-3.8-flash",
        "temperature": None,  # Google: bei Gemini 3.x temperature nicht setzen
    },
}

BILD_ENDUNGEN = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp", ".gif"}
# Diese Formate verstehen beide Anbieter direkt; alles andere wird nach JPEG gewandelt.
DIREKT_SENDEN = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
CSV_SPALTEN = ["datei", "status", "antwort", "modell", "dauer_s", "prompt_tokens", "completion_tokens"]


class Abbruch(Exception):
    """Fehler, der alle Bilder betrifft (falscher Key, unbekanntes Modell): Lauf beenden."""


def bild_als_data_url(pfad: Path, max_kante: int) -> str:
    """Bild base64-kodiert als data:-URL, wie es die OpenAI-Vision-API erwartet.

    JPEG/PNG/WebP bis max_kante Pixel gehen unverändert raus. Grössere Bilder
    werden verkleinert, andere Formate (TIFF, BMP, GIF) nach JPEG gewandelt,
    denn Gemini nimmt sie nicht an und riesige Scans sprengen das Anfrage-Limit.
    """
    endung = pfad.suffix.lower()
    with Image.open(pfad) as im:
        zu_gross = max_kante and max(im.size) > max_kante
        if endung in DIREKT_SENDEN and not zu_gross:
            daten, mime = pfad.read_bytes(), DIREKT_SENDEN[endung]
        else:
            im = ImageOps.exif_transpose(im)  # gedrehte Handyfotos richtig herum
            if zu_gross:
                im.thumbnail((max_kante, max_kante))  # verkleinert, behält das Seitenverhältnis
            buf = BytesIO()
            im.convert("RGB").save(buf, format="JPEG", quality=92)
            daten, mime = buf.getvalue(), "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(daten).decode('ascii')}"


def entferne_thinking(text: str) -> str:
    """"Thinking"-Modelle (z.B. Qwen3) liefern <think>...</think> mit; das wegschneiden."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def fehler_zeile(name: str, modell: str, meldung: str) -> dict:
    return {"datei": name, "status": "fehler", "antwort": meldung, "modell": modell,
            "dauer_s": "", "prompt_tokens": "", "completion_tokens": ""}


def auftrag_name(bilder: list) -> str:
    """Eintrag für die Spalte datei: ein Dateiname, oder bei mehreren Bildern alle mit ' | ' getrennt."""
    return " | ".join(name for _, name in bilder)


def verarbeite_bild(client: OpenAI, modell: str, prompt: str, bilder: list,
                    max_tokens: int, versuche: int, max_kante: int, temperature) -> dict:
    """Ein Auftrag = eine Anfrage. `bilder` ist eine Liste von (Pfad, Name); normalerweise
    ein Bild, mit --zusammen alle Bilder des Ordners auf einmal."""
    name = auftrag_name(bilder)
    zusammen = len(bilder) > 1
    inhalt, groesse = [], 0
    for i, (pfad, bild_name) in enumerate(bilder, 1):
        try:
            data_url = bild_als_data_url(pfad, max_kante)
        except Exception as e:  # defekte Datei, unbekanntes Format ...
            return fehler_zeile(name, modell, f"Bild nicht lesbar: {bild_name}: {type(e).__name__}: {e}")
        groesse += len(data_url)
        if zusammen:
            # Bilder beschriften, damit das Modell sie in der Antwort benennen kann
            inhalt.append({"type": "text", "text": f"Bild {i}: {bild_name}"})
            print(f"  vorbereitet {i}/{len(bilder)}: {bild_name} ({len(data_url) / 1e6:.1f} MB)", flush=True)
        inhalt.append({"type": "image_url", "image_url": {"url": data_url}})
    inhalt.append({"type": "text", "text": prompt})
    if zusammen:
        print(f"Anfrage mit {len(bilder)} Bildern ({groesse / 1e6:.1f} MB) gesendet, warte auf Antwort "
              f"(Timeout {client.timeout:.0f} s). Der Server muss erst alle Bilder einlesen, das kann dauern.",
              flush=True)

    letzter_fehler = None
    for versuch in range(1, versuche + 1):
        start = time.time()
        try:
            resp = client.chat.completions.create(
                model=modell,
                messages=[{"role": "user", "content": inhalt}],
                max_tokens=max_tokens,
                **({"temperature": temperature} if temperature is not None else {}),
            )
            wahl = resp.choices[0]
            antwort = entferne_thinking(wahl.message.content or "")
            usage = resp.usage
            if wahl.finish_reason == "length":
                status = "abgeschnitten"  # Token-Limit erreicht -> Antwort unvollständig
            elif not antwort:
                status = "leer"
            else:
                status = "ok"
            return {
                "datei": name,
                "status": status,
                "antwort": antwort,
                "modell": resp.model or modell,
                "dauer_s": round(time.time() - start, 1),
                "prompt_tokens": usage.prompt_tokens if usage else "",
                "completion_tokens": usage.completion_tokens if usage else "",
            }
        except (openai.AuthenticationError, openai.PermissionDeniedError) as e:
            raise Abbruch(f"API-Key wurde abgelehnt. Key und Anbieter prüfen.\n{e}") from e
        except openai.NotFoundError as e:
            raise Abbruch(f"Modell '{modell}' oder Adresse nicht gefunden. --model und --base-url prüfen.\n{e}") from e
        except openai.BadRequestError as e:
            # Betrifft nur dieses Bild (z.B. zu gross) -> nicht wiederholen
            return fehler_zeile(name, modell, f"{type(e).__name__}: {e}")
        except openai.APITimeoutError as e:
            if zusammen:
                # Ein zweiter Versuch dauert genauso lang -> sofort melden
                return fehler_zeile(name, modell, f"Zeitüberschreitung nach {client.timeout:.0f} s. "
                                    "--timeout erhöhen oder --max-kante verkleinern (z.B. 1024).")
            letzter_fehler = e
        except openai.RateLimitError as e:  # 429: Server überlastet oder Kontingent erschöpft
            letzter_fehler = e
            if versuch < versuche:
                time.sleep(15 * versuch)
        except Exception as e:  # Netzwerk, 5xx ...
            letzter_fehler = e
            if versuch < versuche:
                time.sleep(2 ** versuch)
    return fehler_zeile(name, modell, f"{type(letzter_fehler).__name__}: {letzter_fehler}")


def csv_trennzeichen(csv_pfad: Path, gewuenscht: str) -> str:
    """Bei einer bestehenden CSV deren Trennzeichen übernehmen, damit das Fortsetzen klappt."""
    if not csv_pfad.exists():
        return gewuenscht
    with csv_pfad.open(encoding="utf-8-sig") as f:
        kopf = f.readline()
    vorhanden = ";" if kopf.count(";") > kopf.count(",") else ","
    if vorhanden != gewuenscht:
        print(f"Hinweis: {csv_pfad} verwendet bereits '{vorhanden}' als Trennzeichen, das wird beibehalten.")
    return vorhanden


def bereits_erledigt(csv_pfad: Path, trennzeichen: str) -> set:
    """Dateinamen, die schon erfolgreich in der CSV stehen."""
    if not csv_pfad.exists():
        return set()
    with csv_pfad.open(newline="", encoding="utf-8-sig") as f:
        return {z["datei"] for z in csv.DictReader(f, delimiter=trennzeichen) if z.get("status") == "ok"}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ordner", type=Path, help="Ordner mit den Bildern")
    ap.add_argument("csv", type=Path, help="Ausgabe-CSV")
    ap.add_argument("--provider", choices=ANBIETER, default="gpustack", help="gpustack (Standard) oder gemini")
    ap.add_argument("--base-url", help="API-Adresse; GPUStack z.B. http://server/v1 (ältere Versionen: /v1-openai)")
    ap.add_argument("--api-key", help="API-Key (Standard: GPUSTACK_API_KEY bzw. GEMINI_API_KEY)")
    ap.add_argument("--model", help="Modellname (Standard: qwen3.8-27b bzw. gemini-3.8-flash)")
    ap.add_argument("--prompt-file", type=Path, default=STANDARD_PROMPT_DATEI,
                    help="Textdatei mit dem Prompt (Standard: prompt.txt neben dem Skript)")
    ap.add_argument("--max-tokens", type=int, default=4096, help="Obergrenze für die Antwortlänge")
    ap.add_argument("--max-kante", type=int, default=2048,
                    help="Bilder mit längerer Kante (Pixel) werden vor dem Senden verkleinert; 0 = nie")
    ap.add_argument("--timeout", type=int,
                    help="Sekunden, die eine Anfrage dauern darf (Standard 300; mit --zusammen 120 + 30 pro Bild)")
    ap.add_argument("--workers", type=int, default=2, help="parallele Anfragen")
    ap.add_argument("--retries", type=int, default=3, help="Versuche pro Bild bei Netzwerk-/Serverfehlern")
    ap.add_argument("--recursive", action="store_true", help="auch Unterordner durchsuchen")
    ap.add_argument("--zusammen", action="store_true",
                    help="alle Bilder in EINER Anfrage schicken (z.B. zum Vergleichen); eine CSV-Zeile")
    ap.add_argument("--semikolon", action="store_true",
                    help="Semikolon statt Komma als Trennzeichen (für Excel mit deutschen Einstellungen)")
    args = ap.parse_args()

    anbieter = ANBIETER[args.provider]
    args.base_url = args.base_url or anbieter["base_url"]
    args.api_key = args.api_key or os.environ.get(anbieter["key_env"])
    args.model = args.model or anbieter["model"]
    if not args.api_key:
        sys.exit(f"Kein API-Key: --api-key setzen oder {anbieter['key_env']} exportieren.")
    if not args.ordner.is_dir():
        sys.exit(f"Bildordner nicht gefunden: {args.ordner}")
    if not args.prompt_file.is_file():
        sys.exit(f"Prompt-Datei nicht gefunden: {args.prompt_file}")
    # utf-8-sig: Windows-Editoren schreiben oft eine BOM an den Anfang, die soll nicht in den Prompt
    prompt = args.prompt_file.read_text(encoding="utf-8-sig").strip()
    if not prompt:
        sys.exit(f"Prompt-Datei ist leer: {args.prompt_file}")

    muster = "**/*" if args.recursive else "*"
    bilder = sorted(p for p in args.ordner.glob(muster) if p.is_file() and p.suffix.lower() in BILD_ENDUNGEN)
    # Pfad relativ zum Bildordner, z.B. "a.jpg" oder mit --recursive "unterordner/a.jpg"
    namen = {p: p.relative_to(args.ordner).as_posix() for p in bilder}
    # Ein Auftrag = eine Anfrage = eine CSV-Zeile: pro Bild eines, mit --zusammen ein einziger
    if args.zusammen:
        auftraege = [[(p, namen[p]) for p in bilder]] if bilder else []
    else:
        auftraege = [[(p, namen[p])] for p in bilder]
    trennzeichen = csv_trennzeichen(args.csv, ";" if args.semikolon else ",")
    erledigt = bereits_erledigt(args.csv, trennzeichen)
    offen = [a for a in auftraege if auftrag_name(a) not in erledigt]
    if not bilder:
        print("0 Bilder gefunden.")
    elif args.zusammen:
        print(f"{len(bilder)} Bilder gefunden, gehen zusammen in eine Anfrage"
              + (" (bereits erledigt)." if not offen else "."))
    else:
        print(f"{len(bilder)} Bilder gefunden, {len(erledigt)} bereits erledigt, {len(offen)} zu verarbeiten.")
    if not offen:
        return

    timeout = args.timeout or (120 + 30 * len(bilder) if args.zusammen else 300)
    # max_retries=0: das openai-Paket würde sonst jeden Timeout still 2x wiederholen,
    # zusätzlich zu unseren eigenen Versuchen -> scheinbar endloses Warten
    client = OpenAI(base_url=args.base_url, api_key=args.api_key, timeout=timeout, max_retries=0)
    neu = not args.csv.exists()
    # utf-8-sig, damit Excel Umlaute korrekt anzeigt
    with args.csv.open("a", newline="", encoding="utf-8-sig" if neu else "utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_SPALTEN, delimiter=trennzeichen, quoting=csv.QUOTE_ALL)
        if neu:
            writer.writeheader()
        pool = ThreadPoolExecutor(max_workers=args.workers)
        futures = [pool.submit(verarbeite_bild, client, args.model, prompt, a,
                               args.max_tokens, max(1, args.retries), args.max_kante,
                               anbieter["temperature"]) for a in offen]
        try:
            fertig, start, letzte_meldung = 0, time.time(), time.time()
            ausstehend = set(futures)
            while ausstehend:
                # Kurz warten statt blockieren: so können wir ein Lebenszeichen ausgeben
                erledigte, ausstehend = wait(ausstehend, timeout=10, return_when=FIRST_COMPLETED)
                for fut in erledigte:
                    fertig += 1
                    zeile = fut.result()
                    writer.writerow(zeile)
                    f.flush()  # sofort schreiben -> bei Abbruch geht nichts verloren
                    kurz = zeile["datei"] if not args.zusammen else f"{len(bilder)} Bilder zusammen"
                    print(f"[{fertig}/{len(offen)}] {kurz}: {zeile['status']}", flush=True)
                    letzte_meldung = time.time()
                if ausstehend and time.time() - letzte_meldung >= 30:
                    print(f"  ... läuft seit {time.time() - start:.0f} s, {fertig}/{len(offen)} fertig", flush=True)
                    letzte_meldung = time.time()
        except Abbruch as e:
            pool.shutdown(wait=False, cancel_futures=True)
            f.flush()
            print(f"\nAbbruch: {e}", file=sys.stderr)
            os._exit(1)  # nicht auf laufende Anfragen warten, die scheitern ohnehin gleich
        except KeyboardInterrupt:
            pool.shutdown(wait=False, cancel_futures=True)
            f.flush()
            print("\nAbgebrochen. Beim nächsten Start mit demselben Befehl geht es bei den fehlenden Bildern weiter.")
            os._exit(130)  # sonst würde Python noch auf die laufenden Anfragen warten
        pool.shutdown()
    print(f"Fertig. Ergebnisse in {args.csv}")


if __name__ == "__main__":
    main()
