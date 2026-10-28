#!/usr/bin/env python3
"""Boot a OneBoot ISO in a diskless QEMU VM and capture the VGA screen."""

from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import json
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path


def qmp_command(connection: socket.socket, execute: str, arguments: dict | None = None) -> dict:
    payload: dict[str, object] = {"execute": execute}
    if arguments:
        payload["arguments"] = arguments
    connection.sendall(json.dumps(payload).encode("utf-8") + b"\r\n")

    stream = connection.makefile("rb", buffering=0)
    while True:
        response = json.loads(stream.readline())
        if "return" in response or "error" in response:
            return response


def send_text(connection: socket.socket, value: str) -> None:
    key_names = {".": "dot", "/": "slash", "\n": "ret", " ": "spc", "-": "minus", ":": "shift-semicolon"}
    for character in value:
        key_name = key_names.get(character, character.lower())
        if character.isupper():
            key_name = f"shift-{character.lower()}"
        result = qmp_command(
            connection,
            "human-monitor-command",
            {"command-line": f"sendkey {key_name}"},
        )
        if "error" in result:
            raise RuntimeError(json.dumps(result["error"]))
        time.sleep(0.12)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--firmware", choices=("bios", "uefi"), required=True)
    parser.add_argument("--menu-layout", choices=("legacy", "descending"), default="legacy",
                        help="legacy through v0.9.2; descending/direct OS choices in v0.9.3")
    parser.add_argument(
        "--acceleration",
        choices=("tcg", "kvm"),
        default="tcg",
        help="QEMU accelerator; KVM requires access to /dev/kvm",
    )
    parser.add_argument("--iso", type=Path, required=True)
    parser.add_argument("--dual-boot", action="store_true",
                        help="select an independent environment from the combined ISO")
    parser.add_argument("--stock-netboot", action="store_true",
                        help="netboot uses its original DHCP/startup flow, without our static form")
    parser.add_argument("--restrict-network", action="store_true",
                        help="allow only configured guest-forward services in a controlled test")
    parser.add_argument("--network-pcap", type=Path,
                        help="capture guest network frames for DHCP absence checks")
    parser.add_argument("--direct-legacy-live", action="store_true",
                        help="diagnostic only: boot the Ubuntu 18/20 kernel directly, not the ISO")
    parser.add_argument("--direct-proxmox-probe", action="store_true",
                        help="diagnostic only: upstream kernel/initrd and upstream ISO as CD-ROM")
    parser.add_argument("--ipxe-proxmox-probe", action="store_true",
                        help="diagnostic only: chain the verbose Proxmox probe script from iPXE shell")
    parser.add_argument("--screenshot", type=Path, required=True)
    parser.add_argument("--file-backed-memory", action="store_true",
                        help="reclaimable temporary shared-file RAM, never a guest disk")
    parser.add_argument("--stop-at-reference-header", type=Path,
                        help="stop Proxmox wait when the first 160 pixel rows match a reviewed GUI reference")
    parser.add_argument("--wait-seconds", type=float, default=12.0)
    parser.add_argument("--startup-reference", type=Path,
                        help="wait up to 150 seconds for the reviewed OneBoot header before input")
    parser.add_argument(
        "--memory-mb",
        type=int,
        default=None,
        help="override the target-specific guest RAM allocation",
    )
    parser.add_argument(
        "--target-wait-seconds",
        type=float,
        default=None,
        help="override the target-specific wait before the final screenshot",
    )
    parser.add_argument(
        "--post-target-sendkeys",
        default=None,
        help="comma-separated QEMU key names to send after the target wait",
    )
    parser.add_argument(
        "--post-target-key-delay-seconds",
        type=float,
        default=0.25,
        help="delay between post-target keys when installer screens need time to update",
    )
    parser.add_argument(
        "--guest-network-diagnostics",
        action="store_true",
        help="capture read-only IPv4, route and DNS diagnostics on Debian installer tty2",
    )
    parser.add_argument(
        "--guest-live-diagnostics",
        action="store_true",
        help="capture read-only network and RAM ISO mount diagnostics on Ubuntu live tty2",
    )
    parser.add_argument(
        "--post-target-wait-seconds",
        type=float,
        default=0.0,
        help="additional wait after --post-target-sendkeys",
    )
    parser.add_argument("--post-target-checkpoint-interval",type=float,default=0,
                        help="capture progress periodically during the post-key wait")
    parser.add_argument("--post-target-stop-file",type=Path,
                        help="end the observation wait after an operator creates this marker")
    parser.add_argument(
        "--checkpoint-start-seconds",
        type=float,
        default=None,
        help="for WinPE diagnostics, start periodic screenshots after this delay",
    )
    parser.add_argument(
        "--checkpoint-interval",
        type=float,
        default=1.0,
        help="seconds between WinPE diagnostic screenshots",
    )
    parser.add_argument(
        "--target",
        choices=(
            "boot-selector",
            "netboot-form",
            "netboot-summary",
            "netboot-menu",
            "netboot-invalid",
            "menu",
            "main-menu",
            "proxmox-menu",
            "proxmox-7",
            "proxmox-8",
            "proxmox-9",
            "tools",
            "minitool-menu",
            "memtest",
            "rescue",
            "winpe",
            "minitool",
            "ubuntu-https",
            "network-summary",
            "almalinux-menu",
            "almalinux-810",
            "almalinux-98",
            "almalinux-102",
            "debian-menu",
            "debian-10",
            "debian-11",
            "debian-12",
            "debian-13",
            "ubuntu-menu",
            "ubuntu-1804-menu",
            "ubuntu-2004-menu",
            "ubuntu-1804-live",
            "ubuntu-2004-live",
            "ubuntu-1804-net",
            "ubuntu-2004-net",
        ),
        default="menu",
        help="screen or boot path to exercise in the diskless VM",
    )
    parser.add_argument(
        "--exercise-https",
        action="store_true",
        help="enter the QEMU user-network settings and attempt an Ubuntu HTTPS download",
    )
    parser.add_argument(
        "--guestfwd-https-port",
        type=int,
        default=None,
        help="forward guest 93.114.194.66:443 to this host loopback TCP port",
    )
    parser.add_argument(
        "--test-ip",
        default=None,
        help="override the static IPv4 address entered by the harness",
    )
    parser.add_argument(
        "--test-prefix",
        type=int,
        default=24,
        help="CIDR prefix entered by the harness (default: 24)",
    )
    parser.add_argument("--test-dns", default=None,
                        help="override DNS entered by the controlled network test")
    parser.add_argument(
        "--auto-network-defaults",
        action="store_true",
        help="enter IPv4/prefix together and accept the v0.8 gateway/DNS defaults",
    )
    args = parser.parse_args()
    if args.post_target_checkpoint_interval==0 and args.post_target_wait_seconds>=240:
        args.post_target_checkpoint_interval=30
    target = "ubuntu-https" if args.exercise_https else args.target
    if args.menu_layout == "descending" and target in ("ubuntu-1804-menu", "ubuntu-2004-menu"):
        raise ValueError("Ubuntu method submenus were removed in v0.9.3; use ubuntu-menu")
    iso = args.iso.resolve(strict=True)
    iso_sha256 = hashlib.sha256(iso.read_bytes()).hexdigest()
    screenshot = args.screenshot.resolve()
    header_matched = False
    screenshot.parent.mkdir(parents=True, exist_ok=True)

    with ExitStack() as resources, tempfile.TemporaryDirectory(prefix="oneboot-qemu-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        qmp_socket = temp_dir / "qmp.sock"
        memory_mb = "768"
        if target in (
            "rescue",
            "winpe",
            "minitool",
            "almalinux-810",
            "almalinux-98",
            "almalinux-102",
            "debian-10",
            "debian-11",
            "debian-12",
            "debian-13",
        ):
            memory_mb = "2560"
        if args.memory_mb is not None:
            if args.memory_mb < 256:
                raise ValueError("--memory-mb must be at least 256")
            memory_mb = str(args.memory_mb)

        restrict_network = "on" if target in ("menu", "tools", "network-summary") else "off"
        if args.restrict_network:
            restrict_network = "on"
        netdev = f"user,id=fbnet,restrict={restrict_network}"
        test_ip = args.test_ip or "10.0.2.15"
        test_gateway = "10.0.2.2"
        if args.guestfwd_https_port is not None:
            netdev = (
                f"user,id=fbnet,restrict={restrict_network},"
                "net=93.114.194.0/24,host=93.114.194.1,"
                "guestfwd=tcp:93.114.194.66:443-"
                f"cmd:nc 127.0.0.1 {args.guestfwd_https_port}"
            )
            test_ip = args.test_ip or "93.114.194.100"
            test_gateway = "93.114.194.1"

        command = [
            "qemu-system-x86_64",
            "-m",
            memory_mb,
            "-boot",
            "once=d",
            "-cdrom",
            str(iso),
            "-netdev",
            netdev,
            "-device",
            "e1000,netdev=fbnet,romfile=",
            "-device",
            "virtio-rng-pci",
            "-display",
            "none",
            "-serial",
            "none",
            "-qmp",
            f"unix:{qmp_socket},server=on,wait=off",
            "-no-reboot",
        ]
        if args.network_pcap:
            command.extend(['-object', f'filter-dump,id=nbcapture,netdev=fbnet,file={args.network_pcap.resolve()}'])
        if args.direct_legacy_live:
            if target not in ("ubuntu-1804-live", "ubuntu-2004-live") or args.test_prefix != 24:
                raise ValueError("Direct live probe requires an Ubuntu 18/20 live target and /24")
            version = "18.04.6" if "1804" in target else "20.04.6"
            asset = Path('/srv/oneboot/assets/ubuntu') / version
            del command[3:7]  # remove -boot once=d -cdrom ISO; this is explicitly NOT an ISO test
            command.extend(['-kernel', str(asset / 'vmlinuz'), '-initrd', str(asset / 'initrd'),
                '-append', f'boot=casper root=/dev/ram0 BOOTIF=01-52-54-00-12-34-56 ip={test_ip}::{test_gateway}:255.255.255.0:::none oneboot.iso=https://93.114.194.66/oneboot/ubuntu/ubuntu-{version}-live-server-amd64.iso oneboot_legacy=1 oneboot.prefix=24 oneboot.dns=8.8.8.8 cloud-config-url=/dev/null ---'])

        if args.file_backed_memory:
            # /tmp can itself be a small tmpfs. Back guest RAM on the capture
            # filesystem so the host can reclaim pages to its actual disk.
            memory_dir=resources.enter_context(tempfile.TemporaryDirectory(
                prefix='.oneboot-memory-',dir=screenshot.parent))
            memory_file = Path(memory_dir) / "guest-memory"
            command.extend(["-object", f"memory-backend-file,id=fbmem,size={memory_mb}M,mem-path={memory_file},share=on",
                            "-numa", "node,memdev=fbmem"])

        if args.direct_proxmox_probe:
            version = {"proxmox-9": "9.2-1", "proxmox-8": "8.4-1", "proxmox-7": "7.4-1"}[target]
            asset = Path('/srv/oneboot/assets/proxmox') / version
            command[command.index('-cdrom') + 1] = str(asset / 'proxmox.iso')
            command[command.index('-serial') + 1] = f"file:{screenshot.with_suffix('.serial.log')}"
            command.extend(['-kernel', str(asset / 'linux26'), '-initrd', str(asset / 'initrd.img'),
                            '-append', 'ramdisk_size=16777216 rw console=tty0 console=ttyS0,115200'])
        if args.ipxe_proxmox_probe:
            command[command.index('-serial') + 1] = f"file:{screenshot.with_suffix('.serial.log')}"

        if args.acceleration == "kvm":
            command[1:1] = ["-enable-kvm", "-cpu", "host"]
        elif target in (
            "winpe",
            "minitool",
            "almalinux-810",
            "almalinux-98",
            "almalinux-102",
        ):
            command[1:1] = ["-cpu", "max"]

        if args.firmware == "uefi":
            code = Path("/usr/share/OVMF/OVMF_CODE_4M.fd")
            vars_template = Path("/usr/share/OVMF/OVMF_VARS_4M.fd")
            vars_copy = temp_dir / "OVMF_VARS_4M.fd"
            shutil.copy2(vars_template, vars_copy)
            command[1:1] = ["-machine", "q35"]
            command.extend(
                [
                    "-drive",
                    f"if=pflash,format=raw,readonly=on,file={code}",
                    "-drive",
                    f"if=pflash,format=raw,file={vars_copy}",
                ]
            )
        else:
            command[1:1] = ["-machine", "pc"]

        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 10
            while not qmp_socket.exists():
                if process.poll() is not None:
                    raise RuntimeError(process.stderr.read())
                if time.monotonic() >= deadline:
                    raise TimeoutError("QMP socket was not created")
                time.sleep(0.1)

            connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            while True:
                try:
                    connection.connect(str(qmp_socket))
                    break
                except ConnectionRefusedError:
                    if process.poll() is not None:
                        raise RuntimeError(process.stderr.read())
                    if time.monotonic() >= deadline:
                        raise TimeoutError("QMP socket did not accept connections")
                    time.sleep(0.1)

            with connection:
                greeting = connection.recv(65536)
                if b"QMP" not in greeting:
                    raise RuntimeError("QMP greeting was not received")
                qmp_command(connection, "qmp_capabilities")
                time.sleep(args.wait_seconds)
                if args.startup_reference:
                    def startup_header(path):
                        magic, dimensions, maximum, pixels = path.read_bytes().split(b'\n', 3)
                        assert magic == b'P6' and maximum == b'255'
                        width, height = map(int, dimensions.split())
                        return dimensions, pixels[:width * min(height, 160) * 3]
                    reference = startup_header(args.startup_reference)
                    startup_capture = Path(temp_dir_name)/'startup.ppm'
                    deadline = time.monotonic()+150
                    while True:
                        qmp_command(connection, 'screendump', {'filename':str(startup_capture)})
                        if startup_header(startup_capture)==reference:
                            break
                        if time.monotonic()>=deadline:
                            raise RuntimeError('OneBoot header did not appear before input')
                        time.sleep(2)
                if args.dual_boot and target != 'boot-selector':
                    send_text(connection, '2' if target.startswith('netboot-') else '1')
                    if args.firmware == 'bios':
                        send_text(connection, '\n')
                    time.sleep(3)
                if target.startswith('netboot-') and target != 'netboot-form' and not args.stock_netboot:
                    send_text(connection, '\n')
                    send_text(connection, ('999.1.2.3' if target == 'netboot-invalid' else test_ip) + '\n')
                    send_text(connection, '255.255.255.0\n')
                    send_text(connection, test_gateway + '\n')
                    send_text(connection, '8.8.8.8\n')
                    time.sleep(2)
                    if target == 'netboot-menu':
                        send_text(connection, 'c')
                if target not in ('menu', 'boot-selector') and not target.startswith('netboot-') and not (args.direct_legacy_live or args.direct_proxmox_probe):
                    send_text(connection, "0")
                    time.sleep(1)
                    if args.auto_network_defaults:
                        send_text(connection, f"{test_ip}/{args.test_prefix}\n")
                        send_text(connection, "\n")
                        if args.test_dns:
                            qmp_command(connection,"human-monitor-command",{"command-line":"sendkey ctrl-u"})
                            time.sleep(0.2)
                        send_text(connection, (args.test_dns or "") + "\n")
                    else:
                        send_text(connection, f"{test_ip}\n")
                        send_text(connection, f"{args.test_prefix}\n")
                        send_text(connection, f"{test_gateway}\n")
                        send_text(connection, (args.test_dns or "1.1.1.1") + "\n")
                    time.sleep(1)
                    if target == "network-summary":
                        time.sleep(2)
                    else:
                        send_text(connection, "c")
                        time.sleep(1)

                if args.direct_legacy_live or args.direct_proxmox_probe:
                    time.sleep(args.target_wait_seconds if args.target_wait_seconds is not None else 120)
                elif target.startswith('netboot-'):
                    time.sleep(args.target_wait_seconds if args.target_wait_seconds is not None else 20)
                elif target == "tools":
                    send_text(connection, "t")
                    time.sleep(2)
                elif target == "minitool-menu":
                    send_text(connection, "t")
                    time.sleep(1)
                    send_text(connection, "4")
                    time.sleep(2)
                elif target == "memtest":
                    send_text(connection, "t")
                    time.sleep(1)
                    send_text(connection, "2")
                    time.sleep(1)
                    send_text(connection, "1")
                    time.sleep(15)
                elif target == "rescue":
                    send_text(connection, "t")
                    time.sleep(1)
                    send_text(connection, "1")
                    time.sleep(1)
                    send_text(connection, "1")
                    time.sleep(240)
                elif target == "winpe":
                    send_text(connection, "t")
                    time.sleep(1)
                    send_text(connection, "3")
                    time.sleep(1)
                    send_text(connection, "1")
                    target_wait = args.target_wait_seconds if args.target_wait_seconds is not None else 150
                    if args.checkpoint_start_seconds is None:
                        time.sleep(target_wait)
                    else:
                        checkpoint_start = min(args.checkpoint_start_seconds, target_wait)
                        time.sleep(checkpoint_start)
                        deadline = time.monotonic() + (target_wait - checkpoint_start)
                        checkpoint_number = 0
                        while process.poll() is None and time.monotonic() < deadline:
                            checkpoint = screenshot.with_name(
                                f"{screenshot.stem}-checkpoint-{checkpoint_number:03d}{screenshot.suffix}"
                            )
                            result = qmp_command(
                                connection,
                                "screendump",
                                {"filename": str(checkpoint)},
                            )
                            if "error" in result:
                                raise RuntimeError(json.dumps(result["error"]))
                            checkpoint_number += 1
                            time.sleep(args.checkpoint_interval)
                elif target == "minitool":
                    send_text(connection, "t")
                    time.sleep(1)
                    send_text(connection, "4")
                    time.sleep(1)
                    send_text(connection, "1")
                    target_wait = args.target_wait_seconds if args.target_wait_seconds is not None else 150
                    time.sleep(target_wait)
                elif target == "ubuntu-https":
                    send_text(connection, "2")
                    time.sleep(12)
                elif target == "ubuntu-menu" or target.startswith(("ubuntu-1804-", "ubuntu-2004-")):
                    send_text(connection, "u")
                    time.sleep(1)
                    if target != "ubuntu-menu":
                        if args.menu_layout == "descending":
                            key = {"ubuntu-2004-live": "4", "ubuntu-1804-live": "5",
                                   "ubuntu-2004-net": "6", "ubuntu-1804-net": "7"}[target]
                            send_text(connection, key)
                        else:
                            send_text(connection, "4" if "1804" in target else "5")
                            time.sleep(1)
                            if not target.endswith("-menu"):
                                send_text(connection, "1" if target.endswith("-live") else "2")
                    time.sleep(args.target_wait_seconds if args.target_wait_seconds is not None else 90)
                elif target == "almalinux-menu":
                    send_text(connection, "a")
                    time.sleep(2)
                elif target in ("almalinux-810", "almalinux-98", "almalinux-102"):
                    alma_key = {
                        "almalinux-810": "1",
                        "almalinux-98": "2",
                        "almalinux-102": "3",
                    }[target]
                    if args.menu_layout == "descending":
                        alma_key = {"almalinux-810": "3", "almalinux-98": "2", "almalinux-102": "1"}[target]
                    send_text(connection, "a")
                    time.sleep(1)
                    send_text(connection, alma_key)
                    target_wait = args.target_wait_seconds if args.target_wait_seconds is not None else 180
                    time.sleep(target_wait)
                elif target == "debian-menu":
                    send_text(connection, "d")
                    time.sleep(2)
                elif target.startswith("proxmox-"):
                    if args.ipxe_proxmox_probe:
                        send_text(connection, "s")
                        time.sleep(1)
                        send_text(connection, "chain https://93.114.194.66/oneboot/proxmox/probe.ipxe\n")
                    else:
                        send_text(connection, "p")
                        time.sleep(1)
                        if target != "proxmox-menu":
                            send_text(connection, {"proxmox-9": "1", "proxmox-8": "2", "proxmox-7": "3"}[target])
                    deadline = time.monotonic() + (args.target_wait_seconds if args.target_wait_seconds is not None else 180)
                    checkpoint_number = 0
                    while time.monotonic() < deadline and process.poll() is None:
                        time.sleep(min(30, max(0, deadline - time.monotonic())))
                        checkpoint = screenshot.with_name(f"{screenshot.stem}-checkpoint-{checkpoint_number:03d}{screenshot.suffix}")
                        qmp_command(connection, "screendump", {"filename": str(checkpoint)})
                        checkpoint_number += 1
                        if args.stop_at_reference_header:
                            def header_pixels(path):
                                magic, dimensions, maximum, pixels = path.read_bytes().split(b'\n', 3)
                                assert magic == b'P6' and maximum == b'255'
                                width, height = map(int, dimensions.split())
                                return dimensions, pixels[:width * min(height, 160) * 3]
                            if header_pixels(checkpoint) == header_pixels(args.stop_at_reference_header):
                                header_matched = True
                                # The header renders before hardware discovery fills
                                # the content pane. Allow the original GUI to settle.
                                time.sleep(30)
                                break
                elif target in ("debian-10", "debian-11", "debian-12", "debian-13"):
                    debian_key = {
                        "debian-10": "1",
                        "debian-11": "2",
                        "debian-12": "3",
                        "debian-13": "4",
                    }[target]
                    if args.menu_layout == "descending":
                        debian_key = {"debian-10": "4", "debian-11": "3", "debian-12": "2", "debian-13": "1"}[target]
                    send_text(connection, "d")
                    time.sleep(1)
                    send_text(connection, debian_key)
                    target_wait = args.target_wait_seconds if args.target_wait_seconds is not None else 120
                    time.sleep(target_wait)
                if args.post_target_sendkeys:
                    for key_name in args.post_target_sendkeys.split(","):
                        key_name = key_name.strip()
                        if not key_name:
                            continue
                        result = qmp_command(
                            connection,
                            "human-monitor-command",
                            {"command-line": f"sendkey {key_name}"},
                        )
                        if "error" in result:
                            raise RuntimeError(json.dumps(result["error"]))
                        time.sleep(args.post_target_key_delay_seconds)
                    if args.post_target_checkpoint_interval>0:
                        deadline=time.monotonic()+args.post_target_wait_seconds
                        checkpoint_number=0
                        while time.monotonic()<deadline:
                            time.sleep(min(args.post_target_checkpoint_interval,max(0,deadline-time.monotonic())))
                            checkpoint=screenshot.with_name(f'{screenshot.stem}-progress-{checkpoint_number:03d}{screenshot.suffix}')
                            qmp_command(connection,'screendump',{'filename':str(checkpoint)})
                            checkpoint_number+=1
                            if args.post_target_stop_file and args.post_target_stop_file.exists():
                                break
                    else:
                        time.sleep(args.post_target_wait_seconds)
                if args.guest_network_diagnostics:
                    ubuntu_net = target in ("ubuntu-1804-net", "ubuntu-2004-net")
                    if not ubuntu_net and (not target.startswith("debian-") or target == "debian-menu"):
                        raise ValueError("Guest diagnostics require a Debian or Ubuntu net installer")
                    installer_capture = screenshot.with_name(f"{screenshot.stem}-installer{screenshot.suffix}")
                    qmp_command(connection, "screendump", {"filename": str(installer_capture)})
                    qmp_command(connection, "human-monitor-command", {"command-line": "sendkey alt-f2"})
                    time.sleep(2)
                    send_text(connection, "\n")
                    time.sleep(2)
                    send_text(connection, "ip -4 a\nip r\ncat /etc/resolv.conf\n")
                    time.sleep(2)
                    qmp_command(connection, "screendump", {"filename": str(screenshot)})
                    suite = {"debian-10": "buster", "debian-11": "bullseye", "debian-12": "bookworm", "debian-13": "trixie", "ubuntu-1804-net": "bionic", "ubuntu-2004-net": "focal"}[target]
                    mirror = "archive.ubuntu.com" if ubuntu_net else ("archive.debian.org" if target == "debian-10" else "deb.debian.org")
                    archive = "ubuntu" if ubuntu_net else "debian"
                    send_text(connection, f"wget -T 8 -qO /tmp/release http://{mirror}/{archive}/dists/{suite}/Release\n")
                    time.sleep(10)
                    send_text(connection, "head -n 7 /tmp/release\n")
                    time.sleep(2)
                    screenshot = screenshot.with_name(f"{screenshot.stem}-mirror{screenshot.suffix}")
                if args.guest_live_diagnostics:
                    if target not in ("ubuntu-1804-live", "ubuntu-2004-live"):
                        raise ValueError("Live diagnostics require Ubuntu 18/20 live targets")
                    qmp_command(connection, "screendump", {"filename": str(screenshot)})
                    qmp_command(connection, "human-monitor-command", {"command-line": "sendkey ctrl-alt-f2"})
                    time.sleep(15)
                    send_text(connection, "\nclear\nip -4 a\nip r\nsystemd-resolve --status --no-pager\n")
                    time.sleep(3)
                    network_capture = screenshot.with_name(f"{screenshot.stem}-network{screenshot.suffix}")
                    qmp_command(connection, "screendump", {"filename": str(network_capture)})
                    send_text(connection, "findmnt /cdrom\nsudo ls -lh /run/oneboot-iso\nsudo cat /etc/netplan/99-oneboot-static.yaml\n")
                    time.sleep(3)
                    screenshot = screenshot.with_name(f"{screenshot.stem}-ram{screenshot.suffix}")
                if process.poll() is not None:
                    raise RuntimeError(
                        f"QEMU exited before the screenshot (code {process.returncode}): "
                        f"{process.stderr.read()}"
                    )
                result = qmp_command(connection, "screendump", {"filename": str(screenshot)})
                if "error" in result:
                    raise RuntimeError(json.dumps(result["error"]))
                status = qmp_command(connection, "query-status")
                probe_registers = qmp_command(connection, "human-monitor-command", {"command-line": "info registers"}) if args.ipxe_proxmox_probe else None
                qmp_command(connection, "quit")

            process.wait(timeout=10)
            if not screenshot.is_file() or screenshot.stat().st_size == 0:
                raise RuntimeError("QEMU did not create a screenshot")
            print(
                json.dumps(
                    {
                        "firmware": args.firmware,
                        "target": target,
                        "menu_layout": args.menu_layout,
                        "iso": str(iso),
                        "iso_sha256": iso_sha256,
                        "boot_method": ("direct-kernel-probe" if (args.direct_legacy_live or args.direct_proxmox_probe)
                                        else "ipxe-script-probe" if args.ipxe_proxmox_probe else "oneboot-iso"),
                        "guest_memory_mb": int(memory_mb),
                        "file_backed_memory": args.file_backed_memory,
                        "guest_disks": [],
                        "reference_header_matched": header_matched,
                        "screenshot": str(screenshot),
                        "bytes": screenshot.stat().st_size,
                        "vm_status": status.get("return", {}),
                        "probe_registers": probe_registers,
                    },
                    sort_keys=True,
                )
            )
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)

    return 2 if args.stop_at_reference_header and not header_matched else 0


if __name__ == "__main__":
    raise SystemExit(main())
