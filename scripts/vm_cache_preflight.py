#!/usr/bin/python3 -B
"""Read-only host checks for the manually approved VM cache operation."""

import hashlib
import json
import os
from pathlib import Path
import platform
import stat

CONFIG = Path('/etc/secure-provisioner/vm-prefetch.json')
AGENT_CONFIG = Path('/etc/secure-provisioner/image-agent.json')
AGENT = Path('/usr/local/libexec/runtime-image-agent')


def file_digest(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def trusted_file(path):
    if path.is_symlink():
        raise ValueError('UNTRUSTED_INSTALLATION')
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        raise ValueError('UNTRUSTED_INSTALLATION')
    for parent in path.parents:
        info = parent.stat()
        if parent.is_symlink() or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('UNTRUSTED_INSTALLATION')
    return path


def snapshot():
    if os.geteuid() != 0:
        raise ValueError('PREFLIGHT_PERMISSION')
    config = json.loads(trusted_file(CONFIG).read_bytes())
    agent_config = json.loads(trusted_file(AGENT_CONFIG).read_bytes())
    if set(config) != {'image_fs_path'} or not isinstance(config['image_fs_path'], str):
        raise ValueError('PREFLIGHT_CONFIG')
    image_fs = Path(config['image_fs_path'])
    if not image_fs.is_absolute() or image_fs.is_symlink() or not image_fs.is_dir():
        raise ValueError('PREFLIGHT_CONFIG')
    trusted_file(AGENT)
    if (not isinstance(agent_config, dict) or set(agent_config) != {'node_uid', 'k3s_binary'}
            or not isinstance(agent_config['k3s_binary'], str)
            or not Path(agent_config['k3s_binary']).is_absolute()):
        raise ValueError('PREFLIGHT_CONFIG')
    trusted_file(Path(agent_config['k3s_binary']))
    disk = os.statvfs(image_fs)
    arch = {'x86_64': 'AMD64', 'aarch64': 'ARM64'}.get(platform.machine())
    if platform.system() != 'Linux' or arch is None:
        raise ValueError('PLATFORM_MISMATCH')
    return {
        'schema_version': 1,
        'node_uid': agent_config['node_uid'],
        'node_uid_source': 'OPERATOR_PINNED_AGENT_CONFIG',
        'machine_id': Path('/etc/machine-id').read_text().strip(),
        'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        'os': 'linux', 'architecture': arch,
        'image_fs_path': str(image_fs),
        'available_bytes': disk.f_bavail * disk.f_frsize,
        'total_bytes': disk.f_blocks * disk.f_frsize,
        'agent_sha256': file_digest(AGENT),
        'preflight_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }


def main():
    try:
        result = snapshot()
    except (OSError, ValueError, TypeError, KeyError):
        print(json.dumps({'error_code': 'PREFLIGHT_FAILED'}))
        return 1
    print(json.dumps(result, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
