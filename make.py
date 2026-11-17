"""Bounce Odds – ein Video erzeugen und posten.

Ablauf: Modus aus der Rotation nehmen -> viele Seeds nur physikalisch testen -> spannendsten Lauf
rendern -> per Upload-Post auf YouTube/TikTok posten -> state.json aktualisieren.

Umgebung:
  UPLOAD_POST_API_KEY   Secret
  UPLOAD_POST_USER      Profilname bei Upload-Post (z. B. bounceodds)
  PLATFORMS             youtube oder youtube,tiktok
  SLOTS                 Posting-Stunden (Berlin), z. B. "13,19"  -> 2 Videos/Tag
  AUTO=1                nur posten, wenn ein Slot fällig ist (für den stündlichen Wecker)
  DRY_RUN=1             nur rendern, nicht posten
  MODE=ring             Modus erzwingen (optional)
"""
import json, os, random, sys, time
from datetime import datetime
from zoneinfo import ZoneInfo
import sim

env = os.environ.get
STATE = 'state.json'
ORDER = ['ring', 'versus', 'plinko', 'hexagon', 'cup', 'rings']

DESC = {
    'ring': "Every bounce splits a ball into two – but the gap in the ring keeps spinning. Can it reach the goal before time runs out?",
    'hexagon': "A spinning hexagon with a hole in one side. Every bounce creates a new ball. Will it hit the goal in time?",
    'rings': "One ball, four spinning rings. Every bounce splits it. Can a ball escape all four layers?",
    'plinko': "Balls drop through the pegs. x2 doubles them, x0 deletes them. Will the count hit the goal?",
    'versus': "Red vs Blue. Bounces split balls, collisions convert them to the faster team. Who wins?",
    'cup': "A paddle splits every falling ball, but the cup has holes in the floor. Will it fill up?",
}
TAGS = ['physics', 'simulation', 'satisfying', 'bouncing balls', 'oddly satisfying', 'ball simulation', 'shorts']


def log(*a):
    print(*a, flush=True)


def load():
    try:
        return json.load(open(STATE))
    except Exception:
        return {'i': 0, 'n': 0, 'win_next': True, 'posted': {}}


def due_slot(st, now):
    slots = sorted(int(h) for h in (env('SLOTS') or '13,19').split(',') if h.strip())
    day = now.strftime('%Y-%m-%d')
    done = st['posted'].get(day, [])
    due = [h for h in slots if h <= now.hour and h not in done]
    return (day, due[-1]) if due else (day, None)


def pick(mode, budget_s=300, tries=40):
    """Physik-Probeläufe; liefert den spannendsten Seed (gemischt Sieg/Niederlage)."""
    base = random.randrange(10 ** 6)
    cands, t0 = [], time.time()
    for k in range(tries):
        if time.time() - t0 > budget_s:
            break
        info = sim.run(mode, base + k, dry=True)
        if info['drama'] > 0:
            cands.append(info)
            log('  Kandidat', info)
        if len(cands) >= 8:
            break
    if not cands:
        return None
    return cands


def main():
    st = load()
    now = datetime.now(ZoneInfo('Europe/Berlin'))
    day, slot = due_slot(st, now)
    if env('AUTO') == '1' and slot is None:
        log('Kein Slot fällig –', now.strftime('%H:%M'))
        return
    mode = env('MODE') or ORDER[st['i'] % len(ORDER)]
    log('Modus:', mode, '| Slot:', slot)
    cands = pick(mode)
    if not cands:
        sys.exit('Kein spannender Lauf gefunden')
    want_win = st.get('win_next', True)
    good = [c for c in cands if (c['outcome'] in ('win', 'red', 'blue')) == want_win] or cands
    best = max(good, key=lambda c: c['drama'])
    log('Gewählt:', best)
    out = f"bounce-{mode}-{best['seed']}.mp4"
    info = sim.run(mode, best['seed'], out=out)
    part = st['n'] + 1
    title = f"{info['title']} #shorts"
    desc = (f"{DESC[mode]}\n\nComment your guess before the end! 👇\n\n"
            "100% computed physics – every run is different.\n#physics #simulation #satisfying #bouncingballs")
    json.dump({'title': title, 'description': desc, 'info': info}, open(out + '.json', 'w'), indent=1)
    if env('DRY_RUN') == '1':
        log('Testlauf – nicht gepostet:', out)
        return
    post(out, title, desc)
    st['i'] += 1
    st['n'] = part
    st['win_next'] = not want_win
    if slot is not None:
        st['posted'].setdefault(day, []).append(slot)
    st['posted'] = {d: v for d, v in sorted(st['posted'].items())[-10:]}
    json.dump(st, open(STATE, 'w'), indent=1)


def post(file, title, desc):
    import requests
    key = env('UPLOAD_POST_API_KEY')
    if not key:
        sys.exit('UPLOAD_POST_API_KEY fehlt')
    plats = [p.strip() for p in (env('PLATFORMS') or 'youtube').split(',') if p.strip()]
    data = [('user', env('UPLOAD_POST_USER') or 'bounceodds'), ('title', title), ('youtube_title', title[:100]),
            ('youtube_description', desc), ('categoryId', '28'), ('privacyStatus', 'public'),
            ('defaultLanguage', 'en'), ('defaultAudioLanguage', 'en'), ('containsSyntheticMedia', 'false'),
            ('selfDeclaredMadeForKids', 'false'), ('tiktok_title', title.replace(' #shorts', '') + ' #physics #satisfying #simulation'),
            ('privacy_level', 'PUBLIC_TO_EVERYONE'), ('async_upload', 'true')]
    data += [('platform[]', p) for p in plats] + [('tags[]', t) for t in TAGS]
    log('Posten auf', plats)
    with open(file, 'rb') as f:
        r = requests.post('https://api.upload-post.com/api/upload', headers={'Authorization': f'Apikey {key}'},
                          data=data, files={'video': (os.path.basename(file), f, 'video/mp4')}, timeout=600)
    try:
        j = r.json()
    except Exception:
        j = {'text': r.text[:500]}
    if not r.ok or j.get('success') is False:
        sys.exit(f'Upload-Post {r.status_code}: {j}')
    log('Upload gestartet:', j)


if __name__ == '__main__':
    main()
