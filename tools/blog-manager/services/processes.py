from __future__ import annotations

import atexit
import os
import shutil
import socket
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any


class BlogProcessService:
    def __init__(self, blog_root: Path, preview_port: int = 4321):
        self.blog_root = blog_root
        self.preview_port = preview_port
        self._preview: subprocess.Popen[str] | None = None
        self._logs: deque[str] = deque(maxlen=600)
        self._lock = threading.Lock()
        atexit.register(self.stop_preview)

    def _pnpm(self) -> str | None:
        managed_environment = Path(self.blog_root.anchor) / "Environments" / "05_NodeJS"
        candidates = [
            shutil.which("pnpm.cmd"),
            shutil.which("pnpm"),
            str(Path(os.environ.get("PNPM_HOME", "")) / "pnpm.cmd") if os.environ.get("PNPM_HOME") else None,
            str(Path(os.environ.get("APPDATA", "")) / "npm" / "pnpm.cmd") if os.environ.get("APPDATA") else None,
            str(Path(os.environ.get("LOCALAPPDATA", "")) / "pnpm" / "pnpm.cmd") if os.environ.get("LOCALAPPDATA") else None,
            str(managed_environment / "pnpm" / "bin" / "pnpm.CMD"),
        ]
        return next((candidate for candidate in candidates if candidate and Path(candidate).is_file()), None)

    def _node(self) -> str:
        bundled = self.blog_root / "tools" / "blog-manager" / "runtime" / "node.exe"
        managed = Path(self.blog_root.anchor) / "Environments" / "05_NodeJS" / "Node" / "node.exe"
        executable = shutil.which("node.exe") or shutil.which("node")
        if executable:
            return executable
        if managed.is_file():
            return str(managed)
        if bundled.is_file():
            return str(bundled)
        raise RuntimeError(
            "Neither pnpm nor Node.js could be found. Restore tools/blog-manager/runtime/node.exe or install Node.js."
        )

    def _dev_command(self) -> list[str]:
        pnpm = self._pnpm()
        if pnpm:
            return [pnpm, "dev", "--host", "127.0.0.1", "--port", str(self.preview_port)]
        astro = self.blog_root / "node_modules" / "astro" / "bin" / "astro.mjs"
        if not astro.is_file():
            raise RuntimeError("Astro dependencies are missing. Run pnpm install in the blog directory first.")
        return [self._node(), str(astro), "dev", "--host", "127.0.0.1", "--port", str(self.preview_port)]

    def _environment(self) -> dict[str, str]:
        environment = os.environ.copy()
        # Keep Astro from creating telemetry state under the Windows user profile.
        environment["ASTRO_TELEMETRY_DISABLED"] = "1"
        bundled_node = self.blog_root / "tools" / "blog-manager" / "runtime"
        managed_environment = Path(self.blog_root.anchor) / "Environments" / "05_NodeJS"
        managed_node = managed_environment / "Node"
        managed_pnpm = managed_environment / "pnpm" / "bin"
        search_paths = [path for path in (managed_node, managed_pnpm, bundled_node) if path.is_dir()]
        if search_paths:
            environment["PATH"] = os.pathsep.join(map(str, search_paths)) + os.pathsep + environment.get("PATH", "")
        if managed_pnpm.is_dir():
            environment.setdefault("PNPM_HOME", str(managed_environment / "pnpm"))
        return environment

    def _creation_flags(self) -> int:
        return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

    def _port_open(self) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
            client.settimeout(0.2)
            return client.connect_ex(("127.0.0.1", self.preview_port)) == 0

    def _read_logs(self, process: subprocess.Popen[str]) -> None:
        if process.stdout is None:
            return
        for line in process.stdout:
            self._logs.append(line.rstrip())

    def preview_status(self) -> dict[str, Any]:
        process = self._preview
        running = process is not None and process.poll() is None
        return {
            "running": running,
            "external": not running and self._port_open(),
            "url": f"http://127.0.0.1:{self.preview_port}/zh-cn/",
            "logs": "\n".join(self._logs),
            "pid": process.pid if running else None,
        }

    def start_preview(self) -> dict[str, Any]:
        with self._lock:
            if self._preview is not None and self._preview.poll() is None:
                return self.preview_status()
            if self._port_open():
                raise RuntimeError(f"Port {self.preview_port} is already in use by another process")
            self._logs.clear()
            self._preview = subprocess.Popen(
                self._dev_command(),
                cwd=self.blog_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=self._creation_flags(),
                env=self._environment(),
            )
            threading.Thread(target=self._read_logs, args=(self._preview,), daemon=True).start()
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            if self._preview.poll() is not None:
                raise RuntimeError("Preview exited before it became ready\n" + "\n".join(self._logs))
            if self._port_open():
                return self.preview_status()
            time.sleep(0.15)
        self.stop_preview()
        raise RuntimeError("Preview did not become ready within 12 seconds")

    def stop_preview(self) -> dict[str, Any]:
        with self._lock:
            process = self._preview
            self._preview = None
        if process is None or process.poll() is not None:
            return self.preview_status()
        if os.name == "nt":
            # pnpm.cmd prompts "Terminate batch job (Y/N)?" on CTRL_BREAK and can
            # orphan Astro. taskkill targets only the process we started and its tree.
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                creationflags=self._creation_flags(),
            )
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        else:
            try:
                process.terminate()
                process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                process.kill()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    pass
        deadline = time.monotonic() + 3
        while self._port_open() and time.monotonic() < deadline:
            time.sleep(0.05)
        return self.preview_status()

    def build(self) -> dict[str, Any]:
        pnpm = self._pnpm()
        if pnpm:
            commands = [[pnpm, "build"]]
        else:
            node = self._node()
            astro = self.blog_root / "node_modules" / "astro" / "bin" / "astro.mjs"
            pagefind = self.blog_root / "node_modules" / "pagefind" / "lib" / "runner" / "bin.cjs"
            if not astro.is_file() or not pagefind.is_file():
                raise RuntimeError("Blog dependencies are missing. Run pnpm install in the blog directory first.")
            commands = [
                [node, str(astro), "check"],
                [node, str(astro), "build"],
                [node, str(pagefind), "--site", "dist"],
            ]
        output_parts: list[str] = []
        return_code = 0
        for command in commands:
            completed = subprocess.run(
                command,
                cwd=self.blog_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
                env=self._environment(),
                creationflags=self._creation_flags(),
            )
            output_parts.extend((completed.stdout or "", completed.stderr or ""))
            return_code = completed.returncode
            if return_code != 0:
                break
        return {"success": return_code == 0, "returnCode": return_code, "output": "".join(output_parts)}
