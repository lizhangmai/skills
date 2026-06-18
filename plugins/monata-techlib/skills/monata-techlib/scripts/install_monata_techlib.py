#!/usr/bin/env python
"""Bootstrap or install Monata techlib resources under MONATA_HOME."""

import argparse
from html.parser import HTMLParser
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple, Union


DEFAULT_MONATA_HOME = "~/.monata"
PTM_PAGE_URL = "https://mec.umn.edu/ptm"
GOOGLE_DRIVE_DOWNLOAD_URL = "https://drive.usercontent.google.com/download?id={}&export=download&authuser=0"
VA_MODELS_RAW_BASE = "https://raw.githubusercontent.com/dwarning/VA-Models/main"
NOTICE_FILES = ("LICENSE", "NOTICE", "TECHLIBS.toml", "SHA256SUMS")
FORBIDDEN_SUFFIXES = {".so", ".dll", ".dylib", ".exe", ".osdi"}
FORBIDDEN_NAMES = {"ngspice", "openvaf", "openvaf-r", "xyce"}
NAME_RE = re.compile(r'^\s*name\s*=\s*["\']([^"\']+)["\']\s*$')

PTM_MG_DOWNLOADS = [
    ("1Z7AOFzYk7Lz7-4xwU1pEnt09R_4Kn8Cz", "PTM-MG models", "models/itrs_rev2/models"),
    ("1j_X26O6fvAXM7jWWjoCN-ubHcm3tktq4", "PTM-MG param.inc", "models/param.inc"),
    ("18zBMwfkGBTiJiKmXCjocXyvBP6iVFbbp", "7nm HP NMOS", "models/modelfiles/hp/7nfet.pm"),
    ("1qFpVJBwrXq7XFlqNwBCivHQHK3V3FLLq", "7nm HP PMOS", "models/modelfiles/hp/7pfet.pm"),
    ("159jQFzZfhxTbUEP0peD2PNpU2QYSIl5-", "7nm LSTP NMOS", "models/modelfiles/lstp/7nfet.pm"),
    ("1cK5xBvOqeGh3yVQ2uREqxQisjjKwpD-N", "7nm LSTP PMOS", "models/modelfiles/lstp/7pfet.pm"),
    ("19ClJ0zNhfATVRIm5qEnAUDmIbkfOTLTk", "10nm HP NMOS", "models/modelfiles/hp/10nfet.pm"),
    ("1-77DoF7lzoX4Bq63J3TJORcvBCAz1z3t", "10nm HP PMOS", "models/modelfiles/hp/10pfet.pm"),
    ("19enS4GZSztSSOQuIFh4ewouOvKmH8v6d", "10nm LSTP NMOS", "models/modelfiles/lstp/10nfet.pm"),
    ("1PpqYLREG7H2bclxdeqJ0txY-tET2-2bn", "10nm LSTP PMOS", "models/modelfiles/lstp/10pfet.pm"),
    ("11eqHb2Q0pC7CKJpQ99h9GLuxBdYftqWJ", "14nm HP NMOS", "models/modelfiles/hp/14nfet.pm"),
    ("1O67Lr8fQvUe5TQD4BJw6LFWNvceV_QVi", "14nm HP PMOS", "models/modelfiles/hp/14pfet.pm"),
    ("1JPXVD4Ba27wGNw3dvxDllC1cnMZzUlwh", "14nm LSTP NMOS", "models/modelfiles/lstp/14nfet.pm"),
    ("1I6DaKArZjgzRTtqtH80hjjhfkYoA4Rk2", "14nm LSTP PMOS", "models/modelfiles/lstp/14pfet.pm"),
    ("1QemgwMnBQlga7g7Uag0Llbpd9b0WG1Wt", "16nm HP NMOS", "models/modelfiles/hp/16nfet.pm"),
    ("10e_DTph6LXknF56CMMTK2HjK8X6mwM5N", "16nm HP PMOS", "models/modelfiles/hp/16pfet.pm"),
    ("1nUhvrYTJqhoElWZWmG_eM2pPpr4qDIIz", "16nm LSTP NMOS", "models/modelfiles/lstp/16nfet.pm"),
    ("1zU0hmxNjm7Z2Q5qZtXpJQ0bmemLxAGg8", "16nm LSTP PMOS", "models/modelfiles/lstp/16pfet.pm"),
    ("1pGiSEpGK8INnilqWzHEswjRIQdwJjN4U", "20nm HP NMOS", "models/modelfiles/hp/20nfet.pm"),
    ("19nw5LCw-DskGEwHHf97MPo9Qf44lsrR5", "20nm HP PMOS", "models/modelfiles/hp/20pfet.pm"),
    ("1abHNFeXzJJgNBjNtgcUxH7yIyBFXtlls", "20nm LSTP NMOS", "models/modelfiles/lstp/20nfet.pm"),
    ("1vznPsqB-uUnuQjAwf7iaGOPEx9Vwq6QM", "20nm LSTP PMOS", "models/modelfiles/lstp/20pfet.pm"),
]

