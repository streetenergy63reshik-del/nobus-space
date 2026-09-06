param([Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$dataset = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'dataset.json') -Raw -Encoding UTF8 | ConvertFrom-Json
[void](New-Item -ItemType Directory -Path $OutputDirectory -Force)
$speech = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $speech.SelectVoice('Microsoft Irina Desktop')
    foreach ($item in $dataset.cases) {
        $speech.Volume = if ($item.volume) { [int]$item.volume } else { 100 }
        $speech.SetOutputToWaveFile((Join-Path $OutputDirectory ($item.id + '.wav')))
        $speech.Speak([string]$item.text)
        $speech.SetOutputToNull()
    }
} finally { $speech.Dispose() }
