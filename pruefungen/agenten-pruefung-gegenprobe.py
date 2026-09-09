# -*- coding: utf-8 -*-
"""Gegenprobe: schlaegt agenten-pruefen.py an, wenn wirklich etwas fehlt?

Ohne diese Probe wuesste man nur, dass die Pruefung "OK" sagen kann - nicht,
dass sie ueberhaupt in der Lage ist, "FEHLER" zu sagen.
Die echten Dateien werden dabei NICHT angefasst; nur die Konstanten im
geladenen Modul werden umgebogen.
"""
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

QUELLE = Path(r"C:\Users\karlm\OneDrive\Desktop\claude-anzeige\agenten-pruefen.py")
sys.path.insert(0, str(QUELLE.parent))

spec = importlib.util.spec_from_file_location("ap", QUELLE)
ap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ap)

tmp = Path(tempfile.mkdtemp())
fehler = 0

# --- Probe 1: settings.json ohne den SubagentStop-Hook ---
echte = json.loads(ap.EINSTELLUNGEN.read_text(encoding="utf-8-sig"))
echte.get("hooks", {}).pop("SubagentStop", None)
kaputt = tmp / "settings-ohne-subagentstop.json"
kaputt.write_text(json.dumps(echte), encoding="utf-8")

ap.EINSTELLUNGEN = kaputt
hooks = ap.hooks_lesen()
if "SubagentStop" in (hooks or {}):
    print("[FEHLER] Probe 1: SubagentStop wurde entfernt, hooks_lesen() sieht ihn trotzdem")
    fehler += 1
else:
    print("[  OK  ] Probe 1: fehlender SubagentStop-Hook wird erkannt")

# --- Probe 2: settings.json, in der agent-merker gar nicht vorkommt ---
ohne = {"hooks": {"PreToolUse": [{"hooks": [{"type": "command", "command": "powershell",
                                             "args": ["-File", "irgendwas-anderes.ps1"]}]}]}}
leer = tmp / "settings-ohne-merker.json"
leer.write_text(json.dumps(ohne), encoding="utf-8")
ap.EINSTELLUNGEN = leer
hooks = ap.hooks_lesen()
if hooks:
    print("[FEHLER] Probe 2: kein agent-merker eingetragen, trotzdem gefunden:", hooks)
    fehler += 1
else:
    print("[  OK  ] Probe 2: settings.json ohne agent-merker liefert nichts")

# --- Probe 3: Merker-Skript fehlt -> Selbsttest muss FEHLER melden ---
ap._befunde.clear()
ap.MERKER_SKRIPT = tmp / "gibt-es-nicht.ps1"
ap.selbsttest()
if any(s == ap.FEHLER for s, _ in ap._befunde):
    print("[  OK  ] Probe 3: fehlendes agent-merker.ps1 wird als FEHLER gemeldet")
else:
    print("[FEHLER] Probe 3: fehlendes Skript blieb unbemerkt")
    fehler += 1

# --- Probe 4: Skript da, schreibt aber nichts -> muss FEHLER melden ---
ap._befunde.clear()
stumm = tmp / "stumm.ps1"
stumm.write_text("exit 0", encoding="utf-8")   # tut nichts, endet sauber
ap.MERKER_SKRIPT = stumm
ap.selbsttest()
if any(s == ap.FEHLER for s, _ in ap._befunde):
    print("[  OK  ] Probe 4: ein Merker, der nichts schreibt, wird als FEHLER gemeldet")
else:
    print("[FEHLER] Probe 4: stummer Merker blieb unbemerkt - genau die Bauform,")
    print("                  die das Werkzeug finden soll")
    fehler += 1

print()
print("Gegenprobe:", "bestanden" if not fehler else f"{fehler} Probe(n) gescheitert")
sys.exit(1 if fehler else 0)
