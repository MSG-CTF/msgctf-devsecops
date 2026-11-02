import base64
import copy
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

import yaml

from scripts import vm_image_prefetch as vm
from scripts import vm_cache_preflight as preflight
from tests.test_collect_node_image_plans import plan as source_plan

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 2, 0, 30, tzinfo=timezone.utc)
KEY = 'ssh-ed25519 ' + base64.b64encode(b'\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20' + b'a' * 32).decode()


def inputs():
    published = source_plan()
    scope = {
        'schema_version': 1, 'selection_mode': 'OPERATOR_APPROVED_ACTIVE_RELEASES',
        'inventory_complete_as_attested': True,
        'observed_at': '2026-11-02T00:00:00Z', 'valid_until': '2026-11-02T01:00:00Z',
        'releases': [{'challenge_slug': 'web-one',
                      'release_id': '00000000-0000-4000-8000-000000000001',
                      'registry_revision': 1, 'publish_run_id': 100, 'publish_artifact_id': 200,
                      'source_sha': '1' * 40, 'artifact_sha256': 'c' * 64,
                      'architecture': 'AMD64', 'containers': published['containers'],
                      'policy_approved': True, 'approved_target_ids': ['target-one']}],
    }
    nodes = {'schema_version': 1, 'nodes': [{
        'node_id': 'vm-one', 'target_id': 'target-one', 'node_uid': 'uid-one',
        'machine_id': 'machine-one', 'boot_id': 'boot-one', 'architecture': 'AMD64',
        'ssh_host': '192.0.2.10', 'ssh_port': 22, 'ssh_user': 'prefetch',
        'ssh_host_key': KEY, 'agent_sha256': 'd' * 64,
        'image_fs_path': '/var/lib/rancher/k3s/agent/containerd',
        'reserve_bytes': 1000, 'max_additional_bytes': 2000, 'per_image_workspace_bytes': 500,
    }]}
    return scope, nodes


def build(scope=None, nodes=None, **kwargs):
    default_scope, default_nodes = inputs()
    def api(path):
        if path == 'git/ref/heads/main':
            return {'object': {'sha': '1' * 40}}
        if path == 'actions/artifacts/200':
            return {'name': 'web-one-100-1-abcdef-publish-bundle'}
        if path.startswith('contents/'):
            raw = yaml.safe_dump({'deployment': {'runtime_type': 'KUBERNETES'},
                                  'flag': 'do-not-copy-author-value'}).encode()
            return {'encoding': 'base64', 'size': len(raw), 'content': base64.b64encode(raw).decode()}
        raise AssertionError(path)
    return vm.build_plan(scope or default_scope, nodes or default_nodes, now=NOW,
                         api=kwargs.pop('api', api),
                         fetch=kwargs.pop('fetch', lambda slug, selected: source_plan()), **kwargs)


def host_reply(node, plan):
    return {**{key: node[key] for key in ('node_uid', 'machine_id', 'boot_id', 'architecture',
                                         'image_fs_path', 'agent_sha256')},
            'schema_version': 1, 'os': 'linux', 'available_bytes': 10000, 'total_bytes': 20000,
            'preflight_sha256': plan['preflight_sha256']}


def evidence(node, image):
    return {'evidence': {**{key: node[key] for key in ('node_uid', 'machine_id', 'boot_id', 'architecture')},
                         'os': 'linux', 'image': image, 'complete': True,
                         'resolved_manifest_digest': 'sha256:' + 'a' * 64}}


class FakeAgent:
    def __init__(self, plan, missing=False, change=None):
        self.plan, self.missing, self.change = plan, missing, change
        self.calls = []
        self.cached = set()

    def __call__(self, node, command, request):
        self.calls.append((node['node_id'], command, dict(request)))
        if command == vm.PREFLIGHT_COMMAND:
            reply = host_reply(node, self.plan)
        elif self.missing and not request['pull'] and (node['node_id'], request['image']) not in self.cached:
            reply = {'error_code': 'CONTENT_INCOMPLETE'}
        else:
            if request['pull']:
                self.cached.add((node['node_id'], request['image']))
            reply = evidence(node, request['image'])
        return self.change(node, command, request, reply) if self.change else reply


