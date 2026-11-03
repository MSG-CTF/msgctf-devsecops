#!/usr/bin/env python3
"""Audit active image selections, then optionally fill approved VM caches over SSH."""

import argparse
import base64
from datetime import datetime, timezone, timedelta
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import sys
import tempfile
import time
from uuid import UUID
import zipfile

import yaml

if __package__:
    from . import collect_node_image_plans as sources
else:
    import collect_node_image_plans as sources

NAME = re.compile(r'^[a-z0-9][a-z0-9-]{0,62}$')
SHA = re.compile(r'^[a-f0-9]{64}$')
DIGEST = re.compile(r'^sha256:[a-f0-9]{64}$')
IDENTITY = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$')
REPOSITORY = sources.publication.REPOSITORY
AGENT_COMMAND = 'sudo -n /usr/local/libexec/runtime-image-agent'
PREFLIGHT_COMMAND = 'sudo -n /usr/local/libexec/vm-image-cache-preflight'
MAX_BYTES = 1024 * 1024
MAX_PAIRS = 1000


def require(condition):
    if not condition:
        raise ValueError('INPUT_OR_EVIDENCE_INVALID')


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result)
        result[key] = value
    return result


def load_json(raw):
    require(len(raw) <= MAX_BYTES)
    return json.loads(raw, object_pairs_hook=unique_object,
                      parse_constant=lambda _: require(False))


def read_json(path):
    path = Path(path)
    require(not path.is_symlink() and path.is_file() and path.stat().st_size <= MAX_BYTES)
    return load_json(path.read_bytes())


def timestamp(value):
    require(isinstance(value, str))
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(parsed.tzinfo is not None)
    return parsed.astimezone(timezone.utc)


def positive(value):
    return type(value) is int and 0 < value <= 2**63 - 1


def image_set(containers):
    require(isinstance(containers, list) and 1 <= len(containers) <= 32)
    names = set()
    result = {}
    for container in containers:
        require(isinstance(container, dict) and set(container) == {'name', 'image'})
        name, image = container['name'], container['image']
        require(isinstance(name, str) and NAME.fullmatch(name) and name not in names)
        require(isinstance(image, str) and sources.MSGCTF_GHCR_DIGEST_IMAGE.fullmatch(image))
        names.add(name)
        result[name] = image
    return result


def checked_nodes(inventory):
    require(isinstance(inventory, dict) and set(inventory) == {'schema_version', 'nodes'})
    require(inventory['schema_version'] == 1 and isinstance(inventory['nodes'], list)
            and 1 <= len(inventory['nodes']) <= 50)
    nodes, ids, machines, uids, hosts = [], set(), set(), set(), set()
    fields = {'node_id', 'target_id', 'node_uid', 'machine_id', 'boot_id', 'architecture',
              'ssh_host', 'ssh_port', 'ssh_user', 'ssh_host_key', 'agent_sha256',
              'image_fs_path', 'reserve_bytes', 'max_additional_bytes', 'per_image_workspace_bytes'}
    for row in inventory['nodes']:
        require(isinstance(row, dict) and set(row) == fields)
        for key in ('node_id', 'target_id', 'node_uid', 'machine_id', 'boot_id'):
            require(isinstance(row[key], str) and IDENTITY.fullmatch(row[key]))
        require(NAME.fullmatch(row['node_id']) and row['node_id'] not in ids)
        require(row['machine_id'] not in machines and row['architecture'] in ('AMD64', 'ARM64'))
        require(row['node_uid'] not in uids)
        host = row['ssh_host']
        require(isinstance(host, str) and len(host) <= 253 and not host.startswith('-'))
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            require(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?', host)
                    and '..' not in host and host.lower() != 'localhost')
        else:
            require(not (address.is_loopback or address.is_link_local or address.is_unspecified
                         or address.is_multicast))
        require(type(row['ssh_port']) is int and 1 <= row['ssh_port'] <= 65535)
        require((host, row['ssh_port']) not in hosts)
        require(isinstance(row['ssh_user'], str) and re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}', row['ssh_user']))
        require(isinstance(row['ssh_host_key'], str))
        key = row['ssh_host_key'].split()
        require(len(key) == 2 and key[0] == 'ssh-ed25519')
        decoded = base64.b64decode(key[1], validate=True)
        require(len(decoded) == 51 and decoded[:19] == b'\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20')
        require(isinstance(row['agent_sha256'], str) and SHA.fullmatch(row['agent_sha256']))
        path = row['image_fs_path']
        require(isinstance(path, str) and path.startswith('/') and path != '/'
                and re.fullmatch(r'/[A-Za-z0-9_./-]+', path) and '..' not in Path(path).parts)
        for field in ('reserve_bytes', 'max_additional_bytes', 'per_image_workspace_bytes'):
            require(positive(row[field]))
        require(row['per_image_workspace_bytes'] <= row['max_additional_bytes'])
        ids.add(row['node_id'])
        machines.add(row['machine_id'])
        uids.add(row['node_uid'])
        hosts.add((host, row['ssh_port']))
        nodes.append(dict(row))
    return sorted(nodes, key=lambda row: row['node_id'])


