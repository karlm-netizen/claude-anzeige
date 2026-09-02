# Prueft den Farbwechsel: hell -> dunkel -> hell, dazwischen einmal im
# Kleinformat. Der Neuaufbau ist die Stelle, an der etwas kaputtgehen kann.
import sys

sys.path.insert(0, r"C:\Users\karlm\OneDrive\Desktop\claude-anzeige")
import fenster  # noqa: E402

w = fenster.Monitor()
fehler = []


def lage(was):
    w.update_idletasks()
    print("%-30s %dx%d an %d,%d   Grund %s"
          % (was, w.winfo_width(), w.winfo_height(), w.winfo_x(), w.winfo_y(),
             w.cget("bg")))


def s1():
    lage("1. hell")
    w._thema_setzen(True)
    w.after(800, s2)


def s2():
    lage("2. dunkel")
    if w.cget("bg") != fenster.DUNKEL["GRUND"]:
        fehler.append("Grundfarbe nicht dunkel")
    w._klein_schalten(True)
    w.after(800, s3)


def s3():
    lage("3. dunkel + klein")
    w._thema_setzen(False)          # im Kleinformat umschalten
    w.after(1000, s4)


def s4():
    lage("4. hell, wieder klein")
    if not w.klein:
        fehler.append("Kleinformat nach Farbwechsel verloren")
    w._klein_schalten(False)
    w.after(800, s5)


def s5():
    lage("5. hell + gross")
    if w.cget("bg") != fenster.HELL["GRUND"]:
        fehler.append("Grundfarbe nicht wieder hell")
    print()
    print("ERGEBNIS:", "alles in Ordnung" if not fehler else "; ".join(fehler))
    w.destroy()


w.after(1200, s1)
w.mainloop()
