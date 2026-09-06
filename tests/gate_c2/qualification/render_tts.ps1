param(
    [Parameter(Mandatory=$true)][string]$Corpus,
    [Parameter(Mandatory=$true)][string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath $OutputDirectory) { throw 'TTS output must be a new directory' }
$corpusData = Get-Content -LiteralPath $Corpus -Raw -Encoding UTF8 | ConvertFrom-Json
Add-Type -AssemblyName System.Speech
$speech = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $speech.SelectVoice('Microsoft Irina Desktop')
    $format = [System.Speech.AudioFormat.SpeechAudioFormatInfo]::new(
        16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,
        [System.Speech.AudioFormat.AudioChannel]::Mono)
    [void](New-Item -ItemType Directory -Path $OutputDirectory)
    $manifest = @()
    foreach ($item in $corpusData.holdout) {
        if ([string]$item.id -notmatch '^h_[a-z0-9_]{1,48}$') { throw 'Invalid corpus ID' }
        $speech.Rate = if ($null -ne $item.render.rate) { [int]$item.render.rate } else { 0 }
        $speech.Volume = if ($null -ne $item.render.volume) { [int]$item.render.volume } else { 100 }
        if ($speech.Rate -notin @(-1,0,1) -or $speech.Volume -notin @(25,100)) { throw 'Unexpected rate/volume' }
        $segments = if ($item.render.profile -eq 'segmented_pause') { @($item.render.segments) } else { @(@{ text=[string]$item.text; pause_after_ms=0 }) }
        $index = 0
        foreach ($segment in $segments) {
            $fileName = '{0}-{1:D2}.wav' -f $item.id,$index
            $path = Join-Path $OutputDirectory $fileName
            if (Test-Path -LiteralPath $path) { throw 'Refusing to overwrite TTS bytes' }
            $speech.SetOutputToWaveFile($path,$format)
            $speech.Speak([string]$segment.text)
            $speech.SetOutputToNull()
            $manifest += [ordered]@{ id=[string]$item.id; segment=$index; file=$fileName;
                rate=$speech.Rate; volume=$speech.Volume; pause_after_ms=[int]$segment.pause_after_ms }
            $index++
        }
    }
    $record = [ordered]@{ voice_name=$speech.Voice.Name; voice_culture=$speech.Voice.Culture.Name;
        voice_id=$speech.Voice.Id; voice_gender=[string]$speech.Voice.Gender;
        system_speech_assembly=[System.Speech.Synthesis.SpeechSynthesizer].Assembly.FullName;
        sample_rate=16000;channels=1;sample_width_bytes=2;segments=$manifest }
    $encoding = [System.Text.UTF8Encoding]::new($false)
    [IO.File]::WriteAllText((Join-Path $OutputDirectory 'tts-receipt.json'),($record | ConvertTo-Json -Depth 8),$encoding)
    Write-Output ('TTS completed: {0} cases, {1} segments.' -f $corpusData.holdout.Count,$manifest.Count)
} finally {
    $speech.Dispose()
}
