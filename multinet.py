# Program that uses linux namespaces to divide different apps between many networks
import subprocess
import os
import sys
import shlex
import json

CONFIG_PATH = os.path.expanduser("~/.multinet.json")
EXEC_PATH = os.path.dirname(os.path.abspath(sys.argv[0])) + "/multinet-exec"
def load_config():
    if not os.path.exists(CONFIG_PATH):
        return []

    try:
        with open(CONFIG_PATH, "r") as f:
            content = f.read().strip()

            if not content:
                return []

            return json.loads(content)

    except json.JSONDecodeError:
        print("[config] Warning: invalid JSON, resetting config")
        return []

def save_config(config):
    tmp = CONFIG_PATH + ".tmp"

    with open(tmp, "w") as f:
        json.dump(config, f, indent=4)

    os.replace(tmp, CONFIG_PATH)
def restore_namespaces():
    config = load_config()

    if not config:
        print("No namespaces to restore.")
        return

    for entry in config:
        dev = entry["dev"]
        idx = entry["idx"]

        ns = f"mnet_{dev}_{idx}"
        veth_host = f"veth_{dev[:3]}_{idx}_h"
        veth_ns = f"veth_{dev[:3]}_{idx}_n"

        subnet = f"10.200.{idx}.0/24"
        ip_host = f"10.200.{idx}.1/24"
        ip_ns = f"10.200.{idx}.2/24"
        gw_ns = f"10.200.{idx}.1"

        print(f"[restore] Recreating {ns}...")

        try:
            create_namespace_with_veth(ns, veth_host, veth_ns)
            configure_namespace_ip(ns, veth_ns, ip_ns, gw_ns)
            configure_host_routing(idx, veth_host, ip_host, subnet, dev)

            subprocess.run(["sudo", "mkdir", "-p", f"/etc/netns/{ns}"])
            subprocess.run(["sudo", "cp", "/etc/resolv.conf", f"/etc/netns/{ns}/resolv.conf"])

        except Exception as e:
            print(f"[restore] Failed for {ns}: {e}")

def launch_on_dev(dev, command):
    ns = get_namespace_for_dev(dev)

    if ns is None:
        print(f"No namespace found for device '{dev}'")
        return

    cmd = shlex.split(command)

    env = os.environ.copy()

    # Wayland
    if "WAYLAND_DISPLAY" in os.environ:
        env["WAYLAND_DISPLAY"] = os.environ["WAYLAND_DISPLAY"]

    if "XDG_RUNTIME_DIR" in os.environ:
        env["XDG_RUNTIME_DIR"] = os.environ["XDG_RUNTIME_DIR"]

    # X11 fallback
    if "DISPLAY" in os.environ:
        env["DISPLAY"] = os.environ["DISPLAY"]

    print(f"Launched '{command}' on {ns}")

    try:
        print(EXEC_PATH)
        subprocess.Popen(
            
    ["sudo", EXEC_PATH, ns] + cmd,
    env=env)
    except Exception as e:
        print(f"Error launching command: {e}")

def get_namespace_for_dev(dev):
    namespaces = list_multinet_namespaces()
    for ns in namespaces:
        if ns.startswith(f"mnet_{dev}_"):
            return ns
    return None

def create_solonet(): 
    # Guides the user for the creation of network namespace using mk_namespace()
    print("Please select the network interface: \n")
    ni = list_network_interfaces()
    counter = 1
    for i in ni:
        print(counter, ". ", i)
        counter += 1
    choice = int(input("\nEnter your choice: "))
    dev = ni[choice-1]
    if 0 >= choice > counter:
        print("Out of range")
        return
    if hasSolonet(dev):
        print(f"{dev} already has a solonet")
        return
    if not is_interface_up(dev):
        print(f"Interface {dev} is down or not connected")
        return
    mk_namespace(dev)

def list_network_interfaces():
    # Lists available network interfaces by reading /sys/class/net/
    try:
        # Get all interfaces in /sys/class/net and remove 'lo'
        return [iface for iface in os.listdir('/sys/class/net/') if iface != 'lo']
    except FileNotFoundError:
        # If the directory doesn't exist, return an empty list
        return []

def is_interface_up(dev):
    result = subprocess.run(
        ["ip", "link", "show", dev],
        capture_output=True,
        text=True
    )
    return "UP" in result.stdout and "LOWER_UP" in result.stdout

def hasSolonet(dev):
    namespaces = list_multinet_namespaces()
    return any(ns.startswith(f"mnet_{dev}_") for ns in namespaces)

