Add-Type -AssemblyName System.Windows.Forms,System.Drawing
Add-Type @"
using System;using System.Text;using System.Collections.Generic;using System.Runtime.InteropServices;
public class L{
 [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr p);
 [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
 [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
 [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
 [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr h, StringBuilder s, int n);
 [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
 [DllImport("user32.dll")] public static extern IntPtr GetProcessWindowStation();
 [DllImport("user32.dll")] public static extern IntPtr GetThreadDesktop(uint id);
 [DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
 public delegate bool EnumProc(IntPtr h, IntPtr p);
 public struct RECT{public int L,T,R,B;}
 static List<string> o=new List<string>();
 static EnumProc cb=new EnumProc(Cb);
 static bool Cb(IntPtr h, IntPtr p){
   if(!IsWindowVisible(h)) return true;
   var t=new StringBuilder(300); GetWindowText(h,t,300);
   if(t.Length==0) return true;
   var c=new StringBuilder(300); GetClassName(h,c,300);
   RECT r; GetWindowRect(h,out r);
   uint pid; GetWindowThreadProcessId(h,out pid);
   o.Add(pid+" | "+c+" | "+r.L+","+r.T+","+(r.R-r.L)+"x"+(r.B-r.T)+" | "+t);
   return true;
 }
 public static string[] Do(){ o.Clear(); EnumWindows(cb,IntPtr.Zero); return o.ToArray(); }
}
"@
"Screen: " + [System.Windows.Forms.Screen]::PrimaryScreen.Bounds.ToString()
"Virtual: " + [System.Windows.Forms.SystemInformation]::VirtualScreen.ToString()
"Desktop: " + [L]::GetThreadDesktop([L]::GetCurrentThreadId())
foreach($l in [L]::Do()){ $l }
