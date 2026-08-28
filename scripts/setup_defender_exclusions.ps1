# Windows Defender exclusions for the nematostella recording pipeline.
# Reduces jitter from real-time AV scans on wachsende HDF5 files + Python.
#
# Run in an elevated (Admin) PowerShell:
#     Set-ExecutionPolicy -Scope Process Bypass
#     .\setup_defender_exclusions.ps1
#
# Reversible: comment out and use Remove-MpPreference -ExclusionPath / -ExclusionProcess

$paths = @(
    "W:\recordings",
    "C:\Users\akkna\OneDrive\Dokumente\GitHub\New_Imswitch\ImSwitch\nematostella-time-series"
)

$processes = @(
    "C:\Users\akkna\.conda\envs\new_imswitch\python.exe",
    "C:\Users\akkna\.conda\envs\new_imswitch\Scripts\imswitch.exe",
    "C:\Users\akkna\.conda\envs\imswitch21\python.exe"
)

if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Host "ERROR: This script requires Administrator privileges." -ForegroundColor Red
    Write-Host "Right-click PowerShell -> Run as Administrator, then re-run."
    exit 1
}

Write-Host "Adding Defender path exclusions:" -ForegroundColor Cyan
foreach ($p in $paths) {
    if (Test-Path $p) {
        Add-MpPreference -ExclusionPath $p
        Write-Host "  + $p"
    } else {
        Write-Host "  - $p (does not exist, skipped)" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Adding Defender process exclusions:" -ForegroundColor Cyan
foreach ($e in $processes) {
    if (Test-Path $e) {
        Add-MpPreference -ExclusionProcess $e
        Write-Host "  + $e"
    } else {
        Write-Host "  - $e (does not exist, skipped)" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Current exclusions:" -ForegroundColor Green
$pref = Get-MpPreference
Write-Host "  Paths:"
$pref.ExclusionPath | ForEach-Object { Write-Host "    - $_" }
Write-Host "  Processes:"
$pref.ExclusionProcess | ForEach-Object { Write-Host "    - $_" }
