param([string]$Out="C:\Users\oscar\AppData\Local\hermes\cache\scratch\edge.png")
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;using System.Runtime.InteropServices;
public class H{
 [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
 [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
 [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
 [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
 [DllImport("user32.dll")] public static extern int GetClassNameW(IntPtr h, System.Text.StringBuilder s, int n);
 public struct RECT{public int L,T,R,B;}
}
"@
[H]::SetProcessDPIAware() | Out-Null
$p = Get-Process msedge -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if(-not $p){ "NO_WINDOW"; exit 1 }
$h = [IntPtr]$p.MainWindowHandle
$sb = New-Object System.Text.StringBuilder 256
$null = [H]::GetClassNameW($h,$sb,256)
$cls = $sb.ToString()
$null=[H]::ShowWindow($h,9); $null=[H]::SetForegroundWindow($h); Start-Sleep -Milliseconds 900
$r=New-Object H+RECT; $null=[H]::GetWindowRect($h,[ref]$r)
$w=$r.R-$r.L; $ht=$r.B-$r.T
$bmp=New-Object System.Drawing.Bitmap $w,$ht
$g=[System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($r.L,$r.T,0,0,(New-Object System.Drawing.Size $w,$ht))
$bmp.Save($Out,[System.Drawing.Imaging.ImageFormat]::Png)
"$Out hwnd=$h class=$cls ${w}x${ht} at $($r.L),$($r.T)"
