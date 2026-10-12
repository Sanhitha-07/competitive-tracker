"""Empty the database (all organizations, accounts and stories).

    python reset_data.py
"""
from sqlmodel import Session, delete

from db import create_tables, engine
from models import Competitor, Organization, Post

create_tables()
with Session(engine) as s:
    s.exec(delete(Post))
    s.exec(delete(Competitor))
    s.exec(delete(Organization))
    s.commit()
print("Database emptied. Add an organization in the app, or run seed_demo.bat.")