PTM_BULK_DOWNLOADS = [
    ("1fHtIzXt-mvF2tFyzqpgKUjIqm_YS-yxa", "180nm bulk model", "raw/180nm_bulk.pm", "ptm180", "ptm_bulk_180nm", "180nm", "bulk", 1.8, "180n", "1.2u", "2.4u"),
    ("1y3P3xDfxtQktcMQUb23-zrh7RVxu3MAE", "130nm bulk model", "raw/130nm_bulk.pm", "ptm130", "ptm_bulk_130nm", "130nm", "bulk", 1.5, "130n", "1.2u", "2.4u"),
    ("1qkWkbQVJEHE7Pppm9Mm7QXBS85SYC8Mh", "90nm bulk model", "raw/90nm_bulk.pm", "ptm90", "ptm_bulk_90nm", "90nm", "bulk", 1.2, "90n", "1.2u", "2.4u"),
    ("1S7-gVqEXho0P1nFpuDIlt_7ute53ijOF", "65nm bulk model", "raw/65nm_bulk.pm", "ptm65", "ptm_bulk_65nm", "65nm", "bulk", 1.1, "65n", "1.2u", "2.4u"),
    ("1H5eUrlxDpi2Sdmf5W9rCsjBRjttYPFZs", "45nm HP bulk model", "raw/45nm_hp.pm", "ptm45hp", "ptm_bulk_45nm_hp", "45nm", "hp", 1.0, "45n", "1.2u", "2.4u"),
    ("1l_4DKHzqwFFLugqTWzVWdWruB7eJL4mK", "45nm LP bulk model", "raw/45nm_lp.pm", "ptm45lp", "ptm_bulk_45nm_lp", "45nm", "lp", 1.1, "45n", "1.2u", "2.4u"),
    ("1Wr835xhQDQwXfHIA1k1_fPD1z3af1iAr", "32nm HP bulk model", "raw/32nm_hp.pm", "ptm32hp", "ptm_bulk_32nm_hp", "32nm", "hp", 0.9, "32n", "1.2u", "2.4u"),
    ("1irl52pj95lruVrSEXkKPgQxvjTDH9uJQ", "32nm LP bulk model", "raw/32nm_lp.pm", "ptm32lp", "ptm_bulk_32nm_lp", "32nm", "lp", 1.0, "32n", "1.2u", "2.4u"),
    ("1rXi_b-YINlmufzJa-VWFiyihG41ANKYy", "22nm HP bulk model", "raw/22nm_hp.pm", "ptm22hp", "ptm_bulk_22nm_hp", "22nm", "hp", 0.8, "22n", "1.0u", "2.0u"),
    ("1YH7vUTEpGnez_R603BfGvVXIxSXaaHoI", "22nm LP bulk model", "raw/22nm_lp.pm", "ptm22lp", "ptm_bulk_22nm_lp", "22nm", "lp", 0.95, "22n", "1.0u", "2.0u"),
]

VA_MODEL_FILES = [
    "README.md",
    "code/bsimcmg/vacode/Changelog",
    "code/bsimcmg/vacode/LICENSE.txt",
    "code/bsimcmg/vacode/bsimcmg.va",
    "code/bsimcmg/vacode/constants.vams",
    "code/bsimcmg/vacode/disciplines.vams",
    "code/bsimcmg/vacode/bsimcmg_macros.include",
    "code/bsimcmg/vacode/bsimcmg_parameters.include",
    "code/bsimcmg/vacode/bsimcmg_variables.include",
    "code/bsimcmg/vacode/bsimcmg_body.include",
    "code/bsimcmg/vacode/bsimcmg_checking.include",
    "code/bsimcmg/vacode/bsimcmg_initialization.include",
    "code/bsimcmg/vacode/bsimcmg_noise.include",
]


class TechlibError(RuntimeError):
    """Raised for user-correctable techlib install errors."""


class DriveLinkParser(HTMLParser):
    """Extract Google Drive file links from the PTM page."""

    def __init__(self) -> None:
        HTMLParser.__init__(self)
        self.links = []  # type: List[str]

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href")
        if href and "drive.google.com/file/d/" in href and href not in self.links:
            self.links.append(href)


