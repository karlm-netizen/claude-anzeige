# -*- coding: utf-8 -*-
"""
Claude Monitor - das grosse Fenster, heller Apple-Look.

Zeigt in einem Bild, was gerade laeuft:
  - Claude:   aus / laeuft / arbeitet
  - Agenten:  laufende und kuerzlich fertige
  - Zahlen:   CPU, Arbeitsspeicher, ausgegebene Token, Kontextgroesse

Bedienung:
  F11                      Vollbild an/aus
  Esc                      Vollbild verlassen
  Doppelklick auf den Ring Vollbild an/aus
  "immer oben"             haelt das Fenster ueber allen anderen

Start:  "Fenster starten.vbs"   oder   python fenster.py
"""

import ctypes
import json
import math
import os
import random
import sys
import time
import tkinter as tk
from collections import deque
from pathlib import Path

import psutil

import agenten

# ⚠️ MUSS vor dem ersten Fenster passieren.
# Ohne das rechnet Windows das Fenster hoch, statt es scharf zu zeichnen - und
# die Schrift wird groesser, ohne dass das Fenster mitwaechst. Am 01.09.2026
# genau so passiert: die rechte Karte war abgeschnitten, die Kachelleiste ganz
# weg. Sichtbar wurde es erst auf einem Bildschirmfoto.
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

HIER = Path(__file__).resolve().parent
STELLE_DATEI = HIER / "fenster-stelle.json"
KONFIG_DATEI = HIER / "konfig.json"

BILD_MS = 40          # 25 Bilder je Sekunde, solange sich etwas bewegt
RUHE_MS = 400         # wenn nichts arbeitet, reicht das - spart Rechenzeit
DATEN_TAKT = 1.0
WORT_TAKT = 3.0
AUFRAEUM_TAKT = 300

# Ohne ablesbare Obergrenze fuer den Kontext: der Balken misst gegen diesen Wert,
# waechst aber mit, wenn die Sitzung darueber hinausgeht. Nie ueber 100 %.
KONTEXT_GRENZE = 1_000_000

# Zwei Paletten, beide im Apple-Stil. Beim Umschalten werden die Namen unten
# neu belegt und die Oberflaeche einmal neu gebaut - das ist verlaesslicher,
# als jedes einzelne Fenster nachtraeglich umzufaerben, und dauert einen
# Wimpernschlag.
HELL = {
    "GRUND": "#f5f5f7", "KARTE": "#ffffff", "FELD": "#f5f5f7",
    "LINIE": "#e3e3e8", "TEXT": "#1d1d1f", "GEDAEMPFT": "#6e6e73",
    "BLASS": "#aeaeb2", "SCHIENE": "#e4e4e9",
    "CLAUDE": "#d97757",       # die Farbe aus Karls Stern
    "BLAU": "#0071e3", "GRUEN": "#34c759", "LILA": "#5e5ce6",
    "GELB": "#ff9f0a", "TUERKIS": "#00b3a4", "ROT": "#ff3b30",
}
DUNKEL = {
    "GRUND": "#0b0d14", "KARTE": "#14161f", "FELD": "#1b1e29",
    "LINIE": "#272b38", "TEXT": "#eceef4", "GEDAEMPFT": "#8b90a0",
    "BLASS": "#565c6e", "SCHIENE": "#3a3f4e",
    "CLAUDE": "#e0855f",       # eine Spur heller, sonst saeuft sie ab
    "BLAU": "#0a84ff", "GRUEN": "#30d158", "LILA": "#7d7aff",
    "GELB": "#ffd60a", "TUERKIS": "#40c8bc", "ROT": "#ff453a",
}


# Die Namen einmal ausdruecklich anlegen. Noetig ist es nicht - palette_setzen()
# legt sie ohnehin an -, aber ohne sie meldet jede Code-Pruefung "Name nicht
# gefunden", weil sie den Umweg ueber globals() nicht sehen kann.
GRUND = KARTE = FELD = LINIE = TEXT = GEDAEMPFT = BLASS = SCHIENE = ""
CLAUDE = BLAU = GRUEN = LILA = GELB = TUERKIS = ROT = ""


def palette_setzen(dunkel):
    globals().update(DUNKEL if dunkel else HELL)


palette_setzen(False)

SCHRIFT = "Segoe UI"       # das naechste, was Windows zu SF Pro hat

AGENT_FARBEN = [BLAU, LILA, GRUEN, GELB, TUERKIS, ROT]
WOERTER_NOTFALL = ["Calculating", "Computing", "Honking", "Wandering", "Pondering"]


