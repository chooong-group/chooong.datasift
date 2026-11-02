"""Published metadata and downloaded bytes must match the authenticated bundle."""

import hashlib
import io
import json
from pathlib import Path

import pytest

from scripts import verify_publish


@pytest.mark.parametrize("failure", [None, "bytes", "metadata", "missing", "yanked", "origin"])
def test_pypi_verification_checks_the_exact_published_file_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str | None,
) -> None:
    data = b"synthetic distribution"
    digest = hashlib.sha256(data).hexdigest()
    distribution = tmp_path / "dist"
    distribution.mkdir()
    (distribution / "sample.whl").write_bytes(data)
    checksums = tmp_path / "SHA256SUMS"
    checksums.write_text(f"{digest}  sample.whl\n")
    expected = hashlib.sha256(checksums.read_bytes()).hexdigest()
    payload = {
        "urls": [
            {
                "filename": "sample.whl",
                "digests": {"sha256": digest},
                "url": "https://files.pythonhosted.org/sample.whl",
                "yanked": False,
            }
        ]
    }
    if failure == "missing":
        payload["urls"] = []
    elif failure == "metadata":
        payload["urls"][0]["digests"] = {"sha256": "0" * 64}
    elif failure == "yanked":
        payload["urls"][0]["yanked"] = True
    elif failure == "origin":
        payload["urls"][0]["url"] = "https://untrusted.example/sample.whl"

    def download(url: str, timeout: int) -> io.BytesIO:
        assert timeout > 0
        if url == "https://pypi.org/pypi/chooong.datasift/0.1.0/json":
            return io.BytesIO(json.dumps(payload).encode())
        assert url == "https://files.pythonhosted.org/sample.whl"
        return io.BytesIO(b"tampered" if failure == "bytes" else data)

    monkeypatch.setattr(verify_publish, "urlopen", download)
    if failure is None:
        verify_publish.verify_pypi(tmp_path, expected, "0.1.0")
    else:
        with pytest.raises(ValueError, match="Published|publication|origin|validated artifact"):
            verify_publish.verify_pypi(tmp_path, expected, "0.1.0")
    assert (distribution / "sample.whl").read_bytes() == data
