"""Check that the dependency floors in pyproject.toml can actually resolve.

A floor is a claim: "this package works with at least this version". Nothing
verifies that claim during normal use, because pip installs the NEWEST version
that fits, never the oldest. Two of these were wrong and unnoticed until CI
pinned every dependency to its stated minimum and pip refused:

    mcp 1.2.0 requires pydantic>=2.10.1, but [api] declared pydantic>=2.6.0
    mcp 1.2.0 requires uvicorn>=0.30,    but [api] declared uvicorn>=0.27.0

Either made `pip install "dataprocessing-ai[all]"` unsatisfiable at the versions
the package itself advertised. Run this after changing any dependency, so the
answer costs a few seconds rather than a CI round-trip:

    python scripts/check_dependency_floors.py

Needs network access and `packaging`. CI's `floor` job is the real gate; this is
the fast local version of the same question.
"""
import json
import sys
import tomllib
import urllib.request

from packaging.requirements import Requirement
from packaging.version import Version

SKIP_PREFIXES = ("dataprocessing-ai", "pytest", "httpx")


def declared_floors(pyproject="pyproject.toml"):
    project = tomllib.load(open(pyproject, "rb"))["project"]
    specs = list(project["dependencies"])
    for group in project.get("optional-dependencies", {}).values():
        specs.extend(group)

    floors = {}
    for spec in specs:
        if spec.startswith(SKIP_PREFIXES):
            continue
        req = Requirement(spec)
        for clause in req.specifier:
            if clause.operator == ">=":
                floors[req.name.lower()] = clause.version
    return floors


def requirements_of(name, version):
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            return json.load(response)["info"].get("requires_dist") or []
    except Exception as exc:  # network or a yanked version
        print(f"  ! could not read {name}=={version}: {exc}")
        return []


def main():
    floors = declared_floors()
    print("Declared floors:")
    for name, version in sorted(floors.items()):
        print(f"  {name:20} >= {version}")

    conflicts = []
    for name, version in sorted(floors.items()):
        for raw in requirements_of(name, version):
            try:
                req = Requirement(raw)
            except Exception:
                continue
            # Skip requirements that only apply under an extra we do not install.
            if req.marker and not req.marker.evaluate({"extra": ""}):
                continue
            dep = req.name.lower()
            if dep in floors and not req.specifier.contains(
                Version(floors[dep]), prereleases=True
            ):
                conflicts.append(
                    f"{name}=={version} requires {dep}{req.specifier}, "
                    f"but the floor is {dep}>={floors[dep]}"
                )

    print()
    if conflicts:
        print("Unsatisfiable floors:")
        for line in conflicts:
            print(f"  - {line}")
        return 1
    print("Every declared floor satisfies every other package's requirements.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
