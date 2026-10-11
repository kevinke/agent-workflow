"""CLI process platform, WSL routing and text-stream contract (stdlib only).

Windows WSL UNC repositories must enter Linux *before* any workflow mutation.
Local-drive coordinators stay Windows processes; only their verifier is in WSL2.
Nothing in this module decodes or rewrites artifacts or verifier receipt bytes.
"""
from functools import lru_cache
import json
import ntpath
import os
import platform
import subprocess
import sys

import contracts

_PATH_OPTIONS = {"--output", "--review-context", "--report", "--handoff",
                 "--path", "--spec", "--ticket", "--plan"}


def configure_stdio():
    """CLI text is UTF-8, including redirected pipes and explicit legacy locales."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")


def _refuse(message):
    raise contracts.ContractError("startup-environment-unsupported: " + message)


def wsl_unc(path):
    """Return (distro, POSIX path) for either WSL UNC server; reject other UNC."""
    normalized = os.fspath(path).replace("\\", "/")
    if not normalized.startswith("//"):
        return None
    parts = normalized[2:].split("/")
    if len(parts) < 2 or parts[0].lower() not in ("wsl$", "wsl.localhost") \
            or not parts[1] or parts[1] in (".", ".."):
        _refuse("unsupported UNC path %r; use a local drive or a WSL distro share" % path)
    if any(part in (".", "..") for part in parts[2:]):
        _refuse("UNC path must be normalized without '.' or '..': %r" % path)
    return parts[1], "/" + "/".join(parts[2:])


@lru_cache(maxsize=8)
def _discover_wsl(requested):
    command = ["wsl.exe"] + (["-d", requested] if requested else []) + [
        "--exec", "python3", "-c",
        "import json,os,platform,sys; print(json.dumps({"
        "'distro':os.environ.get('WSL_DISTRO_NAME'),"
        "'platform':sys.platform,'release':platform.release()}))"]
    try:
        proc = subprocess.run(command, capture_output=True, timeout=30,
                              stdin=subprocess.DEVNULL, close_fds=True)
    except (OSError, subprocess.TimeoutExpired) as exc:
        _refuse("cannot discover WSL2/Linux Python: %s" % exc)
    if proc.returncode:
        # wsl.exe's own failures may be UTF-16; keep the diagnostic bounded and
        # do not apply this handling to workflow artifacts or receipt streams.
        diagnostic = proc.stderr or proc.stdout
        encoding = "utf-16-le" if b"\x00" in diagnostic else "utf-8"
        _refuse("WSL/Linux Python discovery failed (exit %s): %s" %
                (proc.returncode, diagnostic.decode(encoding, "replace").strip()[:500]))
    try:
        data = json.loads(proc.stdout.decode("utf-8"))
    except (ValueError, UnicodeError):
        _refuse("WSL/Linux Python discovery returned invalid UTF-8 JSON")
    if not isinstance(data, dict) or data.get("platform") != "linux" \
            or not data.get("distro") \
            or "microsoft-standard" not in data.get("release", "").lower():
        _refuse("a WSL2 distro with Linux python3 is required (observed %r)" % data)
    if requested and data["distro"].casefold() != requested.casefold():
        _refuse("requested distro %r differs from observed distro %r" %
                (requested, data["distro"]))
    return data["distro"]


def wsl_distro(requested=None):
    override = os.environ.get("AI_WORKFLOW_BWRAP_DISTRO") or None
    if requested and override and requested.casefold() != override.casefold():
        _refuse("repository distro %r conflicts with AI_WORKFLOW_BWRAP_DISTRO=%r" %
                (requested, override))
    return _discover_wsl(requested or override)


@lru_cache(maxsize=256)
def _drive_path(path, distro):
    try:
        proc = subprocess.run(["wsl.exe", "-d", distro, "--exec", "wslpath",
                               "-a", "-u", path], capture_output=True, timeout=30,
                              stdin=subprocess.DEVNULL, close_fds=True)
    except (OSError, subprocess.TimeoutExpired) as exc:
        _refuse("cannot translate local drive path %r: %s" % (path, exc))
    try:
        translated = proc.stdout.decode("utf-8", "strict").strip()
    except UnicodeError:
        _refuse("WSL path translation returned invalid UTF-8 for %r" % path)
    if proc.returncode or not translated.startswith("/"):
        _refuse("local drive path %r is unavailable in distro %r" % (path, distro))
    return translated


def path_in_wsl(path, distro):
    unc = wsl_unc(path)
    if unc:
        if unc[0].casefold() != distro.casefold():
            _refuse("path %r belongs to another distro; expected %r" % (path, distro))
        return unc[1]
    drive, tail = ntpath.splitdrive(path)
    if drive:
        if len(drive) != 2 or drive[1] != ":" or not tail.startswith(("/", "\\")):
            _refuse("unsupported Windows path %r; use an absolute drive path" % path)
        return _drive_path(path, distro)
    return path.replace("\\", "/")


def validate_host_path(path):
    """Reject ambiguous spellings before abspath/realpath can hide them."""
    path = os.fspath(path)
    drive, tail = ntpath.splitdrive(path)
    if os.name == "nt":
        wsl_unc(path)  # Reject generic shares and device namespaces explicitly.
        if drive and not path.replace("\\", "/").startswith("//") \
                and (len(drive) != 2 or drive[1] != ":" \
                     or not tail.startswith(("/", "\\"))):
            _refuse("unsupported Windows path %r; use an absolute drive path" % path)
    elif drive or path.startswith("\\\\"):
        _refuse("Linux needs POSIX paths, got %r" % path)


def handoff_command(argv, script, root, host_os=None):
    """Build an argv-only handoff, or None for a native coordinator.

    Only host-side path arguments are translated. The verifier argv after '--'
    is opaque and is already expressed in the frozen Linux sandbox layout.
    """
    if (host_os or os.name) != "nt":
        return None
    unc = wsl_unc(root)
    if unc is None:
        return None
    distro = wsl_distro(unc[0])
    linux_script = path_in_wsl(script, distro)
    translated = list(argv) or ["help"]
    # Match cmd_init's accepted placement of --with-skills around its target.
    target_index = None
    if argv and argv[0] in ("init", "install-skills"):
        target_index = next((index for index in range(1, len(argv))
                             if argv[index] != "--with-skills"), None)
    for index, arg in enumerate(argv):
        if arg == "--":
            break
        if index and argv[index - 1] in _PATH_OPTIONS:
            translated[index] = path_in_wsl(arg, distro)
        elif index == target_index and not arg.startswith("--"):
            translated[index] = path_in_wsl(arg, distro)
    # WSL --cd can fail yet run Python from '/', returning success. Let the
    # Linux CLI confirm and enter the exact root before any workflow dispatch.
    return ["wsl.exe", "-d", distro, "--exec", "python3", "-X", "utf8",
            linux_script, "--repo", unc[1]] + translated


def forward_if_needed(argv, script, root):
    command = handoff_command(argv, script, root)
    if command is None:
        return None
    try:
        # Inherit text streams without capturing or transcoding any child bytes.
        code = subprocess.run(command, stdin=subprocess.DEVNULL,
                              close_fds=True).returncode
    except OSError as exc:
        _refuse("cannot start the WSL workflow: %s" % exc)
    return code if 0 <= code <= 255 else 255


def review_runtime():
    """Identity pinned at preparation, checked again before run/publication."""
    if os.name == "nt":
        return {"platform": "win32", "distro": wsl_distro()}
    if not sys.platform.startswith("linux"):
        _refuse("isolated review requires Windows with WSL2 or Linux")
    distro = os.environ.get("WSL_DISTRO_NAME") or None
    if distro and "microsoft-standard" not in platform.release().lower():
        _refuse("WSL review requires WSL2 (kernel %r)" % platform.release())
    override = os.environ.get("AI_WORKFLOW_BWRAP_DISTRO") or None
    if override and (not distro or override.casefold() != distro.casefold()):
        _refuse("Linux coordinator distro %r conflicts with distro override %r" %
                (distro, override))
    return {"platform": "linux", "distro": distro}


def prepare_paths(root, output):
    for path in (root, output):
        validate_host_path(path)
    identity = review_runtime()
    if os.name == "nt":
        # A native coordinator cannot share a context with the UNC/Linux route.
        for path in (os.path.realpath(root), os.path.realpath(output)):
            if wsl_unc(path):
                _refuse("native Windows preparation needs local drive paths; "
                        "enter the WSL repository through its UNC CLI instead")
            path_in_wsl(path, identity["distro"])
    return identity
