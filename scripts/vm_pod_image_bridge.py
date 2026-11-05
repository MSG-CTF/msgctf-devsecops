#!/usr/bin/python3 -I
"""Fixed privileged transport to an already installed Runtime image-agent Pod."""

import sys
sys.dont_write_bytecode = True

import hashlib
import json
import os
from pathlib import Path
import platform
import re
import selectors
import signal
import stat
import subprocess
import time
from uuid import UUID


CONFIG = Path('/etc/secure-provisioner/vm-image-pod-bridge.json')
K3S = Path('/usr/local/bin/k3s')
KUBECONFIG = Path('/etc/rancher/k3s/k3s.yaml')
NAMESPACE = 'runtime-image-preparation'
LABEL = 'app.kubernetes.io/name=runtime-image-agent'
AGENT_IMAGE = re.compile(r'^ghcr\.io/msg-ctf/secure-provisioner-image-agent@sha256:[a-f0-9]{64}$')
CHALLENGE_IMAGE = re.compile(r'^ghcr\.io/msg-ctf/challenges/[a-z0-9][a-z0-9-]{0,62}/[a-z0-9][a-z0-9-]{0,62}@sha256:[a-f0-9]{64}$')
DNS_NAME = re.compile(r'^[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?$')
MAX_JSON = 1024 * 1024
MAX_REQUEST = 4096
CALL_TIMEOUT_SECONDS = 115
ENVIRONMENT = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C.UTF-8', 'HOME': '/root'}


def require(condition):
    if not condition:
        raise ValueError('POD_AGENT_CHECK_FAILED')


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result)
        result[key] = value
    return result


def parse_json(raw, limit=MAX_JSON):
    require(len(raw) <= limit)
    return json.loads(raw, object_pairs_hook=unique_object, parse_constant=lambda _: require(False))


def read_request(stream, deadline):
    output = bytearray()
    descriptor = stream.fileno()
    # poll supports both SSH pipes and regular-file redirection on Linux.
    with selectors.PollSelector() as selector:
        selector.register(descriptor, selectors.EVENT_READ)
        while True:
            remaining = deadline - time.monotonic()
            require(remaining > 0)
            if not selector.select(remaining):
                continue
            try:
                data = os.read(descriptor, MAX_REQUEST + 1 - len(output))
            except BlockingIOError:
                continue
            if not data:
                return parse_json(output, MAX_REQUEST)
            output.extend(data)
            require(len(output) <= MAX_REQUEST)


def trusted_path(path, *, directory=False, private=False):
    require(not path.is_symlink())
    info = path.stat()
    require((stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
            and info.st_uid == 0 and not info.st_mode & (0o077 if private else 0o022))
    for parent in path.parents:
        info = parent.stat()
        require(not parent.is_symlink() and info.st_uid == 0 and not info.st_mode & 0o022)
    return path


def valid_uuid(value):
    require(isinstance(value, str))
    parsed = UUID(value)
    require(parsed.int != 0 and str(parsed) == value)


def load_config():
    require(os.geteuid() == 0)
    trusted_path(Path(__file__))
    trusted_path(K3S)
    trusted_path(KUBECONFIG, private=True)
    path = trusted_path(CONFIG, private=True)
    require(path.stat().st_size <= 64 * 1024)
    with path.open('rb') as stream:
        config = parse_json(stream.read(64 * 1024 + 1), 64 * 1024)
    fields = {'schema_version', 'node_name', 'node_uid', 'machine_id', 'boot_id', 'architecture',
              'agent_pod_name', 'agent_pod_uid', 'agent_image', 'agent_image_id', 'image_fs_path'}
    require(isinstance(config, dict) and set(config) == fields
            and type(config['schema_version']) is int and config['schema_version'] == 1)
    for key in ('node_name', 'agent_pod_name'):
        require(isinstance(config[key], str) and DNS_NAME.fullmatch(config[key]) and '..' not in config[key])
    for key in ('node_uid', 'boot_id', 'agent_pod_uid'):
        valid_uuid(config[key])
    require(isinstance(config['machine_id'], str) and re.fullmatch(r'[a-f0-9]{32}', config['machine_id']))
    require(config['architecture'] in ('AMD64', 'ARM64'))
    for key in ('agent_image', 'agent_image_id'):
        require(isinstance(config[key], str) and AGENT_IMAGE.fullmatch(config[key]))
    raw = config['image_fs_path']
    require(isinstance(raw, str) and raw.startswith('/') and raw != '/'
            and re.fullmatch(r'/[A-Za-z0-9_./-]+', raw) and '..' not in Path(raw).parts)
    trusted_path(Path(raw), directory=True)
    return config


def bounded_process(args, payload, timeout, limit):
    require(timeout > 0 and len(payload) <= MAX_REQUEST)
    process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, start_new_session=True, env=ENVIRONMENT)
    selector, output = selectors.DefaultSelector(), bytearray()
    deadline = time.monotonic() + timeout
    try:
        process.stdin.write(payload)
        process.stdin.close()
        selector.register(process.stdout, selectors.EVENT_READ)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            require(remaining > 0)
            for key, _ in selector.select(min(0.25, remaining)):
                data = os.read(key.fd, 8192)
                if data:
                    output.extend(data)
                    require(len(output) <= limit)
                else:
                    selector.unregister(key.fileobj)
        require(process.wait(timeout=max(0.01, deadline - time.monotonic())) == 0)
        return parse_json(output, limit)
    finally:
        selector.close()
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        if not process.stdin.closed:
            process.stdin.close()
        process.stdout.close()


