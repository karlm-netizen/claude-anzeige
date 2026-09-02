# Claude-Anzeige

Zwei Anzeigen aus derselben Quelle: **läuft Claude, arbeitet er gerade, und wie viele Agenten
sind dabei?**

| | was |
|---|---|
| `presence.py` | Discord Rich Presence — steht auf dem Profil |
| `fenster.py` | Fenster am PC, animiert, immer obenauf |
| `agenten.py` | die gemeinsame Erkennung. Direkt aufrufbar: `python agenten.py` |

```
Discord                        Fenster am PC
┌────────────────────────┐     ┌────────────────────────────┐
│  Karl                  │     │  ● Honking...      0:12    │
│  Spielt Claudee        │     │  ▓▓▓▓░░░░░░░░░░░░░░░░░░    │
│  Honking...            │     │                            │
│  2 Agenten arbeiten    │     │  2 Agenten arbeiten        │
│  seit 01:23            │     │    ◐ Fund-Sucher   10:31   │
└────────────────────────┘     │    ◐ Landkarte      0:42   │
                               └────────────────────────────┘
```

## Drei Zustände, nicht zwei

| | wann |
|---|---|
| **aus** | kein `claude.exe` |
| **wartet** | läuft, wartet aber auf die nächste Nachricht — nichts bewegt sich |
| **arbeitet** | denkt gerade an einer Antwort — Punkt atmet, Balken läuft, Wort wechselt |

## Einrichtung (einmalig, ist erledigt)

Die Anwendung heißt **`Claudeee (larp has no Limits)`**, ID `1544350360695480330`,
eingetragen in `konfig.json`. Das Bild heißt `claude`.

🔴 **Warum nicht „Claude": Discord lässt den Namen nicht zu.** Der Markenfilter blockt bekannte
Produktnamen — die Meldung lautet nur *„Der Anwendungsname ist ungültig"* und sagt nicht, warum.
Dasselbe passiert bei Spotify oder Minecraft. **Der Anwendungsname ist der Text auf dem Profil**,
also steht dort, was in der App steht — ändern geht nur im Portal, nicht im Code.

ℹ️ Ein frisch hochgeladenes Bild braucht ein paar Minuten, bis Discord es ausliefert.
Ob es überhaupt angekommen ist, verrät die App öffentlich:
`https://discord.com/api/v10/oauth2/applications/<ID>/assets`

ℹ️ Das Portal ist auf Deutsch: der Knopf heißt **„App erstellen"**, nicht „New Application".
Die ID steht danach unter **Allgemeine Informationen**.

ℹ️ **Discord schreibt „Spielt" davor**, bei jeder Rich Presence. Änderbar ist nur die Art
(`aktivitaets_art`), nicht das Weglassen.

## 🔴 Die 15-Sekunden-Grenze

**Discord nimmt höchstens alle 15 Sekunden eine Änderung an.** Das Wort kann dort also nicht im
Sekundentakt wechseln wie im Terminal. `takt_sekunden` unter 15 wird deshalb ignoriert.

Im **Fenster** gilt das nicht — dort wechselt es alle 3 Sekunden (`WORT_TAKT` in `fenster.py`).

## Wie die Agenten erkannt werden

🔴 **Ein Agent hat keinen eigenen Prozess.** Er arbeitet innerhalb der Claude-Sitzung.
Nachgemessen am 01.09.2026: während ein Agent zehn Minuten lief, waren es unverändert zwei
`claude.exe`. Auch die Dateien im `tasks`-Ordner taugen nicht — die des fertig gewordenen
Agenten war **0 Bytes** groß.

**Deshalb meldet Claude Code selbst.** In `ki-os-2/.claude/settings.json` hängen fünf Hooks, alle
auf `ki-os-2/werkzeuge/agent-merker.ps1`:

| Hook | wann | was |
|---|---|---|
| `PreToolUse` (Agent\|Task) | ein Agent startet | Merkdatei anlegen |
| `SubagentStop` | ein Agent ist fertig | ältesten Merker wegräumen |
| `UserPromptSubmit` | Nachricht abgeschickt | „arbeitet" an |
| `Stop` | Antwort fertig | „arbeitet" aus |
| `SessionEnd` | Sitzung zu | alles dieser Sitzung weg |

