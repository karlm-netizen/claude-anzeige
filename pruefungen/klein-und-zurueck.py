# Faehrt das Fenster gross -> klein -> gross und vergleicht, ob es wieder
# genau dort steht. Prueft den WEG, nicht nur die Funktion.
import sys

sys.path.insert(0, r"C:\Users\karlm\OneDrive\Desktop\claude-anzeige")
import fenster  # noqa: E402

w = fenster.Monitor()
schritte = []


def merken(was):
    w.update_idletasks()
    lage = (w.winfo_width(), w.winfo_height(), w.winfo_x(), w.winfo_y())
    schritte.append((was, lage))
    print("%-22s %dx%d an %d,%d" % ((was,) + lage))


def ablauf():
    merken("1. gross (Anfang)")
    w._klein_schalten(True)
    w.after(900, teil2)


def teil2():
    merken("2. klein")
    w._klein_schalten(False)
    w.after(900, teil3)


def teil3():
    merken("3. gross (zurueck)")
    # und noch einmal hin und zurueck - Wandern faellt erst beim zweiten Mal auf
    w._klein_schalten(True)
    w.after(700, teil4)


def teil4():
    w._klein_schalten(False)
    w.after(900, ende)


def ende():
    merken("4. gross (zweites Mal)")
    anfang = schritte[0][1]
    print()
    for name, lage in schritte[2:]:
        gleich = lage == anfang
        print("%-22s %s" % (name, "PASST" if gleich else
                            "WEICHT AB um %d,%d (Groesse %dx%d)"
                            % (lage[2] - anfang[2], lage[3] - anfang[3],
                               lage[0], lage[1])))
    w.destroy()


w.after(1200, ablauf)
w.mainloop()