def kubectl(args, payload, deadline, *, agent=False):
    timeout = min(110 if agent else 5, deadline - time.monotonic())
    require(timeout > 0)
    command = [str(K3S), 'kubectl', '--kubeconfig', str(KUBECONFIG),
               '--insecure-skip-tls-verify=false', f'--request-timeout={timeout:.3f}s', *args]
    return bounded_process(command, payload, timeout, 64 * 1024 if agent else MAX_JSON)


def true_condition(row, kind):
    conditions = row.get('status', {}).get('conditions')
    require(isinstance(conditions, list))
    matches = [item for item in conditions if isinstance(item, dict) and item.get('type') == kind]
    return len(matches) == 1 and matches[0].get('status') == 'True'


def inspect(config, deadline, run=kubectl):
    node = run(['get', 'node', config['node_name'], '-o', 'json'], b'', deadline)
    require(isinstance(node, dict))
    metadata, status = node.get('metadata', {}), node.get('status', {})
    info = status.get('nodeInfo', {})
    require(metadata.get('name') == config['node_name'] and metadata.get('uid') == config['node_uid']
            and not metadata.get('deletionTimestamp') and true_condition(node, 'Ready'))
    for key, field in (('machineID', 'machine_id'), ('bootID', 'boot_id')):
        require(info.get(key) == config[field])
    require(info.get('operatingSystem') == 'linux' and isinstance(info.get('architecture'), str)
            and info['architecture'].upper() == config['architecture'])
    require(Path('/etc/machine-id').read_text().strip() == config['machine_id']
            and Path('/proc/sys/kernel/random/boot_id').read_text().strip() == config['boot_id'])
    arch = {'x86_64': 'AMD64', 'aarch64': 'ARM64'}.get(platform.machine())
    require(platform.system() == 'Linux' and arch == config['architecture'])
    listed = run(['-n', NAMESPACE, 'get', 'pods', '-l', LABEL,
                  '--field-selector', 'spec.nodeName=' + config['node_name'], '-o', 'json'], b'', deadline)
    require(isinstance(listed, dict) and isinstance(listed.get('items'), list) and len(listed['items']) <= 100)
    ready = []
    for pod in listed['items']:
        require(isinstance(pod, dict))
        if (pod.get('status', {}).get('phase') == 'Running'
                and not pod.get('metadata', {}).get('deletionTimestamp') and true_condition(pod, 'Ready')):
            ready.append(pod)
    require(len(ready) == 1)
    pod = ready[0]
    metadata, spec, status = pod.get('metadata', {}), pod.get('spec', {}), pod.get('status', {})
    require(metadata.get('namespace') == NAMESPACE and metadata.get('name') == config['agent_pod_name']
            and metadata.get('uid') == config['agent_pod_uid']
            and metadata.get('labels', {}).get('app.kubernetes.io/name') == 'runtime-image-agent'
            and spec.get('nodeName') == config['node_name'])
    containers = spec.get('containers')
    require(isinstance(containers, list) and len(containers) == 1
            and containers[0].get('name') == 'agent' and containers[0].get('image') == config['agent_image'])
    statuses = status.get('containerStatuses')
    require(isinstance(statuses, list) and len(statuses) == 1)
    actual = statuses[0]
    image_id = actual.get('imageID')
    if isinstance(image_id, str) and image_id.startswith('docker-pullable://'):
        image_id = image_id[len('docker-pullable://'):]
    require(actual.get('name') == 'agent' and actual.get('ready') is True
            and isinstance(actual.get('state', {}).get('running'), dict)
            and image_id == config['agent_image_id'])
    fs = Path(config['image_fs_path'])
    trusted_path(fs, directory=True)
    disk = os.statvfs(fs)
    return {key: config[key] for key in ('node_name', 'node_uid', 'machine_id', 'boot_id', 'architecture',
                                        'agent_pod_name', 'agent_pod_uid', 'agent_image', 'agent_image_id', 'image_fs_path')} | {
        'schema_version': 1, 'agent_transport': 'kubernetes', 'node_uid_source': 'LIVE_KUBERNETES_AND_HOST_CHECK',
        'os': 'linux', 'available_bytes': disk.f_bavail * disk.f_frsize,
        'total_bytes': disk.f_blocks * disk.f_frsize,
        'preflight_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def handle(action, request, config, *, run=kubectl, check=inspect, deadline=None):
    deadline = time.monotonic() + CALL_TIMEOUT_SECONDS if deadline is None else deadline
    require(action in ('preflight', 'prepare') and isinstance(request, dict))
    if action == 'preflight':
        require(not request)
        return check(config, deadline, run)
    require(set(request) == {'image', 'architecture', 'pull'}
            and isinstance(request['image'], str) and CHALLENGE_IMAGE.fullmatch(request['image'])
            and request['architecture'] == config['architecture'] and type(request['pull']) is bool)
    before = check(config, deadline, run)
    reply = run(['-n', NAMESPACE, 'exec', '-i', config['agent_pod_name'], '-c', 'agent', '--',
                 '/usr/local/bin/image-agent', '--kubernetes'],
                json.dumps(request, separators=(',', ':')).encode(), deadline, agent=True)
    after = check(config, deadline, run)
    fields = ('node_uid', 'machine_id', 'boot_id', 'node_name', 'agent_pod_name', 'agent_pod_uid',
              'agent_image', 'agent_image_id', 'preflight_sha256')
    require(all(before[key] == after[key] for key in fields))
    require(isinstance(reply, dict))
    if set(reply) == {'error_code'}:
        code = reply['error_code']
        return {'error_code': code if code in ('CONTENT_INCOMPLETE', 'PLATFORM_MISMATCH') else 'AGENT_UNAVAILABLE'}
    require(set(reply) == {'evidence'} and isinstance(reply['evidence'], dict))
    evidence = reply['evidence']
    require(set(evidence) == {'node_uid', 'machine_id', 'boot_id', 'os', 'architecture', 'image',
                              'resolved_manifest_digest', 'complete'})
    require(all(evidence.get(key) == config[key] for key in ('node_uid', 'machine_id', 'boot_id', 'architecture'))
            and evidence.get('image') == request['image'] and evidence.get('os') == 'linux'
            and evidence.get('complete') is True
            and isinstance(evidence.get('resolved_manifest_digest'), str)
            and re.fullmatch(r'sha256:[a-f0-9]{64}', evidence['resolved_manifest_digest']))
    return {'evidence': evidence}


def main():
    deadline = time.monotonic() + CALL_TIMEOUT_SECONDS
    try:
        require(len(sys.argv) == 2 and sys.argv[1] in ('preflight', 'prepare'))
        config = load_config()
        request = read_request(sys.stdin.buffer, deadline)
        reply = handle(sys.argv[1], request, config, deadline=deadline)
        require(time.monotonic() < deadline)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError,
            RecursionError, subprocess.SubprocessError):
        print(json.dumps({'error_code': 'POD_AGENT_CHECK_FAILED'}))
        return 1
    print(json.dumps(reply, separators=(',', ':'), allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