Die Merker liegen in `%LOCALAPPDATA%\ki-os-agenten` — **bewusst nicht im Vault**, sie ändern
sich im Sekundentakt und hätten in OneDrive und git nichts zu suchen.

⚠️ **Warum die Hooks NICHT an jedem Werkzeugaufruf hängen:** ein Hook-Aufruf kostet gemessen
rund **200 ms**. Bei 50 Werkzeugaufrufen je Antwort wären das zehn Sekunden Wartezeit. So sind
es zwei Aufrufe je Nachricht, und beide laufen `async`.

⚠️ **Zwei bekannte Ungenauigkeiten, beide bewusst:**
- `SubagentStop` sagt nicht, **welcher** Agent fertig ist. Es geht der älteste weg. Laufen zwei
  gleichzeitig und der jüngere ist zuerst fertig, steht kurz der falsche Name da — **die Anzahl
  stimmt immer**, und darum geht es bei der Anzeige.
- Stürzt eine Sitzung ab, bleibt ihr Merker liegen. Deshalb zählt nichts mit, was **älter als
  drei Stunden** ist, und das Fenster räumt alle fünf Minuten auf.

## Das Fenster

Heller Apple-Look, richtiges Fenster mit Titelleiste. Drei Schieber oben rechts:

| Schieber | was er tut |
|---|---|
| **Dunkel** | tauscht die Palette. Beim Umschalten wird die Oberfläche einmal neu gebaut — sicherer, als über hundert Fensterchen nachträglich umzufärben. |
| **Klein in die Ecke** | schrumpft auf ein rahmenloses Kästchen unten rechts, nur Zustand und Agenten. Verschiebbar; **⤢** oder Doppelklick holt es zurück — **genau an die Stelle, wo es vorher war.** |
| **Immer oben** | hält das Fenster über allen anderen. |

- **F11** Vollbild · **Esc** zurück · **Doppelklick auf den Ring** ebenfalls
- **Strg+Home** holt das Fenster in die Bildschirmmitte, falls es irgendwo hängt
- `python fenster.py --klein` fängt gleich in der Ecke an
- Stelle, Größe, Farbwahl und „immer oben" werden gemerkt (`fenster-stelle.json`).
  ⚠️ Vollbild und Eckansicht werden **nicht** gemerkt — sonst startet es winzig.
- Solange nichts arbeitet, zeichnet es nur zweimal je Sekunde statt 25-mal.
- **`fenster.log`** hält bei jedem Start fest, wo und wie groß das Fenster steht und ob die
  Kachelleiste ihren Inhalt fasst.

### ⚠️ Drei Fallen, alle schon zugeschnappt

**Feste Pixelzahlen neben mitwachsender Schrift.** Karls Bildschirm läuft mit **125 %**.
Die Kachelleiste hatte eine feste Höhe von 104 px und war unten abgeschnitten. Alles in
Pixeln wird mit `self.mass` multipliziert — oder besser aus dem Inhalt gemessen
(`Karte.hoehe_an_inhalt`).

**Angeforderte Breite.** Eine `tk.Canvas` bringt von sich aus **238 px** Breitenwunsch mit.
Vier Kacheln verlangten zusammen **1976 px** in einem 1374 px breiten Fenster — die letzte
(Kontext) fiel hinten heraus. Deshalb steht überall `width=1`: dann fordert keine etwas an
und alle teilen sich den Platz. Danach waren es 184 px.

**Verzögerte Befehle, die zu spät ankommen.** Beim Zurückschalten auf groß wird die Position
80 ms später noch einmal gesetzt (Windows verrückt das Fenster beim Zurückholen der
Titelleiste). Beim Farbwechsel *im Kleinformat* feuerte dieser Nachschlag hinterher und
überschrieb die Eckposition. `_stelle_nachziehen` prüft deshalb, ob überhaupt noch die
große Ansicht steht. **Gefunden hat das kein Blick, sondern ein Prüfskript**, das den Weg
hin und zurück fährt und die Zahlen vergleicht (`pruefungen/hell-und-dunkel.py`).

