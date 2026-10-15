param([Parameter(Mandatory=$true)][string]$Config)
$ErrorActionPreference = 'Stop'
try {
    $taskSources = @('Core.cs','Library.cs','Coverage.cs','Adaptive.cs') | ForEach-Object { Join-Path $PSScriptRoot $_ }
    Add-Type -Path $taskSources -CompilerOptions '/optimize+'
    $taskExitCode = [Engine]::Run([System.IO.Path]::GetFullPath($Config))
    exit $taskExitCode
} catch {
    [Console]::Error.WriteLine('Native worker failed: ' + $_.Exception.GetType().Name)
    exit 1
}
