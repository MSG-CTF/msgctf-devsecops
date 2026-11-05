import copy
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import vm_image_prefetch as vm
from scripts import vm_pod_image_bridge as bridge
from tests.test_vm_image_prefetch import build, evidence, host_reply, inputs, NOW


IMAGE = 'ghcr.io/msg-ctf/challenges/web-one/web@sha256:' + 'b' * 64
AGENT = 'ghcr.io/msg-ctf/secure-provisioner-image-agent@sha256:' + 'a' * 64
NODE_UID = '00000000-0000-4000-8000-000000000001'
POD_UID = '00000000-0000-4000-8000-000000000002'
BOOT_ID = '00000000-0000-4000-8000-000000000003'


def config():
    return {'schema_version': 1, 'node_name': 'node-one.example.internal', 'node_uid': NODE_UID,
            'machine_id': 'd' * 32, 'boot_id': BOOT_ID, 'architecture': 'AMD64',
            'agent_pod_name': 'runtime-image-agent-one', 'agent_pod_uid': POD_UID,
            'agent_image': AGENT, 'agent_image_id': AGENT,
            'image_fs_path': '/var/lib/rancher/k3s/agent/containerd'}


def objects(cfg=None):
    cfg = cfg or config()
    node = {'metadata': {'name': cfg['node_name'], 'uid': cfg['node_uid']},
            'status': {'nodeInfo': {'machineID': cfg['machine_id'], 'bootID': cfg['boot_id'],
                                   'operatingSystem': 'linux', 'architecture': 'amd64'},
                       'conditions': [{'type': 'Ready', 'status': 'True'}]}}
    pod = {'metadata': {'name': cfg['agent_pod_name'], 'uid': cfg['agent_pod_uid'],
                        'namespace': bridge.NAMESPACE,
                        'labels': {'app.kubernetes.io/name': 'runtime-image-agent'}},
           'spec': {'nodeName': cfg['node_name'], 'containers': [{'name': 'agent', 'image': cfg['agent_image']}]},
           'status': {'phase': 'Running', 'conditions': [{'type': 'Ready', 'status': 'True'}],
                      'containerStatuses': [{'name': 'agent', 'imageID': cfg['agent_image_id'],
                                             'ready': True, 'state': {'running': {}}}]}}
    return node, pod


def request(pull=False):
    return {'image': IMAGE, 'architecture': 'AMD64', 'pull': pull}


def agent_response(cfg=None):
    cfg = cfg or config()
    return {'evidence': {**{key: cfg[key] for key in ('node_uid', 'machine_id', 'boot_id', 'architecture')},
                         'os': 'linux', 'image': IMAGE, 'resolved_manifest_digest': 'sha256:' + 'b' * 64,
                         'complete': True}}


class FakeKube:
    def __init__(self, cfg=None, change=None, reply=None):
        self.cfg = cfg or config()
        self.calls, self.change = [], change
        self.reply = reply if reply is not None else agent_response(self.cfg)

    def __call__(self, args, payload, deadline, *, agent=False):
        self.calls.append((list(args), payload, agent))
        node, pod = objects(self.cfg)
        if agent:
            result = copy.deepcopy(self.reply)
        elif args[:2] == ['get', 'node']:
            result = node
        else:
            result = {'items': [pod]}
        return self.change(args, result, agent, len(self.calls)) if self.change else result


class HostPatches:
    def __enter__(self):
        self.patchers = [
            patch.object(bridge, 'trusted_path', side_effect=lambda path, **kwargs: path),
            patch.object(Path, 'read_text', lambda path: 'd' * 32 if str(path) == '/etc/machine-id' else BOOT_ID),
            patch.object(bridge.platform, 'system', return_value='Linux'),
            patch.object(bridge.platform, 'machine', return_value='x86_64'),
            patch.object(bridge.os, 'statvfs', return_value=SimpleNamespace(f_bavail=10000, f_frsize=1, f_blocks=20000)),
        ]
        for item in self.patchers:
            item.start()
        return self

    def __exit__(self, *args):
        for item in reversed(self.patchers):
            item.stop()


