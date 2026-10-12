# Builds the controller PCB from build_board.py, checks it, and writes the files to order it.
#   .\make.ps1            -> board + DRC + isolation check + Gerber/drill zip + assembly BOM/CPL + renders
#   .\make.ps1 -NoRender  -> skip the (slow) 3D renders
param([switch]$NoRender)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$kicad = if ($env:KICAD_BIN) { $env:KICAD_BIN } else { "$env:LOCALAPPDATA\Programs\KiCad\10.0\bin" }
$py  = Join-Path $kicad 'python.exe'
$cli = Join-Path $kicad 'kicad-cli.exe'
$pcb = 'tank_controller.kicad_pcb'
New-Item -ItemType Directory -Force out | Out-Null

& $py build_board.py
if ($LASTEXITCODE) { throw 'build_board.py failed' }

# refills the GND zones under the .kicad_dru isolation rules and saves them into the board
& $cli pcb drc --refill-zones --save-board --severity-all --format json -o out\drc.json $pcb | Out-Null
& $py tools\drc_summary.py out\drc.json lib_footprint_issues silk_edge_clearance
$errors = (Get-Content out\drc.json -Raw | ConvertFrom-Json)
$bad = @($errors.violations | Where-Object severity -eq 'error').Count + @($errors.unconnected_items).Count
if ($bad) { throw "DRC: $bad errors / unconnected items - see out\drc.json" }
& $py tools\isolation_check.py $pcb

$g = 'out\gerbers'
if (Test-Path $g) { Remove-Item -Recurse -Force $g }
New-Item -ItemType Directory $g | Out-Null
# --disable-aperture-macros: some fab checkers ignore KiCad's rounded-pad macros and then
# report every hole as "no pad" and every net as open. --no-x2 --no-netlist: those same
# checkers treat unused ESP32 pins (all labelled N/C) as one net that must be joined.
# No --subtract-soldermask: that option draws the mask openings back into the
# silk file, and the fab checker counts those circles as ink on the pads.
& $cli pcb export gerbers -o $g --layers 'F.Cu,B.Cu,F.Mask,B.Mask,F.Silkscreen,B.Silkscreen,Edge.Cuts' --disable-aperture-macros --no-x2 --no-netlist $pcb | Out-Null
& $cli pcb export drill -o "$g\" --excellon-separate-th --generate-map --map-format gerberx2 $pcb | Out-Null
Compress-Archive -Force -Path "$g\*" -DestinationPath out\tank_controller_gerbers.zip
Write-Host "Gerbers: out\tank_controller_gerbers.zip"

# factory assembly: parts list (BOM) + placement (CPL) in JLCPCB format
& $cli pcb export pos --format csv --units mm --side both -o out\positions.csv $pcb | Out-Null
& $py tools\assembly_files.py out\positions.csv out\assembly
if ($LASTEXITCODE) { throw 'assembly_files.py failed' }

if (-not $NoRender) {
    & $cli pcb render --side top -w 1400 -h 1400 --background opaque --quality high -o out\render_top.png $pcb | Out-Null
    & $cli pcb render --side bottom -w 1200 -h 1200 --background opaque -o out\render_bottom.png $pcb | Out-Null
    & $cli pcb render -w 1600 -h 1200 --background opaque --quality high --rotate '-40,0,20' --perspective --zoom 0.9 -o out\render_iso.png $pcb | Out-Null
    Write-Host 'Renders: out\render_top.png, render_bottom.png, render_iso.png'
}

$edge = "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
$sheet = Join-Path $PSScriptRoot 'controller_pcb_build_sheet.pdf'
$url = 'file:///' + ((Join-Path $PSScriptRoot 'build_sheet.html') -replace '\\', '/')
Start-Process -FilePath $edge -Wait -ArgumentList @(
  '--headless=new', '--disable-gpu', '--no-pdf-header-footer',
  "--user-data-dir=$env:TEMP\edge-pdf-profile",
  "--print-to-pdf=`"$sheet`"", $url
)
Write-Host "Build sheet: $sheet"
