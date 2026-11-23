#!/usr/bin/env python3
import argparse
import fcntl
import hashlib
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
REPOSITORY = re.compile(r"[a-zA-Z0-9-]+/[a-zA-Z0-9_.-]+")
REF = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_./-]*")
COMMIT = re.compile(r"[a-fA-F0-9]{40}")
VERSION = re.compile(r"[a-f0-9]{64}")


@dataclass(frozen=True)
class Skill:
    name: str
    repository: str
    directory: str
    ref: str

    def version_path(self, store, commit):
        identity = "\0".join((self.repository.lower(), self.directory, commit.lower()))
        return store / self.name / hashlib.sha256(identity.encode()).hexdigest()


def load_manifest(path):
    skills = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        try:
            fields = shlex.split(line, comments=True)
            if not fields:
                continue
            if len(fields) not in (3, 4):
                raise ValueError("expected NAME OWNER/REPO DIRECTORY [GIT_REF]")
            name, repository, directory = fields[:3]
            ref = fields[3] if len(fields) == 4 else "HEAD"
            if len(name) > 64 or not NAME.fullmatch(name):
                raise ValueError(f"invalid skill name {name!r}")
            if name in skills:
                raise ValueError(f"duplicate skill name {name!r}")
            if not REPOSITORY.fullmatch(repository) or repository.split("/")[1] in (".", ".."):
                raise ValueError(f"invalid GitHub repository {repository!r}")
            folder = PurePosixPath(directory)
            if not directory or folder.is_absolute() or ".." in folder.parts or ".git" in folder.parts:
                raise ValueError(f"invalid skill directory {directory!r}")
            if not REF.fullmatch(ref):
                raise ValueError(f"invalid Git ref {ref!r}")
            skills[name] = Skill(name, repository, folder.as_posix(), ref)
        except ValueError as error:
            raise ValueError(f"{path}:{line_number}: {error}") from error
    if not skills:
        raise ValueError(f"{path}: add at least one skill")
    return list(skills.values())


def xdg_directory(variable, fallback):
    value = Path(os.environ.get(variable) or fallback)
    return value if value.is_absolute() else fallback


def skill_locations(extra_targets):
    home = Path.home()
    config = xdg_directory("XDG_CONFIG_HOME", home / ".config")
    claude = Path(os.environ.get("CLAUDE_CONFIG_DIR") or home / ".claude").expanduser()
    roots = [
        home / ".agents/skills",
        config / "agents/skills",
        claude / "skills",
        home / ".cursor/skills",
        home / ".gemini/skills",
        home / ".copilot/skills",
        config / "opencode/skills",
        home / ".codeium/windsurf/skills",
        *extra_targets,
    ]
    return list(dict.fromkeys(root.expanduser().resolve() for root in roots))


def skill_name(directory):
    try:
        lines = (directory / "SKILL.md").read_text(encoding="utf-8-sig").splitlines()
    except (FileNotFoundError, NotADirectoryError, UnicodeError):
        return None
    if not lines or lines[0].strip() != "---":
        return None
    frontmatter = []
    for line in lines[1:]:
        if line.strip() == "---" and not line[0].isspace():
            break
        frontmatter.append(line)
    else:
        return None
    for line in frontmatter:
        if line.startswith("name:"):
            match = re.fullmatch(
                r"\s*(['\"]?)([a-z0-9-]+)\1\s*(?:#.*)?", line.removeprefix("name:")
            )
            return match[2] if match else None
    return None


def git(directory, *args):
    return subprocess.check_output(
        ["git", "-C", str(directory), *args],
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        text=True,
    ).strip()


def archive_skill(repository, source, destination):
    # git archive reads tracked files without checking out the repo or running its hooks.
    command = ["git", "-C", str(repository), "archive", "--format=tar", source]
    with subprocess.Popen(command, stdout=subprocess.PIPE) as process:
        with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
            for member in archive:
                name = PurePosixPath(member.name)
                if name.is_absolute() or any(
                    part == ".." or part.lower() == ".git" for part in name.parts
                ):
                    raise ValueError(f"unsafe archive path {member.name!r}")
                path = destination.joinpath(*name.parts)
                if member.isdir():
                    path.mkdir(parents=True, exist_ok=True)
                elif member.isreg():
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with archive.extractfile(member) as source_file, path.open("xb") as target:
                        shutil.copyfileobj(source_file, target)
                    if member.mode & 0o111:
                        path.chmod(path.stat().st_mode | 0o111)
                else:
                    raise ValueError(f"unsupported archive entry {member.name!r}")
        if process.wait():
            raise ValueError(f"Git could not archive {source}")