def current_kind(slug, main_sha, api):
    data = api(f'contents/{slug}/info.yaml?ref={main_sha}')
    require(data.get('encoding') == 'base64' and positive(data.get('size')) and data['size'] <= MAX_BYTES)
    spec = yaml.safe_load(base64.b64decode(data['content']))
    require(isinstance(spec, dict))
    deployment = spec.get('deployment')
    if deployment is None:
        return 'STATIC'
    require(isinstance(deployment, dict))
    return deployment.get('runtime_type')


def build_plan(scope, inventory, *, api=sources.publication.github, fetch=None, now=None):
    now = now or datetime.now(timezone.utc)
    require(isinstance(scope, dict) and scope.get('schema_version') == 1
            and scope.get('selection_mode') == 'OPERATOR_APPROVED_ACTIVE_RELEASES'
            and scope.get('inventory_complete_as_attested') is True)
    observed, expires = timestamp(scope.get('observed_at')), timestamp(scope.get('valid_until'))
    require(observed <= now < expires and timedelta(0) < expires - observed <= timedelta(hours=24))
    releases = scope.get('releases')
    require(isinstance(releases, list) and 1 <= len(releases) <= 100)
    nodes = checked_nodes(inventory)
    main_sha = api('git/ref/heads/main')['object']['sha']
    require(isinstance(main_sha, str) and sources.COMMIT_SHA.fullmatch(main_sha))
    plans, held, excluded, seen = [], [], [], set()
    for selected in releases:
        require(isinstance(selected, dict))
        slug = selected.get('challenge_slug')
        require(isinstance(slug, str) and NAME.fullmatch(slug) and slug not in seen)
        seen.add(slug)
        reason = selected.get('exclude_reason')
        if reason is not None:
            require(reason in {'STATIC_CONVERSION', 'KOTH', 'WINDOWS', 'NOT_APPROVED', 'NOT_IN_THIS_MAINTENANCE'})
            excluded.append({'challenge_slug': slug, 'reason': reason})
            continue
        try:
            require(not slug.startswith('koth-') and slug != 'pwn-msgdriver')
            require(str(UUID(selected['release_id'])) == selected['release_id'])
            if selected.get('policy_approved') is not True:
                held.append({'challenge_slug': slug, 'reason': 'POLICY_APPROVAL_NOT_ATTESTED'})
                continue
            require(positive(selected['registry_revision']) and positive(selected['publish_run_id'])
                    and positive(selected['publish_artifact_id']))
            require(isinstance(selected['artifact_sha256'], str) and SHA.fullmatch(selected['artifact_sha256']))
            kind = current_kind(slug, main_sha, api)
            if kind != 'KUBERNETES':
                held.append({'challenge_slug': slug, 'reason': 'CURRENT_PROBLEM_NOT_KUBERNETES'})
                continue
            meta = api(f"actions/artifacts/{selected['publish_artifact_id']}")
            origin = {'id': selected['publish_artifact_id'], 'run_id': selected['publish_run_id'],
                      'registry_revision': selected['registry_revision'], 'source_sha': selected['source_sha'],
                      'name': meta['name']}
            found = fetch(slug, origin) if fetch else sources.fetch_plan(slug, origin, api=api)
            require(found['artifact_sha256'] == selected['artifact_sha256']
                    and found['challenge_slug'] == slug
                    and found['registry_revision'] == selected['registry_revision']
                    and found['source_sha'] == selected['source_sha']
                    and found['publish_run_id'] == selected['publish_run_id']
                    and found['publish_artifact_id'] == selected['publish_artifact_id']
                    and found['runtime_type'] == 'KUBERNETES' and found['source_ref'] == 'refs/heads/main'
                    and found['architecture'] == selected['architecture']
                    and image_set(found['containers']) == image_set(selected['containers']))
            matching = [row for row in nodes if row['architecture'] == found['architecture']]
            targets = selected['approved_target_ids']
            require(isinstance(targets, list) and len(targets) == len(set(targets))
                    and set(targets) == {row['target_id'] for row in matching} and matching)
            plans.append({**found, 'release_id': selected['release_id'], 'approved_target_ids': sorted(targets)})
        except (ValueError, KeyError, TypeError, OSError, RuntimeError, yaml.YAMLError,
                zipfile.BadZipFile, subprocess.SubprocessError):
            held.append({'challenge_slug': slug, 'reason': 'SOURCE_POLICY_OR_SCOPE_NOT_CONFIRMED'})
    require(api('git/ref/heads/main')['object']['sha'] == main_sha)
    require(plans or held)
    tasks = []
    for node in nodes:
        images = sorted({item['image'] for plan in plans if plan['architecture'] == node['architecture']
                         for item in plan['containers']})
        if not images:
            held.append({'node_id': node['node_id'], 'reason': 'NO_APPROVED_IMAGES_FOR_NODE'})
        tasks.append({'node_id': node['node_id'], 'images': images})
    require(sum(len(task['images']) for task in tasks) <= MAX_PAIRS)
    plan = {'schema_version': 1, 'scope': 'PROVIDED_ACTIVE_RELEASES_AND_NODES_ONLY',
            'repository': REPOSITORY, 'source_main_sha': main_sha, 'observed_at': scope['observed_at'],
            'valid_until': scope['valid_until'], 'complete': not held, 'releases': plans,
            'nodes': nodes, 'tasks': tasks, 'held': held, 'excluded': excluded,
            'backend_active_independently_queried': False,
            'preflight_sha256': hashlib.sha256(Path(__file__).with_name('vm_cache_preflight.py').read_bytes()).hexdigest()}
    plan['plan_sha256'] = plan_hash(plan)
    return plan


