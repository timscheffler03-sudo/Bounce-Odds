# Bounce Odds

Automatische Ball-Physik-Shorts (englisch) für YouTube/TikTok. Komplett berechnet – keine KI, keine laufenden Kosten außer Upload-Post.

**6 Arenen, rotierend:** `ring` (Flummi-Ring mit Lücke), `hexagon` (drehendes Sechseck mit Loch), `rings` (4 Ringe ausbrechen), `plinko` (x2/x0), `versus` (Rot gegen Blau), `cup` (Becher füllen).

Pro Lauf werden bis zu 40 Varianten nur physikalisch durchgerechnet; der spannendste Lauf wird gerendert. Sieg und Niederlage wechseln sich ab.

## Einstellungen (Settings → Secrets and variables → Actions)
- Secret `UPLOAD_POST_API_KEY`
- Variable `UPLOAD_POST_USER` – Profilname bei Upload-Post
- Variable `PLATFORMS` – `youtube` oder `youtube,tiktok`
- Variable `SLOTS` – Posting-Stunden, z. B. `13,19` (2 Videos/Tag) oder `12,16,20` (3/Tag)

## Wecker
cron-job.org stündlich: POST `https://api.github.com/repos/timscheffler03-sudo/bounce-odds/actions/workflows/video.yml/dispatches`
Body: `{"ref":"main","inputs":{"auto":"true","dry":"false"}}`

Lokal testen: `python3 sim.py --mode versus --seed 3 --out test.mp4`
