import importlib.util
import sys
from pathlib import Path

import pytest
import logging

log = logging.getLogger(__name__)

logging.basicConfig(level=logging.DEBUG)

MODULE_PATH = Path(__file__).absolute().parent.parent / "coredns_editor.py"
_spec = importlib.util.spec_from_file_location("coredns_editor", MODULE_PATH)
coredns_editor = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(coredns_editor)


EXAMPLE_YAML = """apiVersion: v1
data:
  Corefile: |
    .:53 {
        errors
        health {
           lameduck 5s
        }
        ready
        kubernetes cluster.local in-addr.arpa ip6.arpa {
           pods insecure
           fallthrough in-addr.arpa ip6.arpa
           ttl 30
        }
        prometheus :9153
        forward . /etc/resolv.conf {
           max_concurrent 1000
        }
        cache 30 {
           disable success cluster.local
           disable denial cluster.local
        }
        loop
        reload
        loadbalance
    }
    # block to forward .consul queries to your Consul service
    consul:53 {
        forward . 10.96.19.42:8600
    }
kind: ConfigMap
metadata:
  creationTimestamp: "2026-01-06T17:33:39Z"
  name: coredns
  namespace: kube-system
  resourceVersion: "863"
  uid: 65087509-4ac6-49dd-aff0-d6d126e21cbc
"""


def _extract_corefile(yaml_text: str) -> str:
    start, end, indent = coredns_editor.find_corefile_block(yaml_text)
    lines = yaml_text.splitlines(True)
    stripped = []
    for ln in lines[start:end]:
        if ln.startswith(indent):
            stripped.append(ln[len(indent):])
        else:
            stripped.append(ln)
    return "".join(stripped)


def test_find_corefile_block_basic():
    """Test that the corefile block is found and the indent is correct.
    Test that the corefile block is extracted correctly.
    Test that the corefile block contains the correct content.
    """
    start, end, indent = coredns_editor.find_corefile_block(EXAMPLE_YAML)
    log.debug(f"start: {start}, end: {end}, indent: `{indent}`")
    assert start < end
    assert indent == "    "
    assert end - start == 27
    corefile = _extract_corefile(EXAMPLE_YAML)
    assert corefile.lstrip().startswith(".:53 {")
    assert "consul:53 {" in corefile


def test_find_corefile_block_missing_errors():
    """Test that the correct errors are raised when the corefile block is missing.
    All 3 errors are covered:
    - Could not find 'Corefile: |' in YAML
    - Corefile block has no content
    - Could not determine Corefile block indentation
    """
    with pytest.raises(ValueError, match="Could not find 'Corefile: |' in YAML"):
        coredns_editor.find_corefile_block("apiVersion: v1\nkind: ConfigMap\n")
    with pytest.raises(ValueError, match="Corefile block has no content"):
        coredns_editor.find_corefile_block("apiVersion: v1\nkind: ConfigMap\n\nCorefile: |")
    with pytest.raises(ValueError, match="Could not determine Corefile block indentation"):
        coredns_editor.find_corefile_block("apiVersion: v1\nkind: ConfigMap\n\nCorefile: |\n.:53 {\nerrors")


def test_insert_hosts_after_ready():
    corefile = _extract_corefile(EXAMPLE_YAML)
    updated = coredns_editor.insert_hosts_into_corefile(corefile, "1.2.3.4", "node.local")
    lines = updated.splitlines()
    ready_index = lines.index("    ready")
    hosts_index = lines.index("    hosts {")
    assert hosts_index == ready_index + 1
    assert "        1.2.3.4 node.local" in updated
    assert updated.endswith("\n")


def test_insert_hosts_idempotent():
    """Test that inserting hosts into the corefile is idempotent.
    """
    corefile = _extract_corefile(EXAMPLE_YAML)
    once = coredns_editor.insert_hosts_into_corefile(corefile, "1.2.3.4", "node.local")
    twice = coredns_editor.insert_hosts_into_corefile(once, "1.2.3.4", "node.local")
    assert twice == once


