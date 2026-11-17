param([string]$Out="C:\Users\oscar\AppData\Local\hermes\cache\scratch\full.png")
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;using System.Runtime.InteropServices;
public class D{
 [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
 [DllImport("user32.dll")] public static extern int GetSystemMetrics(int i);
}
"@
[D]::SetProcessDPIAware() | Out-Null
$w = [D]::GetSystemMetrics(0); $h = [D]::GetSystemMetrics(1)
$bmp = New-Object System.Drawing.Bitmap $w,$h
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen(0,0,0,0,(New-Object System.Drawing.Size $w,$h))
$bmp.Save($Out,[System.Drawing.Imaging.ImageFormat]::Png)
"$Out ${w}x${h}"
