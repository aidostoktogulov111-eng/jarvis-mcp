Set fso = CreateObject("Scripting.FileSystemObject")
d = fso.GetParentFolderName(WScript.ScriptFullName)
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = d
sh.Run """" & d & "\.venv\Scripts\pythonw.exe"" """ & d & "\launcher.py""", 0, False
