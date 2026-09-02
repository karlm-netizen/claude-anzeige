# Prueft, ob das Fenster beim Umschalten auf die Eckansicht ueberhaupt noch
# SICHTBAR ist. Koordinaten allein sagen das nicht - ein abgemeldetes Fenster
# meldet weiter brav seine Groesse. Genau daran ist die erste Pruefung
# vorbeigelaufen: sie war gruen, obwohl nichts zu sehen war.
import sys

sys.path.insert(0, r"C:\Users\karlm\OneDrive\Desktop\claude-anzeige")
import fenster  # noqa: E402

w = fenster.Monitor()
fehler = []


def zeigen(was):
    w.update_idletasks()
    sichtbar = bool(w.winfo_viewable())
    print("%-24s %dx%d an %-12s sichtbar=%-5s zustand=%s"
          % (was, w.winfo_width(), w.winfo_height(),
             "%d,%d" % (w.winfo_x(), w.winfo_y()), sichtbar, w.state()))
    if not sichtbar:
        fehler.append(was + ": unsichtbar")
    return sichtbar


def s1():
    zeigen("1. gross")
    w._klein_schalten(True)
    w.after(1000, s2)


def s2():
    zeigen("2. klein")
    w._klein_schalten(False)
    w.after(1000, s3)


def s3():
    zeigen("3. gross zurueck")
    print()
    print("ERGEBNIS:", "alles sichtbar" if not fehler else " | ".join(fehler))
    w.destroy()


w.after(1200, s1)
w.mainloop()
