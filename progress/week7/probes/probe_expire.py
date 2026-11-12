import os
import tempfile

from sqlalchemy import String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.orm.exc import DetachedInstanceError

db = os.path.join(tempfile.gettempdir(), "w7probe", "t7.db")
if os.path.exists(db):
    os.remove(db)
engine = create_engine(f"sqlite:///{db}")


class Base(DeclarativeBase):
    pass


class KB(Base):
    __tablename__ = "kb"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))


Base.metadata.create_all(engine)

SessionDefault = sessionmaker(bind=engine)  # expire_on_commit=True
SessionNoExpire = sessionmaker(bind=engine, expire_on_commit=False)

for label, factory in (
    ("默认(expire_on_commit=True)", SessionDefault),
    ("expire_on_commit=False      ", SessionNoExpire),
):
    with factory() as s:
        k = KB(name="x")
        s.add(k)
        s.commit()
        in_dict_after_commit = "name" in k.__dict__
    try:
        v = k.name
        print(f"{label} commit后__dict__有name={in_dict_after_commit} close后读 k.name -> {v!r}")
    except DetachedInstanceError as e:
        print(
            f"{label} commit后__dict__有name={in_dict_after_commit} close后读 k.name -> DetachedInstanceError: {str(e).splitlines()[0]}"
        )
