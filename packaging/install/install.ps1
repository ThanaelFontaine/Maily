# Maily installer for Windows (x64), in PowerShell:
#
#   irm https://github.com/ThanaelFontaine/Maily/releases/latest/download/install.ps1 | iex
#
# This file is attached to every release (from 0.10.0) and lives in the repository at
# packaging/install/install.ps1. It downloads the latest release from GitHub
# (https://github.com/ThanaelFontaine/Maily/releases), checks it against its published SHA-256,
# checks its build provenance attestation with the GitHub CLI (gh) when it can, installs it in
# %LOCALAPPDATA%\Programs\Maily and adds Maily to the Start menu. Running it again updates Maily.
# Your accounts and mail live in the data folder and are kept. No administrator rights needed.
#
# Options (environment variables): $env:MAILY_VERSION = "0.9.2" installs that version,
# $env:MAILY_INSTALL_DIR = "C:\path" installs somewhere else, $env:MAILY_REQUIRE_ATTESTATION = "1"
# refuses to install a download whose attestation could not be checked.

& {
  $ErrorActionPreference = 'Stop'
  $ProgressPreference = 'SilentlyContinue'   # the progress bar slows Invoke-WebRequest down a lot
  [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

  $repo = 'ThanaelFontaine/Maily'
  $site = 'https://maily.thanaelfontaine.eu'
  # The workflow that builds and attests every release, and the first release that has attestations.
  $signer = "$repo/.github/workflows/release.yml"
  $attestedFrom = [version]'0.10.0'

  if (-not [Environment]::Is64BitOperatingSystem) {
    throw "Maily: the ready-made app needs 64-bit Windows. Run Maily from source: https://github.com/$repo#option-b-run-from-source"
  }

  # The version: the one asked for, or the latest release.
  $version = $env:MAILY_VERSION
  if (-not $version) {
    $release = Invoke-RestMethod -UseBasicParsing -Uri "https://api.github.com/repos/$repo/releases/latest" -Headers @{ 'User-Agent' = 'Maily-installer' }
    $version = $release.tag_name
  }
  $version = $version.TrimStart('v')
  if ($version -notmatch '^\d+(\.\d+)*$') { throw "Maily: could not find the latest version (got: $version)." }

  $file = "Maily-$version-windows-x64.zip"
  $url = "https://github.com/$repo/releases/download/v$version/$file"
  $tmp = Join-Path ([IO.Path]::GetTempPath()) ("maily-" + [Guid]::NewGuid().ToString('N'))
  New-Item -ItemType Directory -Path $tmp | Out-Null

  # Provenance. The checksum only proves that the download matches the file published next to it,
  # which comes from the same place. The attestation proves that the file was built from this
  # repository by its release workflow: the GitHub CLI checks it against GitHub's records (a sign-in
  # with `gh auth login` is needed, https://cli.github.com/manual/gh_attestation_verify).
  # Without it we say so and go on, unless MAILY_REQUIRE_ATTESTATION=1.
  function Skip-Attestation($why) {
    Write-Host "Warning: could not check where this download was built ($why)."
    if ($env:MAILY_REQUIRE_ATTESTATION -eq '1') {
      throw "Maily: MAILY_REQUIRE_ATTESTATION=1: nothing was installed."
    }
    Write-Host "Continuing with the checksum only. Details: https://github.com/$repo/blob/main/SECURITY.md#verify-a-download"
  }
  # Run the GitHub CLI and return its exit code. A native command that writes to stderr must not
  # stop the script, so the error preference is relaxed around the call.
  function Invoke-Gh([string[]]$ghArgs, [switch]$Quiet) {
    $saved = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
      if ($Quiet) { & gh @ghArgs *> $null } else { & gh @ghArgs 2>&1 | Out-Host }
      return $LASTEXITCODE
    }
    finally { $ErrorActionPreference = $saved }
  }

  try {
    Write-Host "Downloading Maily $version for Windows..."
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile (Join-Path $tmp $file)
    Invoke-WebRequest -UseBasicParsing -Uri "$url.sha256" -OutFile (Join-Path $tmp "$file.sha256")

    # The .sha256 file reads "<hash>  <name>".
    $expected = ((Get-Content -Raw (Join-Path $tmp "$file.sha256")).Trim() -split '\s+')[0]
    $actual = (Get-FileHash -Algorithm SHA256 -Path (Join-Path $tmp $file)).Hash
    if (-not $expected -or $expected -ne $actual) {   # -ne ignores case
      throw "Maily: the download does not match its SHA-256 checksum. Nothing was installed."
    }
    Write-Host "Checksum verified."

    $parts = ($version -split '\.') + @('0', '0')
    $parsed = [version]"$($parts[0]).$($parts[1]).$($parts[2])"
    if ($parsed -lt $attestedFrom) {
      Skip-Attestation "Maily $version is older than $attestedFrom, the first release with attestations"
    }
    elseif (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
      Skip-Attestation 'the GitHub CLI (gh) is not installed: https://cli.github.com'
    }
    elseif ((Invoke-Gh @('attestation', 'verify', '--help') -Quiet) -ne 0) {
      Skip-Attestation 'this version of gh has no `gh attestation verify`: update it'
    }
    elseif ((Invoke-Gh @('auth', 'status') -Quiet) -ne 0) {
      Skip-Attestation 'gh is not signed in: run `gh auth login`'
    }
    else {
      Write-Host "Checking the build attestation with gh..."
      if ((Invoke-Gh @('attestation', 'verify', (Join-Path $tmp $file), '--repo', $repo, '--signer-workflow', $signer, '--source-ref', 'refs/heads/main', '--deny-self-hosted-runners')) -ne 0) {
        throw "Maily: the attestation of this download could not be verified. Nothing was installed."
      }
      Write-Host "Attestation verified: built by $signer."
    }

    if (Get-Process -Name Maily -ErrorAction SilentlyContinue) {
      throw "Maily: Maily is open. Close it, then run this command again."
    }

    $dest = $env:MAILY_INSTALL_DIR
    if (-not $dest) { $dest = Join-Path $env:LOCALAPPDATA 'Programs\Maily' }
    Expand-Archive -Path (Join-Path $tmp $file) -DestinationPath (Join-Path $tmp 'x') -Force
    $new = Join-Path $tmp 'x\Maily'
    if (-not (Test-Path (Join-Path $new 'Maily.exe'))) { throw "Maily: the archive does not hold Maily\Maily.exe." }
    New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null
    if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
    Move-Item -Path $new -Destination $dest
    $exe = Join-Path $dest 'Maily.exe'

    # Start menu shortcut, for the current user.
    $programs = [Environment]::GetFolderPath('Programs')
    $shell = New-Object -ComObject WScript.Shell
    $link = $shell.CreateShortcut((Join-Path $programs 'Maily.lnk'))
    $link.TargetPath = $exe
    $link.WorkingDirectory = $dest
    $link.Description = 'All your mailboxes, every AI, one connection'
    $link.Save()

    Write-Host ""
    Write-Host "Maily $version is installed in $dest."
    Write-Host "Open it from the Start menu (Maily), or run: & '$exe'"
    Write-Host "If the window stays blank, install the Microsoft Edge WebView2 Runtime: https://developer.microsoft.com/microsoft-edge/webview2/consumer/"
    Write-Host ""
    Write-Host "To update Maily later, run the same command again. Maily also tells you when a new version is out."
    Write-Host "Next: connect your mailboxes and your AIs, $site/#start"
  }
  finally {
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
  }
}