def test_insert_hosts_missing_server_block():
    """Test that the correct error is raised when the server block is missing.
    """
    with pytest.raises(ValueError, match=".:53"):
        coredns_editor.insert_hosts_into_corefile("consul:53 {\n}\n", "1.2.3.4", "node.local")


def test_main_prints_output(tmp_path, capsys, monkeypatch):
    """Test that main prints the output to the console.

    Args:
        tmp_path (Path): Provide a pathlib.Path object to a temporary directory which is unique to each test function.
        capsys (pytest.CaptureFixture): Capture stdout and stderr.
        monkeypatch (pytest.MonkeyPatch): Temporarily modify classes, functions, dictionaries, os.environ, and other objects.
    """
    input_path = tmp_path / "coredns.yaml"
    input_path.write_text(EXAMPLE_YAML, encoding="utf-8")
    argv = [
        "coredns_editor.py",
        str(input_path),
        "--ip",
        "1.2.3.4",
        "--hostname",
        "node.local",
    ]
    monkeypatch.setattr(sys, "argv", argv)
    assert coredns_editor.main() == 0
    out = capsys.readouterr().out
    assert "hosts {" in out
    assert "1.2.3.4 node.local" in out


def test_main_in_place(tmp_path, monkeypatch):
    """Test that core file is updated in place.

    Args:
        tmp_path (_type_): Provide a pathlib.Path object to a temporary directory which is unique to each test functio
        monkeypatch (_type_): Temporarily modify classes, functions, dictionaries, os.environ, and other objects.
    """
    input_path = tmp_path / "coredns.yaml"
    input_path.write_text(EXAMPLE_YAML, encoding="utf-8")
    argv = [
        "coredns_editor.py",
        str(input_path),
        "--ip",
        "1.2.3.4",
        "--hostname",
        "node.local",
        "-i",
    ]
    monkeypatch.setattr(sys, "argv", argv)
    assert coredns_editor.main() == 0
    updated = input_path.read_text(encoding="utf-8")
    assert "hosts {" in updated
    assert "1.2.3.4 node.local" in updated


def test_main_output_file(tmp_path, monkeypatch):
    """Test that main writes to a separate output file with -o."""
    input_path = tmp_path / "coredns.yaml"
    output_path = tmp_path / "coredns_out.yaml"
    input_path.write_text(EXAMPLE_YAML, encoding="utf-8")
    argv = [
        "coredns_editor.py",
        str(input_path),
        "--ip",
        "1.2.3.4",
        "--hostname",
        "node.local",
        "-o",
        str(output_path),
    ]
    monkeypatch.setattr(sys, "argv", argv)
    assert coredns_editor.main() == 0
    assert input_path.read_text(encoding="utf-8") == EXAMPLE_YAML
    out = output_path.read_text(encoding="utf-8")
    assert "hosts {" in out
    assert "1.2.3.4 node.local" in out


def test_skip_insertion_when_hostname_exists_different_ip():
    """Hostname already in a hosts block with a different IP — no new block added."""
    corefile = _extract_corefile(EXAMPLE_YAML)
    first = coredns_editor.insert_hosts_into_corefile(corefile, "1.2.3.4", "node.local")
    second = coredns_editor.insert_hosts_into_corefile(first, "5.6.7.8", "node.local")
    assert second == first
    assert second.count("hosts {") == 1


def test_insert_new_hostname_when_different_host_exists():
    """Different hostname should get a new hosts block even if one already exists."""
    corefile = _extract_corefile(EXAMPLE_YAML)
    first = coredns_editor.insert_hosts_into_corefile(corefile, "1.2.3.4", "node.local")
    second = coredns_editor.insert_hosts_into_corefile(first, "5.6.7.8", "other.local")
    assert "1.2.3.4 node.local" in second
    assert "5.6.7.8 other.local" in second


