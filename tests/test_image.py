import io
from pathlib import Path
import struct
import sys
import tarfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from publish_image import tags_for, validate_index, validate_attestation
from verify_image import verify_elf, verify_rootfs, verify_build_info


def elf(architecture="amd64", dynamic=False, symbols=False):
    value = bytearray(184)
    value[:6] = b"\x7fELF\x02\x01"
    struct.pack_into("<H", value, 18, {"amd64": 62, "arm64": 183}[architecture])
    struct.pack_into("<QQ", value, 32, 64, 120)
    struct.pack_into("<HHHH", value, 54, 56, 1, 64, 1)
    struct.pack_into("<I", value, 64, 3 if dynamic else 1)
    struct.pack_into("<I", value, 124, 2 if symbols else 1)
    return bytes(value)


class ImageTests(unittest.TestCase):
    def test_size_reduction_tags_in_compiled_binary(self):
        verify_build_info("go\tgo1.27.3\nbuild\t-tags=nopgx,nobadger,nomysql\nbuild\tCGO_ENABLED=0\n")

    def test_missing_size_reduction_tags_are_rejected(self):
        for output in ("", "build\t-trimpath=true\n", "build\t-tags=nobadger,nomysql\n"):
            with self.subTest(output=output), self.assertRaisesRegex(ValueError, "size-reduction build tags"):
                verify_build_info(output)

    def test_both_architectures_static_and_stripped(self):
        for architecture in ("amd64", "arm64"):
            verify_elf(elf(architecture), architecture)

    def test_wrong_architecture_dynamic_and_unstripped_are_rejected(self):
        for binary in (elf("arm64"), elf(dynamic=True), elf(symbols=True), b"shell script"):
            with self.subTest(binary=binary), self.assertRaises(ValueError):
                verify_elf(binary, "amd64")

    def test_extra_runtime_tools_are_rejected(self):
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode="w") as archive:
            entry = tarfile.TarInfo("bin/sh")
            entry.size = 1
            archive.addfile(entry, io.BytesIO(b"x"))
        with self.assertRaisesRegex(ValueError, "Unexpected runtime file"):
            verify_rootfs(output.getvalue(), "amd64")

    def test_release_tags(self):
        self.assertEqual(tags_for("2.11.7"), ["2.11.7", "2.11", "2", "stable"])
        with self.assertRaises(ValueError):
            tags_for("2.12.0-rc.1")

    def test_index_requires_both_platforms_and_attestations(self):
        entries = []
        for architecture in ("amd64", "arm64"):
            entries.append({"digest": architecture, "platform": {"os": "linux", "architecture": architecture}})
            entries.append({"digest": architecture + "-attestation", "platform": {"os": "unknown", "architecture": "unknown"},
                            "annotations": {"vnd.docker.reference.type": "attestation-manifest",
                                            "vnd.docker.reference.digest": architecture}})
        validate_index({"manifests": entries})
        with self.assertRaises(ValueError):
            validate_index({"manifests": entries[:-1]})
        with self.assertRaises(ValueError):
            validate_index({"manifests": entries[:2]})

    def test_attestation_requires_sbom_and_provenance(self):
        layers = [{"annotations": {"in-toto.io/predicate-type": predicate}} for predicate in (
            "https://spdx.dev/Document", "https://slsa.dev/provenance/v0.2")]
        validate_attestation({"layers": layers})
        for invalid in ({}, {"layers": layers[:1]}, {"layers": layers[1:]}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_attestation(invalid)


if __name__ == "__main__":
    unittest.main()
