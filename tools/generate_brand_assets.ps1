<#
.SYNOPSIS
    Regenerate Bytefray's production brand assets from the committed master brand sheet.

.DESCRIPTION
    Development-only tooling. Crops the approved regions of
    assets/branding/bytefray-brand-sheet.png (the "1) Primary Icon" and
    "2) Horizontal Logo" panels), removes the flat presentation background
    via a border-seeded flood fill (not a global color key -- see
    Set-BorderFloodFillTransparent for why) to produce real alpha
    transparency, and writes:
      - assets/branding/bytefray-icon.png            (square mark, transparent)
      - assets/branding/bytefray-icon.ico             (multi-resolution Windows icon)
      - assets/branding/bytefray-logo-horizontal.png  (mark + wordmark lockup, transparent)

    Uses only .NET System.Drawing (already present on Windows) -- no Pillow,
    ImageMagick, or other new dependency, runtime or dev. Crop rectangles were
    derived by measuring the source sheet directly (see the constants below);
    this script does not invent, redraw, or reinterpret any artwork -- it only
    crops, removes the known flat background, and resizes with high-quality
    bicubic resampling (see New-ResizedBitmap for why nearest-neighbor was
    tried first and rejected).

.EXAMPLE
    pwsh -File tools/generate_brand_assets.ps1
    Run from the repository root (or pass -RepoRoot explicitly).
#>

param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$SourcePath = (Join-Path $RepoRoot "assets/branding/bytefray-brand-sheet.png"),
    [string]$OutDir = (Join-Path $RepoRoot "assets/branding")
)

Add-Type -AssemblyName System.Drawing

# ---- Measured crop rectangles (source: 1491x1055 px brand sheet) --------
# "1) Primary Icon" panel: navy rounded-square mark measured at x=[106,411]
# y=[91,405] (background-color scan, tolerance 6) and x=[104,413] y=[90,408]
# including the corner sparkle-particle accents (generic non-background
# scan). This rectangle comfortably contains both with page-background
# margin on every side for clean chroma-keying.
$IconCrop = @{ X = 95; Y = 85; W = 325; H = 325 }

# "2) Horizontal Logo" panel content (icon + wordmark, excluding the
# presentation card border and heading label): x=[582,1396] y=[132,337],
# padded 10px on each side and confirmed to stay inside the white card
# interior (border measured at x=545-546/1446, y=100-101/375-376).
$LogoCrop = @{ X = 572; Y = 122; W = 835; H = 226 }

# Flat page background behind the icon panel, keyed to transparent for the
# icon only (the horizontal logo keeps its white background -- see below).
$PageGray = @{ R = 247; G = 247; B = 247 }
$KeyTolerance = 70   # Euclidean RGB distance; separates flat bg + AA fringe
                      # from real mark colors (navy/cyan/orange/white highlight).

$IcoSizes = 16, 32, 48, 64, 128, 256