def mk_namespace(dev):
    # Configures a new namespace to connect to the internet only by the device "dev" with the prefix mnet_
    idx, subnet, ip_host, ip_ns, gw_ns = allocate_subnet()
    ns = f"mnet_{dev}_{idx}"
    veth_host = f"veth_{dev[:3]}_{idx}_h"
    veth_ns = f"veth_{dev[:3]}_{idx}_n"

    try:
        create_namespace_with_veth(ns, veth_host, veth_ns)
        configure_namespace_ip(ns, veth_ns, ip_ns, gw_ns)
        configure_host_routing(idx, veth_host, ip_host, subnet, dev)
        
        # DNS
        subprocess.run(["sudo", "mkdir", "-p", f"/etc/netns/{ns}"], check=True)
        subprocess.run(["sudo", "cp", "/etc/resolv.conf", f"/etc/netns/{ns}/resolv.conf"],check=True) 
        
        # Save to config
        config = load_config()
        config.append({"dev": dev, "idx": idx})
        save_config(config)

        print(f"Namespace '{ns}' ready using {dev}")

    except Exception as e:
        print(f"Error creating namespace: {e}")
        return

def get_used_indices():
    namespaces = list_multinet_namespaces()
    indices = set()

    for ns in namespaces:
        # Esperamos formato: mnet_<dev>_<index>
        parts = ns.split("_")
        if len(parts) >= 3:
            try:
                idx = int(parts[-1])
                indices.add(idx)
            except ValueError:
                continue

    return indices

def get_next_index():
    used = get_used_indices()
    i = 1

    while True:
        if i not in used:
            return i
        i += 1

def allocate_subnet():
    idx = get_next_index()

    subnet = f"10.200.{idx}.0/24"
    ip_host = f"10.200.{idx}.1/24"
    ip_ns = f"10.200.{idx}.2/24"
    gw_ns = f"10.200.{idx}.1"

    return idx, subnet, ip_host, ip_ns, gw_ns

def create_namespace_with_veth(ns, veth_host, veth_ns):
    try:
        # Create namespace
        subprocess.run([ "ip", "netns", "add", ns], check=True)

        # Create veth pair
        subprocess.run([
             "ip", "link", "add", veth_host,
            "type", "veth", "peer", "name", veth_ns
        ], check=True)

        # Move one end into namespace
        subprocess.run([
             "ip", "link", "set", veth_ns, "netns", ns
        ], check=True)

    except subprocess.CalledProcessError as e:
        print(f"[create_namespace_with_veth] Error: {e}")

def configure_namespace_ip(ns, veth_ns, ip_ns, gw_ns):
    try:
        # Assign IP
        subprocess.run([
            "ip", "netns", "exec", ns,
            "ip", "addr", "add", ip_ns, "dev", veth_ns
        ], check=True)

        # Bring interface up
        subprocess.run([
            "ip", "netns", "exec", ns,
            "ip", "link", "set", veth_ns, "up"
        ], check=True)

        # Loopback
        subprocess.run([
            "ip", "netns", "exec", ns,
            "ip", "link", "set", "lo", "up"
        ], check=True)

        # Default route
        subprocess.run([
            "ip", "netns", "exec", ns,
            "ip", "route", "add", "default", "via", gw_ns
        ], check=True)

    except subprocess.CalledProcessError as e:
        print(f"[configure_namespace_ip] Error: {e}")

def configure_host_routing(idx, veth_host, ip_host, subnet, dev):
    try:
        table_id = str(100 + idx)

        gateway = get_gateway(dev)

        if gateway is None:
            raise Exception(f"No gateway found for {dev}")

        # Assign IP to host side of veth
        subprocess.run([
             "ip", "addr", "add", ip_host, "dev", veth_host
        ], check=True)

        subprocess.run([
             "ip", "link", "set", veth_host, "up"
        ], check=True)

        # Enable IP forwarding
        subprocess.run([
             "sysctl", "-w", "net.ipv4.ip_forward=1"
        ], check=True)

        # Routing table
        subprocess.run([
            "ip", "route", "add", "default", "via", 
            gateway, "dev", dev,"table", table_id], check=True)

        # Rule: traffic from subnet → use table 100
        subprocess.run([
            "ip", "rule", "add",
            "from", subnet, "table", table_id
        ], check=True)

        # NAT (important for internet access)
        subprocess.run([
            "iptables", "-t", "nat", "-A", "POSTROUTING",
            "-s", subnet, "-o", dev, "-j", "MASQUERADE"
        ], check=True)

    except subprocess.CalledProcessError as e:
        print(f"[configure_host_routing] Error: {e}")

