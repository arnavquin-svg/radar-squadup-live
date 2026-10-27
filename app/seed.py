"""Synthetic seed data. Every community, admin name and event here is fictional sample data."""
from __future__ import annotations

from datetime import date, timedelta

from .db import connect, dumps

# (name, kind, platform, city, tags, size, languages, admin_name)
COMMUNITIES: list[tuple[str, str, str, str, list[str], int, list[str], str]] = [
    # Pune
    ("Pune AI Circle", "meetup", "telegram", "Pune", ["ai", "data", "hackathon"], 1200, ["en", "mr", "hi"], "Ishaan"),
    ("COEP Coding Club", "college club", "whatsapp", "Pune", ["web", "hackathon", "beginner"], 640, ["en", "mr"], "Sneha"),
    ("PICT Robotics Society", "college club", "whatsapp", "Pune", ["robotics", "hackathon"], 310, ["en", "mr"], "Omkar"),
    ("Pune Designers Collective", "meetup", "instagram", "Pune", ["design"], 900, ["en", "mr"], "Rhea"),
    ("Pune Freshers Network", "student network", "whatsapp", "Pune", ["beginner", "cultural"], 2100, ["en", "mr", "hi"], "Tanvi"),
    ("MIT-WPU E-Cell", "college club", "telegram", "Pune", ["startup", "social-impact"], 480, ["en", "hi"], "Aditya"),
    # Mumbai
    ("Mumbai ML Meetup", "meetup", "telegram", "Mumbai", ["ai", "data"], 2600, ["en", "hi"], "Farhan"),
    ("VJTI Hackers Guild", "college club", "whatsapp", "Mumbai", ["hackathon", "web", "cybersecurity"], 520, ["en", "mr", "hi"], "Kunal"),
    ("Mumbai Women in Tech", "community", "instagram", "Mumbai", ["ai", "web", "beginner"], 1500, ["en", "hi"], "Priya"),
    # Delhi NCR
    ("Delhi AI Builders", "meetup", "telegram", "Delhi", ["ai", "startup", "hackathon"], 1800, ["en", "hi"], "Rohan"),
    ("DTU Robotics Club", "college club", "whatsapp", "Delhi", ["robotics", "science"], 420, ["en", "hi"], "Harsh"),
    ("IIIT Delhi Design Society", "college club", "instagram", "Delhi", ["design", "web"], 350, ["en", "hi"], "Ananya"),
    ("Delhi Science Fair Mentors", "community", "whatsapp", "Delhi", ["science", "beginner"], 260, ["hi", "en"], "Meenakshi"),
    ("Sonipat Student Makers", "student network", "whatsapp", "Sonipat", ["robotics", "hackathon", "beginner"], 380, ["hi", "en"], "Kabir"),
    ("Sonipat Campus Culture Hub", "student network", "instagram", "Sonipat", ["cultural", "beginner"], 950, ["hi", "en"], "Ira"),
    ("Gurugram Product & Design", "meetup", "telegram", "Gurugram", ["design", "startup"], 1100, ["en", "hi"], "Nikhil"),
    # Bengaluru
    ("Bengaluru GenAI Hackers", "meetup", "telegram", "Bengaluru", ["ai", "hackathon"], 3400, ["en"], "Vikram"),
    ("RVCE Coding Club", "college club", "whatsapp", "Bengaluru", ["web", "data", "hackathon"], 700, ["en"], "Deepa"),
    ("Bengaluru Hardware Hackers", "meetup", "telegram", "Bengaluru", ["robotics", "hackathon"], 980, ["en"], "Arjun"),
    ("Bengaluru UX Guild", "meetup", "instagram", "Bengaluru", ["design"], 1300, ["en"], "Neha"),
    # Hyderabad / Chennai / Kolkata
    ("Hyderabad Data Folks", "meetup", "telegram", "Hyderabad", ["data", "ai"], 1600, ["en", "hi"], "Sameer"),
    ("IIIT-H Robotics Research Group", "college club", "whatsapp", "Hyderabad", ["robotics", "science", "ai"], 240, ["en"], "Lakshmi"),
    ("Chennai Startup Students", "student network", "telegram", "Chennai", ["startup", "hackathon"], 850, ["en"], "Karthik"),
    ("Chennai Science Olympiad Prep", "community", "whatsapp", "Chennai", ["science", "beginner"], 600, ["en"], "Divya"),
    ("Kolkata Creative Coders", "meetup", "instagram", "Kolkata", ["design", "web", "gaming"], 540, ["en", "hi"], "Sayan"),
    # Online / pan-India
    ("India Student Hackathon Network", "online community", "telegram", "Online", ["hackathon", "beginner", "web"], 8200, ["en", "hi"], "Team ISHN"),
    ("Hindi Tech Learners", "online community", "telegram", "Online", ["ai", "web", "beginner"], 5400, ["hi"], "Ravi"),
    ("Climate Tech Students India", "online community", "whatsapp", "Online", ["social-impact", "data", "startup"], 1900, ["en", "hi"], "Zoya"),
    ("Indie Game Jam India", "online community", "telegram", "Online", ["gaming", "design", "hackathon"], 2300, ["en"], "Yash"),
    ("CTF Learners India", "online community", "telegram", "Online", ["cybersecurity", "hackathon", "beginner"], 3100, ["en", "hi"], "Aman"),
    ("Women Who Build India", "online community", "instagram", "Online", ["ai", "startup", "beginner"], 4200, ["en", "hi"], "Sara"),
    ("Pune Hackathon Volunteers", "volunteer group", "whatsapp", "Pune", ["hackathon", "social-impact"], 210, ["en", "mr", "hi"], "Gauri"),
]