def mischen(vorne, hinten, anteil):
    """Zwei Hexfarben mischen - tkinter kennt keine Transparenz."""
    anteil = max(0.0, min(1.0, anteil))
    v = [int(vorne[i:i + 2], 16) for i in (1, 3, 5)]
    h = [int(hinten[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join("%02x" % int(a + (b - a) * anteil) for a, b in zip(v, h))


class Karte(tk.Canvas):
    """Weisse Flaeche mit runden Ecken.

    tkinter kann an Frames keine runden Ecken - deshalb wird die Flaeche auf
    eine Leinwand gezeichnet und der eigentliche Inhalt als Fenster daraufgesetzt.
    Ohne das saehe es nach Windows 95 aus und nicht nach dem, was Karl wollte.
    """

    def __init__(self, eltern, radius=18, fuellung=None, grund=None, **kw):
        # ⚠️ Nicht als Vorgabewert in die Zeile oben schreiben: die wird EINMAL
        # beim Laden der Datei ausgewertet und bliebe beim Farbwechsel hell.
        fuellung = fuellung or KARTE
        grund = grund or GRUND
        super().__init__(eltern, bg=grund, highlightthickness=0, bd=0, **kw)
        self._radius = radius
        self._fuellung = fuellung
        self._form = None
        self.innen = tk.Frame(self, bg=fuellung)
        self._fenster = self.create_window(0, 0, anchor="nw", window=self.innen)
        self.bind("<Configure>", self._neu_zeichnen)

    def _neu_zeichnen(self, ereignis=None):
        b = self.winfo_width()
        h = self.winfo_height()
        if b < 4 or h < 4:
            return
        if self._form is not None:
            self.delete(self._form)
        self._form = self._runde_flaeche(1, 1, b - 1, h - 1, self._radius)
        self.tag_lower(self._form)
        self.coords(self._fenster, 0, 0)
        self.itemconfigure(self._fenster, width=b, height=h)

    def hoehe_an_inhalt(self, zusatz=0):
        """Die Karte so hoch machen, wie ihr Inhalt wirklich braucht.

        Eine feste Pixelhoehe geht schief, sobald die Schrift mitwaechst oder
        eine Kachel eine Zeile mehr hat als die anderen - genau daran war am
        01.09.2026 die Kontext-Kachel zweimal abgeschnitten.
        """
        self.update_idletasks()
        self.configure(height=self.innen.winfo_reqheight() + zusatz)

    def _runde_flaeche(self, x0, y0, x1, y1, r):
        punkte = [
            x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r,
            x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1,
            x0, y1, x0, y1 - r, x0, y0 + r, x0, y0,
        ]
        return self.create_polygon(punkte, smooth=True, splinesteps=24,
                                   fill=self._fuellung, outline=LINIE, width=1)


class Schalter(tk.Canvas):
    """Ein/Aus-Schieber wie am iPhone: Pille mit Knopf, der hinueberfaehrt."""

    def __init__(self, eltern, mass=1.0, an=True, beim_umlegen=None, grund=None):
        grund = grund or GRUND     # siehe Karte: kein Vorgabewert in der Zeile
        self._b, self._h = int(46 * mass), int(26 * mass)
        super().__init__(eltern, width=self._b, height=self._h, bg=grund,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.an = an
        self._beim_umlegen = beim_umlegen
        self._lage = 1.0 if an else 0.0     # 0 = links, 1 = rechts
        self._bahn = None
        self._knopf = None
        self.bind("<Button-1>", lambda e: self.umlegen())
        self._zeichnen()

    def umlegen(self):
        self.an = not self.an
        self._schieben()
        if self._beim_umlegen:
            self._beim_umlegen(self.an)

    def setzen(self, an):
        if an != self.an:
            self.an = an
            self._lage = 1.0 if an else 0.0
            self._zeichnen()

    def _schieben(self):
        ziel = 1.0 if self.an else 0.0
        schritt = 0.16 if ziel > self._lage else -0.16
        self._lage = max(0.0, min(1.0, self._lage + schritt))
        self._zeichnen()
        if abs(self._lage - ziel) > 0.01:
            self.after(16, self._schieben)
        else:
            self._lage = ziel
            self._zeichnen()

    def _zeichnen(self):
        self.delete("all")
        r = self._h / 2
        farbe = mischen(SCHIENE, BLAU, self._lage)   # aus = Schiene, an = blau
        # Pille aus zwei Halbkreisen und einem Rechteck - tkinter kann keine
        # runden Rechtecke von sich aus.
        self.create_oval(0, 0, self._h, self._h, fill=farbe, outline="")
        self.create_oval(self._b - self._h, 0, self._b, self._h, fill=farbe, outline="")
        self.create_rectangle(r, 0, self._b - r, self._h, fill=farbe, outline="")
        x = r + self._lage * (self._b - self._h)
        k = r - max(2, int(self._h * 0.09))
        self.create_oval(x - k, r - k, x + k, r + k, fill="#ffffff", outline="")


class Monitor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Claude Monitor")
        self.configure(bg=GRUND)
        # Bei 150 % Windows-Skalierung ist die Schrift anderthalbmal so gross -
        # also muss das Fenster es auch sein, sonst passt der Inhalt nicht hinein.
        self.mass = max(1.0, self.winfo_fpixels("1i") / 96.0)
        self.minsize(int(900 * self.mass), int(580 * self.mass))
        self._symbol_setzen()

        # Das Fenster bleibt oben, bis Karl es abschaltet.
        self.obenauf = True
        self.attributes("-topmost", True)

        self.woerter = self._woerter_laden()
        self._wort = random.choice(self.woerter)
        self._wort_alter = 0.0
        self._daten_alter = 0.0
        self._letztes_aufraeumen = 0.0
        self._t0 = time.time()
        self._vollbild = False

        self.klein = False
        self.dunkel = self._thema_lesen()
        palette_setzen(self.dunkel)
        self.configure(bg=GRUND)
        self._griff = (0, 0)
        self._zustand = ("aus", None)
        self._laufzeit_ab = None
        self._agenten = []
        self._verlauf = []
        self._last = {"cpu": 0.0, "ram": 0.0, "ram_mb": 0, "prozesse": 0}
        self._token = None
        self._cpu_lauf = deque([0.0] * 40, maxlen=40)
        self._ram_lauf = deque([0.0] * 40, maxlen=40)

        self._bauen()
        self._stelle_laden()
        self.bind("<F11>", lambda e: self._vollbild_wechseln())
        self.bind("<Escape>", lambda e: self._vollbild_aus())
        # Notbremse: holt das Fenster in die Bildschirmmitte zurueck, wenn es
        # irgendwo im Nirgendwo haengt (zweiter Bildschirm abgezogen o. ae.).
        self.bind("<Control-Home>", lambda e: self._mittig())
        self.protocol("WM_DELETE_WINDOW", self._schliessen)
        self._start_notieren()

        self._daten_holen()
        self._bild()

    def _symbol_setzen(self):
        """Der Stern als Fenster- und Taskleistensymbol.

        .ico ist der Weg, der unter Windows auch unten in der Taskleiste
        ankommt - iconphoto allein setzt oft nur das Symbol im Fenstertitel.
        """
        ico = HIER / "symbol.ico"
        if ico.is_file():
            try:
                self.iconbitmap(default=str(ico))
                return
            except tk.TclError:
                pass
        png = HIER / "symbol.png"
        if png.is_file():
            try:
                self._symbol_bild = tk.PhotoImage(file=str(png))
                self.iconphoto(True, self._symbol_bild)
            except tk.TclError:
                pass

    def _woerter_laden(self):
        """Dieselbe Liste wie die Presence, damit beide dasselbe sagen."""
        try:
            d = json.loads(KONFIG_DATEI.read_text(encoding="utf-8"))
            woerter = [str(w) for w in d.get("woerter", []) if str(w).strip()]
            if woerter:
                return woerter
        except (OSError, ValueError, json.JSONDecodeError):
            pass
        return WOERTER_NOTFALL

    # =============================================================== Aufbau
    def _bauen(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self._titelzeile()

        self._inhalt = tk.Frame(self, bg=GRUND)
        self._inhalt.grid(row=1, column=0, sticky="nsew", padx=26)
        self._inhalt.columnconfigure(0, weight=3, uniform="s")
        self._inhalt.columnconfigure(1, weight=2, uniform="s")
        self._inhalt.rowconfigure(0, weight=1)

        self._status_karte(self._inhalt)
        self._agenten_karte(self._inhalt)
        self._fussleiste()
        self._klein_bauen()

    def _titelzeile(self):
        self._titel = tk.Frame(self, bg=GRUND)
        self._titel.grid(row=0, column=0, sticky="ew", padx=26, pady=(22, 16))
        zeile = self._titel

        tk.Label(zeile, text="Übersicht", bg=GRUND, fg=TEXT,
                 font=(SCHRIFT, 24, "bold")).pack(side="left")

        self.oben_schalter = self._schalter_zeile(
            zeile, "Immer oben", True, self._obenauf_setzen, abstand=0)
        self.klein_schalter = self._schalter_zeile(
            zeile, "Klein in die Ecke", False, self._klein_setzen)
        self.dunkel_schalter = self._schalter_zeile(
            zeile, "Dunkel", self.dunkel, self._thema_setzen)

    def _schalter_zeile(self, zeile, text, an, rueckruf, abstand=26):
        """Beschriftung und Schieber - und die Beschriftung schaltet mit.

        ⚠️ Der Schieber allein ist 46 x 26 Pixel gross. Wer auf das Wort daneben
        tippt, trifft nichts, und fuer ihn "geht der Schalter nicht" - am
        01.09.2026 genau so passiert. Beides ist jetzt eine Schaltflaeche.
        """
        s = Schalter(zeile, mass=self.mass, an=an, beim_umlegen=rueckruf)
        s.pack(side="right", padx=(10, abstand))
        beschriftung = tk.Label(zeile, text=text, bg=GRUND, fg=GEDAEMPFT,
                                font=(SCHRIFT, 10), cursor="hand2")
        beschriftung.pack(side="right")
        beschriftung.bind("<Button-1>", lambda e: s.umlegen())
        return s

    def _ueberschrift(self, eltern, text):
        tk.Label(eltern, text=text, bg=KARTE, fg=GEDAEMPFT,
                 font=(SCHRIFT, 10), anchor="w").pack(fill="x", padx=26, pady=(22, 0))

    # --------------------------------------------------------- Claude-Status
    def _status_karte(self, eltern):
        karte = Karte(eltern)
        karte.grid(row=0, column=0, sticky="nsew", padx=(0, 9))
        k = karte.innen
        self._ueberschrift(k, "Status")

        oben = tk.Frame(k, bg=KARTE)
        oben.pack(fill="both", expand=True, padx=26, pady=(6, 26))

        # Laufzeit steht unten in der Karte, Ring und Text darueber als ein Block.
        feld = tk.Frame(oben, bg=FELD)
        feld.pack(fill="x", side="bottom")
        tk.Label(feld, text="Laufzeit", bg=FELD, fg=GEDAEMPFT,
                 font=(SCHRIFT, 9), anchor="w").pack(fill="x", padx=18, pady=(12, 0))
        self.laufzeit = tk.Label(feld, text="--:--:--", bg=FELD, fg=TEXT,
                                 font=("Consolas", 24), anchor="w")
        self.laufzeit.pack(fill="x", padx=18, pady=(0, 14))

        # Der Ring stand vorher allein in der Kartenmitte, waehrend der Text
        # oben rechts klebte. Beide gehoeren auf dieselbe Hoehe.
        reihe = tk.Frame(oben, bg=KARTE)
        reihe.pack(expand=True)

        seite = int(150 * self.mass)
        self.ring = tk.Canvas(reihe, width=seite, height=seite, bg=KARTE,
                              highlightthickness=0)
        self.ring.pack(side="left")
        self.ring.bind("<Double-Button-1>", lambda e: self._vollbild_wechseln())
        self._spur = self.ring.create_oval(0, 0, 0, 0, outline=LINIE, width=3)
        self._bogen = self.ring.create_arc(0, 0, 0, 0, start=0, extent=90,
                                           style=tk.ARC, outline=CLAUDE, width=3)
        self._strahlen = [self.ring.create_line(0, 0, 0, 0, fill=CLAUDE, width=5,
                                                capstyle="round") for _ in range(12)]

        rechts = tk.Frame(reihe, bg=KARTE)
        rechts.pack(side="left", padx=(24, 0))

        self.zustand_wort = tk.Label(rechts, text="aus", bg=KARTE, fg=BLASS,
                                     font=(SCHRIFT, 28, "bold"), anchor="w")
        self.zustand_wort.pack(anchor="w")

        self.zustand_satz = tk.Label(rechts, text="Claude Code ist nicht gestartet",
                                     bg=KARTE, fg=GEDAEMPFT, font=(SCHRIFT, 11),
                                     anchor="w")
        self.zustand_satz.pack(anchor="w", pady=(2, 0))

    # --------------------------------------------------------- Agenten
    def _agenten_karte(self, eltern):
        karte = Karte(eltern)
        karte.grid(row=0, column=1, sticky="nsew", padx=(9, 0))
        k = karte.innen

        kopf = tk.Frame(k, bg=KARTE)
        kopf.pack(fill="x", padx=26, pady=(22, 0))
        tk.Label(kopf, text="Agenten", bg=KARTE, fg=GEDAEMPFT,
                 font=(SCHRIFT, 10)).pack(side="left")
        self.agenten_zahl = tk.Label(kopf, text="", bg=KARTE, fg=BLASS,
                                     font=(SCHRIFT, 9))
        self.agenten_zahl.pack(side="right")

        self.agenten_liste = tk.Frame(k, bg=KARTE)
        self.agenten_liste.pack(fill="both", expand=True, padx=26, pady=(14, 26))
        self.agenten_zeilen = []

        self.agenten_leer = tk.Label(
            self.agenten_liste,
            text="Kein Agent unterwegs.\n\nAgenten entstehen pro Auftrag\nund heißen "
                 "wie der Auftrag.",
            bg=KARTE, fg=BLASS, font=(SCHRIFT, 10), justify="left")

    def _agent_zeile_bauen(self):
        z = tk.Frame(self.agenten_liste, bg=FELD)
        innen = tk.Frame(z, bg=FELD)
        innen.pack(fill="x", padx=14, pady=11)

        symbol = tk.Canvas(innen, width=30, height=30, bg=FELD, highlightthickness=0)
        symbol.pack(side="left")
        scheibe = symbol.create_oval(1, 1, 29, 29, fill=BLASS, outline="")
        glyphe = symbol.create_text(15, 15, text="›", fill="#ffffff",
                                    font=(SCHRIFT, 14, "bold"))

        mitte = tk.Frame(innen, bg=FELD)
        mitte.pack(side="left", fill="x", expand=True, padx=(12, 0))
        name = tk.Label(mitte, bg=FELD, fg=TEXT, font=(SCHRIFT, 10), anchor="w")
        name.pack(fill="x")
        stand = tk.Label(mitte, bg=FELD, fg=GEDAEMPFT, font=(SCHRIFT, 8), anchor="w")
        stand.pack(fill="x")

        rechts = tk.Frame(innen, bg=FELD)
        rechts.pack(side="right")
        zeit = tk.Label(rechts, bg=FELD, fg=TEXT, font=("Consolas", 10), anchor="e")
        zeit.pack()
        drei = tk.Canvas(rechts, width=30, height=8, bg=FELD, highlightthickness=0)
        drei.pack(pady=(2, 0))
        punkte = [drei.create_oval(3 + i * 9, 2, 9 + i * 9, 8, fill=BLASS, outline="")
                  for i in range(3)]

        return {"rahmen": z, "symbol": symbol, "scheibe": scheibe, "glyphe": glyphe,
                "name": name, "stand": stand, "zeit": zeit, "drei": drei,
                "punkte": punkte}

    # --------------------------------------------------------- Fussleiste
    def _fussleiste(self):
        # ⚠️ KEINE feste Hoehe mehr. Sie stand hier auf 104 Pixeln, spaeter auf
        # 112 mal Skalierung - beides geraten, und beide Male war die
        # Kontext-Kachel abgeschnitten: sie hat eine Zeile mehr als CPU und RAM
        # (Titel, Wert, Balken UND die Zeile mit der geschaetzten Grenze).
        # Jetzt misst die Karte ihren eigenen Inhalt aus.
        karte = Karte(self)
        self._fuss_karte = karte
        karte.grid(row=2, column=0, sticky="ew", padx=26, pady=(18, 22))
        karte.grid_propagate(False)
        innen = tk.Frame(karte.innen, bg=KARTE)
        innen.pack(fill="both", expand=True, padx=26, pady=18)
        self.after_idle(lambda: self._fuss_messen(karte, innen))
        for i in range(4):
            innen.columnconfigure(i, weight=1, uniform="f")

        self.kachel_cpu = self._kachel(innen, 0, "CPU", BLAU, kurve=True)
        self.kachel_ram = self._kachel(innen, 1, "Arbeitsspeicher", LILA, kurve=True)
        self.kachel_tok = self._kachel(innen, 2, "Token ausgegeben", TUERKIS)
        # ⚠️ KEIN Balken mehr. Hier stand einer gegen eine geschaetzte Grenze -
        # aber die wahre Obergrenze ist von aussen nirgends ablesbar, und ein
        # Balken ohne bekanntes Ende behauptet mehr, als er weiss.
        # Die Prozente aus Claude Code (Session 5 h / Weekly 7 d) sind es NICHT:
        # die stehen nur in den Antwortkoepfen des Servers und werden nirgends
        # mitgeschrieben. Am 01.09.2026 nachgesehen, sie sind nicht zu holen.
        self.kachel_ktx = self._kachel(innen, 3, "Kontext dieser Sitzung", CLAUDE)

    def _fuss_messen(self, karte, innen):
        """Fussleiste auf Inhaltshoehe bringen und festhalten, was dabei
        herauskam - sonst laesst sich von aussen nicht pruefen, ob es reicht."""
        karte.hoehe_an_inhalt()
        try:
            karte.update_idletasks()
            zeile = (time.strftime("%d.%m.%Y %H:%M:%S")
                     + "  Fussleiste: Inhalt braucht %d x %d px, Karte hat %d x %d px"
                     % (innen.winfo_reqwidth(), innen.winfo_reqheight(),
                        karte.winfo_width(), karte.winfo_height()))
            with (HIER / "fenster.log").open("a", encoding="utf-8") as f:
                f.write(zeile + "\n")
        except Exception:
            pass

    def _kachel(self, eltern, spalte, titel, farbe, kurve=False, balken=False):
        f = tk.Frame(eltern, bg=KARTE)
        f.grid(row=0, column=spalte, sticky="ew",
               padx=(0 if spalte == 0 else 22, 0))

        # ⚠️ width=1 ueberall. Ohne das fordert jede Kachel ihre natuerliche
        # Breite an - eine Leinwand allein bringt 238 Pixel mit -, und vier
        # Kacheln verlangten zusammen 1976 px in einem 1374 px breiten Fenster.
        # Die letzte (Kontext) fiel deshalb hinten heraus. Mit width=1 fordert
        # keine etwas an und alle teilen sich den Platz zu gleichen Teilen.
        tk.Label(f, text=titel, bg=KARTE, fg=GEDAEMPFT, font=(SCHRIFT, 8),
                 anchor="w", width=1).pack(fill="x")
        wert = tk.Label(f, text="--", bg=KARTE, fg=TEXT,
                        font=(SCHRIFT, 19), anchor="w", width=1)
        wert.pack(fill="x")

        kachel = {"wert": wert, "farbe": farbe, "linie": None, "balken": None}
        if kurve:
            c = tk.Canvas(f, height=20, width=1, bg=KARTE, highlightthickness=0)
            c.pack(fill="x")
            kachel["canvas"] = c
            kachel["linie"] = c.create_line(0, 0, 0, 0, fill=farbe, width=2,
                                            smooth=True)
        elif balken:
            c = tk.Canvas(f, height=20, width=1, bg=KARTE, highlightthickness=0)
            c.pack(fill="x")
            kachel["canvas"] = c
            kachel["spur"] = c.create_rectangle(0, 7, 0, 12, fill=LINIE, outline="")
            kachel["balken"] = c.create_rectangle(0, 7, 0, 12, fill=farbe, outline="")
            kachel["klein"] = tk.Label(f, text="", bg=KARTE, fg=BLASS,
                                       font=(SCHRIFT, 7), anchor="w", width=1)
            kachel["klein"].pack(fill="x")
        else:
            kachel["klein"] = tk.Label(f, text="", bg=KARTE, fg=BLASS,
                                       font=(SCHRIFT, 7), anchor="w", width=1)
            kachel["klein"].pack(fill="x")
        return kachel

    # --------------------------------------------------------- Hell / Dunkel
    def _thema_lesen(self):
        try:
            d = json.loads(STELLE_DATEI.read_text(encoding="utf-8"))
            return bool(d.get("dunkel", False))
        except (OSError, ValueError, json.JSONDecodeError):
            return False

    def _thema_setzen(self, dunkel):
        """Farben tauschen und die Oberflaeche einmal neu bauen.

        Neu bauen statt umfaerben: jedes Fensterchen traegt seine Farben von
        der Erzeugung her, und es sind ueber hundert. Ein Neuaufbau kann nichts
        vergessen, ein Umfaerben schon - und er dauert einen Wimpernschlag.
        """
        self.dunkel = dunkel
        palette_setzen(dunkel)
        war_klein = self.klein
        # 🔴 Die gemerkte grosse Stelle MUSS ueber den Neuaufbau gerettet werden.
        # Sonst greift _klein_schalten(True) weiter unten die Groesse ab, die das
        # Fenster mitten im Umbau gerade hat - und das war die Mindestgroesse.
        gemerkt = getattr(self, "_gross_stelle", None)

        if war_klein:                 # erst zurueck in die grosse Ansicht
            self._klein_schalten(False)
        self.klein = False

        for kind in list(self.winfo_children()):
            kind.destroy()
        self.configure(bg=GRUND)
        self.agenten_zeilen = []
        self.k_zeilen = []
        self._bauen()
        self.oben_schalter.setzen(self.obenauf)
        if war_klein:
            self._klein_schalten(True)
            if gemerkt:
                self._gross_stelle = gemerkt
        self._stelle_sichern()

    # --------------------------------------------------------- Kleine Ansicht
    def _klein_bauen(self):
        """Die Eckansicht: nur Zustand und Agenten, ohne Rahmen.

        Wie die allererste Fassung vom Vormittag - nur dass sie jetzt auch
        weiss, ob Claude arbeitet, und nicht nur, ob er laeuft.
        """
        self.klein_rahmen = tk.Frame(self, bg=KARTE, highlightbackground=LINIE,
                                     highlightthickness=1)
        innen = tk.Frame(self.klein_rahmen, bg=KARTE)
        innen.pack(fill="both", expand=True, padx=14, pady=12)

        kopf = tk.Frame(innen, bg=KARTE)
        kopf.pack(fill="x")

        self.k_punkt = tk.Canvas(kopf, width=12, height=12, bg=KARTE,
                                 highlightthickness=0)
        self.k_punkt.pack(side="left", pady=(4, 0))
        self._k_punkt_id = self.k_punkt.create_oval(1, 1, 11, 11, fill=BLASS,
                                                    outline="")
        self.k_wort = tk.Label(kopf, text="aus", bg=KARTE, fg=TEXT,
                               font=(SCHRIFT, 11, "bold"), anchor="w")
        self.k_wort.pack(side="left", padx=(8, 0))

        self.k_gross = tk.Label(kopf, text="⤢", bg=KARTE, fg=BLASS,
                                font=(SCHRIFT, 11), cursor="hand2")
        self.k_gross.pack(side="right")
        self.k_gross.bind("<Button-1>", lambda e: self._klein_schalten(False))

        self.k_zeit = tk.Label(kopf, text="", bg=KARTE, fg=GEDAEMPFT,
                               font=("Consolas", 9))
        self.k_zeit.pack(side="right", padx=(0, 10))

        self.k_agenten = tk.Label(innen, text="keine Agenten", bg=KARTE,
                                  fg=GEDAEMPFT, font=(SCHRIFT, 9), anchor="w")
        self.k_agenten.pack(fill="x", pady=(8, 0))

        self.k_liste = tk.Frame(innen, bg=KARTE)
        self.k_liste.pack(fill="x")
        self.k_zeilen = []

        # Verschieben mit der Maus - ohne Titelleiste geht es sonst nicht.
        for teil in (self.klein_rahmen, innen, kopf, self.k_wort, self.k_agenten):
            teil.bind("<Button-1>", self._klein_anfassen)
            teil.bind("<B1-Motion>", self._klein_ziehen)
            teil.bind("<Double-Button-1>", lambda e: self._klein_schalten(False))

    def _klein_anfassen(self, e):
        self._griff = (e.x_root - self.winfo_x(), e.y_root - self.winfo_y())

    def _klein_ziehen(self, e):
        if not self.klein:
            return
        self.geometry("+%d+%d" % (e.x_root - self._griff[0],
                                  e.y_root - self._griff[1]))

    def _klein_setzen(self, an):
        self._klein_schalten(an, vom_schalter=True)

    def _klein_schalten(self, an, vom_schalter=False):
        if an == self.klein:
            return
        self.klein = an
        if not vom_schalter:
            self.klein_schalter.setzen(an)

        if an:
            self._gross_stelle = self.geometry()
            self._titel.grid_remove()
            self._inhalt.grid_remove()
            self._fuss_karte.grid_remove()
            self.klein_rahmen.grid(row=0, column=0, sticky="nsew")
            self.rowconfigure(0, weight=1)
            self.rowconfigure(1, weight=0)
            self.minsize(1, 1)
            self.overrideredirect(True)
            self.attributes("-topmost", True)
            self._klein_platzieren()
        else:
            self.overrideredirect(False)
            self.klein_rahmen.grid_remove()
            self.rowconfigure(0, weight=0)
            self.rowconfigure(1, weight=1)
            self.minsize(int(900 * self.mass), int(580 * self.mass))
            self._titel.grid()
            self._inhalt.grid()
            self._fuss_karte.grid()
            stelle = getattr(self, "_gross_stelle", None)
            if stelle:
                self.geometry(stelle)
                # ⚠️ Zweites Mal, nachdem die Titelleiste wieder da ist:
                # Windows rueckt das Fenster beim Zurueckholen des Rahmens
                # sonst um die Hoehe der Leiste nach unten. Ohne den zweiten
                # Aufruf wandert es bei jedem Umschalten ein Stueck weiter.
                # 🔴 Aber NUR, wenn dann noch die grosse Ansicht steht: beim
                # Farbwechsel im Kleinformat feuerte dieser Nachschlag hinterher
                # und hat die Eckposition mit der grossen ueberschrieben.
                self.after(80, lambda: self._stelle_nachziehen(stelle))
            self.attributes("-topmost", self.obenauf)
            self.after(60, self.lift)

    def _stelle_nachziehen(self, stelle):
        if not self.klein:
            self.geometry(stelle)

    def _klein_masse(self):
        b = int(250 * self.mass)
        h = int((66 + 20 * min(3, len(self._agenten))) * self.mass)
        return b, h

    def _klein_platzieren(self):
        """Unten rechts, ueber der Uhr - und hoch genug fuer die Agenten."""
        b, h = self._klein_masse()
        self._klein_zahl = len(self._agenten)
        x = self.winfo_screenwidth() - b - int(24 * self.mass)
        y = self.winfo_screenheight() - h - int(80 * self.mass)
        self.geometry("%dx%d+%d+%d" % (b, h, x, y))

    def _klein_hoehe_anpassen(self):
        """Nur die Hoehe nachziehen - die Stelle bleibt, wo Karl sie hingezogen hat."""
        if not self.klein:
            return
        b, h = self._klein_masse()
        self.geometry("%dx%d+%d+%d" % (b, h, self.winfo_x(), self.winfo_y()))

    def _klein_zeichnen(self, name, t, jetzt):
        # Kommt ein Agent dazu oder faellt einer weg, muss die Ecke mitwachsen -
        # sonst steht die Zeile ausserhalb des Fensters und ist unsichtbar.
        if getattr(self, "_klein_zahl", None) != len(self._agenten):
            self._klein_zahl = len(self._agenten)
            self._klein_hoehe_anpassen()

        farbe = {"aus": BLASS, "laeuft": BLAU, "arbeitet": GRUEN}[name]
        self.k_punkt.itemconfigure(self._k_punkt_id, fill=farbe)
        if name == "arbeitet":
            self.k_wort.configure(text=self._wort + "...", fg=TEXT)
        elif name == "laeuft":
            self.k_wort.configure(text="Bereit", fg=TEXT)
        else:
            self.k_wort.configure(text="Aus", fg=BLASS)
        self.k_zeit.configure(
            text=agenten.dauer_text(jetzt - self._laufzeit_ab) if self._laufzeit_ab else "")

        laufend = self._agenten
        if not laufend:
            self.k_agenten.configure(text="keine Agenten", fg=BLASS)
        elif len(laufend) == 1:
            self.k_agenten.configure(text="1 Agent arbeitet", fg=GRUEN)
        else:
            self.k_agenten.configure(text="%d Agenten arbeiten" % len(laufend),
                                     fg=GRUEN)

        while len(self.k_zeilen) < min(3, len(laufend)):
            z = tk.Frame(self.k_liste, bg=KARTE)
            n = tk.Label(z, bg=KARTE, fg=TEXT, font=(SCHRIFT, 8), anchor="w")
            n.pack(side="left")
            d = tk.Label(z, bg=KARTE, fg=GEDAEMPFT, font=("Consolas", 8))
            d.pack(side="right")
            self.k_zeilen.append((z, n, d))

        for i, (z, n, d) in enumerate(self.k_zeilen):
            if i < min(3, len(laufend)):
                a = laufend[i]
                text = a["beschreibung"]
                if len(text) > 22:
                    text = text[:21] + "…"
                n.configure(text="· " + text)
                d.configure(text=agenten.dauer_text(a["laeuft_seit"]))
                z.pack(fill="x", pady=(2, 0))
            else:
                z.pack_forget()

    # =============================================================== Fenster
    def _obenauf_setzen(self, an):
        self.obenauf = an
        self.attributes("-topmost", an)

    def _mittig(self):
        """Fenster auf eine sichere Groesse und in die Bildschirmmitte."""
        b = min(int(1100 * self.mass), self.winfo_screenwidth() - 80)
        h = min(int(700 * self.mass), self.winfo_screenheight() - 120)
        x = max(0, (self.winfo_screenwidth() - b) // 2)
        y = max(0, (self.winfo_screenheight() - h) // 2)
        self.geometry("%dx%d+%d+%d" % (b, h, x, y))
        self.lift()

    def _start_notieren(self):
        """Beim Start festhalten, wo und wie gross das Fenster steht.

        Ohne das laesst sich von aussen nicht klaeren, ob das Fenster wirklich
        falsch sitzt oder nur falsch gemessen wurde - am 01.09.2026 genau die
        Frage, an der eine halbe Stunde verlorenging.
        """
        try:
            self.update_idletasks()
            zeile = (time.strftime("%d.%m.%Y %H:%M:%S")
                     + "  Start: %dx%d an %d,%d | Bildschirm %dx%d | Mass %.2f"
                     % (self.winfo_width(), self.winfo_height(),
                        self.winfo_x(), self.winfo_y(),
                        self.winfo_screenwidth(), self.winfo_screenheight(),
                        self.mass))
            with (HIER / "fenster.log").open("a", encoding="utf-8") as f:
                f.write(zeile + "\n")
        except Exception:
            pass

    def _vollbild_wechseln(self):
        self._vollbild = not self._vollbild
        self.attributes("-fullscreen", self._vollbild)

    def _vollbild_aus(self):
        if self._vollbild:
            self._vollbild = False
            self.attributes("-fullscreen", False)

    def _schliessen(self):
        self._stelle_sichern()
        self.destroy()

    def _stelle_laden(self):
        self.update_idletasks()
        try:
            d = json.loads(STELLE_DATEI.read_text(encoding="utf-8"))
            b, h = int(d.get("breite", 1100)), int(d.get("hoehe", 700))
            x, y = int(d["x"]), int(d["y"])
            self.obenauf = bool(d.get("obenauf", True))
            self.attributes("-topmost", self.obenauf)
            self.oben_schalter.setzen(self.obenauf)
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            b, h = int(1100 * self.mass), int(700 * self.mass)
            b = min(b, self.winfo_screenwidth() - 80)
            h = min(h, self.winfo_screenheight() - 120)
            x = max(0, (self.winfo_screenwidth() - b) // 2)
            y = max(0, (self.winfo_screenheight() - h) // 2)
        # Eine gemerkte Stelle auf einem abgezogenen zweiten Bildschirm waere
        # sonst unerreichbar.
        x = max(0, min(x, self.winfo_screenwidth() - 200))
        y = max(0, min(y, self.winfo_screenheight() - 120))
        self.geometry("%dx%d+%d+%d" % (b, h, x, y))

    def _stelle_sichern(self):
        try:
            # Weder das Vollbild noch die Eckansicht duerfen als Fenstergroesse
            # gemerkt werden - sonst startet das Fenster naechstes Mal winzig.
            if self._vollbild or self.klein:
                return
            STELLE_DATEI.write_text(json.dumps({
                "x": self.winfo_x(), "y": self.winfo_y(),
                "breite": self.winfo_width(), "hoehe": self.winfo_height(),
                "obenauf": self.obenauf, "dunkel": self.dunkel,
            }), encoding="utf-8")
        except OSError:
            pass

    # =============================================================== Daten
    def _daten_holen(self):
        seit = agenten.claude_laeuft()
        if seit is None:
            self._zustand = ("aus", None)
        else:
            arbeit = agenten.claude_arbeitet()
            self._zustand = ("arbeitet", arbeit) if arbeit else ("laeuft", seit)
        self._laufzeit_ab = seit
        self._agenten = agenten.laufende_agenten()
        self._verlauf = agenten.verlauf(hoechstens=5)
        self._last = agenten.system_last()
        self._cpu_lauf.append(self._last["cpu"])
        self._ram_lauf.append(self._last["ram"])
        self._token = agenten.token_stand()
        self._daten_alter = time.time()

    # =============================================================== Bild
    def _bild(self):
        jetzt = time.time()
        if jetzt - self._daten_alter >= DATEN_TAKT:
            self._daten_holen()
        if jetzt - self._letztes_aufraeumen > AUFRAEUM_TAKT:
            agenten.aufraeumen()
            self._letztes_aufraeumen = jetzt

        name, _ = self._zustand
        t = jetzt - self._t0
        bewegt = (name == "arbeitet") or bool(self._agenten)

        if name == "arbeitet" and jetzt - self._wort_alter >= WORT_TAKT:
            neu = self._wort
            while neu == self._wort and len(self.woerter) > 1:
                neu = random.choice(self.woerter)
            self._wort, self._wort_alter = neu, jetzt

        if self.klein:
            self._klein_zeichnen(name, t, jetzt)
        else:
            self._ring_zeichnen(name, t)
            self._status_texte(name, jetzt)
            self._agenten_zeichnen(t)
            self._kacheln_fuellen()

        self.after(BILD_MS if bewegt else RUHE_MS, self._bild)

    def _ring_zeichnen(self, name, t):
        # Aus der tatsaechlichen Leinwandgroesse rechnen, nicht aus festen
        # Zahlen - sonst sitzt der Ring bei anderer Skalierung schief.
        seite = max(40, self.ring.winfo_width())
        m = seite / 2
        r = seite * 0.41
        lebt = name == "arbeitet"
        farbe = CLAUDE if name != "aus" else BLASS

        self.ring.coords(self._spur, m - r, m - r, m + r, m + r)
        self.ring.coords(self._bogen, m - r, m - r, m + r, m + r)
        if lebt:
            # Ein ruhig umlaufender Bogen statt eines Gluehens - auf hellem
            # Grund wirkt Leuchten schmutzig, eine Bewegung nicht.
            self.ring.itemconfigure(self._bogen, state="normal", outline=CLAUDE,
                                    start=(-t * 110) % 360,
                                    extent=70 + 40 * math.sin(t * 1.3))
        else:
            self.ring.itemconfigure(self._bogen, state="hidden")

        dreh = t * 0.30 if lebt else 0.0
        for i, id_ in enumerate(self._strahlen):
            w = dreh + i * (math.pi * 2 / len(self._strahlen))
            innen = seite * 0.045
            aussen = seite * 0.20 + (seite * 0.027 * math.sin(t * 2.6 + i * 0.7)
                                     if lebt else 0)
            self.ring.coords(id_,
                             m + math.cos(w) * innen, m + math.sin(w) * innen,
                             m + math.cos(w) * aussen, m + math.sin(w) * aussen)
            self.ring.itemconfigure(
                id_, fill=farbe if name != "aus" else mischen(BLASS, KARTE, 0.4))

    def _status_texte(self, name, jetzt):
        if name == "arbeitet":
            self.zustand_wort.configure(text=self._wort + "...", fg=TEXT)
            self.zustand_satz.configure(text="Claude arbeitet gerade an einer Antwort",
                                        fg=GEDAEMPFT)
        elif name == "laeuft":
            self.zustand_wort.configure(text="Bereit", fg=TEXT)
            self.zustand_satz.configure(text="Claude läuft und wartet auf dich",
                                        fg=GEDAEMPFT)
        else:
            self.zustand_wort.configure(text="Aus", fg=BLASS)
            self.zustand_satz.configure(text="Claude Code ist nicht gestartet",
                                        fg=BLASS)

        if self._laufzeit_ab:
            lauf = int(jetzt - self._laufzeit_ab)
            self.laufzeit.configure(
                text="%02d:%02d:%02d" % (lauf // 3600, (lauf // 60) % 60, lauf % 60),
                fg=TEXT)
        else:
            self.laufzeit.configure(text="--:--:--", fg=BLASS)

    def _agenten_zeichnen(self, t):
        laufend = self._agenten
        alle = ([("laeuft", a) for a in laufend]
                + [("fertig", e) for e in self._verlauf])[:6]

        if laufend:
            self.agenten_zahl.configure(
                text=("1 läuft" if len(laufend) == 1 else "%d laufen" % len(laufend)),
                fg=GRUEN)
        else:
            self.agenten_zahl.configure(text="keiner läuft", fg=BLASS)

        if not alle:
            self.agenten_leer.pack(anchor="nw")
        else:
            self.agenten_leer.pack_forget()

        while len(self.agenten_zeilen) < len(alle):
            self.agenten_zeilen.append(self._agent_zeile_bauen())

        for i, z in enumerate(self.agenten_zeilen):
            if i >= len(alle):
                z["rahmen"].pack_forget()
                continue
            art, d = alle[i]
            farbe = AGENT_FARBEN[i % len(AGENT_FARBEN)] if art == "laeuft" else BLASS

            text = d["beschreibung"]
            if len(text) > 24:
                text = text[:23] + "…"
            z["name"].configure(text=text, fg=TEXT if art == "laeuft" else GEDAEMPFT)
            z["symbol"].itemconfigure(z["scheibe"], fill=farbe)

            if art == "laeuft":
                z["stand"].configure(text="Läuft", fg=GRUEN)
                z["zeit"].configure(text=agenten.dauer_text(d["laeuft_seit"]), fg=TEXT)
                for k, p in enumerate(z["punkte"]):
                    hell = (math.sin(t * 4 - k * 0.9) + 1) / 2
                    z["drei"].itemconfigure(p, fill=mischen(farbe, FELD, 1 - hell))
            else:
                z["stand"].configure(text="Fertig", fg=BLASS)
                z["zeit"].configure(text=agenten.dauer_text(d["gelaufen"]), fg=GEDAEMPFT)
                for p in z["punkte"]:
                    z["drei"].itemconfigure(p, fill=LINIE)

            z["rahmen"].pack(fill="x", pady=(0 if i == 0 else 8, 0))

    def _kacheln_fuellen(self):
        self.kachel_cpu["wert"].configure(text="%.0f %%" % self._last["cpu"])
        self._sparklinie(self.kachel_cpu, self._cpu_lauf, 100.0)

        self.kachel_ram["wert"].configure(text="%.0f %%" % self._last["ram"])
        self._sparklinie(self.kachel_ram, self._ram_lauf, 100.0)

        if self._token:
            self.kachel_tok["wert"].configure(text=agenten.kurz_zahl(self._token["aus"]))
            self.kachel_tok["klein"].configure(
                text="%d Prozesse · %d MB" % (self._last["prozesse"],
                                              self._last["ram_mb"]))

            kontext = self._token["kontext"]
            self.kachel_ktx["wert"].configure(text=agenten.kurz_zahl(kontext))
            self.kachel_ktx["klein"].configure(
                text="Spitze " + agenten.kurz_zahl(self._token["spitze"]))
        else:
            self.kachel_tok["wert"].configure(text="--")
            self.kachel_tok["klein"].configure(text="kein Protokoll gefunden")
            self.kachel_ktx["wert"].configure(text="--")

    def _sparklinie(self, kachel, werte, hoechstens):
        c = kachel["canvas"]
        b = max(2, c.winfo_width())
        h = max(2, c.winfo_height())
        n = len(werte)
        punkte = []
        for i, w in enumerate(werte):
            x = i / max(1, n - 1) * b
            y = h - 2 - (min(w, hoechstens) / hoechstens) * (h - 4)
            punkte.extend((x, y))
        c.coords(kachel["linie"], *punkte)


TITEL = "Claude Monitor"


def _notiz(text):
    """Eine Zeile ins fenster.log - dieselbe Datei wie die Startmeldung."""
    try:
        with (HIER / "fenster.log").open("a", encoding="utf-8") as f:
            f.write(time.strftime("%d.%m.%Y %H:%M:%S") + "  " + text + "\n")
    except Exception:
        pass


def schon_am_laufen():
    """Zweites Fenster waere kein Gewinn - es zeigt dasselbe, doppelt gerechnet."""
    ich = os.getpid()
    for pr in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if pr.info["pid"] == ich or not pr.info["cmdline"]:
                continue
            if "python" not in (pr.info["name"] or "").lower():
                continue
            if any("fenster.py" in str(teil) for teil in pr.info["cmdline"]):
                return pr.info["pid"]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


def nach_vorn_holen():
    """
    ⚠️ Wichtiger Teil des Schutzes, nicht Zierde.

    Ein zweiter Start, der nur still aussteigt, sieht aus wie ein kaputter
    Doppelklick - das vorhandene Fenster steht ja vielleicht klein in der Ecke
    oder hinter allem anderen. Also wird es hervorgeholt, statt nichts zu tun.
    """
    try:
        hwnd = ctypes.windll.user32.FindWindowW(None, TITEL)
        if not hwnd:
            return False
        if ctypes.windll.user32.IsIconic(hwnd):
            ctypes.windll.user32.ShowWindow(hwnd, 9)   # SW_RESTORE
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


if __name__ == "__main__":
    anderer = schon_am_laufen()
    if anderer:
        geholt = nach_vorn_holen()
        _notiz("Laeuft schon (PID %d) - dieser Start macht Schluss%s."
               % (anderer, ", Fenster nach vorn geholt" if geholt
                  else " (Fenster nicht gefunden)"))
        sys.exit(0)

    fenster = Monitor()
    # "python fenster.py --klein" faengt gleich in der Ecke an.
    if "--klein" in sys.argv:
        fenster.after(400, lambda: fenster._klein_schalten(True))
    fenster.mainloop()
