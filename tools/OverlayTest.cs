using System;
using System.Drawing;
using System.Windows.Forms;
using System.Runtime.InteropServices;

public class OverlayTest : Form
{
    [StructLayout(LayoutKind.Sequential)]
    public struct MARGINS { public int cxLeftWidth, cxRightWidth, cyTopHeight, cyBottomHeight; }

    [DllImport("dwmapi.dll")]
    public static extern int DwmExtendFrameIntoClientArea(IntPtr hwnd, ref MARGINS m);

    static bool extend;

    public OverlayTest()
    {
        this.Text = "OpenGlass overlay test";
        this.FormBorderStyle = FormBorderStyle.Sizable;
        this.StartPosition = FormStartPosition.Manual;
        this.Bounds = new Rectangle(300, 300, 1200, 600);
        this.BackColor = Color.White;
    }

    protected override void OnShown(EventArgs e)
    {
        base.OnShown(e);
        if (!extend) return;
        var m = new MARGINS();
        m.cxLeftWidth = -1; m.cxRightWidth = -1; m.cyTopHeight = -1; m.cyBottomHeight = -1;
        DwmExtendFrameIntoClientArea(this.Handle, ref m);
    }

    protected override void WndProc(ref Message m)
    {
        const int WM_NCCALCSIZE = 0x0083;
        if (m.Msg == WM_NCCALCSIZE)
        {
            // Claim the whole window as client area (Chromium custom-frame behaviour)
            m.Result = IntPtr.Zero;
            return;
        }
        base.WndProc(ref m);
    }

    [DllImport("user32.dll")]
    static extern bool SetProcessDPIAware();

    [STAThread]
    static void Main(string[] args)
    {
        extend = args.Length > 0 && args[0] == "extend";
        SetProcessDPIAware();
        Application.EnableVisualStyles();
        Application.Run(new OverlayTest());
    }
}
