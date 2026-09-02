# -*- coding: utf-8 -*-
"""
Gemeinsame Erkennung fuer die Discord-Presence und das Fenster.

Beantwortet zwei Fragen:
    claude_laeuft()     -> Startzeit der aeltesten Sitzung, sonst None
    laufende_agenten()  -> Liste der Agenten, die gerade arbeiten

WARUM DIE AGENTEN NICHT UEBER PROZESSE GEHEN
Ein Agent bekommt keinen eigenen Prozess - er arbeitet innerhalb der
Claude-Sitzung. Am 01.09.2026 nachgemessen: waehrend ein Agent zehn Minuten
lang lief, waren es unveraendert zwei claude.exe. Auch die Dateien im
tasks-Ordner taugen nicht als Spur - die des fertig gewordenen Agenten war
0 Bytes gross, der Inhalt lag woanders.

Stattdessen meldet Claude Code selbst: werkzeuge/agent-merker.ps1 haengt an
zwei Hooks und legt beim Start eines Agenten eine Merkdatei an, die beim Ende
wieder verschwindet.
"""

import json
import os
import time
from pathlib import Path

import psutil

MERKER_ORDNER = Path(os.environ.get("LOCALAPPDATA", ".")) / "ki-os-agenten"

# Ein Merker, der aelter ist, gilt als Ueberbleibsel eines Absturzes und wird
# nicht mehr mitgezaehlt. Ohne das haengt eine abgestuerzte Sitzung fuer immer
# als "1 Agent arbeitet" im Profil.
ALTERSGRENZE_SEKUNDEN = 3 * 60 * 60


def claude_arbeitet():
    """Seit wann Claude gerade an einer Antwort arbeitet, sonst None.

    'Laeuft' und 'arbeitet' sind zweierlei: ein offenes Fenster, das auf Karls
    naechste Nachricht wartet, laeuft - arbeitet aber nicht. Auch das ist von
    aussen unsichtbar, also melden es Hooks: UserPromptSubmit legt den Zustand
    an, Stop raeumt ihn weg.

    Laufen mehrere Sitzungen, zaehlt die aelteste laufende Arbeit.
    """
    if not MERKER_ORDNER.is_dir():
        return None

    jetzt = time.time()
    seit = None
    for datei in MERKER_ORDNER.glob("arbeit-*.zustand"):
        try:
            daten = json.loads(datei.read_text(encoding="utf-8"))
            angefangen = float(daten.get("seit", 0))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if angefangen <= 0 or jetzt - angefangen > ALTERSGRENZE_SEKUNDEN:
            continue
        if seit is None or angefangen < seit:
            seit = angefangen
    return seit


