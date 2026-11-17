import os
from sqlalchemy import create_engine,event
from sqlalchemy.orm import sessionmaker, declarative_base

URL=os.environ['DATABASE_URL']
_connect_args={'check_same_thread':False} if URL.startswith('sqlite') else {}
engine=create_engine(URL,pool_pre_ping=True,connect_args=_connect_args)

if URL.startswith('sqlite'):
    @event.listens_for(engine,'connect')
    def _sqlite_pragmas(dbapi_connection,_record):
        cursor=dbapi_connection.cursor()
        cursor.execute('PRAGMA journal_mode=WAL')
        cursor.execute('PRAGMA busy_timeout=8000')
        cursor.execute('PRAGMA foreign_keys=ON')
        cursor.close()

Session=sessionmaker(bind=engine,expire_on_commit=False)
Base=declarative_base()


def db():
    with Session() as s:
        yield s
