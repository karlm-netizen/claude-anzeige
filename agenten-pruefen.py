# -*- coding: utf-8 -*-
"""
agenten-pruefen.py - laeuft die Agenten-Anzeige noch, oder luegt sie nur?

Gebaut am 09.09.2026. Karls Ansage: "Besser ueberpruefen koennen ob die
Agenten noch laufen."

WARUM DAS EIN EIGENES WERKZEUG BRAUCHT
`python agenten.py` sagt "Agenten: 0". Das kann zweierlei heissen:

    (a) gerade laeuft wirklich kein Agent          <- normal
    (b) der Melde-Weg ist kaputt und meldet nie    <- still, faellt nie auf

Von aussen sehen (a) und (b) IDENTISCH aus. Ein Agent hat keinen eigenen
Prozess (nachgemessen am 01.09.2026), also gibt es nichts, woran man (b)
erkennen koennte - ausser man prueft den Melde-Weg selbst. Genau das tut
diese Datei: sie ruft agent-merker.ps1 so auf, wie Claude Code es tut, und
sieht nach, ob wirklich etwas entsteht.

Das ist die Lehre vom 01.09.2026, hier angewandt: eine Pruefung muss den
EINBAU pruefen, nicht das Teil. Dass agent-merker.ps1 Dateien schreiben kann,
nuetzt nichts, wenn kein Hook ihn aufruft.

Aufruf:
    python agenten-pruefen.py          alles pruefen
    python agenten-pruefen.py --raeumen  verwaiste Merker zusaetzlich loeschen
"""

import json
import subprocess
import sys
import time
from pathlib import Path

import agenten

VAULT = Path(r"C:\Users\karlm\OneDrive\Desktop\ki-os-2")
MERKER_SKRIPT = VAULT / "werkzeuge" / "agent-merker.ps1"
EINSTELLUNGEN = VAULT / ".claude" / "settings.json"
ORDNER = agenten.MERKER_ORDNER

# Die Sitzungskennung, unter der die Pruefung ihre Testdatei anlegt.
# agent-merker.ps1 kuerzt auf 8 alphanumerische Zeichen - deshalb genau 8,
# damit der Name vorhersagbar bleibt und die Aufraeumung sicher greift.
TEST_SITZUNG = "PRUEFUNG"
TEST_TEXT = "Selbsttest der Anzeige (kein echter Agent)"

# Welche Hooks es geben muss, damit die Anzeige stimmt. Faellt einer aus,
# bleibt die Anzeige stumm oder haengt - je nachdem, welcher.
NOETIGE_HOOKS = {
    "PreToolUse":       ("-Start",      "Agenten werden nie gezaehlt"),
    "SubagentStop":     ("-Ende",       "fertige Agenten haengen als 'laeuft'"),
    "SessionEnd":       ("-SitzungAus", "nach einem Absturz haengen Merker bis zu 3 h"),
    "UserPromptSubmit": ("-ArbeitAn",   "'arbeitet gerade' wird nie angezeigt"),
    "Stop":             ("-ArbeitAus",  "'arbeitet gerade' geht nie wieder aus"),
}

OK, WARN, FEHLER = "  OK  ", " WARN ", "FEHLER"
_befunde = []


def sag(stufe, text, hinweis=""):
    print(f"[{stufe}] {text}")
    if hinweis:
        print(f"         {hinweis}")
    if stufe != OK:
        _befunde.append((stufe, text))