def claude_laeuft(prozessname="claude.exe"):
    """Startzeitpunkt der aeltesten laufenden Sitzung, sonst None.

    Aeltester Start = 'seit wann arbeitest du' - genau das zeigt Discord an.
    """
    gesucht = prozessname.lower()
    starts = []
    for p in psutil.process_iter(["name", "create_time"]):
        try:
            if (p.info["name"] or "").lower() == gesucht:
                starts.append(p.info["create_time"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return int(min(starts)) if starts else None


def laufende_agenten():
    """Die gerade arbeitenden Agenten, aeltester zuerst.

    Je Eintrag: id, beschreibung, gestartet (Zeitstempel), laeuft_seit (Sekunden).
    Kaputte oder uralte Merkdateien werden uebergangen, nicht gemeldet - ein
    Anzeiger, der wegen einer Datei abstuerzt, ist schlechter als einer, der
    einen Eintrag verschweigt.
    """
    if not MERKER_ORDNER.is_dir():
        return []

    jetzt = time.time()
    gefunden = []
    for datei in MERKER_ORDNER.glob("*.lauf"):
        try:
            daten = json.loads(datei.read_text(encoding="utf-8"))
            gestartet = float(daten.get("gestartet", 0))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        alter = jetzt - gestartet
        if gestartet <= 0 or alter > ALTERSGRENZE_SEKUNDEN:
            continue
        gefunden.append({
            "id": datei.stem,
            "beschreibung": str(daten.get("beschreibung") or "Agent").strip(),
            "gestartet": gestartet,
            "laeuft_seit": int(alter),
        })

    gefunden.sort(key=lambda a: a["gestartet"])
    return gefunden


def aufraeumen():
    """Uralte Merker loeschen. Wird vom Fenster gelegentlich aufgerufen."""
    if not MERKER_ORDNER.is_dir():
        return 0
    jetzt = time.time()
    weg = 0
    for muster in ("*.lauf", "arbeit-*.zustand"):
        for datei in MERKER_ORDNER.glob(muster):
            try:
                if jetzt - datei.stat().st_mtime > ALTERSGRENZE_SEKUNDEN:
                    datei.unlink()
                    weg += 1
            except OSError:
                continue
    return weg


def verlauf(hoechstens=6, nicht_aelter_als=6 * 60 * 60):
    """Kuerzlich fertig gewordene Agenten, der zuletzt beendete zuerst.

    Ohne das waere die Agenten-Spalte fast immer leer - Agenten laufen ja nur
    minutenweise. agent-merker.ps1 schreibt beim Ende eine Zeile in verlauf.jsonl.
    """
    datei = MERKER_ORDNER / "verlauf.jsonl"
    if not datei.is_file():
        return []
    jetzt = time.time()
    eintraege = []
    try:
        # ⚠️ utf-8-sig, nicht utf-8: PowerShell schreibt mit `Add-Content -Encoding
        # UTF8` eine BOM an den Dateianfang. Mit reinem utf-8 scheitert json.loads
        # an der ersten Zeile, der Fehler wird uebersprungen - und das Ergebnis
        # sieht aus wie "kein Verlauf" statt wie ein Fehler. Am 01.09.2026 genau
        # so passiert und nur aufgefallen, weil die Datei von Hand nachgesehen wurde.
        # Nur das Ende der Datei lesen - sie waechst mit jedem Agenten weiter.
        with datei.open("r", encoding="utf-8-sig", errors="replace") as f:
            zeilen = f.readlines()[-200:]
    except OSError:
        return []
    for zeile in zeilen:
        try:
            d = json.loads(zeile)
            beendet = float(d.get("beendet", 0))
            gestartet = float(d.get("gestartet", 0))
        except (ValueError, json.JSONDecodeError):
            continue
        if beendet <= 0 or jetzt - beendet > nicht_aelter_als:
            continue
        eintraege.append({
            "beschreibung": str(d.get("beschreibung") or "Agent").strip(),
            "gestartet": gestartet,
            "beendet": beendet,
            "gelaufen": int(max(0, beendet - gestartet)),
        })
    eintraege.sort(key=lambda e: e["beendet"], reverse=True)
    return eintraege[:hoechstens]


# Fuer die CPU-Messung: psutil braucht zwei Messpunkte, der erste liefert immer
# 0.0. Deshalb werden die Prozessobjekte behalten statt jedes Mal neu geholt.
_prozesse = {}


def system_last(prozessname="claude.exe"):
    """Was Claude gerade an CPU und Arbeitsspeicher belegt.

    cpu: Anteil an der gesamten Rechenleistung in Prozent (ueber alle Kerne
         normiert, also 0-100 und nicht 0-1600 bei 16 Kernen).
    ram: Anteil am gesamten Arbeitsspeicher in Prozent, dazu die MB.
    """
    gesucht = prozessname.lower()
    lebende = {}
    cpu_summe = 0.0
    rss = 0
    for p in psutil.process_iter(["pid", "name"]):
        try:
            if (p.info["name"] or "").lower() != gesucht:
                continue
            pid = p.info["pid"]
            merk = _prozesse.get(pid) or psutil.Process(pid)
            lebende[pid] = merk
            cpu_summe += merk.cpu_percent(interval=None)
            rss += merk.memory_info().rss
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    _prozesse.clear()
    _prozesse.update(lebende)

    kerne = psutil.cpu_count() or 1
    gesamt_ram = psutil.virtual_memory().total or 1
    return {
        "cpu": min(100.0, cpu_summe / kerne),
        "ram": min(100.0, rss / gesamt_ram * 100.0),
        "ram_mb": int(rss / (1024 * 1024)),
        "prozesse": len(lebende),
    }


# Die Sitzungsprotokolle von Claude Code. Dort stehen echte Token-Zahlen.
PROTOKOLL_ORDNER = (Path.home() / ".claude" / "projects"
                    / "c--Users-karlm-OneDrive-Desktop-ki-os-2")

# Die Datei waechst nur am Ende. Deshalb wird sie nicht jedes Mal ganz gelesen,
# sondern nur der neue Teil seit dem letzten Blick.
_token = {"pfad": None, "offset": 0, "aus": 0, "kontext": 0, "spitze": 0}


def token_stand():
    """Kontextgroesse und ausgegebene Token der laufenden Sitzung.

    kontext: was bei der letzten Anfrage hineingegangen ist (Eingabe plus
             gelesener und neu angelegter Zwischenspeicher).
    aus:     alle bisher ausgegebenen Token dieser Sitzung.
    Alles None, wenn kein Protokoll zu finden ist.
    """
    if not PROTOKOLL_ORDNER.is_dir():
        return None
    dateien = list(PROTOKOLL_ORDNER.glob("*.jsonl"))
    if not dateien:
        return None
    neueste = max(dateien, key=lambda p: p.stat().st_mtime)

    if _token["pfad"] != str(neueste):
        _token.update({"pfad": str(neueste), "offset": 0, "aus": 0,
                       "kontext": 0, "spitze": 0})

    try:
        groesse = neueste.stat().st_size
        if groesse < _token["offset"]:      # Datei wurde ersetzt
            _token.update({"offset": 0, "aus": 0, "kontext": 0})
        if groesse > _token["offset"]:
            with neueste.open("rb") as f:
                f.seek(_token["offset"])
                roh = f.read(groesse - _token["offset"])
            # Nur bis zum letzten vollstaendigen Zeilenende auswerten - die
            # letzte Zeile kann gerade halb geschrieben sein.
            schnitt = roh.rfind(b"\n")
            if schnitt >= 0:
                _token["offset"] += schnitt + 1
                for zeile in roh[:schnitt].decode("utf-8", "replace").splitlines():
                    if '"usage"' not in zeile:
                        continue
                    try:
                        d = json.loads(zeile)
                    except ValueError:
                        continue
                    u = (d.get("message") or {}).get("usage") or d.get("usage")
                    if not isinstance(u, dict):
                        continue
                    _token["aus"] += int(u.get("output_tokens") or 0)
                    hinein = (int(u.get("input_tokens") or 0)
                              + int(u.get("cache_read_input_tokens") or 0)
                              + int(u.get("cache_creation_input_tokens") or 0))
                    if hinein:
                        _token["kontext"] = hinein
                        _token["spitze"] = max(_token["spitze"], hinein)
    except OSError:
        pass

    return {"kontext": _token["kontext"], "aus": _token["aus"],
            "spitze": _token["spitze"]}


def kurz_zahl(n):
    """263684 -> '264K',  1233 -> '1.2K',  12 -> '12'"""
    n = int(n or 0)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 10_000:
        return f"{round(n / 1000)}K"
    if n >= 1000:
        return f"{n / 1000:.1f}K"
    return str(n)


def dauer_text(sekunden):
    """72 -> '1:12', 3700 -> '1:01:40'"""
    sekunden = max(0, int(sekunden))
    s, m, h = sekunden % 60, (sekunden // 60) % 60, sekunden // 3600
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


if __name__ == "__main__":
    seit = claude_laeuft()
    print("Claude   :", time.strftime("%H:%M:%S", time.localtime(seit)) if seit else "laeuft nicht")
    arbeit = claude_arbeitet()
    print("arbeitet :", f"ja, seit {dauer_text(time.time() - arbeit)}" if arbeit else "nein, wartet")
    laufende = laufende_agenten()
    print("Agenten  :", len(laufende))
    for a in laufende:
        print(f"   - {a['beschreibung']}  ({dauer_text(a['laeuft_seit'])})")
    fertig = verlauf()
    print("fertig   :", len(fertig))
    for e in fertig:
        print(f"   - {e['beschreibung']}  (lief {dauer_text(e['gelaufen'])})")
    last = system_last()
    time.sleep(0.5)                      # zweiter Messpunkt fuer die CPU
    last = system_last()
    print("CPU/RAM  : {0:.0f} % / {1:.0f} % ({2} MB, {3} Prozesse)".format(
        last["cpu"], last["ram"], last["ram_mb"], last["prozesse"]))
    t = token_stand()
    if t:
        print("Token    : Kontext", kurz_zahl(t["kontext"]),
              "| ausgegeben", kurz_zahl(t["aus"]),
              "| Spitze", kurz_zahl(t["spitze"]))
    else:
        print("Token    : kein Protokoll gefunden")
    print("Merker   :", MERKER_ORDNER)
