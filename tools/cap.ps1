param([string]$Out="C:\Users\oscar\AppData\Local\hermes\cache\scratch\edge.png",[long]$Hwnd=0)
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;using System.Runtime.InteropServices;
public class C{
 [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
 [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint flags);
 [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
 [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
 [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
 public struct RECT{public int L,T,R,B;}
}
"@
[C]::SetProcessDPIAware() | Out-Null
$h=[IntPtr]$Hwnd
$null=[C]::ShowWindow($h,9); $null=[C]::SetForegroundWindow($h); Start-Sleep -Milliseconds 600
$r=New-Object C+RECT; $null=[C]::GetWindowRect($h,[ref]$r)
$w=$r.R-$r.L; $ht=$r.B-$r.T
$bmp=New-Object System.Drawing.Bitmap $w,$ht
$g=[System.Drawing.Graphics]::FromImage($bmp)
$hdc=$g.GetHdc()
$null=[C]::PrintWindow($h,$hdc,2)
$g.ReleaseHdc($hdc)
$bmp.Save($Out,[System.Drawing.Imaging.ImageFormat]::Png)
"$Out ${w}x${ht} at $($r.L),$($r.T)"
