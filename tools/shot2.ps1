Add-Type -AssemblyName System.Windows.Forms,System.Drawing
$b = [System.Windows.Forms.SystemInformation]::VirtualScreen
$bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($b.Left, $b.Top, 0, 0, $bmp.Size)
$out = "C:\Users\oscar\AppData\Local\hermes\cache\scratch\desktop2.png"
$bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
Write-Output $out
