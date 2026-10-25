#!/usr/bin/env python3
import sys
import os
import socket
import subprocess
import argparse
import tempfile

DEFAULT_PRIMARY_IP = "192.168.0.20"
DEFAULT_USER = "cfp-90"
SSH_KEY_CONTAINER = "/opt/data/.ssh/id_ed25519"
SSH_KEY_HOST = "/root/.ssh/id_ed25519"
WORKSPACE_V2 = "/home/cfp-90/AI/V2"
AGY_BIN = "/home/cfp-90/.local/bin/agy"

def get_ssh_key():
    if os.path.exists(SSH_KEY_CONTAINER):
        return SSH_KEY_CONTAINER
    return SSH_KEY_HOST

def is_port_open(ip, port=22, timeout=2.0):
    try:
        sock = socket.create_connection((ip, port), timeout=timeout)
        sock.close()
        return True
    except Exception:
        return False

def get_laptop_ip():
    ip_file = "/opt/data/laptop_current_ip.txt"
    if os.path.exists(ip_file):
        try:
            with open(ip_file) as f:
                reg_ip = f.read().strip()
                if reg_ip and is_port_open(reg_ip):
                    return reg_ip
        except Exception:
            pass

    if is_port_open(DEFAULT_PRIMARY_IP):
        return DEFAULT_PRIMARY_IP
        
    ts_ip_file = "/opt/data/laptop_tailscale_ip.txt"
    if os.path.exists(ts_ip_file):
        try:
            with open(ts_ip_file) as f:
                ts_ip = f.read().strip()
                if ts_ip and is_port_open(ts_ip):
                    return ts_ip
        except Exception:
            pass
                
    return None

def run_ssh(cmd, timeout=180):
    ip = get_laptop_ip()
    if not ip:
        return 1, "", "Laptop-ul este OFFLINE sau in sleep."
        
    key = get_ssh_key()
    ssh_cmd = [
        "ssh",
        "-i", key,
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ConnectTimeout=5",
        f"{DEFAULT_USER}@{ip}",
        cmd
    ]
    try:
        res = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=timeout)
        return res.returncode, res.stdout, res.stderr
    except subprocess.TimeoutExpired:
        return 124, "", f"Comanda a depasit timpul limita de {timeout}s."
    except Exception as e:
        return 1, "", str(e)

def status():
    ip = get_laptop_ip()
    if not ip:
        print("🔴 STATUS: Laptop OFFLINE sau in sleep.")
        return
        
    check_cmd = """
    echo "=== PROCESE ACTIVE PE LAPTOP ==="
    ps -eo pid,pcpu,pmem,args | grep -E "[a]gy" | head -n 5
    echo "=== GIT STATUS ==="
    cd /home/cfp-90/AI/V2 && git branch --show-current && git status -s | head -n 5
    if [ -f /tmp/agy_last_run.log ]; then
        echo "=== ULTIMELE LOGURI (/tmp/agy_last_run.log) ==="
        tail -n 8 /tmp/agy_last_run.log
    fi
    """
    code, out, err = run_ssh(check_cmd, timeout=15)
    print(f"🟢 STATUS: Laptop ONLINE la IP: {ip}")
    if out.strip():
        print(out.strip())
    else:
        print("Working directory curat, niciun proces agy activ.")

def cancel():
    ip = get_laptop_ip()
    if not ip:
        print("🔴 Laptop OFFLINE.")
        return
    kill_cmd = "pkill -9 -f agy 2>/dev/null; rm -f /tmp/agy_prompt.txt; echo 'Procesele agy au fost oprite.'"
    code, out, err = run_ssh(kill_cmd, timeout=10)
    print(out.strip() or "Toate procesele Antigravity de pe laptop au fost anulate.")

def add_btw(note):
    ip = get_laptop_ip()
    if not ip:
        print("🔴 Laptop OFFLINE.")
        return
    with tempfile.NamedTemporaryFile("w", delete=False) as tf:
        tf.write(f"[{note}]\n")
        local_path = tf.name
    try:
        key = get_ssh_key()
        scp_cmd = [
            "scp", "-i", key,
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "ConnectTimeout=5",
            local_path,
            f"{DEFAULT_USER}@{ip}:/tmp/incoming_btw.txt"
        ]
        subprocess.run(scp_cmd, capture_output=True, text=True)
        append_cmd = "cat /tmp/incoming_btw.txt >> /tmp/agy_steering_notes.txt && rm -f /tmp/incoming_btw.txt && echo 'Nota /btw a fost adaugata cu succes.'"
        code, out, err = run_ssh(append_cmd, timeout=10)
        print(out.strip() or "Nota /btw a fost adaugata.")
    finally:
        if os.path.exists(local_path):
            os.remove(local_path)

