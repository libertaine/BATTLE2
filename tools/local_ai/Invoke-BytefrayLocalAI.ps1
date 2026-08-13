# Invoke-BytefrayLocalAI.ps1
#
# Bytefray local-AI secondary analysis harness for Ollama.
#
# Designed for Windows PowerShell 5.1 and newer.
#
# Features:
# - Task-specific model defaults based on Bytefray Stage 1 benchmarking
# - Review / Triage / Evidence / Summarize / Tests profiles
# - Explicit model override
# - File input
# - Direct text input
# - Pipeline input
# - Ollama availability/model validation
# - Optional model pulling
# - Deterministic generation (temperature 0)
# - Task-specific output-token limits
# - Timestamped audit artifacts
# - Exact request/response preservation
# - Human-readable Markdown report
# - Performance/token metadata
# - Prompt files stored separately from PowerShell logic
# - -InitializePrompts creates the initial prompt set
#
# IMPORTANT:
# This tool provides LOCAL AI SECONDARY REVIEW.
# Its output is non-authoritative and must be independently verified
# before production-code, release, security, provenance, or behavioral
# decisions are accepted.

[CmdletBinding()]
param(
    [ValidateSet(
        "Review",
        "Triage",
        "Evidence",
        "Summarize",
        "Tests"
    )]
    [string]$Task = "Review",

    [Alias("Input")]
    [string]$InputFile,

    [string]$Text,

    [string]$Model,

    [string]$PromptDirectory = (Join-Path $PSScriptRoot "prompts"),

    [string]$ResultsDirectory = (Join-Path $PSScriptRoot "local-ai-results"),

    [string]$OllamaUrl = "http://localhost:11434",

    [int]$TimeoutSec = 600,

    [switch]$PullMissingModel,

    [switch]$InitializePrompts,

    [Parameter(ValueFromPipeline = $true)]
    [AllowNull()]
    [object]$InputObject
)

