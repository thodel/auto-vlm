#!/usr/bin/env python3
"""
Alle Bilder eines Ordners mit einem Vision-Modell und einem festen Prompt
verarbeiten und die Antworten in eine CSV-Datei schreiben.

Zwei Anbieter stehen zur Wahl (--provider):
  gpustack  GPUStack der Uni Bern (Standard: qwen3.8-27b)
  gemini    Google Gemini API

Beide bieten eine OpenAI-kompatible API, daher nutzen wir für beide das
offizielle `openai`-Paket:

    pip install openai

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
import mimetypes
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from openai import OpenAI

# Der Prompt steht in prompt.txt neben diesem Skript (oder per --prompt-file).
STANDARD_PROMPT_DATEI = Path(__file__).resolve().parent / "prompt.txt"

# Voreinstellungen je Anbieter; alles lässt sich per Kommandozeile überschreiben.
ANBIETER = {
    "gpustack": {
        "base_url": os.environ.get("GPUSTACK_BASE_URL", "http://gpustack.unibe.ch/v1"),
        "key_env": "GPUSTACK_API_KEY",
        "model": "qwen3.8-27b",
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "key_env": "GEMINI_API_KEY",
        "model": "gemini-2.5-flash",
    },
}

BILD_ENDUNGEN = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp", ".gif"}
CSV_SPALTEN = ["datei", "status", "antwort", "modell", "dauer_s", "prompt_tokens", "completion_tokens"]


def bild_als_data_url(pfad: Path) -> str:
    """Bild base64-kodiert als data:-URL, wie es die OpenAI-Vision-API erwartet."""
    mime = mimetypes.guess_type(pfad.name)[0] or "image/jpeg"
    if pfad.suffix.lower() in {".tif", ".tiff"}:
        # TIFF wird von vielen Servern nicht akzeptiert -> nach PNG konvertieren
        from io import BytesIO
        from PIL import Image  # pip install pillow

        buf = BytesIO()
        Image.open(pfad).convert("RGB").save(buf, format="PNG")
        daten, mime = buf.getvalue(), "image/png"
    else:
        daten = pfad.read_bytes()
    return f"data:{mime};base64,{base64.b64encode(daten).decode('ascii')}"


def entferne_thinking(text: str) -> str:
    """"Thinking"-Modelle (z.B. Qwen3) liefern <think>...</think> mit; das wegschneiden."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def verarbeite_bild(client: OpenAI, modell: str, prompt: str, pfad: Path, name: str,
                    max_tokens: int, versuche: int) -> dict:
    data_url = bild_als_data_url(pfad)
    letzter_fehler = None
    for versuch in range(1, versuche + 1):
        start = time.time()
        try:
            resp = client.chat.completions.create(
                model=modell,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url}},
                        {"type": "text", "text": prompt},
                    ],
                }],
                max_tokens=max_tokens,
                temperature=0,
            )
            wahl = resp.choices[0]
            antwort = entferne_thinking(wahl.message.content or "")
            usage = resp.usage
            return {
                "datei": name,
                # "length" = Token-Limit erreicht -> Antwort ist abgeschnitten
                "status": "ok" if wahl.finish_reason != "length" else "abgeschnitten",
                "antwort": antwort,
                "modell": resp.model,
                "dauer_s": round(time.time() - start, 1),
                "prompt_tokens": usage.prompt_tokens if usage else "",
                "completion_tokens": usage.completion_tokens if usage else "",
            }
        except Exception as e:  # Netzwerk, Timeout, 5xx ...
            letzter_fehler = e
            if versuch < versuche:
                time.sleep(2 ** versuch)
    return {"datei": name, "status": "fehler", "antwort": f"{type(letzter_fehler).__name__}: {letzter_fehler}",
            "modell": modell, "dauer_s": "", "prompt_tokens": "", "completion_tokens": ""}


def bereits_erledigt(csv_pfad: Path) -> set:
    """Dateinamen, die schon erfolgreich in der CSV stehen."""
    if not csv_pfad.exists():
        return set()
    with csv_pfad.open(newline="", encoding="utf-8-sig") as f:
        return {z["datei"] for z in csv.DictReader(f) if z.get("status") == "ok"}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ordner", type=Path, help="Ordner mit den Bildern")
    ap.add_argument("csv", type=Path, help="Ausgabe-CSV")
    ap.add_argument("--provider", choices=ANBIETER, default="gpustack", help="gpustack (Standard) oder gemini")
    ap.add_argument("--base-url", help="API-Adresse; GPUStack z.B. http://server/v1 (ältere Versionen: /v1-openai)")
    ap.add_argument("--api-key", help="API-Key (Standard: GPUSTACK_API_KEY bzw. GEMINI_API_KEY)")
    ap.add_argument("--model", help="Modellname (Standard: qwen3.8-27b bzw. gemini-2.5-flash)")
    ap.add_argument("--prompt-file", type=Path, default=STANDARD_PROMPT_DATEI,
                    help="Textdatei mit dem Prompt (Standard: prompt.txt neben dem Skript)")
    ap.add_argument("--max-tokens", type=int, default=4096)
    ap.add_argument("--workers", type=int, default=2, help="parallele Anfragen")
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--recursive", action="store_true", help="auch Unterordner durchsuchen")
    args = ap.parse_args()

    anbieter = ANBIETER[args.provider]
    args.base_url = args.base_url or anbieter["base_url"]
    args.api_key = args.api_key or os.environ.get(anbieter["key_env"])
    args.model = args.model or anbieter["model"]
    if not args.api_key:
        sys.exit(f"Kein API-Key: --api-key setzen oder {anbieter['key_env']} exportieren.")
    if not args.prompt_file.is_file():
        sys.exit(f"Prompt-Datei nicht gefunden: {args.prompt_file}")
    prompt = args.prompt_file.read_text(encoding="utf-8").strip()
    if not prompt:
        sys.exit(f"Prompt-Datei ist leer: {args.prompt_file}")

    muster = "**/*" if args.recursive else "*"
    bilder = sorted(p for p in args.ordner.glob(muster) if p.is_file() and p.suffix.lower() in BILD_ENDUNGEN)
    # Pfad relativ zum Bildordner, z.B. "a.jpg" oder mit --recursive "unterordner/a.jpg"
    namen = {p: p.relative_to(args.ordner).as_posix() for p in bilder}
    erledigt = bereits_erledigt(args.csv)
    offen = [p for p in bilder if namen[p] not in erledigt]
    print(f"{len(bilder)} Bilder gefunden, {len(erledigt)} bereits erledigt, {len(offen)} zu verarbeiten.")
    if not offen:
        return

    client = OpenAI(base_url=args.base_url, api_key=args.api_key, timeout=300)
    neu = not args.csv.exists()
    # utf-8-sig, damit Excel Umlaute korrekt anzeigt
    with args.csv.open("a", newline="", encoding="utf-8-sig" if neu else "utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_SPALTEN, quoting=csv.QUOTE_ALL)
        if neu:
            writer.writeheader()
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(verarbeite_bild, client, args.model, prompt, p, namen[p],
                                   args.max_tokens, args.retries): p for p in offen}
            for i, fut in enumerate(as_completed(futures), 1):
                zeile = fut.result()
                writer.writerow(zeile)
                f.flush()  # sofort schreiben -> bei Abbruch geht nichts verloren
                print(f"[{i}/{len(offen)}] {zeile['datei']}: {zeile['status']}")


if __name__ == "__main__":
    main()
