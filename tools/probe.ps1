param([string]$Out="C:\Users\oscar\AppData\Local\hermes\cache\scratch\edge_now.png")
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;using System.Text;using System.Runtime.InteropServices;
public class W{
 [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
 [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
 [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
 [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
 [DllImport("user32.dll")] public static extern int GetClassNameW(IntPtr h, StringBuilder s, int n);
 [DllImport("user32.dll")] public static extern int GetWindowTextW(IntPtr h, StringBuilder s, int n);
 [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr p);
 [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
 [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
 [DllImport("user32.dll")] public static extern IntPtr GetParent(IntPtr h);
 [DllImport("user32.dll")] public static extern int GetWindowLong(IntPtr h, int i);
 [DllImport("dwmapi.dll")] public static extern int DwmGetWindowAttribute(IntPtr h, int a, out RECT r, int cb);
 public delegate bool EnumProc(IntPtr h, IntPtr p);
 public struct RECT{public int L,T,R,B;}
}
"@
[W]::SetProcessDPIAware() | Out-Null
$pids = @(Get-Process msedge -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
$found = @()
$cb = [W+EnumProc]{
  param($h,$p)
  $pid2 = 0
  [W]::GetWindowThreadProcessId($h, [ref]$pid2) | Out-Null
  if ($pids -contains $pid2 -and [W]::IsWindowVisible($h)) {
    $sb = New-Object System.Text.StringBuilder 512
    [W]::GetClassNameW($h,$sb,512) | Out-Null
    $cls = $sb.ToString()
    $tb = New-Object System.Text.StringBuilder 512
    [W]::GetWindowTextW($h,$tb,512) | Out-Null
    $r = New-Object W+RECT
    [W]::GetWindowRect($h,[ref]$r) | Out-Null
    $e = New-Object W+RECT
    [W]::DwmGetWindowAttribute($h,9,[ref]$e,16) | Out-Null
    $script:found += [pscustomobject]@{hwnd=$h; cls=$cls; title=$tb.ToString(); L=$r.L; T=$r.T; R=$r.R; B=$r.B; EL=$e.L; ET=$e.T; ER=$e.R; EB=$e.B; style=[W]::GetWindowLong($h,-16)}
  }
  return $true
}
[W]::EnumWindows($cb, [IntPtr]::Zero) | Out-Null
foreach($f in $found){
  "{0} cls={1} style=0x{2:X} win={3},{4}-{5},{6} ext={7},{8}-{9},{10} title='{11}'" -f $f.hwnd,$f.cls,$f.style,$f.L,$f.T,$f.R,$f.B,$f.EL,$f.ET,$f.ER,$f.EB,$f.title
}
$main = $found | Where-Object { $_.cls -eq "Chrome_WidgetWin_1" } | Sort-Object { $_.R-$_.L } -Descending | Select-Object -First 1
if (-not $main) { $main = $found | Select-Object -First 1 }
if (-not $main) { "NOWIN"; exit 1 }
$h = $main.hwnd
[W]::ShowWindow($h,9) | Out-Null; [W]::SetForegroundWindow($h) | Out-Null; Start-Sleep -Milliseconds 800
$r = New-Object W+RECT; [W]::GetWindowRect($h,[ref]$r) | Out-Null
$w = $r.R-$r.L; $ht = $r.B-$r.T
$bmp = New-Object System.Drawing.Bitmap $w,$ht
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($r.L,$r.T,0,0,(New-Object System.Drawing.Size $w,$ht))
$bmp.Save($Out,[System.Drawing.Imaging.ImageFormat]::Png)
"SHOT $Out ${w}x${ht} at $($r.L),$($r.T)"
