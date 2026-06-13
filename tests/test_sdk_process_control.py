from server.agent_runtime.sdk_process_control import process_pid, process_returncode


class _FakeProc:
    pid = 4321
    returncode = 0


def test_process_pid_reads_attr():
    assert process_pid(_FakeProc()) == 4321


def test_process_returncode_reads_attr():
    assert process_returncode(_FakeProc()) == 0


def test_process_pid_handles_none():
    assert process_pid(None) is None