def expand_path(value: Union[str, Path]) -> Path:
    return Path(value).expanduser().resolve()


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_url(url: str, target: Path, label: str, retries: int = 4, allow_html: bool = False) -> None:
    if target.exists() and target.stat().st_size > 0:
        print(f"Reusing cached {label}: {target}")
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=90) as response:
                data = response.read()
            if not data:
                raise TechlibError(f"downloaded empty response for {label}")
            if not allow_html and (
                data.lstrip().startswith(b"<!DOCTYPE html") or data.lstrip().startswith(b"<html")
            ):
                raise TechlibError(f"download for {label} returned an HTML page instead of model data")
            target.write_bytes(data)
            print(f"Downloaded {label}: {target}")
            return
        except Exception as exc:  # pragma: no cover - network dependent
            last_error = exc
            if attempt < retries:
                time.sleep(1.5 * attempt)
    if download_with_curl(url, target, label, allow_html):
        return
    raise TechlibError(f"failed to download {label} from {url}: {last_error}")


def download_with_curl(url: str, target: Path, label: str, allow_html: bool) -> bool:
    curl = shutil.which("curl")
    if not curl:
        return False
    tmp = target.with_suffix(target.suffix + ".tmp")
    cmd = [
        curl,
        "-L",
        "--http1.1",
        "-A",
        "Mozilla/5.0",
        "-sS",
        "--retry",
        "5",
        "--retry-delay",
        "2",
        "--max-time",
        "180",
        "-o",
        str(tmp),
        url,
    ]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError:
        return False
    if result.returncode != 0 or not tmp.exists() or tmp.stat().st_size == 0:
        if tmp.exists():
            tmp.unlink()
        return False
    data = tmp.read_bytes()
    if not allow_html and (data.lstrip().startswith(b"<!DOCTYPE html") or data.lstrip().startswith(b"<html")):
        tmp.unlink()
        return False
    tmp.replace(target)
    print(f"Downloaded {label}: {target}")
    return True


def download_drive_file(file_id: str, target: Path, label: str) -> None:
    download_url(GOOGLE_DRIVE_DOWNLOAD_URL.format(file_id), target, label)


def download_ptm_page(cache_dir: Path) -> List[str]:
    page = cache_dir / "ptm-page.html"
    download_url(PTM_PAGE_URL, page, "PTM source page", allow_html=True)
    parser = DriveLinkParser()
    parser.feed(page.read_text(encoding="utf-8", errors="replace"))
    return parser.links


def verify_official_ptm_links(cache_dir: Path) -> None:
    links = download_ptm_page(cache_dir)
    ids = set()
    for link in links:
        match = re.search(r"drive\.google\.com/file/d/([^/]+)/view", link)
        if match:
            ids.add(match.group(1))
    expected = {item[0] for item in PTM_MG_DOWNLOADS} | {item[0] for item in PTM_BULK_DOWNLOADS}
    missing = sorted(expected - ids)
    if missing:
        raise TechlibError(
            "official PTM page did not contain expected Google Drive file ids: "
            + ", ".join(missing[:6])
        )


def parse_name(path: Path) -> str:
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            match = NAME_RE.match(line)
            if match:
                return match.group(1)
    except OSError:
        pass
    return path.parent.name


def collection_name(root: Path) -> str:
    manifest = root / "TECHLIBS.toml"
    if manifest.exists():
        return parse_name(manifest)
    return root.name


def source_layout(source: Path) -> Tuple[Path, Path, List[Path]]:
    """Return metadata root, techlibs root, and techlib directories."""

    if not source.exists():
        raise TechlibError(f"source does not exist: {source}")
    if not source.is_dir():
        raise TechlibError(f"source must be a directory or extracted archive directory: {source}")

    if (source / "TECHLIBS.toml").exists() and (source / "techlibs").is_dir():
        root = source
        techlibs_root = source / "techlibs"
        techlibs = sorted(path for path in techlibs_root.iterdir() if (path / "techlib.toml").exists())
        return root, techlibs_root, techlibs

    if source.name == "techlibs" or any((path / "techlib.toml").exists() for path in source.iterdir() if path.is_dir()):
        techlibs_root = source
        root = source.parent if (source.parent / "TECHLIBS.toml").exists() else source
        techlibs = sorted(path for path in techlibs_root.iterdir() if (path / "techlib.toml").exists())
        return root, techlibs_root, techlibs

    if (source / "techlib.toml").exists():
        return source.parent, source.parent, [source]

    raise TechlibError(
        "source must be a collection with TECHLIBS.toml and techlibs/, "
        "a techlibs/ directory, or a single directory containing techlib.toml"
    )


def check_forbidden_artifacts(paths: List[Path]) -> List[Path]:
    forbidden = []  # type: List[Path]
    for root in paths:
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            lowered = path.name.lower()
            if path.suffix.lower() in FORBIDDEN_SUFFIXES or lowered in FORBIDDEN_NAMES:
                forbidden.append(path)
    return forbidden