def get_gateway(dev):
    result = subprocess.run(
        ["ip", "route", "get", "1.1.1.1"],
        capture_output=True,
        text=True
    )

    parts = result.stdout.split()

    if "via" in parts:
        return parts[parts.index("via") + 1]

    return None

def delete_solonet():

    namespaces = list_multinet_namespaces()

    if not namespaces:
        print("No solonet namespaces found.")
        return

    print("\nAvailable namespaces:")
    for i, ns in enumerate(namespaces, 1):
        print(f"{i}. {ns}")

    try:
        choice = int(input("\nSelect a namespace to delete (number): "))
        if choice < 1 or choice > len(namespaces):
            print("Invalid selection.")
            return
    except ValueError:
        print("Please enter a valid number.")
        return

    selected_ns = namespaces[choice - 1]
    confirm = input(f"Are you sure you want to delete '{selected_ns}'? (y/N): ").lower()
    if confirm != 'y':
        print("Operation cancelled.")
        return

    rm_namespace(selected_ns)

def rm_namespace(ns):
    # Deconfigures the "ns" namespace

    # Parse namespace name: mnet_<dev>_<idx>
    if not ns.startswith("mnet_"):
        print(f"[rm_namespace] Invalid namespace format: {ns}")
        return

    parts = ns.split("_")
    if len(parts) < 3:
        print(f"[rm_namespace] Invalid namespace format: {ns}")
        return

    try:
        dev = parts[1]
        idx = int(parts[2])
    except (ValueError, IndexError):
        print(f"[rm_namespace] Could not parse dev and idx from namespace: {ns}")
        return

    # Reconstruct parameters
    subnet = f"10.200.{idx}.0/24"
    veth_host = f"veth_{dev[:3]}_{idx}_h"
    table_id = str(100 + idx)

    print(f"[rm_namespace] Cleaning up namespace {ns} (dev={dev}, idx={idx}, subnet={subnet}, veth_host={veth_host}, table={table_id})")

    # Cleanup steps
    cleanup_steps = [
        ("Remove iptables NAT rule",
         ["iptables", "-t", "nat", "-D", "POSTROUTING", "-s", subnet, "-o", dev, "-j", "MASQUERADE"]),

        ("Remove IP rule",
         ["ip", "rule", "del", "from", subnet, "table", table_id]),

        ("Remove route",
         ["ip", "route", "del", "default", "dev", dev, "table", table_id]),

        ("Delete namespace",
         ["ip", "netns", "delete", ns]),

        ("Delete host-side veth",
         ["ip", "link", "delete", veth_host])
    ]

    # Execute steps
    for description, command in cleanup_steps:
        try:
            result = subprocess.run(command, check=False, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"[rm_namespace] Warning: {description} failed (exit {result.returncode}): {result.stderr.strip()}")
            else:
                print(f"[rm_namespace] Success: {description}")
        except Exception as e:
            print(f"[rm_namespace] Error executing {description}: {e}")
    config = load_config()
    config = [c for c in config if not (c["dev"] == dev and c["idx"] == idx)]
    save_config(config)
    print(f"[rm_namespace] Cleanup completed for namespace {ns}")

def list_multinet_namespaces():
    try:
        result = subprocess.run(
            ["ip", "netns"],
            capture_output=True,
            text=True,
            check=True
        )
    except subprocess.CalledProcessError as e:
        print(f"Error listing namespaces: {e}")
        return []

    namespaces = []
    for line in result.stdout.splitlines():
        # Formato típico: "mnet_xxx (id: 1)" o solo "mnet_xxx"
        name = line.split()[0]
        if name.startswith("mnet_"):
            namespaces.append(name)

    return namespaces
    
def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--restore":
        restore_namespaces()
        return
    
    # Check if launched with arguments
    if len(sys.argv) > 2:
        dev = sys.argv[1]
        command = " ".join(sys.argv[2:])
        launch_on_dev(dev, command)
        return

# Check for root
    if os.geteuid() != 0:
        print("This program must be run as root (use sudo).")
        exit(1)

    while True:
        print("\nMenu:")
        print("1. Create solonet")
        print("2. Delete solonet")
        print("3. Exit")
        choice = input("Enter your choice: ")
        
        if choice == '1':
            create_solonet()
        elif choice == '2':
            delete_solonet()
        elif choice == '3':
            print("Exiting...")
            break
        else:
            print("Invalid choice. Please try again.")

if __name__ == "__main__":
    main()
