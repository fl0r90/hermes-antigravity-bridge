import sys
import json
import urllib.request
import ssl

PROXMOX_URL = "https://100.87.245.1:8006/api2/json"
TOKEN_HEADER = "PVEAPIToken=root@pam!hermes_agent=c80f204c-8c4f-4977-9aca-6c34a9265cc4"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def proxmox_get(endpoint):
    url = f"{PROXMOX_URL}{endpoint}"
    req = urllib.request.Request(url, headers={"Authorization": TOKEN_HEADER})
    try:
        with urllib.request.urlopen(req, context=ctx) as resp:
            data = json.loads(resp.read().decode())
            return data.get("data", [])
    except Exception as e:
        print(f"Error querying Proxmox API: {e}")
        return None

def list_resources():
    resources = proxmox_get("/cluster/resources")
    if not resources:
        print("No resources found or error.")
        return
    print("Proxmox Resources:")
    for item in resources:
        res_type = item.get("type")
        res_id = item.get("id")
        name = item.get("name") or item.get("node") or item.get("storage")
        status = item.get("status", "unknown")
        cpu = item.get("cpu", 0)
        mem = item.get("mem", 0)
        maxmem = item.get("maxmem", 1)
        mem_pct = round((mem / maxmem) * 100, 1) if maxmem else 0
        print(f"  - [{res_type.upper()}] {name} (ID: {res_id}) | Status: {status} | CPU: {round(cpu*100,1)}% | RAM: {mem_pct}%")

if __name__ == "__main__":
    list_resources()