def selected_techlibs(techlibs: List[Path], selected: Optional[List[str]]) -> List[Path]:
    if not selected:
        return techlibs

    by_name = {parse_name(path / "techlib.toml"): path for path in techlibs}
    by_dir = {path.name: path for path in techlibs}
    result = []  # type: List[Path]
    missing = []  # type: List[str]

    for name in selected:
        path = by_name.get(name) or by_dir.get(name)
        if path is None:
            missing.append(name)
        else:
            result.append(path)

    if missing:
        available = sorted(set(by_name) | set(by_dir))
        raise TechlibError(f"unknown techlib(s): {', '.join(missing)}; available: {', '.join(available)}")
    return result


def copy_or_link(source: Path, target: Path, mode: str, force: bool) -> None:
    if target.exists() or target.is_symlink():
        if not force:
            raise TechlibError(f"target already exists: {target}; rerun with --force to replace")
        if target.is_symlink() or target.is_file():
            target.unlink()
        else:
            shutil.rmtree(target)

    if mode == "symlink":
        target.symlink_to(source, target_is_directory=True)
    else:
        shutil.copytree(source, target)


def copy_notices(root: Path, target_root: Path, installed: List[str], mode: str, source: Path) -> Optional[Path]:
    files = [root / name for name in NOTICE_FILES if (root / name).exists()]
    if not files:
        return None

    notices_root = target_root / ".notices" / collection_name(root)
    notices_root.mkdir(parents=True, exist_ok=True)
    for file_path in files:
        shutil.copy2(file_path, notices_root / file_path.name)

    manifest = {
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "source": str(source),
        "mode": mode,
        "installed_techlibs": installed,
        "target_root": str(target_root),
        "license_boundary": "Third-party model data is not relicensed by this installer.",
    }
    (notices_root / "install-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return notices_root


def copy_notices_for_bootstrap(root: Path, target_root: Path, selected: List[str], source: Path) -> None:
    notices = copy_notices(root, target_root, selected, "download", source)
    if notices:
        print(f"Preserved notices: {notices}")


def write_collection_metadata(root: Path, selected: List[str]) -> None:
    lines = [
        "[collection]",
        'name = "monata-techlib"',
        'version = "0.1.0"',
        'schema = "monata.techlib.collection.v1"',
        'description = "Installer-generated Monata-compatible PTM technology-library resource collection"',
        'license = "ECL-2.0 AND LicenseRef-PTM-Model-Terms"',
        'default_monata_home = "~/.monata"',
        'default_user_dir = "$MONATA_HOME/techlibs"',
        'env_var = "MONATA_TECHLIB_PATH"',
        "",
    ]
    if "PTM_MG" in selected:
        lines.extend([
            "[[techlibs]]",
            'name = "PTM_MG"',
            'path = "techlibs/PTM_MG"',
            'description = "Official PTM multi-gate FinFET model-card and BSIM-CMG source techlib"',
            'source = "Predictive Technology Model (PTM), University of Minnesota / ASU"',
            'license = "LicenseRef-PTM-Model-Terms AND ECL-2.0"',
            "contains_third_party_model_data = true",
            "contains_verilog_a_source = true",
            "ships_compiled_artifacts = false",
            "",
        ])
    if "PTM_BULK" in selected:
        lines.extend([
            "[[techlibs]]",
            'name = "PTM_BULK"',
            'path = "techlibs/PTM_BULK"',
            'description = "Official PTM bulk CMOS model-card techlib"',
            'source = "Predictive Technology Model (PTM), University of Minnesota / ASU"',
            'license = "LicenseRef-PTM-Model-Terms"',
            "contains_third_party_model_data = true",
            "contains_verilog_a_source = false",
            "ships_compiled_artifacts = false",
            "",
        ])
    write_text(root / "TECHLIBS.toml", "\n".join(lines))
    write_text(
        root / "NOTICE",
        "\n".join([
            "Monata Techlib installer-generated collection.",
            "",
            "This collection contains model-card resources downloaded at user request",
            "from the official Predictive Technology Model (PTM) public page:",
            PTM_PAGE_URL,
            "",
            "PTM model cards are third-party model data and are not relicensed by",
            "Monata or this installer. Preserve upstream attribution and cite the",
            "PTM website and related publications when using the models.",
            "",
            "The BSIM-CMG Verilog-A source subset, when present, is downloaded from",
            "https://github.com/dwarning/VA-Models and is under ECL-2.0.",
            "",
            "This collection does not ship ngspice, libngspice, XSPICE code models,",
            "OpenVAF, Xyce, or precompiled .osdi binaries.",
            "",
        ]),
    )


def write_sha256sums(root: Path) -> None:
    entries = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS":
            entries.append("{}  {}".format(sha256_file(path), path.relative_to(root).as_posix()))
    write_text(root / "SHA256SUMS", "\n".join(entries) + "\n")


def download_va_models(target_root: Path, cache_root: Path) -> List[str]:
    source_files = []  # type: List[str]
    for relative in VA_MODEL_FILES:
        url = "{}/{}".format(VA_MODELS_RAW_BASE, relative)
        cache_file = cache_root / "va-models" / relative
        download_url(url, cache_file, "VA-Models {}".format(relative))
        target = target_root / "model_sources" / "VA-Models" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cache_file, target)
        source_files.append(("model_sources/VA-Models/" + relative).replace("\\", "/"))
    return source_files


