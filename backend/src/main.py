import os,logging
from contextlib import asynccontextmanager
from fastapi import FastAPI,Request
from fastapi.responses import JSONResponse
from src.config.database import Base,engine
from src.models import entities
from src.routes.api import router
from src.middlewares.request import RequestId,SecurityHeaders
LEGACY_COLUMNS={
 'forecast_runs':[('revision','INTEGER DEFAULT 0')],
 'staffings':[('branch','VARCHAR(30)'),('revision','INTEGER DEFAULT 0'),('basis','JSON'),('approved_by',"VARCHAR(100) DEFAULT ''"),('approved_at',"VARCHAR(40) DEFAULT ''"),('invalid_reason',"TEXT DEFAULT ''")],
}


def upgrade_legacy_columns():
 """旧库由 create_all 建表时缺少新列；此处补齐，避免无在线迁移器时启动失败。"""
 from sqlalchemy import inspect,text
 inspector=inspect(engine)
 for table,columns in LEGACY_COLUMNS.items():
  if table not in inspector.get_table_names():continue
  existing={c['name'] for c in inspector.get_columns(table)}
  with engine.begin() as c:
   for name,ddl in columns:
    if name not in existing:c.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {ddl}'))


@asynccontextmanager
async def lifespan(app):
 Base.metadata.create_all(engine)
 upgrade_legacy_columns()
 if os.getenv('SEED_DEMO')=='true':
  try:
   from scripts.seed_demo import seed
   seed()
  except Exception:logging.exception('seed failed')
 yield
app=FastAPI(title='服务网点需求预估',lifespan=lifespan)
app.add_middleware(RequestId);app.add_middleware(SecurityHeaders)
app.include_router(router)
@app.get('/health')
def health():
 from sqlalchemy import text
 import redis
 with engine.connect() as c:c.execute(text('SELECT 1'))
 redis.Redis.from_url(os.environ['REDIS_URL']).ping()
 return {'status':'ok'}
@app.exception_handler(Exception)
async def errors(request:Request,exc:Exception):
 logging.exception('request failed');return JSONResponse(status_code=500,content={'detail':'服务暂时异常，请稍后重试'})
