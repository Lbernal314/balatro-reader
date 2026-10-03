"""Local, read-only Balatro dashboard. Python standard library only."""
import json
import copy
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen
from simulator import analyze

API = 'http://127.0.0.1:12346'
RECORDS = Path(__file__).with_name('registros')

class Recorder:
    def __init__(self, folder=RECORDS):
        self.folder = folder
        self.previous = None
        self.total = 0
        self.saved_at = None

    def save(self, data):
        canonical = json.dumps(data, sort_keys=True, ensure_ascii=False)
        if canonical == self.previous:
            return
        self.folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).isoformat()
        record = {'capturado_en': stamp, 'estado': data}
        encoded = json.dumps(record, ensure_ascii=False)
        with (self.folder / 'historial.jsonl').open('a', encoding='utf-8') as f:
            f.write(encoded + '\n')
        temporary = self.folder / 'actual.tmp'
        temporary.write_text(encoded, encoding='utf-8')
        temporary.replace(self.folder / 'actual.json')
        self.previous = canonical
        self.total += 1
        self.saved_at = stamp

recorder = Recorder()
cache_lock = threading.Lock()
cached = None
problem = 'Esperando conexión con Balatro'
def fingerprint(data):
    def area_cards(name):
        cards = (data.get(name) or {}).get('cards', [])
        return [{
            'id': card.get('id'), 'key': card.get('key'),
            'value': {key: (card.get('value') or {}).get(key) for key in ('rank','suit')},
            'modifier': card.get('modifier'), 'ability': card.get('ability'),
            'state': {key: (card.get('state') or {}).get(key) for key in ('hidden','debuff')},
        } for card in cards]

    round_info = data.get('round') or {}
    context = data.get('joker_context') or {}
    blind = next((b for b in (data.get('blinds') or {}).values()
                  if isinstance(b,dict) and b.get('status') == 'CURRENT'), None)
    value = {
        'state': data.get('state'), 'deck': data.get('deck'),
        'ante_num': data.get('ante_num'), 'round_num': data.get('round_num'),
        'money': data.get('money'),
        'round': {key: round_info.get(key) for key in ('chips','hands_left','discards_left','hands_played')},
        'blind': blind, 'blind_disabled': (context.get('blind') or {}).get('disabled'),
        'hand_limit': (data.get('hand') or {}).get('highlighted_limit'),
        'hand': area_cards('hand'), 'draw_pool': area_cards('draw_pool'),
        'jokers': area_cards('jokers'),
        'hands': {name: {key: hand.get(key) for key in ('chips','mult')}
                  for name, hand in (data.get('hands') or {}).items()},
        'tarot_used': (context.get('consumeable_usage_total') or {}).get('tarot'),
        'dollar_buffer': context.get('dollar_buffer'),
    }
    return json.dumps(value,sort_keys=True)


def current_input():
    with cache_lock:
        return cached if not problem else None


class SimulationController:
    def __init__(self, current=current_input):
        self.current = current
        self.lock = threading.Lock()
        self.wakeup = threading.Event()
        self.generation = 0
        self.pending = None
        self.result = {'status':'idle','reason':'Presioná Simular para analizar esta mano.'}

    def submit(self, data):
        data = copy.deepcopy({k:v for k,v in data.items() if k != 'registro'})
        with self.lock:
            self.generation += 1
            self.pending = (self.generation,data,fingerprint(data))
            self.result = {'status':'running','fingerprint':fingerprint(data),'completed':0,'total':0}
            self.wakeup.set()
            return self.generation

    def view(self):
        data = self.current()
        with self.lock:
            result = dict(self.result)
        stored = result.pop('fingerprint',None)
        if data is None:
            return {'status':'waiting','reason':'Esperando conexión con Balatro.'}
        if stored is not None and stored != fingerprint(data):
            return {'status':'stale','reason':'La partida cambió. Presioná Simular para recalcular con la mano y los recursos actuales.'}
        return result

    def run(self):
        while True:
            self.wakeup.wait()
            with self.lock:
                job = self.pending
                self.pending = None
                self.wakeup.clear()
            if job is None:
                continue
            generation,data,signature = job
            def cancelled():
                current = self.current()
                with self.lock:
                    return generation != self.generation or current is None or fingerprint(current) != signature
            def progress(done,total,partial):
                with self.lock:
                    if generation == self.generation:
                        self.result = dict(partial,fingerprint=signature)
            try:
                result = analyze(data,trials=1000,progress=progress,cancelled=cancelled)
                if result.get('status') == 'superseded' or cancelled():
                    with self.lock:
                        if generation == self.generation:
                            self.result = {'status':'stale','fingerprint':signature,
                                'reason':'El cálculo se interrumpió. Presioná Simular para usar el estado actual.'}
                    continue
                if result.get('status') == 'ready':
                    RECORDS.mkdir(parents=True,exist_ok=True)
                    temporary = RECORDS / 'recomendacion.tmp'
                    temporary.write_text(json.dumps({'capturado_en':datetime.now(timezone.utc).isoformat(),
                        'estado':data,'analisis':result},ensure_ascii=False),encoding='utf-8')
                    temporary.replace(RECORDS / 'recomendacion.json')
            except Exception as exc:
                result = {'status':'blocked','reason':str(exc)}
            with self.lock:
                if generation == self.generation:
                    self.result = dict(result,fingerprint=signature)