def build_ptm_mg(target_root: Path, cache_root: Path) -> None:
    for file_id, label, relative in PTM_MG_DOWNLOADS:
        cache_file = cache_root / "ptm-mg" / relative
        download_drive_file(file_id, cache_file, label)
        target = target_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cache_file, target)

    source_files = download_va_models(target_root, cache_root)
    write_ptm_mg_techlib(target_root)
    write_source_metadata(target_root, source_files)


def build_ptm_bulk(target_root: Path, cache_root: Path) -> None:
    models_root = target_root / "models"
    for file_id, label, relative, section, _deck, _node, _flavor, _vdd, _l, _nw, _pw in PTM_BULK_DOWNLOADS:
        cache_file = cache_root / "ptm-bulk" / relative
        download_drive_file(file_id, cache_file, label)
        target = models_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cache_file, target)
        wrapper = models_root / "{}.mod".format(section)
        write_text(
            wrapper,
            ".LIB {0}\n.include '{1}'\n.ENDL {0}\n".format(section, relative),
        )
    write_ptm_bulk_techlib(target_root)


def write_source_metadata(target_root: Path, source_files: List[str]) -> None:
    quoted = "\n".join('    "{}",'.format(path) for path in source_files)
    write_text(
        target_root / "source_metadata.toml",
        """[source]
name = "BSIM-CMG"
version = "111.2.1"
upstream_url = "https://github.com/dwarning/VA-Models/tree/main/code/bsimcmg/vacode"
license = "ECL-2.0"
redistribution = "downloaded_source_subset"
package_policy = "downloaded_source"
source_files = [
{source_files}
]

[provenance]
status = "downloaded source subset"
reason = "PTM_MG downloads the minimal VA-Models BSIM-CMG Verilog-A source subset needed to compile bsimcmg_va with OpenVAF; no .osdi binaries are installed."

[syntax_gate]
openvaf_ngspice_model_card_syntax = "expected"
""".format(source_files=quoted),
    )


