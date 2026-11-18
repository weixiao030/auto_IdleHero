"""Loopback-only control surface with origin, host and CSRF validation."""
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import json
import mimetypes
import secrets
import urllib.parse
import threading
import traceback
from .runtime import SOURCE
from . import VERSION

class Server(ThreadingHTTPServer):
    daemon_threads=True
    request_queue_size=32
    def __init__(self, engine, port=17470):
        self.engine=engine
        self.csrf=secrets.token_urlsafe(32)
        super().__init__(('127.0.0.1',port),Handler)
        self.origin=f'http://127.0.0.1:{self.server_port}'
    def handle_error(self, request, client_address):
        # Windowed releases have no stderr. Keep HTTP thread failures observable.
        from .runtime import DATA
        with (DATA/'server-error.log').open('a', encoding='utf8') as handle:
            handle.write(traceback.format_exc()+'\n')

class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(10)
    def handle(self):
        try: super().handle()
        except (ConnectionError, TimeoutError): pass
    def log_message(self,*args): pass
    def reply(self, code, body, content_type='application/json; charset=utf-8'):
        data=json.dumps(body,ensure_ascii=False).encode('utf8') if not isinstance(body,bytes) else body
        self.send_response(code)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store' if 'json' in content_type else 'no-cache')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)
    def valid_host(self):
        return self.headers.get('Host')==f'127.0.0.1:{self.server.server_port}'
    def do_GET(self):
        if not self.valid_host(): return self.reply(403,{'error':'invalid_host'})
        path=urllib.parse.urlsplit(self.path).path
        if path=='/api/state':
            state=self.server.engine.public_state();state['csrf']=self.server.csrf
            return self.reply(200,state)
        if path=='/api/health': return self.reply(200,{'app':'wallet-heroes-assistant','version':VERSION})
        if path=='/api/config/export': return self.reply(200,self.server.engine.public_state()['config'])
        root=(SOURCE/'web/dist').resolve()
        target=(root/urllib.parse.unquote(path).lstrip('/')).resolve()
        if not target.is_relative_to(root): return self.reply(404,{'error':'not_found'})
        if not target.is_file(): target=root/'index.html'
        if not target.is_file(): return self.reply(503,{'error':'frontend_missing'})
        self.reply(200,target.read_bytes(),mimetypes.guess_type(target.name)[0] or 'application/octet-stream')
    def do_POST(self):
        if not self.valid_host() or self.headers.get('Origin')!=self.server.origin or not secrets.compare_digest(self.headers.get('X-CSRF-Token',''),self.server.csrf):
            return self.reply(403,{'error':'invalid_origin_or_csrf'})
        try:
            size=int(self.headers.get('Content-Length',0))
            if size<0 or size>16384: return self.reply(413,{'error':'body_too_large'})
            value=json.loads(self.rfile.read(size) or b'{}')
            if not isinstance(value,dict): raise ValueError()
        except (ValueError,OSError): return self.reply(400,{'error':'invalid_json'})
        manager = self.server.engine
        if hasattr(manager, 'target_engine'):
            if self.path=='/api/connection/refresh':
                manager.refresh(); return self.reply(200,{'ok':True})
            if self.path=='/api/connection/select':
                try: manager.select(value.get('instance_id'))
                except ValueError as exc: return self.reply(409,{'error':str(exc)})
                return self.reply(200,{'ok':True})
            if self.path=='/api/stop':
                manager.stop()
                manager.persist()
                self.reply(200,{'ok':True})
                threading.Thread(target=self.server.shutdown,daemon=True).start()
                return
            if not isinstance(value.get('_instance_id'), str):
                return self.reply(409,{'error':'请选择实例后重试，页面可能已更新。'})
            try: engine = manager.target_engine(value.pop('_instance_id'))
            except ValueError as exc: return self.reply(409,{'error':str(exc)})
        else: engine = manager
        if self.path in ('/api/salvage/preview', '/api/salvage/start', '/api/salvage/stop'):
            try:
                if self.path.endswith('/preview'): result = engine.preview_salvage()
                elif self.path.endswith('/start'): result = engine.start_salvage(value.get('token'))
                else: result = engine.stop_salvage(disable_auto=True)
            except ValueError as exc: return self.reply(409, {'error': str(exc)})
            return self.reply(200, {'ok': True, 'result': result})
        if self.path=='/api/run':
            engine.set_running(True);return self.reply(200,{'ok':True})
        if self.path=='/api/pause':
            engine.set_running(False);return self.reply(200,{'ok':True})
        if self.path=='/api/config':
            return self.reply(200,{'ok':True,'config':engine.update_config(value)})
        if self.path=='/api/inspect':
            engine.inspect_now();return self.reply(200,{'ok':True})
        if self.path=='/api/connection/launch':
            if not engine.game: return self.reply(409,{'error':'未发现游戏目录'})
            try:
                with engine.lock: engine.launch_game()
            except (OSError,RuntimeError) as exc: return self.reply(409,{'error':str(exc)})
            return self.reply(200,{'ok':True})
        if self.path=='/api/config/open':
            import os
            from .runtime import DATA
            os.startfile(engine.data_dir/'config.json')
            return self.reply(200,{'ok':True})
        if self.path=='/api/stop':
            self.server.engine.stop_event.set()
            self.server.engine.persist()
            self.reply(200,{'ok':True})
            threading.Thread(target=self.server.shutdown,daemon=True).start()
            return
        return self.reply(404,{'error':'not_found'})
