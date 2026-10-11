' Silent background launcher for AudioMind
' Runs the desktop system tray app without keeping a command prompt open
Set FSO = CreateObject("Scripting.FileSystemObject")
Set WshShell = CreateObject("WScript.Shell")

ScriptDir = FSO.GetParentFolderName(WScript.ScriptFullName)
RootDir = FSO.GetParentFolderName(ScriptDir)

WshShell.CurrentDirectory = RootDir

PythonExe = RootDir & "\.venv_voice\Scripts\python.exe"
If Not FSO.FileExists(PythonExe) Then
    PythonExe = RootDir & "\.venv_voice\Scripts\pythonw.exe"
End If
If Not FSO.FileExists(PythonExe) Then
    PythonExe = RootDir & "\.venv\Scripts\python.exe"
End If
If Not FSO.FileExists(PythonExe) Then
    PythonExe = RootDir & "\.venv\Scripts\pythonw.exe"
End If
If Not FSO.FileExists(PythonExe) Then
    PythonExe = "python.exe"
End If

AppScript = RootDir & "\desktop\app.py"

WshShell.Run """" & PythonExe & """ """ & AppScript & """", 0, False
