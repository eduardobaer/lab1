"""Network capture stub (v1).

In v2, this module will:
1. Spawn mitmproxy as a subprocess.
2. Configure the emulator's HTTP proxy via:
     adb shell settings put global http_proxy <host>:<port>
3. Push the mitmproxy CA cert to the system trust store. On recent emulators
   this requires booting with `-writable-system`:
     adb push mitmproxy-ca-cert.pem /system/etc/security/cacerts/<hash>.0
4. Capture all HTTPS traffic to a HAR file alongside the run.
5. On teardown, stop mitmproxy and reset the proxy:
     adb shell settings put global http_proxy :0

The PRD generator will then include a real "API endpoints" section based on
observed traffic. v1 falls back to inferring API behavior from UI changes.
"""

from contextlib import contextmanager


@contextmanager
def capture(*, run_dir, device_serial=None):
    yield None  # no-op in v1
