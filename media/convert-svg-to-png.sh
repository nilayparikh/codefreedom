#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SVG_DIR="${1:-$SCRIPT_DIR}"
OUT_DIR="${2:-$SCRIPT_DIR/icons}"

SIZES=(16 32 48 64 128 256 512)

mkdir -p "$OUT_DIR"

find_tool() {
    for cmd in rsvg-convert inkscape; do
        if command -v "$cmd" &>/dev/null; then
            echo "$cmd"
            return
        fi
    done
    if python3 -c "import cairosvg" &>/dev/null 2>&1; then
        echo "cairosvg"
        return
    fi
    echo ""
}

convert_svg() {
    local svg="$1"
    local base
    base="$(basename "$svg" .svg)"
    local tool
    tool="$(find_tool)"

    if [[ -z "$tool" ]]; then
        echo "Error: No SVG converter found. Install one of: librsvg2-bin, inkscape, or cairosvg" >&2
        exit 1
    fi

    echo "Converting: $svg (using $tool)"

    for size in "${SIZES[@]}"; do
        local outfile="$OUT_DIR/${base}-${size}x${size}.png"

        case "$tool" in
            rsvg-convert)
                rsvg-convert -w "$size" -h "$size" -o "$outfile" "$svg"
                ;;
            inkscape)
                inkscape "$svg" -w "$size" -h "$size" -o "$outfile" 2>/dev/null
                ;;
            cairosvg)
                python3 -c "
import cairosvg
cairosvg.svg2png(url='$svg', write_to='$outfile', output_width=$size, output_height=$size)
"
                ;;
        esac

        echo "  -> $outfile"
    done
}

for svg in "$SVG_DIR"/*.svg; do
    [[ -f "$svg" ]] || continue
    convert_svg "$svg"
done

echo ""
echo "Done. Icons saved to: $OUT_DIR"
