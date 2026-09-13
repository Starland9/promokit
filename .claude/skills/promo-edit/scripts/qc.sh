#!/usr/bin/env bash
# QC of a promokit build: contact sheet, loudness, streams, subtitle overlaps.
set -euo pipefail
f="${1:?usage: qc.sh video.mp4}"; d=$(dirname "$f"); b=$(basename "${f%.*}")
ffmpeg -y -hide_banner -loglevel error -i "$f" -vf "fps=1/2.5,scale=384:-1,tile=6x6" -frames:v 1 "$d/${b}_sheet.png"
echo "sheet: $d/${b}_sheet.png"
echo "streams: $(ffprobe -v error -show_entries stream=codec_name,width,height,r_frame_rate,sample_rate -of csv=p=0 "$f" | tr '\n' ' ')"
echo "duration: $(ffprobe -v error -show_entries format=duration -of csv=p=0 "$f") s"
ffmpeg -hide_banner -i "$f" -af ebur128=peak=true -f null - 2>&1 | grep -E '^\s+(I|LRA|Peak):' | sed 's/^/loudness: /'
srt="$d/subtitles.srt"
if [ -f "$srt" ]; then
python3 - "$srt" <<'PY'
import sys,re
t=open(sys.argv[1]).read().strip().split("\n\n"); p=lambda s:(lambda h,m,x:int(h)*3600+int(m)*60+float(x.replace(',','.')))(*s.split(':'))
cues=[(p(b.split("\n")[1].split(" --> ")[0]),p(b.split("\n")[1].split(" --> ")[1])) for b in t if len(b.split("\n"))>=2]
ov=[(i+1,i+2) for i in range(len(cues)-1) if cues[i][1]>cues[i+1][0]+0.05]
print("subtitles:",len(cues),"cues,","overlaps:",ov if ov else "none")
PY
fi