def hooks_lesen():
    """Welche der noetigen Hooks stehen in settings.json - mit welchem Schalter?

    Gibt {hookname: [schalter, ...]} zurueck. Ein Hook kann mehrere Eintraege
    haben (z. B. SessionStart mit remote-link.ps1 daneben), deshalb eine Liste.
    """
    if not EINSTELLUNGEN.is_file():
        return None
    try:
        daten = json.loads(EINSTELLUNGEN.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None

    gefunden = {}
    for name, gruppen in (daten.get("hooks") or {}).items():
        schalter = []
        for gruppe in gruppen or []:
            for h in gruppe.get("hooks") or []:
                args = [str(a) for a in (h.get("args") or [])]
                if not any("agent-merker" in a for a in args):
                    continue
                schalter += [a for a in args if a.startswith("-") and a[1:2].isupper()]
        if schalter:
            gefunden[name] = schalter
    return gefunden


def selbsttest():
    """agent-merker.ps1 einmal wirklich aufrufen - entsteht eine Datei?

    Das ist der Kern der ganzen Pruefung. Alles davor ist Papierform: die
    Datei ist da, der Hook steht drin. Hier wird gemessen.
    """
    if not MERKER_SKRIPT.is_file():
        sag(FEHLER, f"agent-merker.ps1 fehlt: {MERKER_SKRIPT}")
        return

    hook_json = json.dumps({
        "session_id": TEST_SITZUNG,
        "tool_input": {"description": TEST_TEXT},
    })

    def merker_rufen(schalter):
        try:
            fertig = subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-File",
                 str(MERKER_SKRIPT), schalter],
                input=hook_json, capture_output=True, text=True, timeout=30,
            )
            return fertig.returncode
        except (OSError, subprocess.SubprocessError) as e:
            sag(FEHLER, f"agent-merker.ps1 {schalter} laesst sich nicht aufrufen: {e}")
            return None

    vorher = set(ORDNER.glob(f"{TEST_SITZUNG}-*.lauf")) if ORDNER.is_dir() else set()

    # --- Start: es muss eine .lauf-Datei entstehen ---
    if merker_rufen("-Start") is None:
        return
    neu = (set(ORDNER.glob(f"{TEST_SITZUNG}-*.lauf")) - vorher) if ORDNER.is_dir() else set()
    if not neu:
        sag(FEHLER, "-Start hat KEINEN Merker angelegt",
            "Der Melde-Weg ist tot. Die Anzeige wuerde dauerhaft '0 Agenten' sagen,")
        print("         und das sieht genauso aus wie 'gerade laeuft keiner'.")
        return
    sag(OK, f"-Start legt einen Merker an ({len(neu)} Datei)")

    # Sieht agenten.py ihn auch? Sonst passen Schreiber und Leser nicht zusammen.
    if any(a["beschreibung"] == TEST_TEXT for a in agenten.laufende_agenten()):
        sag(OK, "agenten.py liest den Merker und zaehlt ihn mit")
    else:
        sag(FEHLER, "agenten.py sieht den eben angelegten Merker NICHT",
            "Geschrieben wird, gelesen nicht - Schreiber und Leser passen nicht zusammen.")

    # --- Ende: die Datei muss weg und im Verlauf stehen ---
    verlauf_datei = ORDNER / "verlauf.jsonl"
    zeilen_vorher = 0
    if verlauf_datei.is_file():
        try:
            zeilen_vorher = len(verlauf_datei.read_text(
                encoding="utf-8-sig", errors="replace").splitlines())
        except OSError:
            pass

    merker_rufen("-Ende")
    uebrig = set(ORDNER.glob(f"{TEST_SITZUNG}-*.lauf")) if ORDNER.is_dir() else set()
    if uebrig:
        sag(FEHLER, "-Ende hat den Merker NICHT weggeraeumt",
            "Fertige Agenten wuerden als 'laeuft noch' stehenbleiben, bis zu 3 Stunden lang.")
        for d in uebrig:
            d.unlink(missing_ok=True)
    else:
        sag(OK, "-Ende raeumt den Merker wieder weg")

    if verlauf_datei.is_file():
        try:
            zeilen = verlauf_datei.read_text(encoding="utf-8-sig",
                                             errors="replace").splitlines()
        except OSError:
            zeilen = []
        if len(zeilen) > zeilen_vorher:
            sag(OK, "-Ende schreibt den Lauf in den Verlauf")
            # Den Testeintrag wieder entfernen - sonst steht "Selbsttest" im
            # Fenster unter den zuletzt fertigen Agenten und sieht aus wie einer.
            behalten = [z for z in zeilen if TEST_TEXT not in z]
            if len(behalten) != len(zeilen):
                verlauf_datei.write_text("\n".join(behalten) + ("\n" if behalten else ""),
                                         encoding="utf-8")
                print("         (Testeintrag wieder aus dem Verlauf entfernt)")
        else:
            sag(WARN, "-Ende hat nichts in den Verlauf geschrieben",
                "Die Spalte 'zuletzt fertig' im Fenster bliebe leer.")


def verwaiste_merker(raeumen=False):
    """Merker, die stehengeblieben sind, obwohl kein Claude mehr laeuft.

    Der haeufigste Fall: die Sitzung ist abgestuerzt oder wurde hart beendet,
    SubagentStop und SessionEnd sind nie gefeuert. Die Anzeige zeigt dann bis
    zu drei Stunden lang Agenten, die es nicht mehr gibt.
    """
    if not ORDNER.is_dir():
        return
    laeuft = agenten.claude_laeuft() is not None
    jetzt = time.time()

    dateien = list(ORDNER.glob("*.lauf")) + list(ORDNER.glob("arbeit-*.zustand"))
    verdaechtig = []
    for d in dateien:
        alter = jetzt - d.stat().st_mtime
        # Kein Claude am Laufen, aber Merker da -> sicher verwaist.
        # Claude laeuft -> erst ab einer Stunde verdaechtig; so lange arbeitet
        # normalerweise kein Agent.
        if not laeuft or alter > 60 * 60:
            verdaechtig.append((d, alter))

    if not verdaechtig:
        sag(OK, "keine verwaisten Merker")
        return

    grund = "kein claude.exe laeuft" if not laeuft else "aelter als eine Stunde"
    sag(WARN, f"{len(verdaechtig)} verwaiste(r) Merker ({grund})",
        "Die Anzeige zeigt Agenten, die es nicht mehr gibt.")
    for d, alter in verdaechtig:
        print(f"         - {d.name}  ({agenten.dauer_text(alter)} alt)")
    if raeumen:
        for d, _ in verdaechtig:
            d.unlink(missing_ok=True)
        print(f"         -> {len(verdaechtig)} geloescht.")
    else:
        print("         Zum Loeschen:  python agenten-pruefen.py --raeumen")


