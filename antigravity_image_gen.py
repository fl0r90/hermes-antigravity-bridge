#!/usr/bin/env python3
import sys
import json
import urllib.request

if len(sys.argv) < 2:
    print("Usage: python3 antigravity_image_gen.py <prompt>")
    sys.exit(1)

prompt = " ".join(sys.argv[1:])
url = "http://192.168.0.196:8080/api/antigravity/generate-image"

req = urllib.request.Request(
    url,
    data=json.dumps({"prompt": prompt}).encode("utf-8"),
    headers={"Content-Type": "application/json"}
)

try:
    with urllib.request.urlopen(req, timeout=180) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        if res.get("status") == "success":
            tag = res.get("media_tag")
            print(tag)
            sys.exit(0)
        else:
            print("Error:", res.get("message"))
            sys.exit(1)
except Exception as e:
    print("Error connecting to Antigravity Image Generator:", e)
    sys.exit(1)
