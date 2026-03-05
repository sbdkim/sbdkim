import datetime as dt
import json
import os
import urllib.parse
import urllib.request
from collections import defaultdict

TOKEN = os.environ["GITHUB_TOKEN"]
USER = os.environ["GITHUB_USER"]
OUT_DIR = "assets"

def gh_get(url):
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "profile-stats-generator",
        },
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode("utf-8")), r.headers

def gh_graphql(query, variables):
    data = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=data,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "profile-stats-generator",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as r:
        body = json.loads(r.read().decode("utf-8"))
    if "errors" in body:
        raise RuntimeError(body["errors"])
    return body["data"]

def fetch_all_repos(user):
    repos = []
    page = 1
    while True:
        url = f"https://api.github.com/users/{user}/repos?per_page=100&page={page}&type=owner"
        batch, _ = gh_get(url)
        if not batch:
            break
        repos.extend(batch)
        page += 1
    return repos

def longest_streak(days):
    best = cur = 0
    for d in days:
        if d["contributionCount"] > 0:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best

def esc(s):
    return (
        str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace('"', "&quot;").replace("'", "&apos;")
    )

def write_stats_svg(path, rows):
    lines = []
    y = 40
    for k, v in rows:
        lines.append(f'<text x="24" y="{y}" font-size="16" fill="#0f172a">{esc(k)}</text>')
        lines.append(f'<text x="476" y="{y}" font-size="16" text-anchor="end" fill="#0f172a">{esc(v)}</text>')
        y += 32
    h = y + 16
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="500" height="{h}" role="img" aria-label="GitHub stats">
  <rect width="100%" height="100%" rx="14" fill="#f8fafc" stroke="#cbd5e1"/>
  <text x="24" y="24" font-size="18" font-weight="700" fill="#0f172a">GitHub Stats (Static)</text>
  {''.join(lines)}
  <text x="24" y="{h-12}" font-size="11" fill="#64748b">Updated: {dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}</text>
</svg>"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)

def write_langs_svg(path, langs):
    maxv = max(v for _, v in langs) if langs else 1
    bars = []
    y = 48
    for name, val in langs:
        w = int((val / maxv) * 260)
        bars.append(f'<text x="24" y="{y}" font-size="14" fill="#0f172a">{esc(name)}</text>')
        bars.append(f'<rect x="150" y="{y-12}" width="{w}" height="10" rx="5" fill="#2563eb"/>')
        bars.append(f'<text x="420" y="{y}" font-size="12" text-anchor="end" fill="#334155">{val/1024:.0f} KB</text>')
        y += 28
    h = y + 18
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="460" height="{h}" role="img" aria-label="Top languages">
  <rect width="100%" height="100%" rx="14" fill="#f8fafc" stroke="#cbd5e1"/>
  <text x="24" y="28" font-size="18" font-weight="700" fill="#0f172a">Top Languages (Static)</text>
  {''.join(bars)}
</svg>"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)

def main():
    user_data, _ = gh_get(f"https://api.github.com/users/{USER}")
    repos = fetch_all_repos(USER)

    stars = sum(r.get("stargazers_count", 0) for r in repos)
    lang_bytes = defaultdict(int)
    for r in repos:
        lang_url = r.get("languages_url")
        if not lang_url:
            continue
        data, _ = gh_get(lang_url)
        for lang, b in data.items():
            lang_bytes[lang] += int(b)

    to_date = dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    from_date = (dt.datetime.utcnow() - dt.timedelta(days=365)).replace(microsecond=0).isoformat() + "Z"

    q = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          totalCommitContributions
          contributionCalendar {
            weeks {
              contributionDays {
                date
                contributionCount
              }
            }
          }
        }
      }
    }
    """
    g = gh_graphql(q, {"login": USER, "from": from_date, "to": to_date})
    c = g["user"]["contributionsCollection"]
    days = [d for w in c["contributionCalendar"]["weeks"] for d in w["contributionDays"]]

    rows = [
        ("User", USER),
        ("Public Repos", user_data.get("public_repos", 0)),
        ("Followers", user_data.get("followers", 0)),
        ("Following", user_data.get("following", 0)),
        ("Total Stars (owned repos)", stars),
        ("Commits (last 365 days)", c.get("totalCommitContributions", 0)),
        ("Longest Streak (last 365 days)", longest_streak(days)),
    ]

    top_langs = sorted(lang_bytes.items(), key=lambda x: x[1], reverse=True)[:6]
    write_stats_svg(os.path.join(OUT_DIR, "stats.svg"), rows)
    write_langs_svg(os.path.join(OUT_DIR, "top-langs.svg"), top_langs)

if __name__ == "__main__":
    main()
