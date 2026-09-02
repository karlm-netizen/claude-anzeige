Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

ordner = fso.GetParentFolderName(WScript.ScriptFullName)
python = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python312\pythonw.exe"

If Not fso.FileExists(python) Then
  MsgBox "Python 3.12 nicht gefunden unter:" & vbCrLf & python, 16, "Claude-Anzeige"
  WScript.Quit 1
End If

shell.CurrentDirectory = ordner
shell.Run """" & python & """ """ & ordner & "\fenster.py""", 0, False
