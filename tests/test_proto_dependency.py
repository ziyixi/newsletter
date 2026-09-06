"""Consumer checks use only the installed public wheel, never sibling source/protoc."""

import hashlib
import json
import pickle
import re
from importlib.metadata import distribution, version
from importlib.resources import files
from pathlib import Path

import pytest
from ziyixi_protos.newsletter import editorial_pb2 as pb

from newsletter import preflight as startup


def test_public_wheel_contains_generated_code_types_and_traceable_provenance():
    package = files("ziyixi_protos.newsletter")
    manifest = json.loads(package.joinpath("provenance.json").read_text())
    for key, content in (
        ("descriptor_sha256", pb.DESCRIPTOR.serialized_pb),
        ("generated_sha256", package.joinpath("editorial_pb2.py").read_bytes()),
        ("stubs_sha256", package.joinpath("editorial_pb2.pyi").read_bytes()),
    ):
        assert manifest[key] == hashlib.sha256(content).hexdigest()
    assert manifest["source_repository"] == "https://github.com/ziyixi/protos"
    assert manifest["source_path"] == "proto/newsletter/editorial.proto"
    assert re.fullmatch(r"[a-f0-9]{40}", manifest["source_commit"])
    assert re.fullmatch(r"[a-f0-9]{64}", manifest["source_sha256"])
    assert manifest["protoc_version"].startswith("libprotoc ")
    assert manifest["package_version"] == version("ziyixi-protos")
    installed = distribution("ziyixi-protos")
    member = "ziyixi_protos/newsletter/editorial_pb2.py"
    assert Path(pb.__file__).resolve() == Path(installed.locate_file(member)).resolve()
    startup.check_proto_dependency()


def test_generated_module_identity_supports_normal_python_serialization():
    assert pb.StartRunRequest.__module__ == "ziyixi_protos.newsletter.editorial_pb2"
    value = pb.StartRunRequest(request_key="synthetic-job", issue_date="2026-09-05")
    assert pickle.loads(pickle.dumps(value)) == value
    assert pb.DESCRIPTOR.name == "ziyixi_protos/newsletter/editorial.proto"
    assert pb.DESCRIPTOR.package == "newsletter.v1"


@pytest.fixture
def copied_package(tmp_path, monkeypatch):
    original = files("ziyixi_protos.newsletter")
    for name in ("editorial_pb2.py", "editorial_pb2.pyi", "provenance.json"):
        (tmp_path / name).write_bytes(original.joinpath(name).read_bytes())
    actual_files = startup.files
    monkeypatch.setattr(
        startup,
        "files",
        lambda package: (
            tmp_path if package == "ziyixi_protos.newsletter" else actual_files(package)
        ),
    )
    return tmp_path


@pytest.mark.parametrize("name", ["editorial_pb2.py", "editorial_pb2.pyi"])
def test_tampered_dependency_resources_are_rejected(copied_package, name):
    path = copied_package / name
    path.write_bytes(path.read_bytes() + b"\n# synthetic tampering\n")
    with pytest.raises(startup.PreflightError, match="^PROTO_INTEGRITY_FAILED$"):
        startup.check_proto_dependency()


@pytest.mark.parametrize(
    ("field", "bad", "code"),
    [
        ("descriptor_sha256", "0" * 64, "PROTO_INTEGRITY_FAILED"),
        ("source_repository", "https://example.org/not-the-source", "PROTO_SOURCE_INVALID"),
        ("source_path", "newsletter/editorial.proto", "PROTO_SOURCE_INVALID"),
        ("source_commit", "g" * 40, "PROTO_SOURCE_INVALID"),
        ("source_commit", "", "PROTO_SOURCE_INVALID"),
        ("source_commit", int("1" * 40), "PROTO_SOURCE_INVALID"),
        ("source_sha256", "", "PROTO_SOURCE_INVALID"),
        ("package_version", "0.0.0", "PROTO_VERSION_MISMATCH"),
    ],
)
def test_dependency_metadata_mismatch_fails_closed(copied_package, field, bad, code):
    path = copied_package / "provenance.json"
    manifest = json.loads(path.read_text())
    manifest[field] = bad
    path.write_text(json.dumps(manifest))
    with pytest.raises(startup.PreflightError) as error:
        startup.check_proto_dependency()
    assert error.value.code == code


def test_non_object_manifest_is_not_accepted(copied_package):
    (copied_package / "provenance.json").write_text("[]")
    with pytest.raises(startup.PreflightError, match="^PROTO_SOURCE_INVALID$"):
        startup.check_proto_dependency()


def test_shadow_module_is_not_mistaken_for_installed_distribution(tmp_path, monkeypatch):
    monkeypatch.setattr(pb, "__file__", str(tmp_path / "editorial_pb2.py"))
    with pytest.raises(startup.PreflightError, match="^PROTO_SOURCE_INVALID$"):
        startup.check_proto_dependency()
