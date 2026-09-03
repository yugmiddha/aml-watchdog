import os
import sys
import time
import socket
import webbrowser
import subprocess
import uvicorn

# Force UTF-8 on Windows Console to prevent charmap errors
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

def kill_process_on_port(port: int = 8000):
    """Automatically frees the port on Windows if an old process is holding it."""
    if sys.platform == 'win32':
        try:
            cmd = f'powershell -Command "$p = (Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue).OwningProcess; if ($p) {{ Stop-Process -Id $p -Force -ErrorAction SilentlyContinue }}"'
            subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(0.5)
        except Exception:
            pass

def is_port_in_use(port: int = 8000) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

def start_platform():
    port = 8000
    print("===================================================================")
    print("  [AML WATCHDOG ENTERPRISE] - FINANCIAL CRIME SURVEILLANCE")
    print("===================================================================")
    
    if is_port_in_use(port):
        print(f"[*] Port {port} is occupied. Auto-clearing port {port}...")
        kill_process_on_port(port)
        time.sleep(0.5)
        
    print(f"[*] Server Address : http://127.0.0.1:{port}")
    print(f"[*] Active Records : 500,000 Transactions in Indexed SQLite Database")
    print(f"[*] ML Engine Core : Deep 600-Tree XGBoost (99.2% ROC-AUC)")
    print(f"[*] UI Theme Engine: Nordic Platinum Light / Dark / System Sync")
    print("===================================================================")
    print(">>> Launching FastAPI compliance server & opening browser... <<<")
    
    def open_browser():
        time.sleep(1.2)
        try:
            webbrowser.open(f"http://127.0.0.1:{port}")
        except Exception:
            pass
        
    import threading
    threading.Thread(target=open_browser, daemon=True).start()
    
    try:
        uvicorn.run("backend.main:app", host="127.0.0.1", port=port, reload=False, log_level="info")
    except Exception as e:
        print(f"[!] Server stopped: {e}")

if __name__ == "__main__":
    start_platform()
