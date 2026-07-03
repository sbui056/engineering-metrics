"""Shared identity resolution — the one helper every track imports.

Maps a raw (name, email) to a stable ``author_canonical`` so commits, reviews,
ownership, and coupling all join in the same identity space. Errs toward
UNDER-merging: a wrong merge corrupts every downstream signal, while a missed
merge only splits one person.

Resolution rules, in order of confidence (union-find over all known identities):
  1. ``.mailmap`` if the target repo has one (honored first).
  2. Same GitHub noreply login  (``12345+login@users.noreply.github.com`` -> login).
  3. Same normalized email.
  4. Same normalized full name (>= 2 tokens; single common first names never merge).
  5. High fuzzy name similarity on multi-token names (conservative threshold).

Rules 4 and 5 are flagged in the merge report so a human can eyeball them, along
with any cluster spanning 3+ distinct emails.

Standalone:  ``python scripts/identity.py --repo target-repo/FastVideo``
prints the merge report so you can sanity-check it before trusting any join.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

from rapidfuzz import fuzz

# Add repo root to path so `config` imports work when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

NAME_SCORE_THRESHOLD = 92  # rapidfuzz token_sort_ratio cutoff for name-only merges
_NOREPLY_RE = re.compile(r"^(?:\d+\+)?([^@]+)@users\.noreply\.github\.com$", re.I)
_WS_RE = re.compile(r"\s+")


def normalize_email(email: str | None) -> str:
    return (email or "").strip().lower()


def noreply_login(email: str | None) -> str | None:
    """Return the GitHub login encoded in a noreply email, else None."""
    m = _NOREPLY_RE.match(normalize_email(email))
    return m.group(1).lower() if m else None


def normalize_name(name: str | None) -> str:
    return _WS_RE.sub(" ", (name or "").strip()).lower()


class _UnionFind:
    def __init__(self, items):
        self.parent = {x: x for x in items}

    def find(self, x):
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:  # path compression
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def parse_mailmap(repo_path: Path) -> dict[tuple[str, str], tuple[str, str]]:
    """Minimal .mailmap parser: raw (name,email) -> canonical (name,email).

    Handles the common forms:
      Canonical Name <canonical@email>
      Canonical Name <canonical@email> <raw@email>
      Canonical Name <canonical@email> Raw Name <raw@email>
    """
    path = Path(repo_path) / ".mailmap"
    mapping: dict[tuple[str, str], tuple[str, str]] = {}
    if not path.exists():
        return mapping
    email_re = re.compile(r"<([^>]*)>")
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        emails = email_re.findall(line)
        # Split on the whole <...> token (non-capturing) so emails aren't
        # returned as if they were names.
        names = [seg.strip() for seg in re.split(r"<[^>]*>", line) if seg.strip()]
        if not emails:
            continue
        canon_name = names[0] if names else ""
        canon_email = emails[0]
        # Every (name?, email) on the right maps to the canonical pair.
        if len(emails) == 1:
            mapping[(normalize_name(canon_name), normalize_email(canon_email))] = (
                canon_name,
                canon_email,
            )
        else:
            raw_email = emails[-1]
            raw_name = names[-1] if len(names) > 1 else canon_name
            mapping[(normalize_name(raw_name), normalize_email(raw_email))] = (
                canon_name,
                canon_email,
            )
    return mapping


class IdentityResolver:
    """Builds canonical identities from a set of raw (name, email) pairs."""

    def __init__(self, threshold: int = NAME_SCORE_THRESHOLD):
        self.threshold = threshold
        self._label: dict[tuple[str, str], str] = {}      # (norm_name,norm_email) -> canonical
        self._by_email: dict[str, str] = {}               # norm_email -> canonical
        self._by_login: dict[str, str] = {}               # noreply login -> canonical
        self._by_name: dict[str, str] = {}                # norm_name -> canonical
        self._clusters: dict[str, list] = {}              # canonical -> raw identities
        self._flags: dict[str, set[str]] = defaultdict(set)  # canonical -> review flags

    @classmethod
    def from_identity_counts(
        cls,
        counts: dict[tuple[str, str], int],
        mailmap: dict[tuple[str, str], tuple[str, str]] | None = None,
        threshold: int = NAME_SCORE_THRESHOLD,
    ) -> "IdentityResolver":
        self = cls(threshold)
        mailmap = mailmap or {}
        # Apply mailmap first: rewrite raw identities to their canonical pair.
        ident_counts: Counter[tuple[str, str]] = Counter()
        disp_counts: dict[tuple[str, str], Counter] = defaultdict(Counter)
        for (name, email), c in counts.items():
            key = (normalize_name(name), normalize_email(email))
            cname, cemail = mailmap.get(key, (name, email))
            nk = (normalize_name(cname), normalize_email(cemail))
            ident_counts[nk] += c
            disp_counts[nk][(cname, cemail)] += c
        # Representative display (name,email) per normalized key = most frequent original.
        raw_display: dict[tuple[str, str], tuple[str, str]] = {
            nk: dc.most_common(1)[0][0] for nk, dc in disp_counts.items()
        }

        idents = list(ident_counts.keys())
        uf = _UnionFind(idents)
        name_merges: set[tuple] = set()

        # Union by shared email and by shared noreply login.
        by_email: dict[str, list] = defaultdict(list)
        by_login: dict[str, list] = defaultdict(list)
        for nk in idents:
            _, nemail = nk
            if nemail:
                by_email[nemail].append(nk)
            login = noreply_login(nemail)
            if login:
                by_login[login].append(nk)
        for group in list(by_email.values()) + list(by_login.values()):
            for other in group[1:]:
                uf.union(group[0], other)

        # Union when a git NAME is exactly a known GitHub login (single token),
        # e.g. name "solitarythinker" == login from a "...+SolitaryThinker@
        # users.noreply.github.com" email. Reunites contributors who commit
        # under both their real name and their handle.
        login_merges: set[str] = set()
        known_logins = set(by_login)
        for nk in idents:
            nname = nk[0]
            if nname and " " not in nname and nname in known_logins:
                anchor = by_login[nname][0]
                if uf.find(nk) != uf.find(anchor):
                    login_merges.add(nname)
                uf.union(anchor, nk)

        # Union by exact full name (>= 2 tokens) and conservative fuzzy.
        multi_token = [nk for nk in idents if len(nk[0].split()) >= 2]
        by_name: dict[str, list] = defaultdict(list)
        for nk in multi_token:
            by_name[nk[0]].append(nk)
        for group in by_name.values():
            for other in group[1:]:
                if uf.find(group[0]) != uf.find(other):
                    name_merges.add((group[0], other[0]))
                uf.union(group[0], other)
        # Fuzzy: only between different-name multi-token identities.
        for i in range(len(multi_token)):
            for j in range(i + 1, len(multi_token)):
                a, b = multi_token[i], multi_token[j]
                if uf.find(a) == uf.find(b) or a[0] == b[0]:
                    continue
                if fuzz.token_sort_ratio(a[0], b[0]) >= threshold:
                    uf.union(a, b)
                    name_merges.add((a[0], b[0]))

        # Assign each cluster a canonical label: highest-count display name,
        # tie-broken alphabetically; disambiguate collisions with the email.
        clusters: dict[tuple, list] = defaultdict(list)
        for nk in idents:
            clusters[uf.find(nk)].append(nk)

        used_labels: set[str] = set()
        for root, members in sorted(clusters.items(), key=lambda kv: -sum(ident_counts[m] for m in kv[1])):
            best = max(members, key=lambda m: (ident_counts[m], raw_display[m][0]))
            label = raw_display[best][0].strip() or raw_display[best][1]
            if label.lower() in {l.lower() for l in used_labels}:
                local = raw_display[best][1].split("@")[0]
                label = f"{label} <{local}>"
            used_labels.add(label)

            emails_in_cluster = {m[1] for m in members if m[1]}
            for m in members:
                self._label[m] = label
                if m[1]:
                    self._by_email[m[1]] = label
                login = noreply_login(m[1])
                if login:
                    self._by_login[login] = label
                if m[0]:
                    self._by_name.setdefault(m[0], label)
            self._clusters[label] = [raw_display[m] for m in members]
            member_names = {m[0] for m in members}
            if len(emails_in_cluster) >= 3:
                self._flags[label].add("3+ emails")
            for nm_a, nm_b in name_merges:
                if nm_a in member_names and nm_b in member_names:
                    self._flags[label].add("name-based merge")
            if member_names & login_merges:
                self._flags[label].add("name==login merge")
        return self

    def lookup_login(self, login: str | None) -> str | None:
        """Canonical label for a GitHub login seen in a noreply email, else None."""
        return self._by_login.get((login or "").strip().lower()) or None

    def lookup_name(self, name: str | None) -> str | None:
        """Canonical label for an exact (normalized) git author name, else None."""
        n = normalize_name(name)
        return self._by_name.get(n) if n else None

    def canonical(self, name: str | None, email: str | None) -> str:
        """Resolve a (name, email) to its canonical label; deterministic fallback if unseen."""
        nk = (normalize_name(name), normalize_email(email))
        if nk in self._label:
            return self._label[nk]
        nemail = normalize_email(email)
        login = noreply_login(nemail)
        if login and login in self._by_login:
            return self._by_login[login]
        if nemail and nemail in self._by_email:
            return self._by_email[nemail]
        nname = normalize_name(name)
        if nname and nname in self._by_name:
            return self._by_name[nname]
        # Unseen identity: stable fallback (display name, else email).
        return (name or "").strip() or nemail

    def to_frame(self):
        import pandas as pd

        rows = [
            {"raw_name": rn, "raw_email": re, "author_canonical": label}
            for label, members in self._clusters.items()
            for (rn, re) in members
        ]
        return pd.DataFrame(rows)

    def merge_report(self) -> str:
        lines = ["Identity merge report", "=" * 60]
        for label in sorted(self._clusters, key=lambda l: -len(self._clusters[l])):
            members = self._clusters[label]
            flags = self._flags.get(label)
            if len(members) == 1 and not flags:
                continue
            tag = f"   [REVIEW ME: {', '.join(sorted(flags))}]" if flags else ""
            lines.append(f"\n{label}  ({len(members)} raw identities){tag}")
            for rn, re in members:
                lines.append(f"    - {rn} <{re}>")
        singles = sum(1 for m in self._clusters.values() if len(m) == 1)
        lines.append(f"\n{len(self._clusters)} canonical authors ({singles} single-identity).")
        return "\n".join(lines)


def collect_git_identities(repo_path: Path) -> Counter:
    """Count (name, email) across authors, committers, and Co-authored-by trailers."""
    counts: Counter[tuple[str, str]] = Counter()
    fmt = "%an\t%ae\t%cn\t%ce"
    out = subprocess.run(
        ["git", "-C", str(repo_path), "log", "--no-merges", f"--format={fmt}"],
        capture_output=True, text=True, errors="replace", check=True,
    ).stdout
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 4:
            counts[(parts[0], parts[1])] += 1
            counts[(parts[2], parts[3])] += 1
    # Co-authored-by trailers
    trailer_re = re.compile(r"Co-authored-by:\s*(.*?)\s*<([^>]+)>", re.I)
    body = subprocess.run(
        ["git", "-C", str(repo_path), "log", "--format=%(trailers:key=Co-authored-by)"],
        capture_output=True, text=True, errors="replace", check=True,
    ).stdout
    for m in trailer_re.finditer(body):
        counts[(m.group(1), m.group(2))] += 1
    return counts


def build_from_repo(repo_path: Path) -> IdentityResolver:
    counts = collect_git_identities(repo_path)
    return IdentityResolver.from_identity_counts(counts, mailmap=parse_mailmap(repo_path))


def main() -> None:
    ap = argparse.ArgumentParser(description="Build and print the identity merge report.")
    ap.add_argument("--repo", default=None, help="Target repo path (or REPO_PATH env).")
    args = ap.parse_args()
    repo = config.get_repo_path(args.repo)
    resolver = build_from_repo(repo)
    print(resolver.merge_report())


if __name__ == "__main__":
    main()
