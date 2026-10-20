"""
A small creator history with every shape the R3 read paths have to get right.

Shared by the tests/test_qc2_r3_*.py files. Seeded and written with direct SQL
in the shapes the studio's writers use, so a test can build it in a fraction
of a second: people with the same name (ties), every lead status, scores on
both sides of the VIP and qualified cut points and none at all, comments,
likes and reposts, one person engaging a post several times, engagement in
the last two weeks, readings that tie on their distance from two days old,
studio posts twinned with LinkedIn posts, a lead tied to a post only by
leads.post_id, and outbound activity aimed at people who engaged back.
"""

import random
from datetime import datetime, timedelta, timezone

ME = "r3-creator"
NAMES = ["Asha Rao", "Émile Durand", "Zoë Ölander", "Işık Demir", "Ravi Shah", "Ravi Shah", "Mei Lin",
         "Tom Price", "Ana Pricing", "Lee", None]
STATUSES = ["NEW", "NEW", "NEW", "ENGAGED", "CONVERTED", "DM_SENT", "ARCHIVED", "QUALIFIED", None]
CRM_STATUSES = ["New Lead", "New Lead", "Outreach Sent", "Connected", "Meeting Booked"]
SCORES = [0.0, 12.5, 45.0, 59.9, 60.0, 72.3, 80.0, 95.5, None]
WORDS = ["pricing", "great", "post", "thanks", "question?", "how", "do", "you", "price", "sourdough",
         "repricing", "olander", "café", "naïve", "strasse"]
NOW = datetime.now(timezone.utc).replace(microsecond=0)


def stamp(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def urn(n):
    ms = int((NOW - timedelta(days=200 - 3 * n)).timestamp() * 1000)
    return f"urn:li:activity:{ms << 22}"


def build(conn, seed=7, leads=360, posts=60, interactions=5000):
    r = random.Random(seed)
    with conn:
        conn.execute("INSERT OR REPLACE INTO creator_identity (id, vanity, display_name, confirmed_at) "
                     "VALUES (1, ?, 'R3 Creator', '2026-09-27T00:00:00+00:00')", (ME,))
        own = [urn(n) for n in range(posts)]
        for n, u in enumerate(own):
            published = NOW - timedelta(days=200 - 3 * n, hours=r.randint(0, 5))
            measured = n == posts - 1 or r.random() < 0.8
            conn.execute(
                "INSERT INTO own_posts (activity_urn, text, published_at, published_at_source, reactions, comments, "
                "reposts, impressions, first_seen_at, last_seen_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (u, f"Post {n} about {' '.join(r.sample(WORDS, 4))}\nSecond line {n}", published.isoformat(),
                 "activity" if measured else "archive",
                 r.randint(5, 50) if measured else None, r.randint(0, 9) if measured else None,
                 r.randint(0, 3) if measured else None, r.randint(100, 900) if measured else None,
                 stamp(published), stamp(published)))
            # Readings: hourly in the first four days, with two equally close
            # to 48 hours, so the earlier one must win.
            if measured:
                for age in [a for a in range(1, 96, 1 if n % 3 else 6) if a != 48] + [47.5, 48.5]:
                    observed = published + timedelta(hours=age)
                    conn.execute(
                        "INSERT OR IGNORE INTO post_metric_observations (activity_urn, observed_at, observed_hour, "
                        "age_hours, source, impressions, reactions, comments) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (u, observed.isoformat(), observed.strftime("%Y-%m-%dT%H") + f":{age}", float(age),
                         "post_analytics" if age % 2 else "activity", 10 * age, age // 2, age // 10))
        studio = []
        for n in range(0, posts, 3):
            pid = f"post-{n}"
            studio.append(pid)
            conn.execute("INSERT INTO posts (id, content, status, published_at, activity_urn, tags) "
                         "VALUES (?, ?, 'published', ?, ?, ?)",
                         (pid, f"Studio twin {n} {r.choice(WORDS)}", stamp(NOW - timedelta(days=200 - 3 * n)),
                          own[n], '["growth"]'))
        conn.execute("INSERT INTO posts (id, content, status, tags) VALUES ('post-draft', 'A draft about pricing', "
                     "'draft', '[]')")
        ids = []
        for n in range(leads):
            lead_id = f"lead-{n:04d}" if n % 50 else f"lead_{n:04d}"
            ids.append(lead_id)
            name = NAMES[n % len(NAMES)]
            created = NOW - timedelta(days=r.randint(0, 400))
            conn.execute(
                "INSERT INTO leads (id, name, full_name, headline, company, linkedin_urn, profile_url, status, "
                "lead_status, icp_score, notes, created_at, updated_at, post_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (lead_id, name or "", name, f"Head of {r.choice(['Growth', 'Pricing', 'Ops'])}",
                 r.choice(["Crumb Co", "Ölander AB", "Acme", None]), f"https://www.linkedin.com/in/p{n}",
                 f"https://www.linkedin.com/in/p{n}", r.choice(CRM_STATUSES), STATUSES[n % len(STATUSES)],
                 SCORES[n % len(SCORES)], r.choice(["", "met at a meetup", None]), stamp(created),
                 stamp(created + timedelta(days=r.randint(0, 3))) if n % 7 else None,
                 studio[1] if n == 5 else None))
        seen = set()
        for k in range(interactions):
            lead_id = ids[min(int(r.paretovariate(1.2)) - 1, leads - 1)] if k % 3 else r.choice(ids)
            post = r.choice(own) if k % 25 else (r.choice([None, "", "urn:li:activity:999"]))
            kind = r.choices(["LIKE", "COMMENT", "REPOST"], [69, 26, 5])[0]
            text = " ".join(r.sample(WORDS, 3)) if kind == "COMMENT" else None
            when = NOW - timedelta(days=r.choice([1, 2, 5, 13, 20, 60, 150]), seconds=r.choice([0, 0, 30, 3600]))
            key = (lead_id, post or "", kind, text or "")
            if key in seen:
                continue
            seen.add(key)
            conn.execute(
                "INSERT INTO lead_interactions (lead_id, post_urn, interaction_type, comment_text, interacted_at, "
                "comment_key, first_seen_at, last_seen_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (lead_id, post, kind, text, stamp(when), (text or "")[:40], stamp(when) if k % 4 else None,
                 stamp(when + timedelta(hours=1))))
        for k in range(300):
            author = NAMES[k % len(NAMES)] if k % 5 else "Somebody Else"
            if k % 13 == 0:
                author = None
            conn.execute(
                "INSERT OR IGNORE INTO outbound_engagements (target_activity_urn, target_author, kind, reaction_kind, "
                "my_text, my_text_key, first_seen_at, last_seen_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (f"urn:li:activity:{k}", author.upper() if author and k % 4 == 0 else author,
                 "comment" if k % 3 == 0 else "reaction", "like", f"nice {k}" if k % 3 == 0 else None,
                 f"k{k}", stamp(NOW - timedelta(days=k)), stamp(NOW - timedelta(days=k % 40))))
    return {"own": own, "studio": studio, "leads": ids}
