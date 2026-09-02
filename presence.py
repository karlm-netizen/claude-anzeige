# -*- coding: utf-8 -*-
"""
Discord Rich Presence fuer Claude Code.

So sieht es auf dem Profil aus:

    Spielt Claude          <- Name der Anwendung aus dem Developer Portal
    Honking...             <- wechselt, solange Claude arbeitet
    2 Agenten arbeiten     <- nur wenn welche laufen
    seit 01:23

Braucht:
  - Discord als DESKTOP-App (im Browser gibt es kein Rich Presence)
  - eine Anwendungs-ID aus dem Discord Developer Portal in konfig.json

Start:  "Presence starten.vbs" (ohne Fenster)
        oder  python presence.py --sichtbar   (mit Ausgabe, zum Nachsehen)
"""

import ctypes
import json
import os
import random
import sys
import time
from pathlib import Path

import psutil
from pypresence import ActivityType, Presence
from pypresence.exceptions import (
    DiscordError,
    DiscordNotFound,
    InvalidID,
    InvalidPipe,
    PipeClosed,
    ResponseTimeout,
)

import agenten

HIER = Path(__file__).resolve().parent
KONFIG_DATEI = HIER / "konfig.json"
LOG_DATEI = HIER / "presence.log"
LOG_GRENZE = 200_000

VERBINDUNGSFEHLER = (
    DiscordNotFound, DiscordError, InvalidPipe, InvalidID,
    PipeClosed, ResponseTimeout, ConnectionError, OSError,
)

# Die Woerter aus dem Terminal. Sie stehen in konfig.json und sind dort
# aenderbar - das hier ist die Fassung, mit der eine frische Konfig entsteht.
WOERTER = [
    "Calculating", "Computing", "Honking", "Wandering", "Pondering",
    "Simmering", "Noodling", "Puzzling", "Musing", "Percolating",
    "Ruminating", "Thinking", "Cogitating", "Brewing", "Conjuring",
    "Deliberating", "Finagling", "Herding", "Ideating", "Inferring",
    "Manifesting", "Marinating", "Moseying", "Mulling", "Processing",
    "Reticulating", "Schlepping", "Shucking", "Spelunking", "Stewing",
    "Synthesizing", "Transmuting", "Vibing", "Whirring", "Baking",
    "Channelling", "Crafting", "Divining", "Envisioning", "Forging",
]

STANDARD_KONFIG = {
    "anwendungs_id": "",
    "prozess": "claude.exe",
    "aktivitaets_art": "PLAYING",
    "agenten_zeigen": True,
    "woerter": WOERTER,
    # Karls Ansage am 01.09.2026: auf dem Profil soll IMMER ein Wort laufen.
    # Er schaut meistens dann hin, wenn gerade nicht gearbeitet wird - und dann
    # stand da "wartet". Auf false: dann steht in Ruhe der wartet_text.
    # ⚠️ Das Fenster bleibt ehrlich, dort sind die drei Zustaende zu sehen.
    "immer_arbeiten": True,
    "wartet_text": "wartet",
    "bild_schluessel": "",
    "bild_text": "",
    "takt_sekunden": 15,
}

SICHTBAR = "--sichtbar" in sys.argv


