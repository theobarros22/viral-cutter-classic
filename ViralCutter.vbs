' Lancador unico do Viral Cutter Classic.
' Mantem o atalho leve: a verificacao pesada fica dentro do aplicativo.
Option Explicit

Dim sh, fso, shellApp, base, pyw

Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
Set shellApp = CreateObject("Shell.Application")

base = fso.GetParentFolderName(WScript.ScriptFullName)
pyw = base & "\venv311\Scripts\pythonw.exe"

If Not fso.FileExists(pyw) Then
    MsgBox "Ambiente do Viral Cutter nao encontrado em:" & vbCrLf & _
           base & "\venv311", vbCritical, "Viral Cutter Classic"
    WScript.Quit 1
End If

' Segundo clique traz a janela existente para frente em vez de criar
' processos invisiveis que bloqueiam o proximo inicio.
If sh.AppActivate("Viral Cutter Classic") Then
    WScript.Quit 0
End If

' ShellExecute abre a janela nativa normalmente; pythonw evita console.
shellApp.ShellExecute pyw, Chr(34) & base & "\app_desktop.py" & Chr(34), base, "open", 1