class PodBridgeTests(unittest.TestCase):
    def test_preflight_reads_live_node_and_pod_only(self):
        kube = FakeKube()
        with HostPatches():
            result = bridge.handle('preflight', {}, config(), run=kube)
        self.assertEqual(result['node_uid_source'], 'LIVE_KUBERNETES_AND_HOST_CHECK')
        self.assertEqual(result['node_uid'], NODE_UID)
        self.assertEqual(result['agent_pod_uid'], POD_UID)
        self.assertEqual(result['agent_image_id'], AGENT)
        self.assertEqual(result['available_bytes'], 10000)
        self.assertEqual(len(kube.calls), 2)
        self.assertFalse(any(agent for _, _, agent in kube.calls))

    def test_prepare_reuses_exact_runtime_exec_command_and_json(self):
        for pull in (False, True):
            kube = FakeKube()
            with self.subTest(pull=pull), HostPatches():
                result = bridge.handle('prepare', request(pull), config(), run=kube)
            self.assertEqual(result, agent_response())
            self.assertEqual(len(kube.calls), 5)
            args, payload, agent = kube.calls[2]
            self.assertTrue(agent)
            self.assertEqual(args, ['-n', bridge.NAMESPACE, 'exec', '-i', 'runtime-image-agent-one',
                                    '-c', 'agent', '--', '/usr/local/bin/image-agent', '--kubernetes'])
            self.assertEqual(json.loads(payload), request(pull))
            self.assertFalse(any('apply' in args or 'delete' in args or 'crictl' in args for args, _, _ in kube.calls))

    def test_node_uid_machine_boot_arch_and_ready_mismatch_stop_before_exec(self):
        changes = [('uid', 'different'), ('machineID', 'wrong'), ('bootID', 'wrong'),
                   ('architecture', 'arm64'), ('operatingSystem', 'windows'), ('ready', 'False')]
        for field, value in changes:
            def change(args, row, agent, count):
                if args[:2] == ['get', 'node']:
                    if field == 'uid':
                        row['metadata']['uid'] = value
                    elif field == 'ready':
                        row['status']['conditions'][0]['status'] = value
                    else:
                        row['status']['nodeInfo'][field] = value
                return row
            kube = FakeKube(change=change)
            with self.subTest(field=field), HostPatches(), self.assertRaises(ValueError):
                bridge.handle('prepare', request(True), config(), run=kube)
            self.assertFalse(any(agent for _, _, agent in kube.calls))

    def test_host_identity_or_platform_mismatch_cannot_be_ignored(self):
        for target, value in (('system', 'Darwin'), ('machine', 'aarch64')):
            kube = FakeKube()
            with HostPatches(), patch.object(bridge.platform, target, return_value=value), self.assertRaises(ValueError):
                bridge.handle('prepare', request(True), config(), run=kube)
            self.assertFalse(any(agent for _, _, agent in kube.calls))
        with HostPatches(), patch.object(Path, 'read_text', return_value='wrong'), self.assertRaises(ValueError):
            bridge.handle('preflight', {}, config(), run=FakeKube())

    def test_pod_uid_node_image_status_and_ready_are_pinned(self):
        for field in ('uid', 'name', 'node', 'image', 'image_id', 'container_ready', 'waiting', 'deleting', 'namespace'):
            def change(args, row, agent, count):
                if 'items' in row:
                    pod = row['items'][0]
                    if field in ('uid', 'name', 'namespace'):
                        pod['metadata'][field] = 'unexpected'
                    elif field == 'node':
                        pod['spec']['nodeName'] = 'another-node'
                    elif field == 'image':
                        pod['spec']['containers'][0]['image'] = AGENT.replace('a' * 64, 'c' * 64)
                    elif field == 'image_id':
                        pod['status']['containerStatuses'][0]['imageID'] = 'containerd://sha256:' + 'a' * 64
                    elif field == 'container_ready':
                        pod['status']['containerStatuses'][0]['ready'] = False
                    elif field == 'waiting':
                        pod['status']['containerStatuses'][0]['state'] = {'waiting': {}}
                    else:
                        pod['metadata']['deletionTimestamp'] = '2026-11-05T00:00:00Z'
                return row
            kube = FakeKube(change=change)
            with self.subTest(field=field), HostPatches(), self.assertRaises(ValueError):
                bridge.handle('prepare', request(True), config(), run=kube)
            self.assertFalse(any(agent for _, _, agent in kube.calls))

    def test_duplicate_ready_agents_and_extra_containers_are_rejected(self):
        for mode in ('duplicate', 'sidecar', 'conditions'):
            def change(args, row, agent, count):
                if 'items' in row:
                    if mode == 'duplicate':
                        row['items'].append(copy.deepcopy(row['items'][0]))
                    elif mode == 'sidecar':
                        row['items'][0]['spec']['containers'].append({'name': 'sidecar'})
                    else:
                        row['items'][0]['status']['conditions'] *= 2
                return row
            with self.subTest(mode=mode), HostPatches(), self.assertRaises(ValueError):
                bridge.handle('preflight', {}, config(), run=FakeKube(change=change))

    def test_approved_index_and_resolved_image_id_are_separate(self):
        cfg = config()
        cfg['agent_image_id'] = AGENT.replace('a' * 64, 'c' * 64)
        with HostPatches():
            result = bridge.handle('preflight', {}, cfg, run=FakeKube(cfg))
        self.assertEqual(result['agent_image'], AGENT)
        self.assertNotEqual(result['agent_image_id'], AGENT)

    def test_docker_pullable_prefix_is_normalized_without_guessing_config_ids(self):
        def change(args, row, agent, count):
            if 'items' in row:
                row['items'][0]['status']['containerStatuses'][0]['imageID'] = 'docker-pullable://' + AGENT
            return row
        with HostPatches():
            result = bridge.handle('preflight', {}, config(), run=FakeKube(change=change))
        self.assertEqual(result['agent_image_id'], AGENT)

    def test_identity_drift_after_exec_is_failure_not_success(self):
        def change(args, row, agent, count):
            if count > 3 and 'items' in row:
                row['items'][0]['metadata']['uid'] = 'recreated-pod'
            return row
        kube = FakeKube(change=change)
        with HostPatches(), self.assertRaises(ValueError):
            bridge.handle('prepare', request(True), config(), run=kube)
        self.assertEqual(sum(agent for _, _, agent in kube.calls), 1)

    def test_agent_incomplete_is_preserved_and_unknown_errors_are_redacted(self):
        for code, expected in (('CONTENT_INCOMPLETE', 'CONTENT_INCOMPLETE'),
                               ('PLATFORM_MISMATCH', 'PLATFORM_MISMATCH'),
                               ('private-token-from-error', 'AGENT_UNAVAILABLE')):
            with self.subTest(code=code), HostPatches():
                result = bridge.handle('prepare', request(), config(), run=FakeKube(reply={'error_code': code}))
            self.assertEqual(result, {'error_code': expected})

    def test_false_wrong_identity_image_and_malformed_digest_are_rejected(self):
        for change in ({'complete': False}, {'node_uid': 'wrong'}, {'machine_id': 'wrong'},
                       {'image': 'wrong'}, {'architecture': 'ARM64'}, {'resolved_manifest_digest': 'bad'}):
            reply = agent_response()
            reply['evidence'].update(change)
            with self.subTest(change=change), HostPatches(), self.assertRaises(ValueError):
                bridge.handle('prepare', request(), config(), run=FakeKube(reply=reply))

    def test_unexpected_agent_payload_is_not_returned(self):
        for reply in ({'evidence': agent_response()['evidence'], 'body': 'private-value'},
                      {'error_code': 'CONTENT_INCOMPLETE', 'evidence': agent_response()['evidence']}):
            with HostPatches(), self.assertRaises(ValueError):
                bridge.handle('prepare', request(), config(), run=FakeKube(reply=reply))

    def test_requests_cannot_override_command_target_namespace_or_credentials(self):
        cases = [dict(request(), pull='true'), dict(request(), image=IMAGE + '\ncommand'),
                 dict(request(), image='ghcr.io/other/project/web@sha256:' + 'a' * 64),
                 dict(request(), architecture='ARM64'), dict(request(), namespace='kube-system'),
                 dict(request(), token='private-token')]
        for payload in cases:
            kube = FakeKube()
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                bridge.handle('prepare', payload, config(), run=kube)
            self.assertEqual(kube.calls, [])
        with self.assertRaises(ValueError):
            bridge.handle('preflight', {'pull': True}, config(), run=FakeKube())

    def test_config_is_exact_and_does_not_accept_commands_or_alternate_images(self):
        for change in ({'schema_version': True}, {'k3s_binary': '/tmp/user-command'},
                       {'agent_image': 'ghcr.io/other/project@sha256:' + 'a' * 64},
                       {'node_name': 'node;command'}, {'agent_pod_uid': 'not-a-uuid'},
                       {'machine_id': 'wrong'}, {'image_fs_path': '/var/../tmp'}):
            cfg = config()
            cfg.update(change)
            with tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / 'config.json'
                path.write_text(json.dumps(cfg))
                with self.subTest(change=change), patch.object(bridge, 'CONFIG', path), \
                     patch.object(bridge.os, 'geteuid', return_value=0), \
                     patch.object(bridge, 'trusted_path', side_effect=lambda value, **kwargs: value), \
                     self.assertRaises(ValueError):
                    bridge.load_config()

    def test_readonly_config_and_private_root_ownership_are_required(self):
        with patch.object(bridge.os, 'geteuid', return_value=1), self.assertRaises(ValueError):
            bridge.load_config()
        path = SimpleNamespace(is_symlink=lambda: False,
            stat=lambda: SimpleNamespace(st_mode=stat.S_IFREG | 0o644, st_uid=0), parents=[])
        with self.assertRaises(ValueError):
            bridge.trusted_path(path, private=True)
        path.stat = lambda: SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_uid=1000)
        with self.assertRaises(ValueError):
            bridge.trusted_path(path)

    def test_json_duplicate_nonfinite_and_oversized_input_are_rejected(self):
        for raw in (b'{"pull":false,"pull":true}', b'{"x":NaN}', b'x' * (bridge.MAX_REQUEST + 1)):
            with self.subTest(raw=raw[:30]), self.assertRaises(ValueError):
                bridge.parse_json(raw, bridge.MAX_REQUEST)

    def test_kubectl_uses_fixed_kubeconfig_tls_and_limits(self):
        with patch.object(bridge, 'bounded_process', return_value={}) as run:
            bridge.kubectl(['get', 'node', 'node-one', '-o', 'json'], b'', bridge.time.monotonic() + 10)
        args, payload, timeout, limit = run.call_args.args
        self.assertEqual(args[:4], ['/usr/local/bin/k3s', 'kubectl', '--kubeconfig', '/etc/rancher/k3s/k3s.yaml'])
        self.assertIn('--insecure-skip-tls-verify=false', args)
        self.assertTrue(any(value.startswith('--request-timeout=') for value in args))
        self.assertLessEqual(timeout, 5)
        self.assertEqual(limit, bridge.MAX_JSON)

    def test_expired_bridge_budget_does_not_start_kubectl(self):
        with patch.object(bridge, 'bounded_process') as run, self.assertRaises(ValueError):
            bridge.kubectl(['get', 'node', 'node-one'], b'', bridge.time.monotonic() - 1)
        run.assert_not_called()

    def test_child_environment_excludes_auth_proxy_and_python_injection(self):
        with patch.dict(os.environ, {'GH_TOKEN': 'private-token', 'HTTPS_PROXY': 'private-proxy',
                                    'PYTHONPATH': '/user/path', 'KUBECONFIG': '/user/config'}):
            result = bridge.bounded_process([sys.executable, '-c',
                'import os,sys,json;sys.stdin.read();print(json.dumps({"clean": all(k not in os.environ for k in ("GH_TOKEN","HTTPS_PROXY","PYTHONPATH","KUBECONFIG"))}))'], b'{}', 3, 1000)
        self.assertTrue(result['clean'])

    def test_child_output_and_time_are_bounded(self):
        for code, timeout, limit in (('import sys;sys.stdin.read();print("x"*2000)', 3, 1000),
                                     ('import time;time.sleep(2)', 0.03, 1000)):
            with self.subTest(code=code), self.assertRaises((ValueError, subprocess.SubprocessError)):
                bridge.bounded_process([sys.executable, '-c', code], b'{}', timeout, limit)

    def test_cli_errors_do_not_print_private_configuration(self):
        with patch('sys.argv', ['bridge', 'preflight']), \
             patch.object(bridge, 'load_config', side_effect=ValueError('private-config-value')), \
             patch('sys.stdout', new_callable=io.StringIO) as output:
            code = bridge.main()
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output.getvalue()), {'error_code': 'POD_AGENT_CHECK_FAILED'})
        self.assertNotIn('private-config-value', output.getvalue())


