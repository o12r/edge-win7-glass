Add-Type -AssemblyName System.Drawing
Add-Type -ReferencedAssemblies System.Drawing @"
using System;using System.Text;using System.Collections.Generic;using System.Runtime.InteropServices;
public class W{
 [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
 [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
 [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
 [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
 [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr h, StringBuilder s, int n);
 [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
 [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr p);
 [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr h, EnumProc cb, IntPtr p);
 [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
 [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
 [DllImport("user32.dll")] public static extern int GetWindowLong(IntPtr h, int i);
 [DllImport("dwmapi.dll")] public static extern int DwmGetWindowAttribute(IntPtr h, int a, out RECT r, int cb);
 public delegate bool EnumProc(IntPtr h, IntPtr p);
 public struct RECT{public int L,T,R,B;}
 public static List<IntPtr> Tops;
 public static List<IntPtr> Kids;
 static EnumProc cbT = new EnumProc(CbT), cbK = new EnumProc(CbK);
 static bool CbT(IntPtr h, IntPtr p){ Tops.Add(h); return true; }
 static bool CbK(IntPtr h, IntPtr p){ Kids.Add(h); return true; }
 public static IntPtr[] GetTops(){ Tops=new List<IntPtr>(); EnumWindows(cbT, IntPtr.Zero); return Tops.ToArray(); }
 public static IntPtr[] GetKids(IntPtr h){ Kids=new List<IntPtr>(); EnumChildWindows(h, cbK, IntPtr.Zero); return Kids.ToArray(); }
 public static string Cls(IntPtr h){ var sb=new StringBuilder(512); GetClassName(h,sb,512); return sb.ToString(); }
 public static string Txt(IntPtr h){ var sb=new StringBuilder(512); GetWindowText(h,sb,512); return sb.ToString(); }
 public static uint Pid(IntPtr h){ uint p; GetWindowThreadProcessId(h, out p); return p; }
 public static string R(IntPtr h){ RECT r; GetWindowRect(h, out r); return r.L+","+r.T+"-"+r.R+","+r.B; }
 public static string ER(IntPtr h){ RECT e; DwmGetWindowAttribute(h,9,out e,16); return e.L+","+e.T+"-"+e.R+","+e.B; }
}
"@
[W]::SetProcessDPIAware() | Out-Null
$pids = @(Get-Process msedge -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
$best = $null
foreach($h in [W]::GetTops()){
  if (-not [W]::IsWindowVisible($h)) { continue }
  if ($pids -notcontains [int][W]::Pid($h)) { continue }
  "TOP {0} cls={1} style=0x{2:X} ex=0x{3:X} win={4} ext={5} t='{6}'" -f $h,[W]::Cls($h),[W]::GetWindowLong($h,-16),[W]::GetWindowLong($h,-20),[W]::R($h),[W]::ER($h),[W]::Txt($h)
  if (-not $best) { $best = $h }
}
if(-not $best){ "NOWIN"; exit 1 }
"--- children of $best"
foreach($k in [W]::GetKids($best)){
  if ([W]::IsWindowVisible($k)) { "  CH {0} cls={1} win={2}" -f $k,[W]::Cls($k),[W]::R($k) }
}