def write_ptm_mg_techlib(target_root: Path) -> None:
    corners = [
        ("ptm20hp", "20nm", "hp", 0.9, "20n", 15, 30),
        ("ptm20lstp", "20nm", "lstp", 0.9, "20n", 15, 30),
        ("ptm16hp", "16nm", "hp", 0.85, "16n", 12, 24),
        ("ptm16lstp", "16nm", "lstp", 0.85, "16n", 12, 24),
        ("ptm14hp", "14nm", "hp", 0.8, "14n", 10, 20),
        ("ptm14lstp", "14nm", "lstp", 0.8, "14n", 10, 20),
        ("ptm10hp", "10nm", "hp", 0.75, "10n", 7, 14),
        ("ptm10lstp", "10nm", "lstp", 0.75, "10n", 7, 14),
        ("ptm7hp", "7nm", "hp", 0.7, "7n", 5, 10),
        ("ptm7lstp", "7nm", "lstp", 0.7, "7n", 5, 10),
    ]
    corner_text = []
    for name, node, flavor, vdd, length, nfins, pfins in corners:
        corner_text.append(
            """
[[corners]]
name = "{name}"
model_deck = "ptm_mg"
section = "{name}"
nominal_vdd = {vdd}
process_node = "{node}"
flavor = "{flavor}"
device_defaults = {{ nfet = {{ l = "{length}", nfin = {nfins} }}, pfet = {{ l = "{length}", nfin = {pfins} }} }}
""".format(name=name, node=node, flavor=flavor, vdd=vdd, length=length, nfins=nfins, pfins=pfins)
        )
    write_text(
        target_root / "techlib.toml",
        """[techlib]
name = "PTM_MG"
description = "PTM multi-gate FinFET technology library downloaded from the official PTM page"
default_corner = "ptm20hp"

[provenance]
source = "Predictive Technology Model (PTM), University of Minnesota / Arizona State University"
url = "{ptm_url}"
citation_required = true
no_warranty = true
notice = "Downloaded at user request from the official PTM page; PTM model cards remain subject to upstream terms."

[[model_decks]]
name = "ptm_mg"
path = "models/itrs_rev2/models"
description = "ITRS 2011 aligned PTM-MG FinFET model deck"

[[model_flows]]
name = "ptm-mg-raw-level72"
model_deck = "ptm_mg"
output = "native_spice_lib"
requires = {{ native_spice_model_levels = [72], spice_lib = true }}
enabled = true
package_policy = "downloaded_source"

[[model_flows]]
name = "ptm-mg-ngspice-osdi"
model_deck = "ptm_mg"
output = "ngspice_osdi"
requires = {{ osdi = true, compiler = "openvaf", supports_subckt_wrappers = true }}
dialects = ["ngspice"]
enabled = true
source_va = "model_sources/VA-Models/code/bsimcmg/vacode/bsimcmg.va"
source_name = "bsimcmg"
source_includes = [
    "constants.vams",
    "disciplines.vams",
    "bsimcmg_macros.include",
    "bsimcmg_parameters.include",
    "bsimcmg_variables.include",
    "bsimcmg_body.include",
    "bsimcmg_checking.include",
    "bsimcmg_initialization.include",
    "bsimcmg_noise.include",
]
source_metadata = "source_metadata.toml"
module_name = "bsimcmg_va"
compiler_args = ["-D__NGSPICE__"]
converter = "ptm_mg_level72_to_bsimcmg"
package_policy = "downloaded_source"
validation = {{ smoke = "ngspice-bsimcmg-osdi-inverter", source_version = "BSIM-CMG 111.2.1" }}
{corners}
[[devices]]
name = "nfet"
kind = "mosfet"
pins = ["d", "g", "s", "b"]

[devices.params.l]
default = "lg"
unit = "m"
description = "Gate length"

[devices.params.nfin]
default = 1
type = "integer"
description = "Number of fins"

[[devices.views]]
name = "symbol"
primitive = "symbol"
pin_order = ["d", "g", "s", "b"]

[[devices.views]]
name = "ngspice"
primitive = "subckt"
subckt = "nfet"
pin_order = ["d", "g", "s", "b"]
params = ["l", "nfin"]
model_deck = "ptm_mg"

[[devices]]
name = "pfet"
kind = "mosfet"
pins = ["d", "g", "s", "b"]

[devices.params.l]
default = "lg"
unit = "m"
description = "Gate length"

[devices.params.nfin]
default = 1
type = "integer"
description = "Number of fins"

[[devices.views]]
name = "symbol"
primitive = "symbol"
pin_order = ["d", "g", "s", "b"]

[[devices.views]]
name = "ngspice"
primitive = "subckt"
subckt = "pfet"
pin_order = ["d", "g", "s", "b"]
params = ["l", "nfin"]
model_deck = "ptm_mg"
""".format(ptm_url=PTM_PAGE_URL, corners="".join(corner_text)),
    )


def write_ptm_bulk_techlib(target_root: Path) -> None:
    decks = []
    corners = []
    for _file_id, _label, _relative, section, deck, node, flavor, vdd, length, nwidth, pwidth in PTM_BULK_DOWNLOADS:
        flavor_label = "bulk" if flavor == "bulk" else "{} bulk".format(flavor.upper())
        decks.append(
            """
[[model_decks]]
name = "{deck}"
path = "models/{section}.mod"
description = "PTM {node} {flavor_label} model deck"
""".format(deck=deck, section=section, node=node, flavor_label=flavor_label)
        )
        corners.append(
            """
[[corners]]
name = "{section}"
model_deck = "{deck}"
section = "{section}"
nominal_vdd = {vdd}
process_node = "{node}"
flavor = "{flavor}"
device_defaults = {{ nmos = {{ w = "{nwidth}", l = "{length}" }}, pmos = {{ w = "{pwidth}", l = "{length}" }} }}
""".format(section=section, deck=deck, vdd=vdd, node=node, flavor=flavor, nwidth=nwidth, pwidth=pwidth, length=length)
        )
    corner_names = [item[3] for item in PTM_BULK_DOWNLOADS]
    nmos_models = "\n".join('{} = "nmos"'.format(name) for name in corner_names)
    pmos_models = "\n".join('{} = "pmos"'.format(name) for name in corner_names)
    write_text(
        target_root / "techlib.toml",
        """[techlib]
name = "PTM_BULK"
description = "PTM bulk CMOS technology library downloaded from the official PTM page"
default_corner = "ptm65"

[provenance]
source = "Predictive Technology Model (PTM), University of Minnesota / Arizona State University"
url = "{ptm_url}"
citation_required = true
no_warranty = true
notice = "Downloaded at user request from the official PTM page; PTM model cards remain subject to upstream terms."
{decks}
{corners}
[[devices]]
name = "nmos"
kind = "mosfet"
pins = ["d", "g", "s", "b"]

[devices.params.w]
default = "1.2u"
unit = "m"
description = "Transistor width"

[devices.params.l]
default = "65n"
unit = "m"
description = "Gate length"

[[devices.views]]
name = "symbol"
primitive = "symbol"
pin_order = ["d", "g", "s", "b"]

[[devices.views]]
name = "ngspice"
primitive = "mos"
pin_order = ["d", "g", "s", "b"]
params = ["w", "l"]

[devices.views.corner_models]
{nmos_models}

[[devices]]
name = "pmos"
kind = "mosfet"
pins = ["d", "g", "s", "b"]

[devices.params.w]
default = "2.4u"
unit = "m"
description = "Transistor width"

[devices.params.l]
default = "65n"
unit = "m"
description = "Gate length"

[[devices.views]]
name = "symbol"
primitive = "symbol"
pin_order = ["d", "g", "s", "b"]

[[devices.views]]
name = "ngspice"
primitive = "mos"
pin_order = ["d", "g", "s", "b"]
params = ["w", "l"]

[devices.views.corner_models]
{pmos_models}
""".format(
            ptm_url=PTM_PAGE_URL,
            decks="".join(decks),
            corners="".join(corners),
            nmos_models=nmos_models,
            pmos_models=pmos_models,
        ),
    )


