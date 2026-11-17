"""Standalone Windows entry: start the game, the scheduler and its local console."""
import ctypes
import json
from pathlib import Path
import sys
import threading
import time
import urllib.request
import webbrowser

def register_hotkeys(engine):
    """Register only our advertised function keys; release them on helper shutdown."""
    from ctypes import wintypes
    user=ctypes.WinDLL('user32',use_last_error=True)
    registered={}
    try:
        for ident,key in enumerate(['F8','F9','F10'],1):
            ok=bool(user.RegisterHotKey(None,ident,0x4000,0x76+ident))
            engine.hotkeys[key]=ok
            if ok: registered[ident]=key
        message=wintypes.MSG()
        while not engine.stop_event.wait(.05):
            while user.PeekMessageW(ctypes.byref(message),None,0,0,1):
                if message.message==0x0312 and message.wParam in registered:
                    engine.handle_hotkey(registered[message.wParam])
    finally:
        for ident in registered: user.UnregisterHotKey(None,ident)

def main():
    from wallet_assistant.manager import Manager
    from wallet_assistant.server import Server
    if '--stop' in sys.argv or '--uninstall' in sys.argv:
        try:
            state=json.load(urllib.request.urlopen('http://127.0.0.1:17470/api/state',timeout=2))
            request=urllib.request.Request('http://127.0.0.1:17470/api/stop',data=b'{}',headers={
                'Origin':'http://127.0.0.1:17470','X-CSRF-Token':state['csrf'],'Content-Type':'application/json'})
            urllib.request.urlopen(request,timeout=3).close()
            time.sleep(1)
        except OSError: pass
        if '--uninstall' in sys.argv:
            from wallet_assistant import runtime
            game=runtime.discover_game()
            if game:
                runtime.close_gracefully(game)
                runtime.uninstall(game)
        return
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateMutexW.restype=ctypes.c_void_p
    mutex=kernel.CreateMutexW(None,False,'Local\\WalletHeroesAssistant-17470')
    if ctypes.get_last_error()==183:
        if '--no-browser' not in sys.argv: webbrowser.open('http://127.0.0.1:17470')
        return
    try:
        engine=Manager()
        server=Server(engine)
        threading.Thread(target=register_hotkeys,args=(engine,),name='hotkeys',daemon=True).start()
        threading.Thread(target=engine.run,name='growth',daemon=True).start()
        if '--no-browser' not in sys.argv:
            threading.Timer(.6,lambda:webbrowser.open(server.origin)).start()
        try: server.serve_forever()
        finally:
            engine.stop()
            engine.persist()
            server.server_close()
    finally: kernel.CloseHandle(ctypes.c_void_p(mutex))

if __name__=='__main__':
    if '--self-test' in sys.argv:
        from tools.self_test import run
        run(Path(sys.argv[sys.argv.index('--self-test')+1]))
    else:
        try: main()
        except Exception as exc:
            from wallet_assistant.runtime import DATA
            import traceback
            DATA.mkdir(parents=True,exist_ok=True)
            (DATA/'startup-error.log').write_text(traceback.format_exc(),encoding='utf8')
            ctypes.windll.user32.MessageBoxW(None,f'{exc}\n\n详情：{DATA / "startup-error.log"}','自动远征启动失败',0x10)