def test_insert_hosts_before_kubernetes_when_no_ready():
    """Without a 'ready' plugin, hosts block goes before 'kubernetes'."""
    corefile = """\
.:53 {
    errors
    kubernetes cluster.local in-addr.arpa ip6.arpa {
       pods insecure
       fallthrough in-addr.arpa ip6.arpa
       ttl 30
    }
    forward . /etc/resolv.conf {
       max_concurrent 1000
    }
}
"""
    updated = coredns_editor.insert_hosts_into_corefile(corefile, "1.2.3.4", "node.local")
    lines = updated.splitlines()
    hosts_idx = lines.index("    hosts {")
    kube_idx = next(i for i, ln in enumerate(lines) if ln.strip().startswith("kubernetes "))
    assert hosts_idx < kube_idx


def test_insert_hosts_unclosed_server_block():
    """Unclosed '.:53 {' should raise ValueError."""
    corefile = ".:53 {\n    errors\n"
    with pytest.raises(ValueError, match="closing '}'"):
        coredns_editor.insert_hosts_into_corefile(corefile, "1.2.3.4", "node.local")


def test_multiple_hosts_insertions():
    corefile = _extract_corefile(EXAMPLE_YAML)
    updated = coredns_editor.insert_hosts_into_corefile(corefile, "1.1.1.1", "a.local")
    updated = coredns_editor.insert_hosts_into_corefile(updated, "2.2.2.2", "b.local")
    updated = coredns_editor.insert_hosts_into_corefile(updated, "3.3.3.3", "c.local")
    assert "1.1.1.1 a.local" in updated
    assert "2.2.2.2 b.local" in updated
    assert "3.3.3.3 c.local" in updated
    assert updated.count("hosts {") == 3


def test_same_hostname_different_ips_only_once():
    corefile = _extract_corefile(EXAMPLE_YAML)
    first = coredns_editor.insert_hosts_into_corefile(corefile, "1.1.1.1", "same.local")
    second = coredns_editor.insert_hosts_into_corefile(first, "2.2.2.2", "same.local")
    assert second == first
    assert second.count("same.local") == 1


def test_empty_corefile():
    with pytest.raises(ValueError):
        coredns_editor.insert_hosts_into_corefile("", "1.2.3.4", "node.local")


def test_fallback_indent_logic():
    corefile = """.:53 {
}
"""
    updated = coredns_editor.insert_hosts_into_corefile(corefile, "1.2.3.4", "node.local")
    assert "hosts {" in updated
    assert "1.2.3.4 node.local" in updated


def test_corefile_without_trailing_newline():
    corefile = """.:53 {
    ready
}"""

    updated = coredns_editor.insert_hosts_into_corefile(corefile, "1.2.3.4", "node.local")
    assert updated.endswith("}") or updated.endswith("\n")


def test_existing_hosts_block_with_other_entries():
    corefile = """.:53 {
    ready
    hosts {
        9.9.9.9 existing.local
        fallthrough
    }
}
"""
    updated = coredns_editor.insert_hosts_into_corefile(corefile, "1.2.3.4", "new.local")
    assert "new.local" in updated
    assert "existing.local" in updated



def test_corefile_block_indent_drop_early():
    yaml_text = """apiVersion: v1
data:
  Corefile: |
    .:53 {
        errors
    }
  something_else: value
"""

    start, end, indent = coredns_editor.find_corefile_block(yaml_text)

    assert start < end



def test_plugin_indent_empty_block():
    corefile = """.:53 {
# only comment
}
"""

    updated = coredns_editor.insert_hosts_into_corefile(corefile, "1.2.3.4", "node.local")

    assert "hosts {" in updated


def test_main_output_file_branch(tmp_path, monkeypatch):
    input_path = tmp_path / "coredns.yaml"
    output_path = tmp_path / "out.yaml"

    input_path.write_text(EXAMPLE_YAML, encoding="utf-8")

    argv = [
        "coredns_editor.py",
        str(input_path),
        "--ip", "1.2.3.4",
        "--hostname", "node.local",
        "-o", str(output_path),
    ]

    monkeypatch.setattr(sys, "argv", argv)

    result = coredns_editor.main()

    assert result == 0
    assert output_path.exists()



