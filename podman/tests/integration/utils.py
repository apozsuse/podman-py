#   Copyright 2020 Red Hat, Inc.
#
#   Licensed under the Apache License, Version 2.0 (the "License"); you may
#   not use this file except in compliance with the License. You may obtain
#   a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#   WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#   License for the specific language governing permissions and limitations
#   under the License.
#
"""Integration Test Utils"""
import logging
import os
import shutil
import subprocess
import threading
import time
from typing import List, Optional

import podman.tests.errors as errors

logger = logging.getLogger("podman.service")


class PodmanLauncher:
    """Podman service launcher"""

    def __init__(
        self,
        socket_uri: str,
        podman_path: Optional[str] = None,
        timeout: int = 0,
        privileged: bool = False,
        log_level: int = logging.WARNING,
    ) -> None:
        """create a launcher and build podman command"""
        podman_exe: str = podman_path
        if not podman_exe:
            podman_exe = shutil.which('podman')
        if podman_exe is None:
            raise errors.PodmanNotInstalled()

        self.socket_file: str = socket_uri.replace('unix://', '')
        self.log_level = log_level

        self.proc = None
        self.reference_id = hash(time.time_ns())

        self.cmd: List[str] = []
        if privileged:
            self.cmd.append('sudo')

        self.cmd.append(podman_exe)

        self.cmd.append(f"--log-level={logging.getLevelName(log_level).lower()}")

        if os.environ.get("container") == "oci":
            self.cmd.append("--storage-driver=vfs")

        self.cmd.extend(
            [
                "system",
                "service",
                f"--time={timeout}",
                socket_uri,
            ]
        )

    def start(self) -> None:
        """start podman service"""
        logger.info("Launching %s refid=%s", ' '.join(self.cmd), self.reference_id)

        def consume_lines(pipe, consume_fn):
            with pipe:
                for line in iter(pipe.readline, b""):
                    consume_fn(line.decode("utf-8"))

        def consume(line: str):
            logger.debug(line.strip("\n") + f" refid={self.reference_id}")

        self.proc = subprocess.Popen(self.cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        threading.Thread(target=consume_lines, args=[self.proc.stdout, consume]).start()

        # wait for socket to be created
        timeout = time.monotonic() + 30
        while not os.path.exists(self.socket_file):
            if time.monotonic() > timeout:
                raise subprocess.TimeoutExpired("podman service ", timeout)
            time.sleep(0.2)

    def stop(self) -> None:
        """stop podman service"""
        if not self.proc:
            return

        self.proc.terminate()
        try:
            return_code = self.proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            return_code = self.proc.wait()
        self.proc = None

        logger.info("Command return Code: %d refid=%s", return_code, self.reference_id)
