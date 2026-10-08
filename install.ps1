param(
    [Parameter(Mandatory = $true)][string]$VaultPath,
    [string]$PythonCommand = 'python',
    [switch]$SkipDependencies,
    [switch]$SkipSkillRegistration
)
$ErrorActionPreference = 'Stop'
$sourceRoot = $PSScriptRoot
$targetRoot = [IO.Path]::GetFullPath($VaultPath)
$textEncoding = New-Object System.Text.UTF8Encoding($false)
function Get-SourceDigest([string]$LiteralPath) {
    $stream = [IO.File]::OpenRead($LiteralPath)
    $hasher = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($hasher.ComputeHash($stream)) }
    finally { $stream.Dispose(); $hasher.Dispose() }
}
# Only distribute source/configuration; never mirror runtime directories.
$sourceFiles = @(Get-ChildItem -LiteralPath $sourceRoot -File -Force | Where-Object { $_.Name -notlike '.*' -or $_.Name -eq '.gitignore' })
foreach ($subdir in @('_scripts', '_skills', '_references')) {
    $sourceFiles += @(Get-ChildItem -LiteralPath (Join-Path $sourceRoot $subdir) -File -Recurse | Where-Object { $_.Extension -ne '.pyc' })
}
$copies = @()
foreach ($sourceFile in $sourceFiles) {
    $relative = $sourceFile.FullName.Substring($sourceRoot.Length).TrimStart('\', '/')
    $destination = Join-Path $targetRoot $relative
    if ($sourceFile.FullName -eq $destination) { continue }
    if (Test-Path -LiteralPath $destination) {
        if ((Get-SourceDigest $destination) -ne (Get-SourceDigest $sourceFile.FullName)) {
            throw "Existing file differs; refusing to overwrite: $destination"
        }
    } else { $copies += @{ Source = $sourceFile.FullName; Destination = $destination } }
}
$skillRoot = $null
if (-not $SkipSkillRegistration) {
    $codexConfigRoot = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
    $skillRoot = Join-Path $codexConfigRoot 'skills\literature-reading-brief'
    if (Test-Path -LiteralPath $skillRoot) { throw "Skill already exists; inspect it before installing: $skillRoot" }
}
if (-not $SkipDependencies) {
    & $PythonCommand -c "import sys; assert sys.version_info >= (3, 11), 'Python 3.11+ is required'"
    if ($LASTEXITCODE -ne 0) { throw 'Python prerequisite check failed.' }
}
New-Item -ItemType Directory -Path $targetRoot -Force | Out-Null
foreach ($copy in $copies) {
    New-Item -ItemType Directory -Path (Split-Path -Parent $copy.Destination) -Force | Out-Null
    Copy-Item -LiteralPath $copy.Source -Destination $copy.Destination
}
foreach ($subdir in @('Literature\pdfs', 'Literature\notes', 'Literature\reports', 'maps\daily-briefs', '_data\brain')) {
    New-Item -ItemType Directory -Path (Join-Path $targetRoot $subdir) -Force | Out-Null
}
if (-not $SkipDependencies) {
    $runtimeRoot = Join-Path $targetRoot 'tools\scansci-pdf-env'
    $runtimePython = Join-Path $runtimeRoot 'Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $runtimePython)) {
        & $PythonCommand -m venv $runtimeRoot
        if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
    }
    & $runtimePython -m pip install -r (Join-Path $targetRoot 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed; skill was not registered.' }
}
if ($skillRoot) {
    New-Item -ItemType Directory -Path $skillRoot -Force | Out-Null
    $portableTarget = $targetRoot.Replace('\', '/')
    $wrapper = "---`nname: literature-reading-brief`ndescription: Local literature briefs, verified formal PDFs, Zotero intake and interactive guided reading.`n---`n`nRead the complete workflow instructions at ``$portableTarget/SKILL.md`` before acting. The user-selected workspace is ``$portableTarget``. Run its scripts there; do not use this registration directory as a Vault. Preserve all existing user data.`n"
    [IO.File]::WriteAllText((Join-Path $skillRoot 'SKILL.md'), $wrapper, $textEncoding)
}
Write-Output "Installed workspace: $targetRoot"
Write-Output 'Next: edit _references/research-topics.yml, verify venue metrics, and authorize Zotero Local API locally.'