begin {

    $ErrorActionPreference = "Stop"

    # Collect pipeline content here.
    $pipelineBuffer = New-Object System.Collections.Generic.List[string]

    function Write-Section {
        param([string]$Text)

        Write-Host ""
        Write-Host ("=" * 72)
        Write-Host $Text
        Write-Host ("=" * 72)
    }

    function Convert-NanosecondsToSeconds {
        param($Nanoseconds)

        if ($null -eq $Nanoseconds) {
            return $null
        }

        return [math]::Round(
            ([double]$Nanoseconds / 1000000000),
            3
        )
    }

    function Get-SafeName {
        param([string]$Name)

        return ($Name -replace '[:/\\]', '_')
    }

    function Write-PlainTextFile {
        param(
            [string]$Path,
            [string]$Content
        )

        [System.IO.File]::WriteAllText(
            $Path,
            $Content,
            [System.Text.UTF8Encoding]::new($false)
        )
    }

    function Initialize-BytefrayPrompts {

        Write-Section "Initializing Bytefray Local AI Prompts"

        $resolvedPromptDirectory = [System.IO.Path]::GetFullPath($PromptDirectory)

        New-Item `
            -ItemType Directory `
            -Path $resolvedPromptDirectory `
            -Force |
            Out-Null

        $PromptDirectory = $resolvedPromptDirectory

        Write-Host "Prompt directory:"
        Write-Host "  $PromptDirectory"

        $commonPrompt = @'
You are performing a secondary technical review for the Bytefray project.

You are a local AI assistant. Your output is advisory and non-authoritative.

You have no knowledge of repository state, execution results, source files, requirements, or history beyond the material explicitly supplied to you.

## Required reasoning discipline

- Base conclusions only on supplied evidence.
- Never assume unseen implementation behavior.
- Never invent files, functions, APIs, tests, requirements, execution results, or repository state.
- Separate observed facts from hypotheses.
- A failing test does not automatically prove production code is defective.
- A passing test does not automatically prove implementation correctness.
- Do not claim a root cause when multiple explanations remain plausible.
- Do not claim a defect merely because additional hardening is imaginable.
- If evidence cannot distinguish among plausible explanations, say INSUFFICIENT_EVIDENCE.
- Prefer the smallest safe correction over redesign.
- Do not weaken or retry-away a valid failing test merely to make it pass.
- Do not recommend suppressing diagnostics that could expose a real defect.
- Security, filesystem containment, provenance, determinism, replay integrity, evaluation identity, and reproducibility are fail-closed boundaries unless supplied requirements explicitly state otherwise.
- Windows and POSIX behavior may differ.
- Distinguish demonstrated defects from adjacent hypothetical risks.
- Keep hypothetical risks clearly labeled.
- Preserve legitimate implementation flexibility when correcting an invariant.
- Do not restructure architecture merely to eliminate one reproduction if the underlying invariant can be enforced directly.

When classification is requested, use these meanings:

DEFECT:
The supplied evidence demonstrates implementation behavior that violates a stated requirement.

TEST_DEFECT:
The supplied evidence demonstrates that the test itself is incorrect, invalid, or asserts behavior contrary to the stated requirement.

EXPECTED:
The supplied behavior satisfies the stated requirement.

INSUFFICIENT_EVIDENCE:
The supplied evidence does not establish a reliable diagnosis or classification.

Do not confuse "a test exposed a defect" with TEST_DEFECT.
'@

        $reviewPrompt = @'
Perform a narrow Bytefray technical review of the supplied material.

Focus on:

1. What behavior is actually demonstrated.
2. Whether a defect is established.
3. The smallest root cause supported by evidence.
4. The smallest safe correction.
5. Regression coverage required before accepting the correction.
6. Directly implied adjacent risks.
7. Any unsupported assumptions in the supplied material.

Return exactly these sections:

### Disposition
Choose exactly one:
DEFECT
TEST_DEFECT
EXPECTED
INSUFFICIENT_EVIDENCE

### Confidence
Choose exactly one:
HIGH
MEDIUM
LOW

### Evidence
Only facts established by the supplied material.

### Root cause
Use "Not established." when evidence does not establish one.

### Smallest safe correction
Use "None established." when no correction is justified.

### Required regression coverage
Minimum tests justified by the demonstrated mechanism.

### Adjacent risks
Only directly implied risks. Do not brainstorm unrelated hardening.

### Escalate
YES or NO.

Escalate when evidence is insufficient, requirements are ambiguous,
or the correction materially affects architecture, security, provenance,
identity, determinism, or documented behavior.
'@

        $triagePrompt = @'
Triage the supplied Bytefray failure, traceback, test result, or CI output.

The primary goal is diagnosis discipline, not producing a fix at any cost.

Determine:

1. Whether the evidence establishes a production defect, test defect,
   expected behavior, or insufficient evidence.
2. The narrowest demonstrated failure mechanism.
3. What information is missing if root cause is not established.
4. The next diagnostic action with the highest information value.
5. A correction only if the evidence actually supports one.
6. Minimum regression coverage if a correction is justified.

Return exactly these sections:

### Disposition
DEFECT / TEST_DEFECT / EXPECTED / INSUFFICIENT_EVIDENCE

### Confidence
HIGH / MEDIUM / LOW

### Demonstrated facts

### Root cause
Use "Not established." if appropriate.

### Missing evidence

### Next diagnostic action

### Smallest safe correction
Use "None established." if appropriate.

### Required regression coverage

### Escalate
YES or NO.

Do not recommend retries merely because a CI failure is intermittent.
Do not infer environmental failure simply because a rerun passes.
'@

        $evidencePrompt = @'
Act only as an evidence referee.

Your purpose is NOT to solve the problem unless the evidence genuinely
establishes the cause.

Determine what the supplied material proves and what it does not prove.

Be especially skeptical of:

- intermittent CI failures;
- conclusions inferred from a single traceback;
- stale metadata being treated as proof of stale execution;
- passing reruns being treated as proof of environmental failure;
- security claims not demonstrated by a reproduction;
- provenance claims based on incomplete identity evidence;
- guessed races, timing failures, dependency problems, or resource limits.

Return exactly these sections:

### Proven
Facts directly established by the supplied material.

### Not proven
Claims that would require additional evidence.

### Classification
DEFECT / TEST_DEFECT / EXPECTED / INSUFFICIENT_EVIDENCE

### Confidence
HIGH / MEDIUM / LOW

### Root cause
Use "Not established." unless the evidence establishes it.

### Evidence needed next
The smallest additional evidence that would resolve the uncertainty.

### Safe action now
What can safely be done without assuming an unproven cause.

### Escalate
YES or NO.
'@

        $summarizePrompt = @'
Summarize the supplied Bytefray technical output concisely.

Do not diagnose beyond the evidence.

Prioritize:

- failing tests or commands;
- repeated failure signatures;
- affected files/modules if explicitly named;
- infrastructure or environment errors if explicitly demonstrated;
- warnings;
- counts;
- the first useful traceback/root failure;
- items that appear related;
- information needed for deeper triage.

Return:

### Summary

### Failures

### Likely related groups

### Explicit environment/infrastructure findings

### Information missing

### Recommended next review target

Do not invent a root cause.
'@

        $testsPrompt = @'
Design adversarial regression coverage for the supplied Bytefray change,
requirement, defect, or proposed correction.

Focus on behavior and invariants rather than implementation trivia.

Include:

### Core regression tests
Tests directly required by the demonstrated behavior.

### Boundary cases
Relevant edge cases implied by the mechanism.

### Negative controls
Cases that must continue to succeed or must not be classified as defects.

### Cross-platform cases
Windows/POSIX differences where directly relevant.

### Determinism and provenance cases
Only when relevant to the supplied material.

### Failure assertions
What each test must prove, including fail-closed behavior where appropriate.

### Avoid
Tests that would overfit the current implementation or merely duplicate
the reproduction without protecting the underlying invariant.

Do not invent requirements not supplied in the input.
'@

        $promptFiles = @{
            "common.txt"    = $commonPrompt
            "review.txt"    = $reviewPrompt
            "triage.txt"    = $triagePrompt
            "evidence.txt"  = $evidencePrompt
            "summarize.txt" = $summarizePrompt
            "tests.txt"     = $testsPrompt
        }

        foreach ($entry in $promptFiles.GetEnumerator()) {

            $path = Join-Path $PromptDirectory $entry.Key

            if (Test-Path $path) {
                Write-Host "Exists, leaving unchanged: $path"
            }
            else {
                Write-PlainTextFile `
                    -Path $path `
                    -Content $entry.Value

                Write-Host "Created: $path"
            }
        }

        Write-Host ""
        Write-Host "Prompt initialization complete."
    }
}

process {

    if ($null -ne $InputObject) {
        $pipelineBuffer.Add([string]$InputObject)
    }
}

end {

    # -----------------------------------------------------------------------
    # Prompt initialization mode
    # -----------------------------------------------------------------------

    if ($InitializePrompts) {
        Initialize-BytefrayPrompts
        return
    }

    # -----------------------------------------------------------------------
    # Task profiles
    # -----------------------------------------------------------------------

    $profiles = @{
        "Review" = @{
            DefaultModel = "qwen2.5-coder:14b"
            PromptFile   = "review.txt"
            NumPredict   = 1400
        }

        "Triage" = @{
            DefaultModel = "qwen2.5-coder:14b"
            PromptFile   = "triage.txt"
            NumPredict   = 1400
        }

        "Evidence" = @{
            DefaultModel = "gpt-oss:20b"
            PromptFile   = "evidence.txt"

            # GPT-OSS hit the 1200-token benchmark ceiling on deeper
            # reasoning cases, so give this profile additional room.
            NumPredict   = 2400
        }

        "Summarize" = @{
            DefaultModel = "qwen2.5-coder:7b"
            PromptFile   = "summarize.txt"
            NumPredict   = 1000
        }

        "Tests" = @{
            DefaultModel = "qwen2.5-coder:14b"
            PromptFile   = "tests.txt"
            NumPredict   = 1600
        }
    }

    $profile = $profiles[$Task]

    if (-not $Model) {
        $Model = $profile.DefaultModel
    }

    $numPredict = $profile.NumPredict

    Write-Section "Bytefray Local AI"

    Write-Host "Task:        $Task"
    Write-Host "Model:       $Model"
    Write-Host "Num predict: $numPredict"
    Write-Host "Authoritative: NO"

    # -----------------------------------------------------------------------
    # Validate Ollama
    # -----------------------------------------------------------------------

    $ollamaCommand = Get-Command ollama -ErrorAction SilentlyContinue

    if (-not $ollamaCommand) {
        throw "Ollama executable was not found in PATH."
    }

    $ollamaVersion = (
        & ollama --version 2>&1 |
        Out-String
    ).Trim()

    Write-Host "Ollama:      $ollamaVersion"

    try {
        $installedResponse = Invoke-RestMethod `
            -Method Get `
            -Uri "$OllamaUrl/api/tags" `
            -TimeoutSec 10
    }
    catch {
        throw "Ollama API is not responding at $OllamaUrl. $($_.Exception.Message)"
    }

    $installedModels = @(
        $installedResponse.models |
            ForEach-Object { $_.name }
    )

    if ($installedModels -notcontains $Model) {

        if ($PullMissingModel) {

            Write-Host ""
            Write-Host "Model is not installed. Pulling:"
            Write-Host "  $Model"

            & ollama pull $Model

            if ($LASTEXITCODE -ne 0) {
                throw "Unable to pull Ollama model: $Model"
            }
        }
        else {
            throw @"
Model is not installed: $Model

Install it with:

    ollama pull $Model

or rerun with:

    -PullMissingModel
"@
        }
    }

    # -----------------------------------------------------------------------
    # Validate/read prompts
    # -----------------------------------------------------------------------

    $commonPromptPath = Join-Path $PromptDirectory "common.txt"
    $taskPromptPath = Join-Path $PromptDirectory $profile.PromptFile

    if (-not (Test-Path $commonPromptPath)) {
        throw @"
Common prompt not found:

    $commonPromptPath

Initialize the prompt set with:

    .\Invoke-BytefrayLocalAI.ps1 -InitializePrompts
"@
    }

    if (-not (Test-Path $taskPromptPath)) {
        throw "Task prompt not found: $taskPromptPath"
    }

    # Use .NET ReadAllText rather than Get-Content -Raw.
    # Windows PowerShell 5.1 may attach extended file metadata to
    # Get-Content output, causing ConvertTo-Json to serialize megabytes
    # of unintended metadata.

    $commonPrompt = [System.IO.File]::ReadAllText(
        (Resolve-Path $commonPromptPath).Path
    )

    $taskPrompt = [System.IO.File]::ReadAllText(
        (Resolve-Path $taskPromptPath).Path
    )

    if ([string]::IsNullOrWhiteSpace($commonPrompt)) {
        throw "Common prompt is empty: $commonPromptPath"
    }

    if ([string]::IsNullOrWhiteSpace($taskPrompt)) {
        throw "Task prompt is empty: $taskPromptPath"
    }

    $systemPrompt = @"
$commonPrompt

============================================================
TASK-SPECIFIC INSTRUCTIONS
============================================================

$taskPrompt
"@

    # Force a genuine plain System.String before JSON serialization.
    $systemPrompt = [string]$systemPrompt

    # -----------------------------------------------------------------------
    # Determine input source
    # -----------------------------------------------------------------------

    $inputText = $null
    $inputSource = $null

    $sourceCount = 0

    if ($InputFile) {
        $sourceCount++
    }

    if (-not [string]::IsNullOrWhiteSpace($Text)) {
        $sourceCount++
    }

    if ($pipelineBuffer.Count -gt 0) {
        $sourceCount++
    }

    if ($sourceCount -eq 0) {
        throw @"
No input was supplied.

Use one of:

    -InputFile .\some-file.txt
    -Text "some text"
    pipeline input

Examples:

    .\Invoke-BytefrayLocalAI.ps1 -Task Review -InputFile .\review.diff

    .\Invoke-BytefrayLocalAI.ps1 -Task Evidence -Text "failure details"

    git diff | .\Invoke-BytefrayLocalAI.ps1 -Task Review
"@
    }

    if ($sourceCount -gt 1) {
        throw "Specify exactly one input source: -InputFile, -Text, or pipeline."
    }

    if ($InputFile) {

        if (-not (Test-Path $InputFile)) {
            throw "Input file not found: $InputFile"
        }

        $resolvedInput = (Resolve-Path $InputFile).Path

        $inputText = [System.IO.File]::ReadAllText(
            $resolvedInput
        )

        $inputSource = $resolvedInput
    }
    elseif (-not [string]::IsNullOrWhiteSpace($Text)) {

        $inputText = [string]$Text
        $inputSource = "direct-text"
    }
    else {

        $inputText = [string]::Join(
            [Environment]::NewLine,
            $pipelineBuffer.ToArray()
        )

        $inputSource = "pipeline"
    }

    if ([string]::IsNullOrWhiteSpace($inputText)) {
        throw "Input is empty."
    }

    # Again force a plain string for PowerShell 5.1 JSON safety.
    $inputText = [string]$inputText

    Write-Host ""
    Write-Host "Input:       $inputSource"
    Write-Host "Input chars: $($inputText.Length)"

    # -----------------------------------------------------------------------
    # Create run directory
    # -----------------------------------------------------------------------

    $timestamp = Get-Date -Format "yyyy-MM-dd_HHmmss_fff"
    $safeModelName = Get-SafeName $Model
    $safeTaskName = $Task.ToLowerInvariant()

    $runDirectory = Join-Path `
        $ResultsDirectory `
        "${timestamp}_${safeTaskName}_${safeModelName}"

    New-Item `
        -ItemType Directory `
        -Path $runDirectory `
        -Force |
        Out-Null

    # Preserve exact supplied material independently of the API request.
    Write-PlainTextFile `
        -Path (Join-Path $runDirectory "input.txt") `
        -Content $inputText

    # -----------------------------------------------------------------------
    # Build Ollama request
    # -----------------------------------------------------------------------

    $body = @{
        model  = $Model
        system = $systemPrompt
        prompt = $inputText
        stream = $false

        options = @{
            temperature = 0
            num_predict = $numPredict
        }
    }

    Write-Host ""
    Write-Host "Building request..."

    # Depth 5 is sufficient and avoids expensive PowerShell 5.1
    # recursive serialization behavior seen at unnecessarily high depths.
    $jsonBody = $body | ConvertTo-Json -Depth 5

    Write-Host "Request JSON: $($jsonBody.Length) characters"

    # Save the exact request sent to Ollama.
    Write-PlainTextFile `
        -Path (Join-Path $runDirectory "request.json") `
        -Content $jsonBody

    # -----------------------------------------------------------------------
    # Execute
    # -----------------------------------------------------------------------

    Write-Host "Sending to Ollama..."
    Write-Host "Started: $(Get-Date -Format 'HH:mm:ss')"

    $wallClock = [System.Diagnostics.Stopwatch]::StartNew()

    try {

        $response = Invoke-RestMethod `
            -Method Post `
            -Uri "$OllamaUrl/api/generate" `
            -ContentType "application/json" `
            -Body $jsonBody `
            -TimeoutSec $TimeoutSec
    }
    catch {

        $wallClock.Stop()

        $errorPath = Join-Path $runDirectory "error.txt"

        Write-PlainTextFile `
            -Path $errorPath `
            -Content ($_ | Out-String)

        throw @"
Ollama request failed.

Task:  $Task
Model: $Model
Error: $($_.Exception.Message)

Error details:
$errorPath
"@
    }

    $wallClock.Stop()

    Write-Host "Returned: $(Get-Date -Format 'HH:mm:ss')"

    # -----------------------------------------------------------------------
    # Save raw API response
    # -----------------------------------------------------------------------

    $responseJson = $response | ConvertTo-Json -Depth 10

    Write-PlainTextFile `
        -Path (Join-Path $runDirectory "response.json") `
        -Content $responseJson

    # -----------------------------------------------------------------------
    # Performance metadata
    # -----------------------------------------------------------------------

    $tokensPerSecond = $null

    if (
        $response.eval_count -and
        $response.eval_duration -gt 0
    ) {
        $tokensPerSecond = [math]::Round(
            $response.eval_count /
            ($response.eval_duration / 1000000000),
            2
        )
    }

    $metadata = [ordered]@{
        timestamp            = (Get-Date).ToString("o")
        task                 = $Task
        model                = $Model
        authoritative        = $false

        input_source         = $inputSource
        input_characters     = $inputText.Length

        powershell_version   = $PSVersionTable.PSVersion.ToString()
        powershell_edition   = $PSVersionTable.PSEdition
        computer_name        = $env:COMPUTERNAME

        ollama_version       = $ollamaVersion
        ollama_url           = $OllamaUrl

        num_predict          = $numPredict
        timeout_seconds      = $TimeoutSec

        wall_seconds         = [math]::Round(
            $wallClock.Elapsed.TotalSeconds,
            3
        )

        total_seconds        =
            Convert-NanosecondsToSeconds $response.total_duration

        load_seconds         =
            Convert-NanosecondsToSeconds $response.load_duration

        prompt_tokens        = $response.prompt_eval_count

        prompt_seconds       =
            Convert-NanosecondsToSeconds $response.prompt_eval_duration

        output_tokens        = $response.eval_count

        generation_seconds   =
            Convert-NanosecondsToSeconds $response.eval_duration

        tokens_per_second    = $tokensPerSecond

        done_reason          = $response.done_reason

        common_prompt_file   = (
            Resolve-Path $commonPromptPath
        ).Path

        task_prompt_file     = (
            Resolve-Path $taskPromptPath
        ).Path
    }

    $metadataJson = $metadata | ConvertTo-Json -Depth 5

    Write-PlainTextFile `
        -Path (Join-Path $runDirectory "metadata.json") `
        -Content $metadataJson

    # -----------------------------------------------------------------------
    # Human-readable report
    # -----------------------------------------------------------------------

    $report = @"
