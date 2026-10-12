import json,os,sys,urllib.request,base64
req=json.load(open('lyria_req.json')); req["stream"]=True
r=urllib.request.Request("https://openrouter.ai/api/v1/chat/completions",data=json.dumps(req).encode(),
    headers={"Authorization":"Bearer "+os.environ["OPENROUTER_API_KEY"],"Content-Type":"application/json"})
b64=[]; cost=None
with urllib.request.urlopen(r,timeout=600) as resp:
    for line in resp:
        line=line.decode().strip()
        if not line.startswith("data:") or line[5:].strip()=="[DONE]": continue
        ev=json.loads(line[5:])
        cost=(ev.get("usage") or {}).get("cost",cost)
        for ch in ev.get("choices",[]):
            a=ch.get("delta",{}).get("audio") or {}
            if a.get("data"): b64.append(a["data"])
open(sys.argv[1],"wb").write(base64.b64decode(''.join(b64))); print(sys.argv[1],"cost",cost)
