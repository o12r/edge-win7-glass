param([string]$Pid2="19048")
Add-Type @"
using System;using System.Text;using System.Runtime.InteropServices;
public class P{
 [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
 [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
 [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
 [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
 [DllImport("user32.dll")] public static extern int GetWindowLong(IntPtr h, int i);
 [DllImport("user32.dll")] public static extern bool SetWindowLong(IntPtr h, int i, int v);
 [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RECT r);
 [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr h, ref POINT p);
 [DllImport("user32.dll")] public static extern int GetSystemMetrics(int i);
 [DllImport("user32.dll")] public static extern bool AdjustWindowRectEx(out RECT r, int style, bool menu, int ex);
 [DllImport("dwmapi.dll")] public static extern int DwmGetWindowAttribute(IntPtr h, int a, out RECT r, int cb);
 [DllImport("dwmapi.dll")] public static extern int DwmGetWindowAttribute(IntPtr h, int a, out int v, int cb);
 public struct RECT{public int L,T,R,B;}
 public struct POINT{public int X,Y;}
}
"@
[P]::SetProcessDPIAware() | Out-Null
$T = [IntPtr]::Zero
Add-Type -AssemblyName System.Windows.Forms -ErrorAction SilentlyContinue
# find window by pid
Add-Type @"
using System;using System.Collections.Generic;using System.Runtime.InteropServices;
public class F{
 [DllImport("user32.dll")] public static extern bool EnumWindows(E cb, IntPtr p);
 [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
 [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr h, StringBuilder s, int n);
 public delegate bool E(IntPtr h, IntPtr p);
 static List<IntPtr> r; static uint want; static E cb=new E(C);
 static bool C(IntPtr h, IntPtr p){ uint q; GetWindowThreadProcessId(h,out q); if(q==want){ var sb=new StringBuilder(200); GetClassName(h,sb,200); if(sb.ToString()=="Chrome_WidgetWin_1") r.Add(h);} return true; }
 public static IntPtr[] Find(uint pid){ r=new List<IntPtr>(); want=pid; EnumWindows(cb,IntPtr.Zero); return r.ToArray(); }
}
"@
$hs = [F]::Find([uint32]$Pid2)
foreach($h in $hs){ "cand $h" }
$h = $hs[-1]
[P]::ShowWindow($h,9) | Out-Null
[P]::SetForegroundWindow($h) | Out-Null
Start-Sleep -Milliseconds 900
$r=New-Object P+RECT; [P]::GetWindowRect($h,[ref]$r) | Out-Null
$e=New-Object P+RECT; [P]::DwmGetWindowAttribute($h,9,[ref]$e,16) | Out-Null
$cr=New-Object P+RECT; [P]::GetClientRect($h,[ref]$cr) | Out-Null
$pt=New-Object P+POINT; [P]::ClientToScreen($h,[ref]$pt) | Out-Null
$st=[P]::GetWindowLong($h,-16); $ex=[P]::GetWindowLong($h,-20)
"hwnd=$h style=0x$('{0:X8}' -f $st) ex=0x$('{0:X8}' -f $ex)"
"window=$($r.L),$($r.T)-$($r.R),$($r.B)  ext_frame=$($e.L),$($e.T)-$($e.R),$($e.B)"
"client $($cr.R)x$($cr.B) origin_screen=$($pt.X),$($pt.Y)"
"caption_top_px = $($pt.Y - $r.T)   (windowTop->clientTop)"
"SM_CYCAPTION=$([P]::GetSystemMetrics(4)) SM_CXSIZEFRAME=$([P]::GetSystemMetrics(32)) SM_CXPADDEDBORDER=$([P]::GetSystemMetrics(92)) SM_CYSIZEFRAME=$([P]::GetSystemMetrics(33))"
$nc=New-Object P+RECT
[P]::AdjustWindowRectEx([ref]$nc,$st,$false,$ex) | Out-Null
"AdjustWindowRectEx nc: L=$($nc.L) T=$($nc.T) R=$($nc.R) B=$($nc.B)"