function New-CroppedBitmap {
    param($Source, [hashtable]$Rect)
    $dest = New-Object System.Drawing.Bitmap $Rect.W, $Rect.H, ([System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $g = [System.Drawing.Graphics]::FromImage($dest)
    $g.CompositingMode = [System.Drawing.Drawing2D.CompositingMode]::SourceCopy
    $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::NearestNeighbor
    $srcRect = New-Object System.Drawing.Rectangle $Rect.X, $Rect.Y, $Rect.W, $Rect.H
    $destRect = New-Object System.Drawing.Rectangle 0, 0, $Rect.W, $Rect.H
    $g.DrawImage($Source, $destRect, $srcRect, [System.Drawing.GraphicsUnit]::Pixel)
    $g.Dispose()
    return $dest
}

function Set-BorderFloodFillTransparent {
    # Clears the background to transparent via a border-seeded flood fill,
    # rather than a global color key. This matters because the sheet's flat
    # background gray/white sits close, in plain RGB distance, to colors the
    # mark itself legitimately uses (e.g. the B-mark's pure-white fill
    # squares, and the horizontal lockup's white card behind the small
    # embedded icon) -- a global key indiscriminately erased those enclosed
    # design fills too (confirmed by rendering on a checkerboard). Flood
    # fill only removes background reachable from the crop's edge, so
    # enclosed white fill surrounded by opaque mark pixels is left alone,
    # while the true outer background (and open letterform apertures, e.g.
    # "e"/"a" in the wordmark) are correctly cleared.
    param([System.Drawing.Bitmap]$Bitmap, [hashtable]$Key, [int]$Tolerance)
    $w = $Bitmap.Width; $h = $Bitmap.Height
    $rect = New-Object System.Drawing.Rectangle 0, 0, $w, $h
    $data = $Bitmap.LockBits($rect, [System.Drawing.Imaging.ImageLockMode]::ReadWrite, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $stride = $data.Stride
    $bytes = New-Object byte[] ($stride * $h)
    [System.Runtime.InteropServices.Marshal]::Copy($data.Scan0, $bytes, 0, $bytes.Length)
    $tol2 = $Tolerance * $Tolerance
    $visited = New-Object bool[] ($w * $h)
    $isBg = {
        param($x, $y)
        $i = $y * $stride + $x * 4
        $dr = [int]$bytes[$i + 2] - $Key.R
        $dg = [int]$bytes[$i + 1] - $Key.G
        $db = [int]$bytes[$i] - $Key.B
        return (($dr * $dr + $dg * $dg + $db * $db) -le $tol2)
    }
    $queue = New-Object System.Collections.Generic.Queue[int]
    for ($x = 0; $x -lt $w; $x++) {
        foreach ($y in 0, ($h - 1)) {
            if (-not $visited[$y * $w + $x] -and (& $isBg $x $y)) { $visited[$y * $w + $x] = $true; $queue.Enqueue($y * $w + $x) }
        }
    }
    for ($y = 0; $y -lt $h; $y++) {
        foreach ($x in 0, ($w - 1)) {
            if (-not $visited[$y * $w + $x] -and (& $isBg $x $y)) { $visited[$y * $w + $x] = $true; $queue.Enqueue($y * $w + $x) }
        }
    }
    while ($queue.Count -gt 0) {
        $idx = $queue.Dequeue()
        $py = [int]($idx / $w); $px = $idx % $w
        foreach ($d in (@(1,0), @(-1,0), @(0,1), @(0,-1))) {
            $nx = $px + $d[0]; $ny = $py + $d[1]
            if ($nx -lt 0 -or $nx -ge $w -or $ny -lt 0 -or $ny -ge $h) { continue }
            $nidx = $ny * $w + $nx
            if ($visited[$nidx]) { continue }
            if (& $isBg $nx $ny) {
                $visited[$nidx] = $true
                $queue.Enqueue($nidx)
            }
        }
    }
    for ($y = 0; $y -lt $h; $y++) {
        $rowStart = $y * $stride
        for ($x = 0; $x -lt $w; $x++) {
            $i = $rowStart + $x * 4
            $bytes[$i + 3] = if ($visited[$y * $w + $x]) { 0 } else { 255 }
        }
    }
    [System.Runtime.InteropServices.Marshal]::Copy($bytes, 0, $data.Scan0, $bytes.Length)
    $Bitmap.UnlockBits($data)
}

function New-ResizedBitmap {
    # NOTE: the source sheet is a high-resolution *rendering* of pixel art
    # (each "big pixel" square is drawn with its own antialiased edges/gaps),
    # not literal 1:1 low-res pixel data. Visual inspection of a
    # nearest-neighbor downscale (see report) showed the ~20px grid gaps
    # between squares being point-sampled unpredictably at small target
    # sizes, making the mark unrecognizable at 16x16 and moire-y up to
    # 128x128. High-quality bicubic resampling reproduces the mark
    # correctly at every target size, so it is used instead per the
    # documented "unless inspection proves otherwise" exception.
    # Resizing is done in premultiplied-alpha space (Format32bppPArgb) to
    # avoid GDI+'s known dark-fringing bug when interpolating straight-alpha
    # transparent images.
    param([System.Drawing.Bitmap]$Source, [int]$Size)
    $srcP = $Source.Clone((New-Object System.Drawing.Rectangle 0, 0, $Source.Width, $Source.Height), [System.Drawing.Imaging.PixelFormat]::Format32bppPArgb)
    $destP = New-Object System.Drawing.Bitmap $Size, $Size, ([System.Drawing.Imaging.PixelFormat]::Format32bppPArgb)
    $g = [System.Drawing.Graphics]::FromImage($destP)
    $g.CompositingMode = [System.Drawing.Drawing2D.CompositingMode]::SourceCopy
    $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
    $g.DrawImage($srcP, (New-Object System.Drawing.Rectangle 0, 0, $Size, $Size))
    $g.Dispose()
    $srcP.Dispose()
    # Convert back to straight (non-premultiplied) alpha for PNG output.
    $dest = $destP.Clone((New-Object System.Drawing.Rectangle 0, 0, $Size, $Size), [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $destP.Dispose()
    return $dest
}

function Save-Png {
    param([System.Drawing.Bitmap]$Bitmap, [string]$Path)
    $Bitmap.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
}

function Write-Ico {
    param([System.Drawing.Bitmap[]]$Bitmaps, [int[]]$Sizes, [string]$Path)
    $pngBlobs = @()
    foreach ($bmp in $Bitmaps) {
        $ms = New-Object System.IO.MemoryStream
        $bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
        $pngBlobs += , $ms.ToArray()
        $ms.Dispose()
    }
    $fs = New-Object System.IO.FileStream $Path, ([System.IO.FileMode]::Create)
    $bw = New-Object System.IO.BinaryWriter $fs
    # ICONDIR
    $bw.Write([UInt16]0)      # reserved
    $bw.Write([UInt16]1)      # type = icon
    $bw.Write([UInt16]$Sizes.Count)
    $offset = 6 + (16 * $Sizes.Count)
    for ($i = 0; $i -lt $Sizes.Count; $i++) {
        $sz = $Sizes[$i]
        $blobLen = $pngBlobs[$i].Length
        $dim = if ($sz -ge 256) { 0 } else { $sz }   # 0 means 256 per ICO spec
        $bw.Write([byte]$dim)       # width
        $bw.Write([byte]$dim)       # height
        $bw.Write([byte]0)          # color palette
        $bw.Write([byte]0)          # reserved
        $bw.Write([UInt16]1)        # color planes
        $bw.Write([UInt16]32)       # bits per pixel
        $bw.Write([UInt32]$blobLen)
        $bw.Write([UInt32]$offset)
        $offset += $blobLen
    }
    foreach ($blob in $pngBlobs) {
        $bw.Write($blob)
    }
    $bw.Flush()
    $bw.Dispose()
    $fs.Dispose()
}

if (-not (Test-Path $SourcePath)) {
    throw "Source brand sheet not found: $SourcePath"
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$source = [System.Drawing.Bitmap]::FromFile($SourcePath)
Write-Output "Loaded source sheet: $($source.Width)x$($source.Height) from $SourcePath"

# ---- Square icon ----------------------------------------------------------
$iconBmp = New-CroppedBitmap -Source $source -Rect $IconCrop
Set-BorderFloodFillTransparent -Bitmap $iconBmp -Key $PageGray -Tolerance $KeyTolerance
$iconPngPath = Join-Path $OutDir "bytefray-icon.png"
Save-Png -Bitmap $iconBmp -Path $iconPngPath
Write-Output "Wrote $iconPngPath ($($iconBmp.Width)x$($iconBmp.Height))"

$icoFrames = @()
foreach ($sz in $IcoSizes) {
    $icoFrames += (New-ResizedBitmap -Source $iconBmp -Size $sz)
}
$icoPath = Join-Path $OutDir "bytefray-icon.ico"
Write-Ico -Bitmaps $icoFrames -Sizes $IcoSizes -Path $icoPath
Write-Output "Wrote $icoPath (sizes: $($IcoSizes -join ', '))"
foreach ($f in $icoFrames) { $f.Dispose() }
$iconBmp.Dispose()

# ---- Horizontal logo --------------------------------------------------------
# NOTE: the wordmark is not flat-colored text -- each letter is a white
# "face" shape plus an offset solid-navy "shadow" face (a hard 3D-bevel
# treatment that only reads correctly against a white backdrop; the white
# face optically disappears into the white card, leaving just the navy
# shadow visible as "the letter"). Confirmed by direct pixel sampling and
# by isolating the crop on a checkerboard: the white face is a genuine
# opaque design element, not antialiasing or background bleed, so keying
# it to transparent breaks the letterforms into a disconnected white
# shape plus a separate dark shape. There is no clean-alpha equivalent of
# this bevel without redrawing it, which is out of scope, so the
# horizontal logo keeps its natural white background intact -- exactly as
# Section 2 of the brand sheet itself presents the lockup.
$logoBmp = New-CroppedBitmap -Source $source -Rect $LogoCrop
$logoPngPath = Join-Path $OutDir "bytefray-logo-horizontal.png"
Save-Png -Bitmap $logoBmp -Path $logoPngPath
Write-Output "Wrote $logoPngPath ($($logoBmp.Width)x$($logoBmp.Height)) -- white background retained (see script comments)"
$logoBmp.Dispose()

$source.Dispose()
Write-Output "Done."