def pod_inventory():
    scope, nodes = inputs()
    cfg = config()
    node = nodes['nodes'][0]
    del node['agent_sha256']
    node.update(agent_transport='kubernetes', **{key: cfg[key] for key in (
        'node_name', 'node_uid', 'machine_id', 'boot_id', 'agent_pod_name', 'agent_pod_uid',
        'agent_image', 'agent_image_id')})
    return scope, nodes


def bridge_reply(node, plan):
    return {**{key: node[key] for key in vm.POD_FIELDS | {
                'node_uid', 'machine_id', 'boot_id', 'architecture', 'image_fs_path'}},
            'schema_version': 1, 'os': 'linux', 'agent_transport': 'kubernetes',
            'available_bytes': 10000, 'total_bytes': 20000,
            'preflight_sha256': plan['pod_bridge_sha256']}


class PodTransportTests(unittest.TestCase):
    def test_plan_pins_pod_identity_image_and_bridge_without_host_agent_hash(self):
        scope, nodes = pod_inventory()
        plan = build(scope, nodes)
        self.assertTrue(plan['complete'])
        self.assertIn('pod_bridge_sha256', plan)
        self.assertNotIn('agent_sha256', plan['nodes'][0])
        self.assertEqual(plan['nodes'][0]['agent_pod_uid'], POD_UID)
        self.assertNotIn(AGENT, plan['tasks'][0]['images'])

    def test_fixed_ssh_commands_use_bridge_without_raw_kubectl_or_install(self):
        scope, nodes = pod_inventory()
        with tempfile.TemporaryDirectory() as temporary:
            key = Path(temporary) / 'key'
            key.write_text('private-fixture')
            key.chmod(0o600)
            called = []
            agent = vm.SSHAgent(key, runner=lambda args, payload: called.append(args[-1]) or {})
            agent(nodes['nodes'][0], vm.PREFLIGHT_COMMAND, {})
            agent(nodes['nodes'][0], vm.AGENT_COMMAND, request())
        self.assertEqual(called, [vm.POD_PREFLIGHT_COMMAND, vm.POD_AGENT_COMMAND])
        self.assertFalse(any('kubectl' in value or 'install' in value for value in called))

    def test_bad_transport_partial_pins_or_tagged_agent_are_rejected(self):
        for change in ({'agent_transport': 'auto'}, {'agent_image': AGENT.split('@')[0] + ':latest'},
                       {'agent_pod_uid': 'wrong'}, {'node_name': 'node;command'}):
            scope, nodes = pod_inventory()
            nodes['nodes'][0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                build(scope, nodes)
        scope, nodes = pod_inventory()
        del nodes['nodes'][0]['agent_image_id']
        with self.assertRaises(ValueError):
            build(scope, nodes)

    def test_pod_or_bridge_drift_is_failure_before_any_pull(self):
        for field, value in (('agent_pod_uid', 'wrong'), ('agent_image', AGENT.replace('a'*64, 'b'*64)),
                             ('preflight_sha256', 'e'*64)):
            scope, nodes = pod_inventory()
            plan, calls = build(scope, nodes), []
            def call(node, command, payload):
                calls.append((command, payload))
                result = bridge_reply(node, plan)
                result[field] = value
                return result
            with self.subTest(field=field):
                report = vm.execute(plan, plan['plan_sha256'], call, now=NOW)
                self.assertEqual(report['status'], 'FAILED')
                self.assertFalse(any(command == vm.AGENT_COMMAND for command, _ in calls))

    def test_pod_flow_keeps_shared_final_sweep_and_no_workload_activation(self):
        scope, nodes = pod_inventory()
        plan = build(scope, nodes)
        def call(node, command, payload):
            return bridge_reply(node, plan) if command == vm.PREFLIGHT_COMMAND else evidence(node, payload['image'])
        report = vm.execute(plan, plan['plan_sha256'], call, now=NOW)
        self.assertEqual(report['status'], 'SUCCEEDED')
        self.assertTrue(report['final_sweep_complete'])
        self.assertFalse(report['active_changed'])
        self.assertFalse(report['pod_started'])

    def test_host_inventory_remains_unchanged_and_no_automatic_fallback(self):
        original = build()
        self.assertNotIn('pod_bridge_sha256', original)
        self.assertNotIn('agent_transport', original['nodes'][0])
        scope, nodes = pod_inventory()
        nodes['nodes'][0]['agent_sha256'] = 'd'*64
        with self.assertRaises(ValueError):
            build(scope, nodes)

    def test_mixed_host_and_pod_inventory_uses_each_approved_evidence(self):
        scope, nodes = pod_inventory()
        host = inputs()[1]['nodes'][0]
        host.update(node_id='vm-two', target_id='target-two', node_uid='host-uid',
                    machine_id='host-machine', ssh_host='192.0.2.11')
        nodes['nodes'].append(host)
        scope['releases'][0]['approved_target_ids'].append('target-two')
        plan = build(scope, nodes)
        def call(node, command, payload):
            if command == vm.PREFLIGHT_COMMAND:
                return bridge_reply(node, plan) if node.get('agent_transport') == 'kubernetes' else host_reply(node, plan)
            return evidence(node, payload['image'])
        result = vm.execute(plan, plan['plan_sha256'], call, now=NOW)
        self.assertEqual(result['status'], 'SUCCEEDED')
        self.assertEqual(len(result['results']), 2)
        self.assertTrue(result['final_sweep_complete'])

    def test_pod_recreation_requires_new_plan_approval(self):
        scope, nodes = pod_inventory()
        old = build(scope, nodes)
        nodes['nodes'][0]['agent_pod_uid'] = '00000000-0000-4000-8000-000000000099'
        new = build(scope, nodes)
        self.assertNotEqual(old['plan_sha256'], new['plan_sha256'])
        with self.assertRaises(ValueError):
            vm.execute(new, old['plan_sha256'], lambda *_: self.fail('must not start SSH'), now=NOW)


if __name__ == '__main__':
    unittest.main()