def sagen(text):
    """Eine Zeile ins Log, und bei --sichtbar auch auf den Bildschirm."""
    zeile = time.strftime("%d.%m.%Y %H:%M:%S") + "  " + text
    try:
        if LOG_DATEI.exists() and LOG_DATEI.stat().st_size > LOG_GRENZE:
            alt = LOG_DATEI.read_text(encoding="utf-8", errors="replace")
            LOG_DATEI.write_text(alt[-LOG_GRENZE // 2:], encoding="utf-8")
        with LOG_DATEI.open("a", encoding="utf-8") as f:
            f.write(zeile + "\n")
    except OSError:
        pass
    if SICHTBAR:
        try:
            print(zeile, flush=True)
        except UnicodeEncodeError:
            print(zeile.encode("ascii", "replace").decode(), flush=True)


def abbrechen(text):
    """Fataler Fehler: ins Log, als Fenster zeigen (es laeuft ohne Konsole), Schluss."""
    sagen("ABBRUCH: " + text)
    try:
        ctypes.windll.user32.MessageBoxW(0, text, "Claude Presence", 0x10)
    except Exception:
        pass
    sys.exit(1)


def konfig_laden():
    if not KONFIG_DATEI.exists():
        KONFIG_DATEI.write_text(
            json.dumps(STANDARD_KONFIG, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        abbrechen(
            "konfig.json war nicht da und wurde neu angelegt.\n\n"
            "Jetzt fehlt nur noch die Anwendungs-ID aus dem Discord Developer Portal.\n"
            "Wie das geht, steht in der README.md daneben."
        )
    try:
        roh = json.loads(KONFIG_DATEI.read_text(encoding="utf-8"))
    except json.JSONDecodeError as fehler:
        abbrechen("konfig.json ist kaputt (Zeile " + str(fehler.lineno) + "): " + fehler.msg)
    konfig = {**STANDARD_KONFIG, **roh}
    if not str(konfig["anwendungs_id"]).strip():
        abbrechen(
            "In konfig.json fehlt die Anwendungs-ID.\n\n"
            "Sie steht im Discord Developer Portal unter deiner Anwendung\n"
            "bei 'General Information' -> 'Application ID'.\n\n"
            "Schritt fuer Schritt: README.md im selben Ordner."
        )
    if not konfig["woerter"]:
        konfig["woerter"] = WOERTER
    return konfig


def schon_am_laufen():
    """Zweiter Start waere schlimmer als kein Start - Discord bekaeme zwei Aktualisierungen."""
    ich = os.getpid()
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if p.info["pid"] == ich or not p.info["cmdline"]:
                continue
            if "python" not in (p.info["name"] or "").lower():
                continue
            if any("presence.py" in str(teil) for teil in p.info["cmdline"]):
                return p.info["pid"]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


def agenten_satz(anzahl):
    if anzahl <= 0:
        return ""
    if anzahl == 1:
        return "1 Agent arbeitet"
    return str(anzahl) + " Agenten arbeiten"


def wort_ziehen(woerter, vorheriges):
    """Ein neues Wort, moeglichst nicht dasselbe wie eben."""
    if len(woerter) < 2:
        return woerter[0]
    neu = vorheriges
    while neu == vorheriges:
        neu = random.choice(woerter)
    return neu


def anzeigen(rpc, konfig, seit, wort, anzahl):
    felder = {"start": seit}

    art = str(konfig["aktivitaets_art"]).upper()
    if art in ActivityType.__members__:
        felder["activity_type"] = ActivityType[art]

    # Erste Zeile: das Wort, solange gearbeitet wird - sonst der Wartetext.
    if wort:
        felder["details"] = wort + "..."
    elif konfig["wartet_text"].strip():
        felder["details"] = konfig["wartet_text"].strip()

    # Zweite Zeile: die Agenten, und sonst nichts.
    satz = agenten_satz(anzahl) if konfig["agenten_zeigen"] else ""
    if satz:
        felder["state"] = satz

    if konfig["bild_schluessel"].strip():
        felder["large_image"] = konfig["bild_schluessel"].strip()
        if konfig["bild_text"].strip():
            felder["large_text"] = konfig["bild_text"].strip()

    rpc.update(**felder)


def main():
    anderer = schon_am_laufen()
    if anderer:
        sagen("Laeuft schon (PID " + str(anderer) + ") - dieser Start macht Schluss.")
        return

    konfig = konfig_laden()
    # ⚠️ Discord nimmt hoechstens alle 15 Sekunden eine Aenderung an. Schneller
    # koennen die Woerter also nicht wechseln, auch wenn sie es im Terminal tun.
    takt = max(15, int(konfig["takt_sekunden"]))
    sagen("Start. Beobachtet " + str(konfig["prozess"]) + ", Takt " + str(takt)
          + " s, " + str(len(konfig["woerter"])) + " Woerter.")

    rpc = None
    gezeigt = None           # was gerade bei Discord steht
    wort = None
    letzte_meldung = None    # damit das Log nicht jede Runde dasselbe schreibt

    while True:
        try:
            seit = agenten.claude_laeuft(konfig["prozess"])
            arbeitet = agenten.claude_arbeitet() is not None
            anzahl = len(agenten.laufende_agenten()) if konfig["agenten_zeigen"] else 0

            if seit is not None:
                if rpc is None:
                    rpc = Presence(str(konfig["anwendungs_id"]))
                    rpc.connect()
                    gezeigt = None
                    sagen("Mit Discord verbunden.")

                # In JEDER Runde ein neues Wort. Mit immer_arbeiten=True auch dann,
                # wenn gerade nichts laeuft - das Profil soll beschaeftigt aussehen.
                zeige_wort = arbeitet or konfig["immer_arbeiten"]
                wort = wort_ziehen(konfig["woerter"], wort) if zeige_wort else None

                stand = (seit, wort, anzahl)
                if stand != gezeigt:
                    anzeigen(rpc, konfig, seit, wort, anzahl)
                    gezeigt = stand
                    sagen("Angezeigt: " + (wort + "..." if wort else konfig["wartet_text"])
                          + (" | " + agenten_satz(anzahl) if anzahl else ""))
                letzte_meldung = None

            elif rpc is not None and gezeigt is not None:
                rpc.clear()
                gezeigt = None
                wort = None
                sagen("Claude ist zu - Anzeige weggeraeumt.")

        except VERBINDUNGSFEHLER as fehler:
            # Meistens: Discord ist gar nicht offen. Das ist keine Stoerung, nur ein Zustand.
            meldung = type(fehler).__name__ + ": " + str(fehler)
            if meldung != letzte_meldung:
                sagen("Keine Verbindung zu Discord (" + meldung + ") - versuche es weiter.")
                letzte_meldung = meldung
            try:
                if rpc is not None:
                    rpc.close()
            except Exception:
                pass
            rpc = None
            gezeigt = None

        time.sleep(takt)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sagen("Von Hand beendet.")