class VMImagePrefetchTests(unittest.TestCase):
    def test_plan_is_deterministic_without_ssh_or_host_changes(self):
        one, two = build(), build()
        self.assertEqual(one, two)
        self.assertTrue(one['complete'])
        self.assertEqual(one['plan_sha256'], vm.plan_hash(one))
        self.assertFalse(one['backend_active_independently_queried'])
        self.assertNotIn('do-not-copy-author-value', json.dumps(one))

    def test_expired_future_and_overlong_operator_selection_are_rejected(self):
        for key, value in (('valid_until', '2026-11-02T00:30:00Z'),
                           ('observed_at', '2026-11-02T00:31:00Z'),
                           ('valid_until', '2026-11-04T00:00:00Z'),
                           ('observed_at', '2026-11-02T00:00:00')):
            scope, nodes = inputs()
            scope[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                build(scope, nodes)

    def test_inventory_attestation_and_duplicate_releases_are_required(self):
        scope, nodes = inputs()
        scope['inventory_complete_as_attested'] = False
        with self.assertRaises(ValueError):
            build(scope, nodes)
        scope, nodes = inputs()
        scope['releases'] *= 2
        with self.assertRaises(ValueError):
            build(scope, nodes)

    def test_policy_approval_is_not_inferred_from_source_success(self):
        scope, nodes = inputs()
        scope['releases'][0]['policy_approved'] = False
        result = build(scope, nodes, fetch=lambda *_: self.fail('must not fetch'))
        self.assertFalse(result['complete'])
        self.assertEqual(result['held'][0]['reason'], 'POLICY_APPROVAL_NOT_ATTESTED')

    def test_static_docker_and_vm_are_not_silently_preloaded(self):
        for kind in ('STATIC', 'DOCKER', 'VM'):
            raw = yaml.safe_dump({} if kind == 'STATIC' else {'deployment': {'runtime_type': kind}}).encode()
            def api(path):
                if path == 'git/ref/heads/main':
                    return {'object': {'sha': '1' * 40}}
                return {'encoding': 'base64', 'size': len(raw), 'content': base64.b64encode(raw).decode()}
            with self.subTest(kind=kind):
                result = build(api=api, fetch=lambda *_: self.fail('must not fetch'))
                self.assertFalse(result['complete'])
                self.assertEqual(result['held'][0]['reason'], 'CURRENT_PROBLEM_NOT_KUBERNETES')

    def test_exclusions_are_visible_not_hidden_as_ready(self):
        scope, nodes = inputs()
        scope['releases'].append({'challenge_slug': 'crypto-reused-seal', 'exclude_reason': 'STATIC_CONVERSION'})
        result = build(scope, nodes)
        self.assertTrue(result['complete'])
        self.assertEqual(len(result['excluded']), 1)
        self.assertEqual(len(result['releases']), 1)

    def test_exact_active_revision_hash_architecture_and_all_containers_match(self):
        for change in ({'artifact_sha256': 'f' * 64}, {'architecture': 'ARM64'},
                       {'registry_revision': 2}, {'source_sha': '2' * 40}, {'publish_run_id': 101},
                       {'containers': [{'name': 'web', 'image': 'ghcr.io/msg-ctf/challenges/web-one/web:latest'}]},
                       {'release_id': 'not-a-uuid'}, {'approved_target_ids': ['other-target']}):
            scope, nodes = inputs()
            scope['releases'][0].update(change)
            with self.subTest(change=change):
                self.assertFalse(build(scope, nodes)['complete'])

    def test_missing_helper_is_held_not_representative_only(self):
        published = source_plan()
        published['containers'].append({'name': 'db', 'image':
            'ghcr.io/msg-ctf/challenges/web-one/db@sha256:' + 'b' * 64})
        self.assertFalse(build(fetch=lambda *_: published)['complete'])

    def test_source_failure_or_malformed_yaml_is_redacted(self):
        for error in (ValueError('private-marker'), yaml.YAMLError('private-marker'),
                      OSError('private-marker')):
            def fail(*_):
                raise error
            result = build(fetch=fail)
            self.assertFalse(result['complete'])
            self.assertNotIn('private-marker', json.dumps(result))

    def test_mid_audit_main_change_is_rejected(self):
        calls = 0
        def api(path):
            nonlocal calls
            if path == 'git/ref/heads/main':
                calls += 1
                return {'object': {'sha': str(calls) * 40}}
            if path.startswith('contents/'):
                raw = b'deployment: {runtime_type: KUBERNETES}'
                return {'encoding': 'base64', 'size': len(raw), 'content': base64.b64encode(raw).decode()}
            return {'name': 'web-one-100-1-abcdef-publish-bundle'}
        with self.assertRaises(ValueError):
            build(api=api)

    def test_all_nodes_of_matching_architecture_are_bound_to_approval(self):
        scope, nodes = inputs()
        second = dict(nodes['nodes'][0], node_id='vm-two', target_id='target-two', node_uid='uid-two',
                      machine_id='machine-two', ssh_host='192.0.2.11')
        nodes['nodes'].append(second)
        self.assertFalse(build(scope, nodes)['complete'])
        scope['releases'][0]['approved_target_ids'].append('target-two')
        result = build(scope, nodes)
        self.assertTrue(result['complete'])
        self.assertEqual(len(result['tasks']), 2)

    def test_oversized_maintenance_is_rejected_before_ssh(self):
        scope, nodes = inputs()
        nodes['nodes'].append(dict(nodes['nodes'][0], node_id='vm-two', node_uid='uid-two',
                                  machine_id='machine-two', ssh_host='192.0.2.11'))
        with patch.object(vm, 'MAX_PAIRS', 1), self.assertRaises(ValueError):
            build(scope, nodes)

    def test_ssh_injection_duplicate_nodes_and_bad_bounds_are_rejected(self):
        for change in ({'ssh_host': '-oProxyCommand=bad'}, {'ssh_host': 'host;bad'},
                       {'ssh_host': '127.0.0.1'}, {'ssh_user': 'root;bad'},
                       {'ssh_port': True}, {'ssh_port': 65536}, {'agent_sha256': 'bad'},
                       {'ssh_host_key': 'ssh-ed25519 not-base64'}, {'image_fs_path': '/tmp/../outside'},
                       {'max_additional_bytes': -1}, {'reserve_bytes': True}):
            _, nodes = inputs()
            nodes['nodes'][0].update(change)
            with self.subTest(change=change), self.assertRaises((ValueError, TypeError)):
                vm.checked_nodes(nodes)
        _, nodes = inputs()
        nodes['nodes'] *= 2
        with self.assertRaises(ValueError):
            vm.checked_nodes(nodes)

    def test_cache_hit_is_verified_without_any_pull(self):
        plan = build()
        fake = FakeAgent(plan)
        result = vm.execute(plan, plan['plan_sha256'], fake, now=NOW)
        self.assertEqual(result['status'], 'SUCCEEDED')
        self.assertEqual(result['results'][0]['mode'], 'REUSED_VERIFIED')
        self.assertFalse(any(payload.get('pull') for _, _, payload in fake.calls))
        self.assertFalse(result['runtime_readiness_registered'])
        self.assertFalse(result['backend_operation_registered'])
        self.assertFalse(result['cold_pull_proven'])
        self.assertTrue(result['final_sweep_complete'])
        self.assertIn('final_verified_at', result['results'][0])

    def test_eviction_before_final_sweep_is_failure_without_automatic_repull(self):
        plan, inspections = build(), 0
        def change(node, command, payload, reply):
            nonlocal inspections
            if command == vm.AGENT_COMMAND:
                inspections += 1
                if inspections == 2:
                    return {'error_code': 'CONTENT_INCOMPLETE'}
            return reply
        fake = FakeAgent(plan, change=change)
        result = vm.execute(plan, plan['plan_sha256'], fake, now=NOW)
        self.assertEqual(result['status'], 'FAILED')
        self.assertFalse(result['final_sweep_complete'])
        self.assertEqual(result['failure']['stage'], 'FINAL_CACHE_CHECK')
        self.assertFalse(any(payload.get('pull') for _, _, payload in fake.calls))

    def test_identity_drift_during_final_sweep_cannot_be_complete(self):
        plan, observations = build(), 0
        def change(node, command, payload, reply):
            nonlocal observations
            if command == vm.PREFLIGHT_COMMAND:
                observations += 1
                if observations >= 4:
                    reply['boot_id'] = 'changed-after-download'
            return reply
        result = vm.execute(plan, plan['plan_sha256'], FakeAgent(plan, change=change), now=NOW)
        self.assertEqual(result['status'], 'FAILED')
        self.assertFalse(result['final_sweep_complete'])

    def test_partial_final_sweep_keeps_completed_checks_and_failure_location(self):
        scope, nodes = inputs()
        nodes['nodes'].append(dict(nodes['nodes'][0], node_id='vm-two', node_uid='uid-two',
                                  machine_id='machine-two', ssh_host='192.0.2.11'))
        plan, inspections = build(scope, nodes), {}
        def change(node, command, payload, reply):
            if command == vm.AGENT_COMMAND:
                count = inspections.get(node['node_id'], 0) + 1
                inspections[node['node_id']] = count
                if node['node_id'] == 'vm-two' and count == 2:
                    return {'error_code': 'CONTENT_INCOMPLETE'}
            return reply
        result = vm.execute(plan, plan['plan_sha256'], FakeAgent(plan, change=change), now=NOW)
        self.assertEqual(result['status'], 'FAILED')
        self.assertEqual(sum('final_verified_at' in row for row in result['results']), 1)
        self.assertEqual(result['failure']['node_id'], 'vm-two')

    def test_incomplete_content_is_pulled_then_verified_not_claimed_cold(self):
        plan = build()
        fake = FakeAgent(plan, missing=True)
        result = vm.execute(plan, plan['plan_sha256'], fake, now=NOW)
        self.assertEqual(result['status'], 'SUCCEEDED')
        self.assertEqual(result['results'][0]['mode'], 'PULLED_OR_REPAIRED')
        self.assertEqual(sum(payload.get('pull') is True for _, _, payload in fake.calls), 1)
        self.assertIn('agent_prepare_seconds', result['results'][0])
        self.assertFalse(result['cold_pull_proven'])

    def test_plan_tampering_wrong_approval_and_expiry_fail_before_ssh(self):
        plan = build()
        for expected in ('', 'f' * 64):
            with self.subTest(expected=expected), self.assertRaises(ValueError):
                vm.execute(plan, expected, lambda *_: self.fail('SSH must not start'), now=NOW)
        with self.assertRaises(ValueError):
            vm.execute(plan, plan['plan_sha256'], lambda *_: self.fail('SSH must not start'),
                       now=datetime(2026, 11, 3, tzinfo=timezone.utc))
        old = plan['plan_sha256']
        plan['tasks'][0]['images'].append('different-image')
        with self.assertRaises(ValueError):
            vm.execute(plan, old, lambda *_: self.fail('SSH must not start'), now=NOW)

    def test_held_scope_never_starts_ssh(self):
        scope, nodes = inputs()
        scope['releases'][0]['policy_approved'] = False
        plan = build(scope, nodes)
        with self.assertRaises(ValueError):
            vm.execute(plan, plan['plan_sha256'], lambda *_: self.fail('SSH must not start'), now=NOW)

    def test_identity_binary_and_disk_mismatch_stop_without_pull(self):
        plan = build()
        for field, value in (('node_uid', 'wrong'), ('boot_id', 'new-boot'),
                             ('machine_id', 'wrong'), ('architecture', 'ARM64'),
                             ('agent_sha256', 'e' * 64), ('preflight_sha256', 'e' * 64),
                             ('image_fs_path', '/wrong'), ('available_bytes', 1)):
            def change(node, command, payload, reply):
                if command == vm.PREFLIGHT_COMMAND:
                    reply[field] = value
                return reply
            fake = FakeAgent(plan, missing=True, change=change)
            with self.subTest(field=field):
                result = vm.execute(plan, plan['plan_sha256'], fake, now=NOW)
                self.assertEqual(result['status'], 'FAILED')
                self.assertFalse(any(payload.get('pull') for _, _, payload in fake.calls))

    def test_every_vm_is_preflighted_before_the_first_mutation(self):
        scope, nodes = inputs()
        second = dict(nodes['nodes'][0], node_id='vm-two', node_uid='uid-two',
                      machine_id='machine-two', ssh_host='192.0.2.11')
        nodes['nodes'].append(second)
        plan = build(scope, nodes)
        def change(node, command, payload, reply):
            if node['node_id'] == 'vm-two':
                reply['available_bytes'] = 0
            return reply
        fake = FakeAgent(plan, missing=True, change=change)
        result = vm.execute(plan, plan['plan_sha256'], fake, now=NOW)
        self.assertEqual(result['status'], 'FAILED')
        self.assertFalse(any(command == vm.AGENT_COMMAND for _, command, _ in fake.calls))

    def test_agent_policy_auth_and_platform_errors_do_not_trigger_a_pull(self):
        plan = build()
        for code in ('REGISTRY_UNAUTHORIZED', 'PLATFORM_MISMATCH', 'AGENT_UNAVAILABLE'):
            def change(node, command, payload, reply):
                return {'error_code': code} if command == vm.AGENT_COMMAND else reply
            fake = FakeAgent(plan, change=change)
            result = vm.execute(plan, plan['plan_sha256'], fake, now=NOW)
            self.assertEqual(result['status'], 'FAILED')
            self.assertFalse(any(payload.get('pull') for _, _, payload in fake.calls))

    def test_wrong_evidence_and_partial_failure_cannot_be_success(self):
        plan = build()
        for change in ({'complete': False}, {'node_uid': 'wrong'}, {'boot_id': 'wrong'},
                       {'architecture': 'ARM64'}, {'image': 'wrong'}, {'resolved_manifest_digest': 'bad'}):
            def alter(node, command, payload, reply):
                if command == vm.AGENT_COMMAND and 'evidence' in reply:
                    reply['evidence'].update(change)
                return reply
            result = vm.execute(plan, plan['plan_sha256'], FakeAgent(plan, change=alter), now=NOW)
            self.assertEqual(result['status'], 'FAILED')
            self.assertEqual(result['results'], [])

    def test_oci_index_child_digest_is_not_mistaken_for_root_digest_mismatch(self):
        plan = build()
        def change(node, command, payload, reply):
            if command == vm.AGENT_COMMAND:
                reply['evidence']['resolved_manifest_digest'] = 'sha256:' + 'b' * 64
            return reply
        result = vm.execute(plan, plan['plan_sha256'], FakeAgent(plan, change=change), now=NOW)
        self.assertEqual(result['status'], 'SUCCEEDED')
        self.assertEqual(result['results'][0]['resolved_manifest_digest'], 'sha256:' + 'b' * 64)

    def test_boot_change_between_inspection_and_pull_stops_mutation(self):
        plan, count = build(), 0
        def change(node, command, payload, reply):
            nonlocal count
            if command == vm.PREFLIGHT_COMMAND:
                count += 1
                if count >= 3:
                    reply['boot_id'] = 'rebooted'
            return reply
        fake = FakeAgent(plan, missing=True, change=change)
        self.assertEqual(vm.execute(plan, plan['plan_sha256'], fake, now=NOW)['status'], 'FAILED')
        self.assertFalse(any(payload.get('pull') for _, _, payload in fake.calls))

    def test_approval_expiring_during_inspection_stops_before_pull(self):
        plan = build()
        clock = SimpleNamespace(now=lambda _: NOW, fromisoformat=datetime.fromisoformat)
        def change(node, command, payload, reply):
            if command == vm.AGENT_COMMAND:
                clock.now = lambda _: datetime(2026, 11, 3, tzinfo=timezone.utc)
            return reply
        fake = FakeAgent(plan, missing=True, change=change)
        with patch.object(vm, 'datetime', clock):
            result = vm.execute(plan, plan['plan_sha256'], fake)
        self.assertEqual(result['status'], 'FAILED')
        self.assertFalse(any(payload.get('pull') for _, _, payload in fake.calls))

    def test_approval_expiring_during_final_sweep_cannot_report_success(self):
        plan, inspections = build(), 0
        clock = SimpleNamespace(now=lambda _: NOW, fromisoformat=datetime.fromisoformat)
        def change(node, command, payload, reply):
            nonlocal inspections
            if command == vm.AGENT_COMMAND:
                inspections += 1
                if inspections == 2:
                    clock.now = lambda _: datetime(2026, 11, 3, tzinfo=timezone.utc)
            return reply
        with patch.object(vm, 'datetime', clock):
            result = vm.execute(plan, plan['plan_sha256'], FakeAgent(plan, change=change))
        self.assertEqual(result['status'], 'FAILED')
        self.assertFalse(result['final_sweep_complete'])
        self.assertNotIn('final_verified_at', result['results'][0])

    def test_completed_pairs_are_persisted_before_a_later_failure(self):
        scope, nodes = inputs()
        second = dict(nodes['nodes'][0], node_id='vm-two', node_uid='uid-two',
                      machine_id='machine-two', ssh_host='192.0.2.11')
        nodes['nodes'].append(second)
        plan = build(scope, nodes)
        def change(node, command, payload, reply):
            if node['node_id'] == 'vm-two' and command == vm.AGENT_COMMAND:
                raise ValueError('private-server-error')
            return reply
        saved = []
        result = vm.execute(plan, plan['plan_sha256'], FakeAgent(plan, change=change), now=NOW,
                            on_result=lambda value: saved.append(copy.deepcopy(value)))
        self.assertEqual(result['status'], 'FAILED')
        self.assertEqual(len(result['results']), 1)
        self.assertEqual(len(saved[0]['results']), 1)
        self.assertNotIn('private-server-error', json.dumps(result))

    def test_ssh_uses_fixed_commands_pinned_hosts_and_no_forwarded_auth(self):
        _, inventory = inputs()
        node = inventory['nodes'][0]
        with tempfile.TemporaryDirectory() as temporary:
            key = Path(temporary) / 'key'
            key.write_text('private-key-fixture')
            key.chmod(0o600)
            def runner(args, payload):
                self.assertIn('-F', args)
                self.assertIn('/dev/null', args)
                for option in ('-oStrictHostKeyChecking=yes', '-oForwardAgent=no',
                               '-oIdentitiesOnly=yes', '-oIdentityAgent=none', '-oProxyCommand=none'):
                    self.assertIn(option, args)
                known = Path(next(value.split('=', 1)[1] for value in args if value.startswith('-oUserKnownHostsFile=')))
                self.assertEqual(known.read_text(), node['ssh_host'] + ' ' + KEY + '\n')
                self.assertEqual(args[-1], vm.PREFLIGHT_COMMAND)
                return {'ok': True}
            agent = vm.SSHAgent(key, runner)
            self.assertEqual(agent(node, vm.PREFLIGHT_COMMAND, {}), {'ok': True})
            with self.assertRaises(ValueError):
                agent(node, 'rm -rf /', {})

    def test_shared_permissions_empty_key_and_symlink_key_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            key = Path(temporary) / 'key'
            key.write_text('fixture')
            key.chmod(0o644)
            with self.assertRaises(ValueError):
                vm.SSHAgent(key)
            key.chmod(0o600)
            link = key.with_name('link')
            link.symlink_to(key)
            with self.assertRaises(ValueError):
                vm.SSHAgent(link)
            key.write_text('')
            with self.assertRaises(ValueError):
                vm.SSHAgent(key)

    def test_bounded_command_rejects_oversized_output_and_timeout(self):
        for code, timeout in (('import sys;sys.stdin.read();print("x"*70000)', 2),
                              ('import time;time.sleep(1)', 0.03)):
            with self.subTest(code=code), self.assertRaises((ValueError, subprocess.TimeoutExpired)):
                vm.bounded_command([sys.executable, '-c', code], {}, timeout=timeout)

    def test_subprocess_does_not_inherit_tokens(self):
        with patch.dict(os.environ, {'GH_TOKEN': 'private-github-token', 'VM_SSH_KEY': 'private-key'}):
            reply = vm.bounded_command([sys.executable, '-c',
                'import json,os,sys;sys.stdin.read();print(json.dumps({"clean": "GH_TOKEN" not in os.environ and "VM_SSH_KEY" not in os.environ}))'], {})
        self.assertTrue(reply['clean'])

    def test_invalid_json_and_duplicate_keys_are_rejected(self):
        for raw in (b'{"a":1,"a":2}', b'{"x":NaN}', b'x' * (1024 * 1024 + 1)):
            with self.subTest(raw=raw[:30]), self.assertRaises(ValueError):
                vm.load_json(raw)

    def test_private_reports_are_atomic_and_do_not_overwrite_a_pending_temp(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'report.json'
            vm.save_private(path, {'ok': True})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            vm.save_private(path, {'ok': False})
            self.assertEqual(json.loads(path.read_text()), {'ok': False})
            path.with_suffix('.tmp').write_text('retain')
            with self.assertRaises(FileExistsError):
                vm.save_private(path, {})

    def test_missing_ssh_key_does_not_create_an_ssh_process(self):
        result = subprocess.run([sys.executable, '-B', '-m', 'scripts.vm_image_prefetch',
                                 '--scope', '/missing', '--nodes', '/missing',
                                 '--output-dir', '/missing', '--apply'], cwd=ROOT,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn('Traceback', result.stderr)

    def test_cli_plan_keeps_inventory_private_and_never_constructs_ssh(self):
        scope, nodes = inputs()
        plan = build(scope, nodes)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'scope.json').write_text(json.dumps(scope))
            (root / 'nodes.json').write_text(json.dumps(nodes))
            argv = ['vm_image_prefetch', '--scope', str(root / 'scope.json'),
                    '--nodes', str(root / 'nodes.json'), '--output-dir', str(root / 'output')]
            output = io.StringIO()
            with patch.object(sys, 'argv', argv), patch.object(vm, 'build_plan', return_value=plan), \
                    patch.object(vm, 'SSHAgent') as ssh, redirect_stdout(output):
                self.assertEqual(vm.main(), 0)
            ssh.assert_not_called()
            self.assertNotIn('192.0.2.10', output.getvalue())
            self.assertNotIn('machine-one', output.getvalue())
            self.assertEqual((root / 'output').stat().st_mode & 0o777, 0o700)
            self.assertEqual((root / 'output/plan.json').stat().st_mode & 0o777, 0o600)
            self.assertFalse(json.loads((root / 'output/summary.json').read_text())['applied'])

    def test_content_growth_exceeding_budget_is_not_reported_successful(self):
        plan, checks = build(), 0
        def change(node, command, request, reply):
            nonlocal checks
            if command == vm.PREFLIGHT_COMMAND:
                checks += 1
                if checks >= 3:
                    reply['available_bytes'] = 7999
            return reply
        result = vm.execute(plan, plan['plan_sha256'], FakeAgent(plan, change=change), now=NOW)
        self.assertEqual(result['status'], 'FAILED')
        self.assertFalse(result['results'])


class VMCachePreflightTests(unittest.TestCase):
    def test_snapshot_reads_identity_space_and_binary_hash_without_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config, agent_config, binary = root / 'scope.json', root / 'agent.json', root / 'agent'
            config.write_text(json.dumps({'image_fs_path': temporary}))
            agent_config.write_text(json.dumps({'node_uid': 'node-one', 'k3s_binary': '/usr/local/bin/k3s'}))
            binary.write_bytes(b'trusted-agent-fixture')
            read_text = Path.read_text
            def identity(path, *args, **kwargs):
                if str(path) == '/etc/machine-id':
                    return 'machine-one\n'
                if str(path) == '/proc/sys/kernel/random/boot_id':
                    return 'boot-one\n'
                return read_text(path, *args, **kwargs)
            with patch.object(preflight, 'CONFIG', config), patch.object(preflight, 'AGENT_CONFIG', agent_config), \
                    patch.object(preflight, 'AGENT', binary), patch.object(preflight.os, 'geteuid', return_value=0), \
                    patch.object(preflight, 'trusted_file', side_effect=lambda path: path), \
                    patch.object(preflight.platform, 'system', return_value='Linux'), \
                    patch.object(preflight.platform, 'machine', return_value='x86_64'), \
                    patch.object(preflight.os, 'statvfs', return_value=SimpleNamespace(f_bavail=2, f_blocks=4, f_frsize=4096)), \
                    patch.object(Path, 'read_text', identity):
                reply = preflight.snapshot()
            self.assertEqual(reply['available_bytes'], 8192)
            self.assertEqual(reply['total_bytes'], 16384)
            self.assertEqual(reply['boot_id'], 'boot-one')
            self.assertEqual(reply['agent_sha256'], hashlib.sha256(b'trusted-agent-fixture').hexdigest())
            self.assertEqual(reply['node_uid_source'], 'OPERATOR_PINNED_AGENT_CONFIG')
    def test_non_root_invocation_fails_before_reading_host_files(self):
        with patch.object(preflight.os, 'geteuid', return_value=1000), self.assertRaises(ValueError):
            preflight.snapshot()

    def test_symlink_installation_is_not_trusted(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / 'file'
            target.write_text('fixture')
            link = target.with_name('link')
            link.symlink_to(target)
            with self.assertRaises(ValueError):
                preflight.trusted_file(link)

    def test_host_errors_do_not_disclose_paths_or_config(self):
        output = io.StringIO()
        with patch.object(preflight, 'snapshot', side_effect=OSError('private-marker')), redirect_stdout(output):
            self.assertEqual(preflight.main(), 1)
        self.assertEqual(json.loads(output.getvalue()), {'error_code': 'PREFLIGHT_FAILED'})
        self.assertNotIn('private-marker', output.getvalue())


class VMPrefetchWorkflowTests(unittest.TestCase):
    def test_native_cms_roundtrip_preserves_private_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            commands = [
                ['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                 '-subj', '/CN=prefetch-regression', '-keyout', str(root / 'key.pem'), '-out', str(root / 'cert.pem')],
                ['openssl', 'x509', '-in', str(root / 'cert.pem'), '-checkend', '10800', '-noout'],
            ]
            (root / 'evidence.tar').write_bytes(b'private-test-evidence')
            commands += [
                ['openssl', 'cms', '-encrypt', '-binary', '-aes-256-cbc', '-outform', 'DER',
                 '-in', str(root / 'evidence.tar'), '-out', str(root / 'evidence.cms'), str(root / 'cert.pem')],
                ['openssl', 'cms', '-decrypt', '-binary', '-inform', 'DER', '-in', str(root / 'evidence.cms'),
                 '-recip', str(root / 'cert.pem'), '-inkey', str(root / 'key.pem'), '-out', str(root / 'recovered.tar')],
            ]
            for command in commands:
                result = subprocess.run(command, capture_output=True, timeout=20)
                self.assertEqual(result.returncode, 0, 'Native CMS operation failed')
            self.assertEqual((root / 'recovered.tar').read_bytes(), b'private-test-evidence')
            self.assertNotIn(b'private-test-evidence', (root / 'evidence.cms').read_bytes())
    def workflow(self):
        return yaml.load((ROOT / '.github/workflows/vm-image-prefetch.yml').read_text(), Loader=yaml.BaseLoader)

    def test_write_is_manual_disabled_by_default_and_requires_approval_environment(self):
        workflow = self.workflow()
        self.assertEqual(set(workflow['on']), {'workflow_dispatch'})
        self.assertEqual(workflow['on']['workflow_dispatch']['inputs']['apply']['default'], 'false')
        self.assertEqual(workflow['permissions'], {'contents': 'read'})
        self.assertEqual(workflow['jobs']['apply']['environment'], 'vm-image-prefetch')
        self.assertEqual(workflow['jobs']['apply']['if'], 'inputs.apply')
        self.assertEqual(workflow['concurrency']['cancel-in-progress'], 'false')
        plan_text = json.dumps(workflow['jobs']['plan'])
        self.assertNotIn('VM_IMAGE_PREFETCH_SSH_KEY', plan_text)
        self.assertIn('VM_IMAGE_PREFETCH_ENABLED', plan_text)

    def test_guard_actually_rejects_wrong_event_branch_repository_and_disabled_apply(self):
        command = self.workflow()['jobs']['plan']['steps'][0]['run']
        base = {**os.environ, 'GITHUB_REPOSITORY': 'MSG-CTF/msgctf-devsecops',
                'GITHUB_EVENT_NAME': 'workflow_dispatch', 'GITHUB_REF': 'refs/heads/main',
                'APPLY': 'false', 'ENABLED': '', 'EXPECTED_SHA': ''}
        cases = [({}, 0), ({'GITHUB_EVENT_NAME': 'push'}, 1),
                 ({'GITHUB_EVENT_NAME': 'schedule'}, 1), ({'GITHUB_REF': 'refs/heads/feature'}, 1),
                 ({'GITHUB_REPOSITORY': 'other/repo'}, 1), ({'APPLY': 'true'}, 1),
                 ({'APPLY': 'true', 'ENABLED': 'true', 'EXPECTED_SHA': 'bad'}, 1),
                 ({'APPLY': 'true', 'ENABLED': 'true', 'EXPECTED_SHA': 'a' * 64}, 0)]
        for change, expected in cases:
            result = subprocess.run(['bash', '-c', command], env={**base, **change},
                                    capture_output=True, timeout=5)
            with self.subTest(change=change):
                self.assertEqual(result.returncode, expected)

    def test_only_aggregate_reports_are_uploaded_and_private_files_are_cleaned(self):
        workflow = self.workflow()
        for job in workflow['jobs'].values():
            for step in job['steps']:
                if 'actions/upload-artifact' in step.get('uses', ''):
                    self.assertTrue('summary.json' in step['with']['path'] or
                                    'vm-prefetch-private-results.cms' in step['with']['path'])
                    self.assertNotIn('plan.json', step['with']['path'])
                    self.assertNotIn('ssh-key', step['with']['path'])
        text = (ROOT / '.github/workflows/vm-image-prefetch.yml').read_text()
        self.assertIn('trap ', text)
        self.assertNotIn('packages: write', text)
        self.assertNotIn('id-token: write', text)

    def test_report_recipient_is_checked_before_any_ssh_execution(self):
        step = next(step for step in self.workflow()['jobs']['apply']['steps']
                    if 'REPORT_CERT' in step.get('env', {}))
        self.assertLess(step['run'].index('openssl x509'), step['run'].index('python3 -B -m scripts.vm_image_prefetch'))
        self.assertIn('REPORT_CERT_SHA', step['run'])
        self.assertIn('openssl cms -encrypt -binary -aes-256-cbc', step['run'])

    def test_workflow_only_changes_trigger_existing_ci(self):
        workflow = yaml.load((ROOT / '.github/workflows/pipeline-self-test.yml').read_text(), Loader=yaml.BaseLoader)
        for event in ('push', 'pull_request'):
            self.assertIn('.github/workflows/vm-image-prefetch.yml', workflow['on'][event]['paths'])


if __name__ == '__main__':
    unittest.main()
