using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;

[assembly: AssemblyTitle("AudioMind")]
[assembly: AssemblyDescription("AudioMind - Ambient Voice Companion & Screen Intelligence for Antigravity")]
[assembly: AssemblyProduct("AudioMind")]
[assembly: AssemblyCompany("AudioMind")]
[assembly: AssemblyCopyright("Copyright © 2026")]
[assembly: AssemblyFileVersion("1.0.0.0")]
[assembly: AssemblyInformationalVersion("1.0.0.0")]

namespace AudioMind
{
    class Program
    {
        static void Main(string[] args)
        {
            string rootDir = AppDomain.CurrentDomain.BaseDirectory;
            if (File.Exists(Path.Combine(rootDir, @"..\desktop\app.py")))
            {
                rootDir = Path.GetFullPath(Path.Combine(rootDir, @".."));
            }

            string pythonExe = Path.Combine(rootDir, @".venv\Scripts\pythonw.exe");
            if (!File.Exists(pythonExe))
            {
                pythonExe = Path.Combine(rootDir, @".venv\Scripts\python.exe");
            }
            if (!File.Exists(pythonExe))
            {
                pythonExe = Path.Combine(rootDir, @".venv_voice\Scripts\pythonw.exe");
            }
            if (!File.Exists(pythonExe))
            {
                pythonExe = Path.Combine(rootDir, @".venv_voice\Scripts\python.exe");
            }
            if (!File.Exists(pythonExe))
            {
                pythonExe = "python.exe";
            }

            string scriptPath = Path.Combine(rootDir, @"desktop\app.py");
            if (args != null && args.Length > 0 && File.Exists(args[0]))
            {
                scriptPath = args[0];
            }

            ProcessStartInfo psi = new ProcessStartInfo();
            psi.FileName = pythonExe;
            psi.Arguments = "\"" + scriptPath + "\"";
            psi.WorkingDirectory = rootDir;
            psi.UseShellExecute = false;
            psi.CreateNoWindow = true;

            try
            {
                using (Process proc = Process.Start(psi))
                {
                    if (proc != null)
                    {
                        proc.WaitForExit();
                    }
                }
            }
            catch (Exception)
            {
            }
        }
    }
}