def test_main_print_branch(tmp_path, monkeypatch, capsys):
    input_path = tmp_path / "coredns.yaml"
    input_path.write_text(EXAMPLE_YAML, encoding="utf-8")

    argv = [
        "coredns_editor.py",
        str(input_path),
        "--ip", "1.2.3.4",
        "--hostname", "node.local",
    ]

    monkeypatch.setattr(sys, "argv", argv)

    coredns_editor.main()

    captured = capsys.readouterr()

    assert "hosts {" in captured.out



def test_corefile_not_found_exact_branch():
    yaml = """apiVersion: v1
kind: ConfigMap
metadata:
  name: test
"""
    with pytest.raises(ValueError, match="Could not find 'Corefile: |'"):
        coredns_editor.find_corefile_block(yaml)

def test_corefile_indent_not_found_only_blank_lines():
    yaml = """apiVersion: v1
data:
  Corefile: |
    
    
"""
    with pytest.raises(ValueError, match="Could not determine Corefile block indentation"):
        coredns_editor.find_corefile_block(yaml)



def test_main_no_change_branch(tmp_path, monkeypatch):
    input_path = tmp_path / "coredns.yaml"
    input_path.write_text(EXAMPLE_YAML, encoding="utf-8")

    # First insert
    argv1 = [
        "coredns_editor.py",
        str(input_path),
        "--ip", "1.2.3.4",
        "--hostname", "node.local",
        "-i",
    ]
    monkeypatch.setattr(sys, "argv", argv1)
    coredns_editor.main()

    # Second run → should NOT modify
    argv2 = [
        "coredns_editor.py",
        str(input_path),
        "--ip", "1.2.3.4",
        "--hostname", "node.local",
    ]
    monkeypatch.setattr(sys, "argv", argv2)
    coredns_editor.main()

    content = input_path.read_text()
    assert content.count("hosts {") == 1



def test_main_output_file_overwrite(tmp_path, monkeypatch):
    input_path = tmp_path / "coredns.yaml"
    output_path = tmp_path / "out.yaml"

    input_path.write_text(EXAMPLE_YAML, encoding="utf-8")
    output_path.write_text("OLD DATA", encoding="utf-8")

    argv = [
        "coredns_editor.py",
        str(input_path),
        "--ip", "1.2.3.4",
        "--hostname", "node.local",
        "-o", str(output_path),
    ]
    monkeypatch.setattr(sys, "argv", argv)

    coredns_editor.main()

    content = output_path.read_text()
    assert "OLD DATA" not in content
    assert "1.2.3.4 node.local" in content



def test_main_print_stdout_branch(tmp_path, monkeypatch, capsys):
    input_path = tmp_path / "coredns.yaml"
    input_path.write_text(EXAMPLE_YAML, encoding="utf-8")

    argv = [
        "coredns_editor.py",
        str(input_path),
        "--ip", "8.8.8.8",
        "--hostname", "dummy.local",
    ]
    monkeypatch.setattr(sys, "argv", argv)

    coredns_editor.main()

    out = capsys.readouterr().out
    assert "8.8.8.8 dummy.local" in out


def test_main_no_change_prints_original_yaml(tmp_path, monkeypatch, capsys):
    """Covers:
    - new_corefile == corefile
    - print(out_contents)
    """

    # YAML that already has the hostname
    yaml_with_host = """apiVersion: v1
data:
  Corefile: |
    .:53 {
        ready
        hosts {
            1.2.3.4 node.local
            fallthrough
        }
    }
"""

    input_path = tmp_path / "coredns.yaml"
    input_path.write_text(yaml_with_host, encoding="utf-8")

    argv = [
        "coredns_editor.py",
        str(input_path),
        "--ip", "1.2.3.4",
        "--hostname", "node.local",
    ]

    monkeypatch.setattr(sys, "argv", argv)
    coredns_editor.main()
    out = capsys.readouterr().out
    assert yaml_with_host in out
    assert out.count("hosts {") == 1