DEMO_EVENT = {
    "name": "BuildPune AI Hackathon",
    "city": "Pune",
    "description": (
        "A 24-hour beginner-friendly AI hackathon where students build practical tools for local "
        "problems, with mentors on site. Teams of four: developer, designer, domain expert and presenter."
    ),
    "tags": ["ai", "hackathon", "beginner"],
    "venue": "Synthetic Campus Hall, Pune",
    "team_size": 4,
}


def seed_communities() -> int:
    with connect() as conn:
        existing = conn.execute("SELECT COUNT(*) FROM communities").fetchone()[0]
        if existing:
            return 0
        conn.executemany(
            """INSERT INTO communities (name, kind, platform, city, tags, size, languages, admin_name, discovered_via)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'seed')""",
            [(n, k, p, c, dumps(t), s, dumps(l), a) for n, k, p, c, t, s, l, a in COMMUNITIES],
        )
        return len(COMMUNITIES)


def seed_demo_event() -> int | None:
    with connect() as conn:
        if conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]:
            return None
        start = (date.today() + timedelta(days=21)).isoformat()
        cur = conn.execute(
            """INSERT INTO events (name, city, description, tags, start_date, venue, team_size)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (DEMO_EVENT["name"], DEMO_EVENT["city"], DEMO_EVENT["description"], dumps(DEMO_EVENT["tags"]),
             start, DEMO_EVENT["venue"], DEMO_EVENT["team_size"]),
        )
        return int(cur.lastrowid)


# Synthetic first names used only by the demo "simulate registrations" endpoint.
SYNTHETIC_NAMES = [
    "Aarav", "Meera", "Vihaan", "Diya", "Kabir", "Anika", "Reyansh", "Saanvi", "Arnav", "Ira",
    "Advait", "Myra", "Dhruv", "Kiara", "Ayaan", "Tara", "Rudra", "Navya", "Shaurya", "Aadhya",
    "Vivaan", "Pari", "Atharv", "Riya", "Krish", "Sara", "Ishan", "Mahi", "Yuvan", "Zara",
]