# Bytefray Local AI Secondary Review

**Authoritative:** NO
**Task:** $Task
**Model:** $Model
**Input:** $inputSource
**Timestamp:** $($metadata.timestamp)

---

$($response.response)

---

## Local execution metadata

- Wall time: $($metadata.wall_seconds) seconds
- Prompt tokens: $($metadata.prompt_tokens)
- Output tokens: $($metadata.output_tokens)
- Generation rate: $($metadata.tokens_per_second) tokens/sec
- Done reason: $($metadata.done_reason)

This report was generated by a local Ollama model as secondary analysis.
Findings must be independently verified before production, release,
security, provenance, or documented-behavior decisions are accepted.
"@

    $reportPath = Join-Path $runDirectory "response.md"

    Write-PlainTextFile `
        -Path $reportPath `
        -Content $report

    # -----------------------------------------------------------------------
    # Console result
    # -----------------------------------------------------------------------

    Write-Section "LOCAL AI RESULT"

    Write-Host $response.response

    Write-Section "RUN COMPLETE"

    Write-Host "Task:           $Task"
    Write-Host "Model:          $Model"
    Write-Host "Wall time:      $($metadata.wall_seconds) sec"
    Write-Host "Prompt tokens:  $($metadata.prompt_tokens)"
    Write-Host "Output tokens:  $($metadata.output_tokens)"
    Write-Host "Generation:     $($metadata.tokens_per_second) tok/s"
    Write-Host "Done reason:    $($metadata.done_reason)"
    Write-Host ""
    Write-Host "Results:"
    Write-Host "  $runDirectory"
    Write-Host ""
    Write-Host "Report:"
    Write-Host "  $reportPath"

    if ($response.done_reason -eq "length") {
        Write-Host ""
        Write-Warning "The model reached its output-token limit. The response may be incomplete."
    }
}