def command_install(args: argparse.Namespace) -> int:
    source = expand_path(args.source)
    monata_home = expand_path(args.monata_home or os.environ.get("MONATA_HOME", DEFAULT_MONATA_HOME))
    target_root = monata_home / "techlibs"

    root, _techlibs_root, techlibs = source_layout(source)
    techlibs = selected_techlibs(techlibs, args.techlib)
    if not techlibs:
        raise TechlibError(f"no techlibs found under source: {source}")

    forbidden = check_forbidden_artifacts(techlibs)
    if forbidden:
        detail = "\n".join(f"  {path}" for path in forbidden[:20])
        extra = "" if len(forbidden) <= 20 else f"\n  ... and {len(forbidden) - 20} more"
        raise TechlibError(f"refusing to install compiled simulator/model artifacts:\n{detail}{extra}")

    target_root.mkdir(parents=True, exist_ok=True)
    installed = []  # type: List[str]

    for techlib in techlibs:
        name = parse_name(techlib / "techlib.toml")
        copy_or_link(techlib, target_root / name, args.mode, args.force)
        installed.append(name)

    notices = copy_notices(root, target_root, installed, args.mode, source)

    print(f"MONATA_HOME={monata_home}")
    print(f"Installed techlibs root: {target_root}")
    for name in installed:
        print(f"Installed: {name}")
    if notices:
        print(f"Preserved notices: {notices}")
    print("Next: export MONATA_HOME=\"{}\"".format(monata_home))
    return 0


def command_bootstrap_ptm(args: argparse.Namespace) -> int:
    selected = args.techlib or ["PTM_MG", "PTM_BULK"]
    invalid = sorted(set(selected) - {"PTM_MG", "PTM_BULK"})
    if invalid:
        raise TechlibError("bootstrap-ptm supports only PTM_MG and PTM_BULK; invalid: " + ", ".join(invalid))

    monata_home = expand_path(args.monata_home or os.environ.get("MONATA_HOME", DEFAULT_MONATA_HOME))
    cache_root = expand_path(args.cache_dir) if args.cache_dir else monata_home / "downloads" / "ptm-official"
    stage_root = cache_root / "stage" / "monata-techlib"
    target_root = monata_home / "techlibs"
    already_installed = []  # type: List[str]
    build_selected = []  # type: List[str]
    if args.force or args.stage_only:
        build_selected = list(selected)
    else:
        for name in selected:
            target = target_root / name
            if target.is_dir() and (target / "techlib.toml").exists():
                already_installed.append(name)
            else:
                build_selected.append(name)

    if already_installed and not build_selected:
        print("Using MONATA_HOME={}".format(monata_home))
        print("Already installed: {}".format(", ".join(already_installed)))
        print("No downloads needed. Rerun with --force to refresh installed techlibs.")
        return command_verify(argparse.Namespace(monata_home=str(monata_home)))

    if stage_root.exists():
        shutil.rmtree(stage_root)
    (stage_root / "techlibs").mkdir(parents=True, exist_ok=True)

    print("Using MONATA_HOME={}".format(monata_home))
    print("Using download cache={}".format(cache_root))
    print("Verifying official PTM source page: {}".format(PTM_PAGE_URL))
    verify_official_ptm_links(cache_root)

    if "PTM_MG" in build_selected:
        print("Bootstrapping PTM_MG from official PTM and VA-Models sources")
        build_ptm_mg(stage_root / "techlibs" / "PTM_MG", cache_root / "downloads")
    if "PTM_BULK" in build_selected:
        print("Bootstrapping PTM_BULK from official PTM sources")
        build_ptm_bulk(stage_root / "techlibs" / "PTM_BULK", cache_root / "downloads")

    write_collection_metadata(stage_root, build_selected)
    write_sha256sums(stage_root)

    if args.stage_only:
        print("Staged techlib collection: {}".format(stage_root))
        return 0

    target_root.mkdir(parents=True, exist_ok=True)
    installed = []  # type: List[str]
    skipped = []  # type: List[str]
    for name in build_selected:
        source = stage_root / "techlibs" / name
        target = target_root / name
        if target.exists() and not args.force:
            skipped.append(name)
            print("Already installed, skipping without --force: {}".format(target))
            continue
        copy_or_link(source, target, "copy", args.force)
        installed.append(name)
        print("Installed: {}".format(name))

    copy_notices_for_bootstrap(stage_root, target_root, build_selected, stage_root)
    print("Installed techlibs root: {}".format(target_root))
    if already_installed:
        print("Already installed before this run: {}".format(", ".join(already_installed)))
    if skipped:
        print("Skipped existing: {}".format(", ".join(skipped)))
    print("Next: export MONATA_HOME=\"{}\"".format(monata_home))
    return command_verify(argparse.Namespace(monata_home=str(monata_home)))


