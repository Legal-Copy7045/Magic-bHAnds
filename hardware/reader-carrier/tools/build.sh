#!/usr/bin/env bash
# Rebuild everything: schematic, placed board, autoroute, ground pours, DRC,
# Gerbers/drill, JLCPCB BOM + CPL, PDFs/SVGs.
#
# Needs KiCad 7 (with its Python module), Java 17+, xvfb-run and the
# Freerouting 1.9.0 jar:  FREEROUTING=/path/to/freerouting-1.9.0.jar tools/build.sh
#
# Freerouting results vary with small placement changes; if the import step
# reports unrouted connections, nudge a part in make_pcb.py and run again.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${FREEROUTING:?set FREEROUTING to the freerouting jar}"
WORK="$(mktemp -d)"
# KiCad's own footprints, for the DRC's library check (fp-lib-table uses this).
export KICAD7_FOOTPRINT_DIR="${KICAD7_FOOTPRINT_DIR:-/usr/share/kicad/footprints}"
B=magicband-carrier
python3 tools/make_schematic.py $B.kicad_sch
python3 tools/make_pcb.py $B.kicad_pcb
python3 tools/export_dsn.py $B.kicad_pcb "$WORK/board.dsn"
xvfb-run -a java -jar "$FREEROUTING" -de "$WORK/board.dsn" -do "$WORK/board.ses" -mp 100 -mt 1
python3 tools/import_ses.py $B.kicad_pcb "$WORK/board.ses"
python3 tools/check_widths.py $B.kicad_pcb
python3 -c "import pcbnew; b=pcbnew.LoadBoard('$B.kicad_pcb'); pcbnew.WriteDRCReport(b, 'fab/drc.rpt', pcbnew.EDA_UNITS_MILLIMETRES, True)"
grep '^\*\*' fab/drc.rpt
grep -q 'Found 0 unconnected pads' fab/drc.rpt || { echo 'unrouted connections: nudge a part in make_pcb.py and run again'; exit 1; }
grep -q 'Found 0 DRC violations' fab/drc.rpt || { echo 'DRC violations: see fab/drc.rpt'; exit 1; }
grep -q 'Found 0 Footprint errors' fab/drc.rpt || { echo 'footprint errors: see fab/drc.rpt'; exit 1; }
rm -rf fab/gerbers && mkdir -p fab/gerbers
kicad-cli pcb export gerbers --layers F.Cu,B.Cu,F.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts \
  --subtract-soldermask --no-x2 -o fab/gerbers/ $B.kicad_pcb
kicad-cli pcb export drill --format excellon --drill-origin absolute --excellon-units mm \
  --generate-map --map-format gerberx2 -o fab/gerbers/ $B.kicad_pcb
python3 tools/make_fab.py $B.kicad_pcb fab
(cd fab && rm -f $B-gerbers.zip && zip -qj $B-gerbers.zip gerbers/*)
kicad-cli sch export pdf -o docs/schematic.pdf $B.kicad_sch
kicad-cli pcb export svg --layers F.Cu,F.SilkS,Edge.Cuts --page-size-mode 2 --exclude-drawing-sheet -o docs/front.svg $B.kicad_pcb
kicad-cli pcb export svg --layers B.Cu,B.SilkS,Edge.Cuts --mirror --page-size-mode 2 --exclude-drawing-sheet -o docs/back.svg $B.kicad_pcb