def prepare_versions(skills, store):
    versions = {}
    repositories = {}
    with tempfile.TemporaryDirectory(prefix=".prepare-", dir=store) as workspace:
        workspace = Path(workspace)
        for skill in skills:
            if COMMIT.fullmatch(skill.ref):
                version = skill.version_path(store, skill.ref)
                if skill_name(version) == skill.name:
                    versions[skill.name] = version
                    continue
            source = (skill.repository, skill.ref)
            if source not in repositories:
                if not shutil.which("git"):
                    raise ValueError("install Git to download skills")
                repo = workspace / str(len(repositories))
                repo.mkdir()
                git(repo, "init", "--quiet", "--template=")
                print(f"Fetch {skill.repository} @ {skill.ref}", flush=True)
                git(
                    repo, "fetch", "--quiet", "--depth=1", "--no-tags",
                    "--no-recurse-submodules", "--",
                    f"https://github.com/{skill.repository}.git", skill.ref,
                )
                repositories[source] = (repo, git(repo, "rev-parse", "FETCH_HEAD^{commit}"))
            repo, commit = repositories[source]
            version = skill.version_path(store, commit)
            if not os.path.lexists(version):
                with tempfile.TemporaryDirectory(dir=workspace) as folder:
                    staged = Path(folder) / skill.name
                    staged.mkdir()
                    tree = commit if skill.directory == "." else f"{commit}:{skill.directory}"
                    archive_skill(repo, tree, staged)
                    if skill_name(staged) != skill.name:
                        raise ValueError(f"{skill.name}: expected matching name in {tree}/SKILL.md")
                    version.parent.mkdir(parents=True, exist_ok=True)
                    staged.rename(version)
            if skill_name(version) != skill.name:
                raise ValueError(f"invalid cached skill at {version}")
            versions[skill.name] = version
    return versions


def link_target(path):
    if path.is_symlink():
        return Path(os.path.abspath(path.parent / path.readlink()))
    return None


def managed_link(path, store):
    target = link_target(path)
    return target is not None and target.parent == store / path.name and VERSION.fullmatch(target.name)


def publish_skill(path, version, store):
    if version is None:
        if skill_name(path) != path.name:
            raise ValueError(f"conflict at {path}")
        print(f"Keep {path} (existing skill)")
    elif link_target(path) == version:
        print(f"Current {path.name}")
    elif not os.path.lexists(path):
        path.symlink_to(version, target_is_directory=True)
        print(f"Installed {path.name}")
    elif managed_link(path, store):
        with tempfile.TemporaryDirectory(prefix=".link-", dir=path.parent) as workspace:
            replacement = Path(workspace) / path.name
            replacement.symlink_to(version, target_is_directory=True)
            replacement.replace(path)
        print(f"Updated {path.name}")
    else:
        raise ValueError(f"conflict at {path}; run again to review the existing entry")


def publish_alias(alias, canonical):
    if link_target(alias) == canonical:
        return
    if not os.path.lexists(alias):
        alias.parent.mkdir(parents=True, exist_ok=True)
        alias.symlink_to(canonical, target_is_directory=True)
    elif skill_name(alias) == canonical.name:
        print(f"Keep {alias} (existing skill)")
    else:
        raise ValueError(f"conflict at {alias}")


def install(skills, roots, store):
    canonical, *aliases = roots
    canonical.mkdir(parents=True, exist_ok=True)
    store.mkdir(parents=True, exist_ok=True)
    with (canonical.parent / ".skills-install.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        pending = [
            skill for skill in skills
            if not os.path.lexists(canonical / skill.name)
            or managed_link(canonical / skill.name, store)
        ]
        versions = prepare_versions(pending, store)
        failures = 0
        for skill in skills:
            path = canonical / skill.name
            try:
                publish_skill(path, versions.get(skill.name), store)
            except (OSError, ValueError) as error:
                print(f"Error: {error}", file=sys.stderr)
                failures += 1
                continue
            for root in aliases:
                try:
                    publish_alias(root / skill.name, path)
                except (OSError, ValueError) as error:
                    print(f"Error: {error}", file=sys.stderr)
                    failures += 1
    return int(bool(failures))


def main():
    parser = argparse.ArgumentParser(description="Install Agent Skills globally for your Linux account.")
    parser.add_argument(
        "--manifest", type=Path, default=Path(__file__).resolve().with_name("skills.txt"),
        help="skill list (default: skills.txt alongside this script)",
    )
    parser.add_argument(
        "--target", type=Path, action="append", default=[],
        help="also link skills into this agent directory (repeatable)",
    )
    parser.add_argument("--dry-run", action="store_true", help="show the skills and paths without changes")
    args = parser.parse_args()
    try:
        skills = load_manifest(args.manifest.expanduser())
        roots = skill_locations(args.target)
        data = xdg_directory("XDG_DATA_HOME", Path.home() / ".local/share")
        store = (data / "agent-skills/versions").resolve()
        if args.dry_run:
            print("Skills")
            for skill in skills:
                print(f"  {skill.name}  {skill.repository}:{skill.directory} @ {skill.ref}")
            print(f"\nStore: {store}\nDiscovery directories")
            for path in roots:
                print(f"  {path}")
            return 0
        return install(skills, roots, store)
    except (OSError, ValueError, RuntimeError, tarfile.TarError, subprocess.CalledProcessError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
