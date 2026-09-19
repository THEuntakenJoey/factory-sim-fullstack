import urllib.request
import json

try:
    res = urllib.request.urlopen('http://127.0.0.1:8000/api/simulation/state')
    data = json.loads(res.read())
    print('Sim time:', data.get('sim_time'))
    for a in data.get('agents', []):
        print(f"{a['id']}: state={a['state']}, block={a['current_block']}, pos=({a['x']:.2f}, {a['y']:.2f}), heading={a['heading']:.1f}, speed={a['speed']:.2f}, cargo={a['cargo']}")
except Exception as e:
    print("Error:", e)