def main():
    raeumen = "--raeumen" in sys.argv
    print("=" * 64)
    print("  Laeuft die Agenten-Anzeige noch?  " + time.strftime("%d.%m.%Y  %H:%M"))
    print("=" * 64)

    # --- 1. Papierform: liegen die Teile da? ---
    print("\n--- Die Teile ---")
    sag(OK if MERKER_SKRIPT.is_file() else FEHLER, f"agent-merker.ps1  {MERKER_SKRIPT}")
    sag(OK if ORDNER.is_dir() else WARN, f"Merker-Ordner     {ORDNER}",
        "" if ORDNER.is_dir() else "Wird beim ersten Agenten selbst angelegt - noch lief keiner.")

    # --- 2. Sind die Hooks eingetragen? ---
    print("\n--- Die Hooks in .claude/settings.json ---")
    hooks = hooks_lesen()
    if hooks is None:
        sag(FEHLER, "settings.json fehlt oder ist unlesbar", str(EINSTELLUNGEN))
    else:
        for name, (schalter, folge) in NOETIGE_HOOKS.items():
            if name in hooks and schalter in hooks[name]:
                sag(OK, f"{name:<17} {schalter}")
            else:
                sag(FEHLER, f"{name:<17} {schalter} FEHLT", f"Folge: {folge}.")

    # --- 3. Der eigentliche Test ---
    print("\n--- Der Melde-Weg, wirklich aufgerufen ---")
    selbsttest()

    # --- 4. Leichen ---
    print("\n--- Verwaiste Merker ---")
    verwaiste_merker(raeumen)

    # --- 5. Lebenszeichen ---
    print("\n--- Wann zuletzt ein Agent lief ---")
    # ⚠️ NICHT ueber das Aenderungsdatum der Datei gehen. Der Selbsttest oben
    # schreibt selbst hinein und setzt es auf JETZT - beim ersten Lauf am
    # 09.09.2026 meldete diese Pruefung deshalb "letzter Agentenlauf: gerade
    # eben", obwohl der letzte echte vom 06.09. war. Eine Pruefung, die ihre
    # eigene Messung verfaelscht, ist schlimmer als keine.
    # Deshalb: den juengsten "beendet"-Zeitstempel aus dem INHALT lesen.
    letzter = None
    verlauf_datei = ORDNER / "verlauf.jsonl" if ORDNER.is_dir() else None
    if verlauf_datei and verlauf_datei.is_file():
        try:
            for zeile in verlauf_datei.read_text(encoding="utf-8-sig",
                                                 errors="replace").splitlines():
                try:
                    beendet = float(json.loads(zeile).get("beendet", 0))
                except (ValueError, AttributeError):
                    continue
                if beendet > 0 and (letzter is None or beendet > letzter):
                    letzter = beendet
        except OSError:
            pass
    if letzter:
        alter = time.time() - letzter
        tage = alter / 86400
        wann = time.strftime("%d.%m.%Y %H:%M", time.localtime(letzter))
        if tage > 3:
            sag(WARN, f"letzter Agentenlauf am {wann} - vor {tage:.0f} Tagen",
                "Nach der Regel in CLAUDE.md laeuft der Fund-Sucher nach jedem groesseren")
            print("         Umbau automatisch. Drei Tage ohne Lauf heisst: entweder wurde")
            print("         nichts Groesseres gebaut, oder er wurde vergessen.")
        else:
            sag(OK, f"letzter Agentenlauf am {wann}")
    else:
        sag(WARN, "noch nie ein Agent zu Ende gelaufen",
            "Kein verlauf.jsonl oder keine Zeile mit Endzeit darin.")

    # --- Fazit ---
    print("\n" + "=" * 64)
    fehler = [b for b in _befunde if b[0] == FEHLER]
    warnungen = [b for b in _befunde if b[0] == WARN]
    if fehler:
        print(f"  {len(fehler)} FEHLER - die Anzeige ist NICHT verlaesslich.")
        for _, t in fehler:
            print(f"    - {t}")
    elif warnungen:
        print(f"  Keine Fehler, {len(warnungen)} Hinweis(e).")
        for _, t in warnungen:
            print(f"    - {t}")
    else:
        print("  Alles in Ordnung - was die Anzeige sagt, stimmt auch.")
    print("=" * 64)
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
