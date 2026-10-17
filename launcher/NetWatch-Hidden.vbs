' Starts NetWatch inside WSL with no visible window. Used by NetWatch-Start.bat.
' Arguments: <WSL distro name> <project directory inside WSL>
Set args = WScript.Arguments
distro = args(0)
projectDir = args(1)
command = "wsl.exe -d " & distro & " --cd " & projectDir & " -e bash scripts/run_server.sh"
' window style 0 = hidden, False = do not wait for it to finish
CreateObject("WScript.Shell").Run command, 0, False
