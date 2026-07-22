using System;
using System.Diagnostics;
using System.IO;
using System.Threading;

internal static class WindowsJobProbe
{
    private const string MarkerName = "job-probe-child.pid";

    private static int Main(string[] args)
    {
        if (args.Length == 1 && args[0] == "descendant")
        {
            Thread.Sleep(60000);
            return 0;
        }

        if (!IsAllowedProfile(args))
        {
            return Fail("profile");
        }

        string input = Console.ReadLine();
        string mode = input != null && input.StartsWith("{") ? "cancel" : input;
        if (mode != "exit" && mode != "wait" && mode != "cancel")
        {
            return Fail("input");
        }

        try
        {
            ProcessStartInfo start = new ProcessStartInfo();
            start.FileName = Process.GetCurrentProcess().MainModule.FileName;
            start.Arguments = "descendant";
            start.UseShellExecute = false;
            start.CreateNoWindow = true;

            using (Process child = Process.Start(start))
            {
                File.WriteAllText(MarkerName, child.Id.ToString());
                Console.WriteLine(
                    "{\"mode\":\"" + mode + "\",\"root_pid\":"
                    + Process.GetCurrentProcess().Id + ",\"child_pid\":"
                    + child.Id + "}"
                );
                Console.Out.Flush();
                Thread.Sleep(mode == "exit" ? 1500 : 60000);
            }
            return 0;
        }
        catch
        {
            return Fail("child_start");
        }
    }

    private static int Fail(string stage)
    {
        Console.WriteLine("{\"probe_error\":\"" + stage + "\"}");
        Console.Out.Flush();
        return 125;
    }

    private static bool IsAllowedProfile(string[] args)
    {
        return args.Length == 5
            && args[0] == "exec"
            && args[1] == "--json"
            && args[2] == "--sandbox"
            && args[3] == "read-only"
            && args[4] == "-";
    }
}
