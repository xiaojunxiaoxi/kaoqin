#!/usr/bin/env python
"""
?????? - ?????
??????? + ???????? (localtunnel)
"""
import subprocess, time, urllib.request, json, sys, os, signal

os.chdir(os.path.dirname(os.path.abspath(__file__)))

print("""
============================================
  ?????? - ???...
============================================
""")

# 1. Start Flask server
print("[1/3] ???????...")
proc = subprocess.Popen(['python', 'app.py'],
    stdout=open('server.log', 'w', encoding='utf-8'),
    stderr=subprocess.STDOUT)
time.sleep(3)

# Verify Flask is running
try:
    resp = urllib.request.urlopen('http://127.0.0.1:5000/api/ping', timeout=5)
    print("  OK - ????????")
except Exception as e:
    print(f"  ERROR - ???????: {e}")
    sys.exit(1)

# 2. Create localtunnel
print("[2/3] ????????...")
try:
    tunnel_proc = subprocess.Popen(
        ['npx.cmd', 'lt', '--port', '5000'],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    time.sleep(3)
    
    # Read the URL from output
    url_line = None
    import threading, queue
    q = queue.Queue()
    def reader():
        for line in tunnel_proc.stdout:
            q.put(line)
            if '.loca.lt' in line:
                break
    t = threading.Thread(target=reader, daemon=True)
    t.start()
    try:
        line = q.get(timeout=10)
        url = line.strip()
        print(f"  OK - {url}")
    except:
        print("  ERROR - ??????")
        sys.exit(1)
except Exception as e:
    print(f"  ERROR - ????: {e}")
    print("  ??: ???? localtunnel: npm install -g localtunnel")
    sys.exit(1)

# 3. Verify tunnel
print("[3/3] ??????...")
try:
    resp = urllib.request.urlopen(url + '/api/ping', timeout=10)
    data = json.loads(resp.read())
    print(f"  OK - ?????")
except Exception as e:
    print(f"  WARN - ????: {e}")

print(f"""
============================================
  DONE!
  
  ?????????App????:
  {url}
  
  ??App -> ??[??] -> ?????
  
  ????: http://127.0.0.1:5000
  
  ? Ctrl+C ?????
============================================
""")

# Keep running until Ctrl+C
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\\n????...")
    tunnel_proc.terminate()
    proc.terminate()
    print("??????")
