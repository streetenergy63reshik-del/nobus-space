[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $GitleaksReportPath
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding

try {
    if (-not [System.IO.File]::Exists($GitleaksReportPath)) {
        throw "Gitleaks report is missing."
    }

    $raw = [System.IO.File]::ReadAllText(
        $GitleaksReportPath,
        [System.Text.Encoding]::UTF8
    )
    if ([string]::IsNullOrWhiteSpace($raw)) {
        throw "Gitleaks report is empty."
    }

    $trimmed = $raw.Trim()
    if (
        $trimmed.Length -lt 2 -or
        $trimmed[0] -ne "[" -or
        $trimmed[$trimmed.Length - 1] -ne "]"
    ) {
        throw "Gitleaks report must be a JSON array."
    }

    try {
        $parsed = ConvertFrom-Json -InputObject $trimmed -ErrorAction Stop
    }
    catch {
        throw "Gitleaks report is malformed JSON."
    }

    if ($trimmed -match "^\[\s*\]$") {
        $findingCount = 0
    }
    elseif ($null -eq $parsed) {
        throw "Gitleaks report contains an invalid array item."
    }
    elseif ($parsed -is [System.Array]) {
        $findingCount = $parsed.Length
    }
    else {
        $findingCount = 1
    }

    if ($findingCount -ne 0) {
        throw "Gitleaks report contains one or more findings."
    }

    [ordered]@{
        schema = "nobus.gate0.gitleaks_report_verdict.v1"
        status = "passed"
        finding_count = 0
        raw_values_emitted = $false
    } | ConvertTo-Json -Compress
}
catch {
    [Console]::Error.WriteLine("Gitleaks report rejected.")
    exit 1
}