## 🔴 Was die Kachel „Kontext" NICHT ist

Sie zeigt, **wie viel Text in dieser einen Sitzung im Kopf ist** — gelesen aus dem
Sitzungsprotokoll, echte Zahlen, im Sekundentakt aktuell.

**Sie ist nicht der Verbrauch.** Die Prozente, die Claude Code selbst anzeigt
(*Session 5 h · Weekly 7 d · resets in …*), stehen **nirgends auf der Platte** — sie kommen
aus den Antwortköpfen des Servers und werden nicht mitgeschrieben. Am 01.09.2026 danach
gesucht: die einzigen Treffer im Protokoll waren die Suchbefehle selbst.

⚠️ Deshalb hat die Kachel **keinen Balken mehr.** Vorher lief einer gegen eine geschätzte
Obergrenze — und ein Balken ohne bekanntes Ende behauptet mehr, als er weiß.

## konfig.json

| Feld | Bedeutung |
|---|---|
| `anwendungs_id` | Die Zahl aus dem Developer Portal. **Ohne sie läuft die Presence nicht.** |
| `prozess` | Worauf geschaut wird. `claude.exe` — so heißt Claude Code auf diesem PC. |
| `aktivitaets_art` | `PLAYING` · `WATCHING` · `LISTENING` · `COMPETING` |
| `agenten_zeigen` | `true` = die Agentenzahl steht in der zweiten Zeile |
| `wartet_text` | Was dasteht, wenn Claude läuft, aber nicht arbeitet |
| `woerter` | Die 40 Wörter. Hier änderbar — Fenster und Presence nehmen dieselbe Liste. |
| `bild_schluessel` | Name eines Bildes aus **Rich Presence → Art Assets** im Portal |
| `takt_sekunden` | **Mindestens 15**, siehe oben |

## Nachsehen, ob etwas läuft

```
python agenten.py
```

Sagt in vier Zeilen, was beide Anzeigen sehen. Dazu für die Presence:

```
type presence.log
```

## Voraussetzungen

- **Discord als Desktop-App** (im Browser gibt es kein Rich Presence)
- **Python 3.12** unter `%LOCALAPPDATA%\Programs\Python\Python312`
- `pypresence` und `psutil` (installiert)

## Mit dem PC starten

✅ **Eingerichtet am 02.09.2026** (Karls Ansage). Im Autostart-Ordner
`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup` liegen jetzt zwei
Verknüpfungen neben der für Obsidian und die IDE:

| Verknüpfung | ruft auf |
|---|---|
| `Claude-Anzeige Fenster.lnk` | `wscript.exe "…\Fenster starten.vbs"` |
| `Claude-Anzeige Presence.lnk` | `wscript.exe "…\Presence starten.vbs"` |

ℹ️ **Die Reihenfolge zu Discord ist egal.** Discord startet auf diesem PC selbst mit
(`--start-inactive`) und braucht ein paar Sekunden — `presence.py` fängt den Fehler ab und
probiert es alle 15 Sekunden wieder. Im Log steht dann einmal *„Keine Verbindung zu Discord"*
und danach *„Mit Discord verbunden."*

🔴 **Warum das überhaupt nötig war:** am Morgen des 02.09. lief die Rich Presence nicht — und
zwar nicht, weil etwas kaputt war, sondern weil **nach dem Neustart kein einziger der beiden
Prozesse lief.** Discord startete mit, die Anzeigen nicht. Das Log endete um 23:45 des Vortags
mitten im Betrieb. **Ein Werkzeug, das nur läuft, solange man es von Hand startet, sieht nach
einem Neustart aus wie ein defektes Werkzeug.**

⚠️ **`fenster.py` hat keinen Doppelstart-Schutz**, `presence.py` schon. Wer das Fenster zusätzlich
von Hand startet, bekommt ein zweites. (Nachgemessen am 02.09.: die Presence-Verknüpfung meldet
sauber *„Laeuft schon (PID …) — dieser Start macht Schluss."*)

⚠️ **Dieser Ordner ist kein git-Repo** — er liegt nur auf dieser Platte, genau wie
`glukose-anzeige`. Ein Plattenschaden kostet ihn.