def command_verify(args: argparse.Namespace) -> int:
    monata_home = expand_path(args.monata_home or os.environ.get("MONATA_HOME", DEFAULT_MONATA_HOME))
    target_root = monata_home / "techlibs"

    if not target_root.is_dir():
        raise TechlibError(f"missing techlibs directory: {target_root}")

    techlibs = sorted(path for path in target_root.iterdir() if path.is_dir() and (path / "techlib.toml").exists())
    if not techlibs:
        raise TechlibError(f"no installed techlibs with techlib.toml found under: {target_root}")

    print(f"MONATA_HOME={monata_home}")
    print(f"Found techlibs root: {target_root}")
    for path in techlibs:
        print(f"Found: {parse_name(path / 'techlib.toml')} ({path})")

    try:
        from monata.techlib.registry import TechlibRegistry  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on user environment
        print(f"Monata import skipped: {exc}")
        return 0

    old_monata_home = os.environ.get("MONATA_HOME")
    os.environ["MONATA_HOME"] = str(monata_home)
    try:
        registry = TechlibRegistry()
        print("Monata TechlibRegistry:", ", ".join(registry.list_techlibs()))
    finally:
        if old_monata_home is None:
            os.environ.pop("MONATA_HOME", None)
        else:
            os.environ["MONATA_HOME"] = old_monata_home
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command")

    install = subparsers.add_parser("install", help="Install techlibs from a local source directory.")
    install.add_argument("--source", required=True, help="Collection, techlibs, or single-techlib source directory.")
    install.add_argument("--monata-home", help="Monata home directory. Defaults to MONATA_HOME or ~/.monata.")
    install.add_argument("--techlib", action="append", help="Techlib name to install. Repeat for multiple names.")
    install.add_argument("--mode", choices=["copy", "symlink"], default="copy", help="Install by copying or symlinking.")
    install.add_argument("--force", action="store_true", help="Replace existing installed techlib directories.")
    install.set_defaults(func=command_install)

    bootstrap = subparsers.add_parser(
        "bootstrap-ptm",
        help="Download official PTM resources, generate Monata techlibs, and install them.",
    )
    bootstrap.add_argument("--monata-home", help="Monata home directory. Defaults to MONATA_HOME or ~/.monata.")
    bootstrap.add_argument(
        "--cache-dir",
        help="Download/staging cache directory. Defaults to $MONATA_HOME/downloads/ptm-official.",
    )
    bootstrap.add_argument(
        "--techlib",
        action="append",
        choices=["PTM_MG", "PTM_BULK"],
        help="Techlib to bootstrap. Repeat for multiple names. Defaults to both PTM_MG and PTM_BULK.",
    )
    bootstrap.add_argument("--force", action="store_true", help="Replace existing installed techlib directories.")
    bootstrap.add_argument("--stage-only", action="store_true", help="Download and generate the collection without installing.")
    bootstrap.set_defaults(func=command_bootstrap_ptm)

    verify = subparsers.add_parser("verify", help="Verify installed techlibs under MONATA_HOME.")
    verify.add_argument("--monata-home", help="Monata home directory. Defaults to MONATA_HOME or ~/.monata.")
    verify.set_defaults(func=command_verify)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help(sys.stderr)
        return 2
    try:
        return args.func(args)
    except TechlibError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