def plan_hash(plan):
    return hashlib.sha256(json.dumps({key: value for key, value in plan.items() if key != 'plan_sha256'},
                                     sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def bounded_command(args, payload, timeout=130):
    environment = {key: os.environ[key] for key in ('PATH', 'LANG', 'LC_ALL') if key in os.environ}
    process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, start_new_session=True, env=environment)
    output, selector = bytearray(), selectors.DefaultSelector()
    try:
        process.stdin.write(json.dumps(payload, separators=(',', ':')).encode())
        process.stdin.close()
        selector.register(process.stdout, selectors.EVENT_READ)
        deadline = time.monotonic() + timeout
        while selector.get_map():
            require(time.monotonic() < deadline)
            for key, _ in selector.select(min(0.5, max(0, deadline - time.monotonic()))):
                data = os.read(key.fd, 8192)
                if not data:
                    selector.unregister(key.fileobj)
                else:
                    output.extend(data)
                    require(len(output) <= 64 * 1024)
        require(process.wait(timeout=max(0.1, deadline - time.monotonic())) == 0)
        return load_json(output)
    finally:
        selector.close()
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        if not process.stdin.closed:
            process.stdin.close()
        process.stdout.close()


class SSHAgent:
    def __init__(self, key_file, runner=bounded_command):
        self.key_file = Path(key_file)
        require(not self.key_file.is_symlink() and self.key_file.is_file())
        require(1 <= self.key_file.stat().st_size <= 16 * 1024)
        require(stat.S_IMODE(self.key_file.stat().st_mode) & 0o077 == 0)
        self.runner = runner

    def __call__(self, node, command, payload):
        require(command in (AGENT_COMMAND, PREFLIGHT_COMMAND))
        with tempfile.TemporaryDirectory() as temporary:
            known = Path(temporary) / 'known_hosts'
            host = node['ssh_host'] if node['ssh_port'] == 22 else f"[{node['ssh_host']}]:{node['ssh_port']}"
            known.write_text(f"{host} {node['ssh_host_key']}\n")
            known.chmod(0o600)
            args = ['ssh', '-F', '/dev/null', '-i', str(self.key_file), '-p', str(node['ssh_port']),
                    '-oBatchMode=yes', '-oIdentitiesOnly=yes', '-oIdentityAgent=none',
                    '-oForwardAgent=no', '-oClearAllForwardings=yes', '-oPermitLocalCommand=no',
                    '-oProxyCommand=none', '-oProxyJump=none', '-oPasswordAuthentication=no',
                    '-oKbdInteractiveAuthentication=no', '-oStrictHostKeyChecking=yes',
                    '-oGlobalKnownHostsFile=/dev/null', f'-oUserKnownHostsFile={known}',
                    '-oConnectTimeout=10', '-oConnectionAttempts=1', '-T', '--',
                    f"{node['ssh_user']}@{node['ssh_host']}", command]
            return self.runner(args, payload)


def check_host(node, plan, reply, initial_free=None, workspace=0):
    require(isinstance(reply, dict) and reply.get('schema_version') == 1)
    for field in ('node_uid', 'machine_id', 'boot_id', 'architecture', 'image_fs_path', 'agent_sha256'):
        require(reply.get(field) == node[field])
    require(reply.get('os') == 'linux' and reply.get('preflight_sha256') == plan['preflight_sha256'])
    available, total = reply.get('available_bytes'), reply.get('total_bytes')
    require(type(available) is int and positive(total) and 0 <= available <= total)
    reserve = max(node['reserve_bytes'], (total + 4) // 5)
    require(available >= reserve + workspace)
    if initial_free is not None:
        require(max(0, initial_free - available) <= node['max_additional_bytes'])
    return available


def checked_evidence(node, image, reply):
    require(isinstance(reply, dict) and set(reply) == {'evidence'})
    data = reply['evidence']
    require(isinstance(data, dict))
    for field in ('node_uid', 'machine_id', 'boot_id', 'architecture'):
        require(data.get(field) == node[field])
    require(data.get('os') == 'linux' and data.get('image') == image and data.get('complete') is True)
    require(isinstance(data.get('resolved_manifest_digest'), str) and DIGEST.fullmatch(data['resolved_manifest_digest']))
    return {'resolved_manifest_digest': data['resolved_manifest_digest'], 'complete': True}


def execute(plan, expected_sha, call, *, now=None, on_result=None):
    require(plan['complete'] is True and isinstance(expected_sha, str) and SHA.fullmatch(expected_sha)
            and expected_sha == plan['plan_sha256'] == plan_hash(plan))
    require((now or datetime.now(timezone.utc)) < timestamp(plan['valid_until']))
    report = {'schema_version': 1, 'plan_sha256': expected_sha, 'status': 'FAILED', 'results': [],
              'final_sweep_complete': False,
              'runtime_readiness_registered': False, 'backend_operation_registered': False,
              'pod_started': False, 'active_changed': False, 'cold_pull_proven': False}
    baseline = {}
    context = {'stage': 'PREFLIGHT'}
    try:
        # Check every configured VM before allowing the first cache mutation.
        for node in plan['nodes']:
            context = {'node_id': node['node_id'], 'stage': 'PREFLIGHT'}
            response = call(node, PREFLIGHT_COMMAND, {})
            baseline[node['node_id']] = check_host(node, plan, response,
                                                   workspace=node['max_additional_bytes'])
        for node, task in zip(plan['nodes'], plan['tasks']):
            for image in task['images']:
                context = {'node_id': node['node_id'], 'image': image, 'stage': 'CACHE_CHECK'}
                require((now or datetime.now(timezone.utc)) < timestamp(plan['valid_until']))
                check_host(node, plan, call(node, PREFLIGHT_COMMAND, {}), baseline[node['node_id']])
                request = {'image': image, 'architecture': node['architecture'], 'pull': False}
                reply = call(node, AGENT_COMMAND, request)
                if isinstance(reply, dict) and reply.get('error_code') == 'CONTENT_INCOMPLETE' and set(reply) == {'error_code'}:
                    check_host(node, plan, call(node, PREFLIGHT_COMMAND, {}), baseline[node['node_id']],
                               workspace=node['per_image_workspace_bytes'])
                    require((now or datetime.now(timezone.utc)) < timestamp(plan['valid_until']))
                    request['pull'] = True
                    context['stage'] = 'PULL_OR_REPAIR'
                    started = time.monotonic()
                    reply = call(node, AGENT_COMMAND, request)
                    elapsed = time.monotonic() - started
                    mode = 'PULLED_OR_REPAIRED'
                else:
                    elapsed, mode = None, 'REUSED_VERIFIED'
                evidence = checked_evidence(node, image, reply)
                check_host(node, plan, call(node, PREFLIGHT_COMMAND, {}), baseline[node['node_id']])
                report['results'].append({'node_id': node['node_id'], 'image': image, 'mode': mode,
                                          'agent_prepare_seconds': elapsed,
                                          'verified_at': datetime.now(timezone.utc).isoformat(), **evidence})
                if on_result:
                    on_result(report)
        indexed_nodes = {node['node_id']: node for node in plan['nodes']}
        for row in report['results']:
            node = indexed_nodes[row['node_id']]
            context = {'node_id': node['node_id'], 'image': row['image'], 'stage': 'FINAL_CACHE_CHECK'}
            require((now or datetime.now(timezone.utc)) < timestamp(plan['valid_until']))
            check_host(node, plan, call(node, PREFLIGHT_COMMAND, {}), baseline[node['node_id']])
            checked_evidence(node, row['image'], call(node, AGENT_COMMAND,
                {'image': row['image'], 'architecture': node['architecture'], 'pull': False}))
            check_host(node, plan, call(node, PREFLIGHT_COMMAND, {}), baseline[node['node_id']])
            require((now or datetime.now(timezone.utc)) < timestamp(plan['valid_until']))
            row['final_verified_at'] = datetime.now(timezone.utc).isoformat()
            if on_result:
                on_result(report)
        report['final_sweep_complete'] = True
        report['status'] = 'SUCCEEDED'
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError):
        report['error_code'] = 'PREFLIGHT_SSH_OR_AGENT_CHECK_FAILED'
        report['failure'] = context
    if on_result:
        on_result(report)
    return report


def save_private(path, data):
    temporary = path.with_suffix('.tmp')
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        json.dump(data, stream, ensure_ascii=True, indent=2, allow_nan=False)
        stream.write('\n')
    os.replace(temporary, path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scope', required=True, type=Path)
    parser.add_argument('--nodes', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--expected-plan-sha256', default='')
    parser.add_argument('--ssh-key', type=Path)
    args = parser.parse_args()
    try:
        plan = build_plan(read_json(args.scope), read_json(args.nodes))
        args.output_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
        save_private(args.output_dir / 'plan.json', plan)
        summary = {'plan_sha256': plan['plan_sha256'], 'complete': plan['complete'],
                   'release_count': len(plan['releases']), 'node_count': len(plan['nodes']),
                   'image_node_pairs': sum(len(row['images']) for row in plan['tasks']),
                   'held_count': len(plan['held']), 'excluded_count': len(plan['excluded']),
                   'applied': False}
        code = 0 if plan['complete'] else 1
        if args.apply:
            require(args.ssh_key is not None)
            result = execute(plan, args.expected_plan_sha256, SSHAgent(args.ssh_key),
                             on_result=lambda value: save_private(args.output_dir / 'results.json', value))
            summary.update(applied=True, status=result['status'], checked_pairs=len(result['results']),
                           final_verified_pairs=sum('final_verified_at' in row for row in result['results']))
            code = 0 if result['status'] == 'SUCCEEDED' else 1
        save_private(args.output_dir / 'summary.json', summary)
        print(json.dumps(summary))
        return code
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError, subprocess.SubprocessError):
        print('VM image prefetch failed: check approved scope, source, node evidence and output path.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
