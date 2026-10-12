# Builds smart_water_tank_controller_guide_v2.pdf from guide.html + the firmware sketch.
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

$html = [IO.File]::ReadAllText("$here\guide.html")
$code = [IO.File]::ReadAllText("$here\firmware\water_tank_controller\water_tank_controller.ino")
$code = $code.Replace('&', '&amp;').Replace('<', '&lt;').Replace('>', '&gt;')
$tmp = Join-Path $env:TEMP 'tank_guide_build.html'
[IO.File]::WriteAllText($tmp, $html.Replace('{{FIRMWARE}}', $code), (New-Object Text.UTF8Encoding $false))

$edge = "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
$pdf = Join-Path $here 'smart_water_tank_controller_guide_v2.pdf'
$url = 'file:///' + ($tmp -replace '\\', '/')
Start-Process -FilePath $edge -Wait -ArgumentList @(
  '--headless=new', '--disable-gpu', '--no-pdf-header-footer',
  "--user-data-dir=$env:TEMP\edge-pdf-profile",
  "--print-to-pdf=`"$pdf`"", $url
)
Write-Host "Wrote $pdf"