simulations = SimulationController()

def monitor():
    global cached, problem
    while True:
        try:
            data = state()
            recorder.save(data)
            with cache_lock:
                cached = dict(data, registro={'guardado_en': recorder.saved_at, 'cambios': recorder.total})
                problem = None
        except Exception as exc:
            with cache_lock:
                problem = str(exc)
        threading.Event().wait(1)

def state():
    payload = json.dumps(dict(jsonrpc='2.0', method='gamestate', params={}, id=1)).encode()
    with urlopen(Request(API, payload, {'Content-Type': 'application/json'}), timeout=3) as r:
        result = json.load(r)
    if 'error' in result:
        raise RuntimeError(result['error'].get('message', 'Error de API'))
    data = result['result']
    # Do not expose the draw pile or identities of face-down cards.
    pool = data.pop('cards', None)
    if isinstance(pool, dict):
        # Composition only: never expose or use the future draw order.
        pool['cards'] = sorted(pool.get('cards', []), key=lambda c: c.get('id', 0))
        for card in pool['cards']:
            card['state'] = {}
        data['draw_pool'] = pool
    for key in ('hand', 'jokers', 'consumables', 'shop', 'pack', 'collection'):
        if key not in data:
            continue
        area = data.get(key)
        if not isinstance(area, dict):
            area = {'cards': area if isinstance(area, list) else []}
            data[key] = area
        for card in area.get('cards', []):
            for field in ('state', 'value', 'modifier', 'cost'):
                if not isinstance(card.get(field), dict):
                    card[field] = {}
            if card['state'].get('hidden'):
                flags = card['state']
                card.clear()
                card.update(label='Carta oculta', state=flags)
    return data

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/analysis':
            body = json.dumps(simulations.view()).encode()
            status, kind = 200, 'application/json; charset=utf-8'
        elif self.path == '/state':
            try:
                with cache_lock:
                    if problem:
                        raise RuntimeError(problem)
                    body = json.dumps(cached).encode()
                status = 200
            except Exception as exc:
                body = json.dumps({'error': 'Sin conexión con Balatro: ' + str(exc)}).encode()
                status = 503
            kind = 'application/json; charset=utf-8'
        elif self.path == '/':
            body = Path(__file__).with_name('index.html').read_bytes()
            status, kind = 200, 'text/html; charset=utf-8'
        elif self.path == '/favicon.ico':
            body, status, kind = b'', 204, 'image/x-icon'
        else:
            body, status, kind = b'Not found', 404, 'text/plain'
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        global cached, problem
        if self.path != '/simulate':
            self.send_error(404)
            return
        # Browser-triggered writes are restricted to this local panel.
        origin = self.headers.get('Origin')
        if origin and origin not in ('http://127.0.0.1:8765','http://localhost:8765'):
            self.send_error(403)
            return
        try:
            data = state()
            if data.get('state') != 'SELECTING_HAND' or (data.get('round') or {}).get('hands_left',0)<1:
                raise ValueError('Esperando una mano disponible para jugar.')
            with cache_lock:
                cached = dict(data,registro={'guardado_en':recorder.saved_at,'cambios':recorder.total})
                problem = None
            request_id = simulations.submit(data)
            result, status = {'status':'running','request_id':request_id},202
        except Exception as exc:
            result,status = {'status':'blocked','reason':str(exc)},409
        body=json.dumps(result).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass

if __name__ == '__main__':
    threading.Thread(target=monitor, daemon=True).start()
    threading.Thread(target=simulations.run, daemon=True).start()
    print('Lector de Balatro: http://127.0.0.1:8765', flush=True)
    ThreadingHTTPServer(('127.0.0.1', 8765), Handler).serve_forever()