def run_agy(prompt, continue_session=True, is_async=False):
    ip = get_laptop_ip()
    if not ip:
        print("EROARE: Laptopul este offline.")
        return
        
    key = get_ssh_key()
    with tempfile.NamedTemporaryFile("w", delete=False) as tf:
        tf.write(prompt)
        local_prompt_path = tf.name
        
    try:
        scp_cmd = [
            "scp",
            "-i", key,
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "ConnectTimeout=5",
            local_prompt_path,
            f"{DEFAULT_USER}@{ip}:/tmp/agy_prompt.txt"
        ]
        res_scp = subprocess.run(scp_cmd, capture_output=True, text=True)
        if res_scp.returncode != 0:
            print(f"EROARE la transfer prompt catre laptop: {res_scp.stderr}")
            return
    finally:
        if os.path.exists(local_prompt_path):
            os.remove(local_prompt_path)

    flag_c = "-c" if continue_session else ""
    clean_env = "env -i HOME=/home/cfp-90 USER=cfp-90 PATH=/home/cfp-90/.local/bin:/usr/local/bin:/usr/bin:/bin"
    
    if is_async:
        bg_cmd = f"cd {WORKSPACE_V2} && nohup {clean_env} {AGY_BIN} {flag_c} --dangerously-skip-permissions -p \"$(cat /tmp/agy_prompt.txt)\" < /dev/null > /tmp/agy_last_run.log 2>&1 & echo $!"
        code, out, err = run_ssh(bg_cmd, timeout=15)
        pid = out.strip().splitlines()[-1] if out.strip() else "activ"
        print(f"🚀 Sarcina a fost lansata in fundal pe laptop (PID: {pid}).\nChat-ul ramane complet liber! Poti verifica statusul cu /status sau trimite note rapide cu /btw <text>.")
        return

    remote_cmd = f"cd {WORKSPACE_V2} && {clean_env} {AGY_BIN} {flag_c} --dangerously-skip-permissions -p \"$(cat /tmp/agy_prompt.txt)\" < /dev/null"
    code, out, err = run_ssh(remote_cmd, timeout=120)
    if code == 0:
        print(out.strip())
    else:
        if continue_session:
            retry_cmd = f"cd {WORKSPACE_V2} && {clean_env} {AGY_BIN} --dangerously-skip-permissions -p \"$(cat /tmp/agy_prompt.txt)\" < /dev/null"
            code2, out2, err2 = run_ssh(retry_cmd, timeout=120)
            if code2 == 0:
                print(out2.strip())
                return
        print(f"EROARE (exit code {code}):\n{err}\n{out}")

def apply_patch(patch_content):
    ip = get_laptop_ip()
    if not ip:
        print("EROARE: Laptopul este offline.")
        return
        
    key = get_ssh_key()
    with tempfile.NamedTemporaryFile("w", delete=False) as tf:
        tf.write(patch_content)
        temp_path = tf.name
        
    try:
        scp_cmd = [
            "scp",
            "-i", key,
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "ConnectTimeout=5",
            temp_path,
            f"{DEFAULT_USER}@{ip}:/tmp/incoming.patch"
        ]
        res_scp = subprocess.run(scp_cmd, capture_output=True, text=True)
        if res_scp.returncode != 0:
            print(f"EROARE la transfer patch: {res_scp.stderr}")
            return
            
        apply_cmd = f"cd {WORKSPACE_V2} && git apply --check /tmp/incoming.patch && git apply /tmp/incoming.patch && git status -s"
        code, out, err = run_ssh(apply_cmd)
        if code == 0:
            print("✅ PATCH APLICAT CU SUCCES in DocAI V2!\nModificari active:")
            print(out.strip())
        else:
            print(f"❌ EROARE la aplicare patch (git apply a esuat):\n{err}\n{out}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Hermes <-> Laptop Antigravity Bridge")
    sub = parser.add_subparsers(dest="cmd")
    
    sub.add_parser("status")
    sub.add_parser("cancel")
    
    p_btw = sub.add_parser("btw")
    p_btw.add_argument("note", help="Note to inject into steering context on laptop")
    
    p_run = sub.add_parser("run")
    p_run.add_argument("prompt", help="Prompt to send to Antigravity CLI on laptop")
    p_run.add_argument("--new", action="store_true", help="Start new session instead of continuing")
    p_run.add_argument("--async", dest="is_async", action="store_true", help="Run detached in background")
    
    p_patch = sub.add_parser("patch")
    p_patch.add_argument("patch_file_or_text", help="Path to patch file or verbatim diff string")
    
    args = parser.parse_args()
    if args.cmd == "status":
        status()
    elif args.cmd == "cancel":
        cancel()
    elif args.cmd == "btw":
        add_btw(args.note)
    elif args.cmd == "run":
        run_agy(args.prompt, continue_session=not args.new, is_async=args.is_async)
    elif args.cmd == "patch":
        if os.path.exists(args.patch_file_or_text):
            with open(args.patch_file_or_text) as f:
                apply_patch(f.read())
        else:
            apply_patch(args.patch_file_or_text)
    else:
        parser.print_help()
